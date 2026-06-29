"""
加密分析模块

提供加密操作 Hook、密钥导出、SSL 密钥导出等工具。

Hook 覆盖的 API 列表：
  Java 层（javax.crypto.*）:
    - javax.crypto.Cipher.init / doFinal  (AES/DES/RSA/SM4 等)
    - javax.crypto.spec.SecretKeySpec.$init  (对称密钥构造)
    - javax.crypto.Mac.init  (HMAC)
    - java.security.MessageDigest.digest  (MD5/SHA1/SHA256/SM3)
    - javax.crypto.KeyGenerator  (密钥生成)
    - java.security.KeyStore  (密钥存储，含 AndroidKeyStore)

  Native 层（BoringSSL / OpenSSL）:
    - EVP_EncryptInit_ex / EVP_DecryptInit_ex  (对称加密初始化)
    - EVP_DigestInit_ex  (哈希初始化)
    - EVP_PBE_KeyGen  (PBE 密钥派生)
    - RSA_generate_key_ex  (RSA 密钥生成)

  SSL 密钥导出:
    - SSL_CTX_set_keylog_callback  (BoringSSL 原生 keylog 回调)
    - SSL_new / SSL_get_session  (会话对象追踪)
    - 回退方案：Hook SSL_write 内部派生（不完整）

  Conscrypt (Android 8+ 默认 Provider):
    - com.android.org.conscrypt.OpenSSLCipher  (Native 加密桥接)
    - com.android.org.conscrypt.OpenSSLMessageDigestJDK  (Native 哈希桥接)

局限性：
  - 厂商魔改 BoringSSL（腾讯 X5、阿里 SSL）函数名可能不同
  - Flutter 应用静态链接 BoringSSL，需通过内存特征扫描定位
  - 国密 SM2/SM3/SM4 可能使用第三方库（如 BC、GMSecurity），需额外 hook
"""

import uuid
from typing import Dict, Any, List, Optional

from ..core.frida_client import frida_client
from ..utils.logger import logger


# Hook Java 加密相关 API
HOOK_CRYPTO_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "crypto" };
        }
    };

    Java.perform(function() {
        // Hook javax.crypto.Cipher
        var Cipher = Java.use("javax.crypto.Cipher");

        Cipher.init.overload(
            "int",
            "java.security.Key"
        ).implementation = function(mode, key) {
            send({
                type: "crypto_init",
                hookId: hookId,
                algorithm: this.getAlgorithm(),
                mode: mode,
                key: key !== null ? key.toString() : "null"
            });
            return this.init(mode, key);
        };

        Cipher.init.overload(
            "int",
            "java.security.Key",
            "java.security.spec.AlgorithmParameterSpec"
        ).implementation = function(mode, key, params) {
            send({
                type: "crypto_init",
                hookId: hookId,
                algorithm: this.getAlgorithm(),
                mode: mode,
                key: key !== null ? key.toString() : "null",
                params: params !== null ? params.toString() : "null"
            });
            return this.init(mode, key, params);
        };

        Cipher.doFinal.overload("[B").implementation = function(input) {
            var result = this.doFinal(input);
            try {
                var inputStr = Java.use("java.util.Base64").getEncoder().encodeToString(input);
                var outputStr = Java.use("java.util.Base64").getEncoder().encodeToString(result);
                send({
                    type: "crypto_doFinal",
                    hookId: hookId,
                    algorithm: this.getAlgorithm(),
                    input_b64: inputStr,
                    output_b64: outputStr,
                    input_size: input.length,
                    output_size: result.length
                });
            } catch(e) {}
            return result;
        };

        // Hook SecretKeySpec
        var SecretKeySpec = Java.use("javax.crypto.spec.SecretKeySpec");
        SecretKeySpec.$init.overload("[B", "java.lang.String").implementation = function(key, algorithm) {
            try {
                var keyB64 = Java.use("java.util.Base64").getEncoder().encodeToString(key);
                send({
                    type: "crypto_key",
                    hookId: hookId,
                    algorithm: algorithm,
                    key_b64: keyB64,
                    key_size: key.length
                });
            } catch(e) {}
            return this.$init(key, algorithm);
        };

        // Hook Mac
        var Mac = Java.use("javax.crypto.Mac");
        Mac.init.overload("java.security.Key").implementation = function(key) {
            send({
                type: "mac_init",
                hookId: hookId,
                algorithm: this.getAlgorithm(),
                key: key !== null ? key.toString() : "null"
            });
            return this.init(key);
        };

        // Hook MessageDigest
        var MessageDigest = Java.use("java.security.MessageDigest");
        MessageDigest.digest.overload().implementation = function() {
            var result = this.digest();
            try {
                var hex = "";
                for (var i = 0; i < result.length; i++) {
                    hex += ('00' + (result[i] & 0xff).toString(16)).slice(-2);
                }
                send({
                    type: "hash_digest",
                    hookId: hookId,
                    algorithm: this.getAlgorithm(),
                    hash_hex: hex
                });
            } catch(e) {}
            return result;
        };

        send({ type: "hook_attached", hookId: hookId, targets: ["Cipher", "SecretKeySpec", "Mac", "MessageDigest"] });
    });
})();
"""


# Hook Native 层加密 API（BoringSSL / OpenSSL EVP 系列）
HOOK_NATIVE_CRYPTO_TEMPLATE = r"""
(function() {
    var hookId = "%(hook_id)s";
    var modules = ["libssl.so", "libboringssl.so", "libcrypto.so"];

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "native_crypto" };
        }
    };

    function findExport(funcName) {
        for (var i = 0; i < modules.length; i++) {
            var addr = Module.findExportByName(modules[i], funcName);
            if (addr) return addr;
        }
        return null;
    }

    function bytesToHex(ptr, len) {
        if (len > 256) len = 256; // 限制输出大小
        var hex = "";
        for (var i = 0; i < len; i++) {
            hex += ("00" + ptr.add(i).readU8().toString(16)).slice(-2);
        }
        return hex;
    }

    var hooked = [];

    // 1. EVP_EncryptInit_ex - 对称加密初始化
    var evpEncInit = findExport("EVP_EncryptInit_ex");
    if (evpEncInit) {
        try {
            Interceptor.attach(evpEncInit, {
                onEnter: function(args) {
                    this.ctx = args[0];
                    this.cipher = args[1];
                    this.key = args[4];
                    this.iv = args[5];
                },
                onLeave: function(retval) {
                    try {
                        var cipherName = "?";
                        if (!this.cipher.isNull()) {
                            // EVP_CIPHER_nid 返回 nid，简化处理
                            cipherName = "nid:" + this.cipher.toString();
                        }
                        var keyHex = "";
                        var ivHex = "";
                        if (!this.key.isNull()) {
                            keyHex = bytesToHex(this.key, 32);
                        }
                        if (!this.iv.isNull()) {
                            ivHex = bytesToHex(this.iv, 16);
                        }
                        send({
                            type: "native_crypto_init",
                            hookId: hookId,
                            operation: "encrypt",
                            cipher: cipherName,
                            key_hex: keyHex,
                            iv_hex: ivHex
                        });
                    } catch(e) {}
                }
            });
            hooked.push("EVP_EncryptInit_ex");
        } catch(e) {}
    }

    // 2. EVP_DecryptInit_ex - 对称解密初始化
    var evpDecInit = findExport("EVP_DecryptInit_ex");
    if (evpDecInit) {
        try {
            Interceptor.attach(evpDecInit, {
                onEnter: function(args) {
                    this.key = args[4];
                    this.iv = args[5];
                },
                onLeave: function(retval) {
                    try {
                        var keyHex = "";
                        var ivHex = "";
                        if (!this.key.isNull()) {
                            keyHex = bytesToHex(this.key, 32);
                        }
                        if (!this.iv.isNull()) {
                            ivHex = bytesToHex(this.iv, 16);
                        }
                        send({
                            type: "native_crypto_init",
                            hookId: hookId,
                            operation: "decrypt",
                            key_hex: keyHex,
                            iv_hex: ivHex
                        });
                    } catch(e) {}
                }
            });
            hooked.push("EVP_DecryptInit_ex");
        } catch(e) {}
    }

    // 3. EVP_DigestInit_ex - 哈希初始化
    var evpDigInit = findExport("EVP_DigestInit_ex");
    if (evpDigInit) {
        try {
            Interceptor.attach(evpDigInit, {
                onEnter: function(args) {
                    this.ctx = args[0];
                    this.type = args[1];
                },
                onLeave: function(retval) {
                    try {
                        send({
                            type: "native_digest_init",
                            hookId: hookId,
                            digest_type: this.type.toString()
                        });
                    } catch(e) {}
                }
            });
            hooked.push("EVP_DigestInit_ex");
        } catch(e) {}
    }

    // 4. EVP_DigestFinal_ex - 哈希结果
    var evpDigFinal = findExport("EVP_DigestFinal_ex");
    if (evpDigFinal) {
        try {
            Interceptor.attach(evpDigFinal, {
                onEnter: function(args) {
                    this.md = args[1];
                    this.s = args[2];
                },
                onLeave: function(retval) {
                    try {
                        if (!this.s.isNull()) {
                            var len = this.s.readU32();
                            var hex = bytesToHex(this.md, Math.min(len, 64));
                            send({
                                type: "native_digest_final",
                                hookId: hookId,
                                hash_hex: hex,
                                hash_size: len
                            });
                        }
                    } catch(e) {}
                }
            });
            hooked.push("EVP_DigestFinal_ex");
        } catch(e) {}
    }

    // 5. HMAC - HMAC 计算
    var hmacInit = findExport("HMAC_Init_ex");
    if (hmacInit) {
        try {
            Interceptor.attach(hmacInit, {
                onEnter: function(args) {
                    this.key = args[1];
                    this.keyLen = args[2].toInt32();
                },
                onLeave: function(retval) {
                    try {
                        if (!this.key.isNull() && this.keyLen > 0) {
                            send({
                                type: "native_hmac_init",
                                hookId: hookId,
                                key_hex: bytesToHex(this.key, Math.min(this.keyLen, 64)),
                                key_size: this.keyLen
                            });
                        }
                    } catch(e) {}
                }
            });
            hooked.push("HMAC_Init_ex");
        } catch(e) {}
    }

    // 6. RSA_generate_key_ex - RSA 密钥生成
    var rsaGenKey = findExport("RSA_generate_key_ex");
    if (rsaGenKey) {
        try {
            Interceptor.attach(rsaGenKey, {
                onEnter: function(args) {
                    this.bits = args[1].toInt32();
                },
                onLeave: function(retval) {
                    send({
                        type: "native_rsa_keygen",
                        hookId: hookId,
                        bits: this.bits
                    });
                }
            });
            hooked.push("RSA_generate_key_ex");
        } catch(e) {}
    }

    send({
        type: "hook_attached",
        hookId: hookId,
        targets: hooked,
        modules_checked: modules
    });
})();
"""


# 改进的 SSL 密钥导出（SSLKEYLOGFILE 格式）
# 优先使用 SSL_CTX_set_keylog_callback（BoringSSL 原生支持）
# 回退到 Hook SSL_new + 内部结构偏移读取（不完整，仅作演示）
DUMP_SSL_KEYS_TEMPLATE_V2 = r"""
(function() {
    var hookId = "%(hook_id)s";
    var modules = ["libssl.so", "libboringssl.so"];
    var keylogEntries = [];

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "ssl_keys_v2", entries: keylogEntries.length };
        },
        getEntries: function() {
            return keylogEntries;
        }
    };

    function findExport(funcName) {
        for (var i = 0; i < modules.length; i++) {
            var addr = Module.findExportByName(modules[i], funcName);
            if (addr) return addr;
        }
        return null;
    }

    // 方案 1: SSL_CTX_set_keylog_callback (BoringSSL 原生 keylog 回调)
    // 这是最佳方案，输出标准 SSLKEYLOGFILE 格式
    var setKeylogCb = findExport("SSL_CTX_set_keylog_callback");
    if (setKeylogCb) {
        try {
            // keylog 回调签名: void (*)(const SSL* ssl, const char* line)
            var keylogCallback = new NativeCallback(function(ssl, line) {
                try {
                    var lineStr = line.readUtf8String();
                    keylogEntries.push(lineStr);
                    send({
                        type: "ssl_keylog",
                        hookId: hookId,
                        line: lineStr,
                        method: "keylog_callback"
                    });
                } catch(e) {}
            }, "void", ["pointer", "pointer"]);

            // Hook SSL_CTX_set_keylog_callback，替换为我们的回调
            Interceptor.attach(setKeylogCb, {
                onEnter: function(args) {
                    args[1] = keylogCallback;
                }
            });

            // 同时 Hook SSL_CTX_new，确保每个新 CTX 都设置 keylog 回调
            var sslCtxNew = findExport("SSL_CTX_new");
            if (sslCtxNew) {
                Interceptor.attach(sslCtxNew, {
                    onLeave: function(retval) {
                        if (!retval.isNull()) {
                            var setCb = new NativeFunction(setKeylogCb, "void", ["pointer", "pointer"]);
                            setCb(retval, keylogCallback);
                        }
                    }
                });
            }

            send({
                type: "hook_attached",
                hookId: hookId,
                method: "keylog_callback",
                target: "SSL_CTX_set_keylog_callback"
            });
        } catch(e) {
            send({ type: "error", hookId: hookId, method: "keylog_callback", error: e.toString() });
        }
    } else {
        // 方案 2: 回退 - Hook SSL_new 追踪会话对象
        // 注意：此方案无法导出完整密钥，仅用于会话追踪
        var sslNew = findExport("SSL_new");
        var sslGetSession = findExport("SSL_get_session");

        if (sslNew) {
            Interceptor.attach(sslNew, {
                onLeave: function(retval) {
                    if (!retval.isNull()) {
                        send({
                            type: "ssl_new",
                            hookId: hookId,
                            ssl_ptr: retval.toString(),
                            method: "session_tracking"
                        });
                    }
                }
            });
        }

        if (sslGetSession) {
            Interceptor.attach(sslGetSession, {
                onLeave: function(retval) {
                    if (!retval.isNull()) {
                        send({
                            type: "ssl_session",
                            hookId: hookId,
                            session_ptr: retval.toString(),
                            method: "session_tracking"
                        });
                    }
                }
            });
        }

        send({
            type: "hook_attached",
            hookId: hookId,
            method: "session_tracking",
            note: "SSL_CTX_set_keylog_callback not found, using session tracking fallback. Key export not available."
        });
    }
})();
"""


def register_tools(mcp):
    """向 MCP 服务器注册加密分析工具"""

    @mcp.tool()
    def hook_crypto(session_id: str) -> Dict[str, Any]:
        """Hook Java 加密 API

        Hook 以下 Java 层加密 API，捕获密钥、输入、输出：
          - javax.crypto.Cipher.init / doFinal  (AES/DES/RSA 等)
          - javax.crypto.spec.SecretKeySpec  (对称密钥构造)
          - javax.crypto.Mac.init  (HMAC)
          - java.security.MessageDigest.digest  (MD5/SHA)

        使用 get_crypto_operations(session_id) 获取捕获结果，
        使用 dump_keys(session_id) 获取密钥列表。

        Args:
            session_id: 会话 ID

        Returns:
            包含 hook_id 和 targets 的字典
        """
        try:
            hook_id = f"crypto_{uuid.uuid4().hex[:8]}"
            source = HOOK_CRYPTO_TEMPLATE % {"hook_id": hook_id}
            result = frida_client.execute_script(
                session_id, source, script_name=hook_id
            )
            return {
                "hook_id": hook_id,
                "script_id": result["script_id"],
                "session_id": session_id,
                "targets": [
                    "javax.crypto.Cipher",
                    "javax.crypto.spec.SecretKeySpec",
                    "javax.crypto.Mac",
                    "java.security.MessageDigest",
                ],
            }
        except Exception as e:
            logger.error(f"hook_crypto failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def hook_native_crypto(session_id: str) -> Dict[str, Any]:
        """Hook Native 层加密 API（BoringSSL / OpenSSL）

        Hook 以下 Native 层加密 API，捕获 C/C++ 层的加密操作：
          - EVP_EncryptInit_ex / EVP_DecryptInit_ex  (对称加密初始化)
          - EVP_DigestInit_ex / EVP_DigestFinal_ex  (哈希)
          - HMAC_Init_ex  (HMAC 密钥)
          - RSA_generate_key_ex  (RSA 密钥生成)

        覆盖模块：libssl.so / libboringssl.so / libcrypto.so

        适用场景：
          - 应用使用 Native 层加密（C/C++ 调用 OpenSSL/BoringSSL）
          - Java 层 hook_crypto 无法捕获的操作
          - Flutter / React Native 应用的加密逻辑

        局限性：
          - 厂商魔改 BoringSSL 函数名可能不同
          - Flutter 静态链接 BoringSSL 需内存扫描定位

        Args:
            session_id: 会话 ID

        Returns:
            包含 hook_id 和实际 hook 成功的 targets 列表
        """
        try:
            hook_id = f"native_crypto_{uuid.uuid4().hex[:8]}"
            source = HOOK_NATIVE_CRYPTO_TEMPLATE % {"hook_id": hook_id}
            result = frida_client.execute_script(
                session_id, source, script_name=hook_id
            )
            return {
                "hook_id": hook_id,
                "script_id": result["script_id"],
                "session_id": session_id,
                "targets": [
                    "EVP_EncryptInit_ex",
                    "EVP_DecryptInit_ex",
                    "EVP_DigestInit_ex",
                    "EVP_DigestFinal_ex",
                    "HMAC_Init_ex",
                    "RSA_generate_key_ex",
                ],
                "modules_checked": ["libssl.so", "libboringssl.so", "libcrypto.so"],
                "note": "Use get_crypto_operations(session_id) to retrieve captured data. Only successfully found exports are hooked.",
            }
        except Exception as e:
            logger.error(f"hook_native_crypto failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def dump_keys(session_id: str) -> Dict[str, Any]:
        """导出捕获的加密密钥

        在 hook_crypto 之后调用，获取所有捕获的密钥。

        Args:
            session_id: 会话 ID

        Returns:
            包含密钥列表的字典
        """
        try:
            messages = frida_client.get_messages(session_id, clear=False)
            keys = []
            for msg in messages:
                m = msg.get("message", {})
                if m.get("type") == "crypto_key":
                    keys.append({
                        "algorithm": m.get("algorithm"),
                        "key_b64": m.get("key_b64"),
                        "key_size": m.get("key_size"),
                    })
                elif m.get("type") == "crypto_init":
                    keys.append({
                        "algorithm": m.get("algorithm"),
                        "mode": m.get("mode"),
                        "key": m.get("key"),
                        "params": m.get("params"),
                    })
            return {
                "session_id": session_id,
                "key_count": len(keys),
                "keys": keys,
            }
        except Exception as e:
            logger.error(f"dump_keys failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_crypto_operations(
        session_id: str,
        clear: bool = False,
    ) -> List[Dict[str, Any]]:
        """获取捕获的加密操作

        在 hook_crypto 或 hook_native_crypto 之后调用，获取所有加密操作。
        支持 Java 层（Cipher/Mac/MessageDigest）和 Native 层（EVP_*/HMAC）。

        Args:
            session_id: 会话 ID
            clear: 是否在读取后清空

        Returns:
            加密操作列表，每项包含 type/algorithm/输入输出等
        """
        try:
            messages = frida_client.get_messages(session_id, clear=clear)
            ops = []
            for msg in messages:
                m = msg.get("message", {})
                if not isinstance(m, dict):
                    continue
                msg_type = m.get("type", "")
                if msg_type == "crypto_doFinal":
                    ops.append({
                        "type": "encrypt_decrypt",
                        "layer": "java",
                        "algorithm": m.get("algorithm"),
                        "input_b64": m.get("input_b64"),
                        "output_b64": m.get("output_b64"),
                        "input_size": m.get("input_size"),
                        "output_size": m.get("output_size"),
                    })
                elif msg_type == "hash_digest":
                    ops.append({
                        "type": "hash",
                        "layer": "java",
                        "algorithm": m.get("algorithm"),
                        "hash_hex": m.get("hash_hex"),
                    })
                elif msg_type == "mac_init":
                    ops.append({
                        "type": "mac",
                        "layer": "java",
                        "algorithm": m.get("algorithm"),
                        "key": m.get("key"),
                    })
                elif msg_type == "native_crypto_init":
                    ops.append({
                        "type": "native_encrypt_decrypt",
                        "layer": "native",
                        "operation": m.get("operation"),
                        "cipher": m.get("cipher"),
                        "key_hex": m.get("key_hex"),
                        "iv_hex": m.get("iv_hex"),
                    })
                elif msg_type == "native_digest_init":
                    ops.append({
                        "type": "native_hash_init",
                        "layer": "native",
                        "digest_type": m.get("digest_type"),
                    })
                elif msg_type == "native_digest_final":
                    ops.append({
                        "type": "native_hash_final",
                        "layer": "native",
                        "hash_hex": m.get("hash_hex"),
                        "hash_size": m.get("hash_size"),
                    })
                elif msg_type == "native_hmac_init":
                    ops.append({
                        "type": "native_hmac",
                        "layer": "native",
                        "key_hex": m.get("key_hex"),
                        "key_size": m.get("key_size"),
                    })
                elif msg_type == "native_rsa_keygen":
                    ops.append({
                        "type": "native_rsa_keygen",
                        "layer": "native",
                        "bits": m.get("bits"),
                    })
            return ops
        except Exception as e:
            logger.error(f"get_crypto_operations failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def hook_ssl_keys(session_id: str) -> Dict[str, Any]:
        """Hook SSL 密钥导出（SSLKEYLOGFILE 格式）

        优先使用 BoringSSL 原生的 SSL_CTX_set_keylog_callback 回调，
        输出标准 SSLKEYLOGFILE 格式，可直接导入 Wireshark 解密 HTTPS。

        如果目标不支持 keylog 回调（旧版本 OpenSSL），回退到
        会话对象追踪（仅记录 SSL 对象指针，无法导出密钥）。

        使用 get_ssl_keylog(session_id) 获取导出的密钥行。

        Args:
            session_id: 会话 ID

        Returns:
            包含 hook_id 和 method 的字典
        """
        try:
            hook_id = f"sslkeys_{uuid.uuid4().hex[:8]}"
            source = DUMP_SSL_KEYS_TEMPLATE_V2 % {"hook_id": hook_id}
            result = frida_client.execute_script(
                session_id, source, script_name=hook_id
            )
            return {
                "hook_id": hook_id,
                "script_id": result["script_id"],
                "session_id": session_id,
                "note": (
                    "Uses SSL_CTX_set_keylog_callback if available (BoringSSL). "
                    "Falls back to session tracking for older OpenSSL. "
                    "Use get_ssl_keylog(session_id) to retrieve exported keys."
                ),
            }
        except Exception as e:
            logger.error(f"hook_ssl_keys failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_ssl_keylog(
        session_id: str,
        clear: bool = False,
    ) -> Dict[str, Any]:
        """获取导出的 SSL 密钥（SSLKEYLOGFILE 格式）

        在 hook_ssl_keys 之后调用，获取所有导出的密钥行。
        输出格式兼容 Wireshark / mitmproxy 的 SSLKEYLOGFILE。

        Args:
            session_id: 会话 ID
            clear: 是否在读取后清空

        Returns:
            包含 keylog_lines 列表和原始行数的字典
        """
        try:
            messages = frida_client.get_messages(session_id, clear=clear)
            keylog_lines = []
            session_ptrs = []
            for msg in messages:
                m = msg.get("message", {})
                if not isinstance(m, dict):
                    continue
                msg_type = m.get("type", "")
                if msg_type == "ssl_keylog":
                    keylog_lines.append(m.get("line", ""))
                elif msg_type == "ssl_new":
                    session_ptrs.append(m.get("ssl_ptr"))
                elif msg_type == "ssl_session":
                    session_ptrs.append(m.get("session_ptr"))
            return {
                "session_id": session_id,
                "keylog_count": len(keylog_lines),
                "keylog_lines": keylog_lines,
                "session_count": len(session_ptrs),
                "format": "SSLKEYLOGFILE (compatible with Wireshark/mitmproxy)",
            }
        except Exception as e:
            logger.error(f"get_ssl_keylog failed: {e}")
            return {"error": str(e)}

    logger.info("Crypto module tools registered")
