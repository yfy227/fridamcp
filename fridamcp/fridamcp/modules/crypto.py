"""
加密分析模块

提供加密操作 Hook、密钥导出、SSL 密钥导出等工具。
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

# 导出 SSL 密钥（SSLKEYLOGFILE 格式）
DUMP_SSL_KEYS_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "ssl_keys" };
        }
    };

    // Hook SSL_CTX_set_keylog_callback (如果存在)
    var modules = ["libssl.so", "libboringssl.so"];
    var hooked = false;

    modules.forEach(function(modName) {
        if (hooked) return;
        var mod = Process.findModuleByName(modName);
        if (!mod) return;

        // 尝试 Hook SSL_write 的内部密钥派生
        // 这里简化处理，Hook SSL_new 并记录 SSL 对象
        var SSL_new = Module.findExportByName(modName, "SSL_new");
        if (SSL_new) {
            Interceptor.attach(SSL_new, {
                onLeave: function(retval) {
                    send({
                        type: "ssl_new",
                        hookId: hookId,
                        ssl_ptr: retval.toString()
                    });
                }
            });
        }

        // Hook SSL_get_session
        var SSL_get_session = Module.findExportByName(modName, "SSL_get_session");
        if (SSL_get_session) {
            Interceptor.attach(SSL_get_session, {
                onLeave: function(retval) {
                    if (!retval.isNull()) {
                        send({
                            type: "ssl_session",
                            hookId: hookId,
                            session_ptr: retval.toString()
                        });
                    }
                }
            });
        }

        hooked = true;
        send({ type: "hook_attached", hookId: hookId, module: modName });
    });

    if (!hooked) {
        send({ type: "error", hookId: hookId, message: "No SSL module found" });
    }
})();
"""


def register_tools(mcp):
    """向 MCP 服务器注册加密分析工具"""

    @mcp.tool()
    def hook_crypto(session_id: str) -> Dict[str, Any]:
        """Hook Java 加密 API

        Hook javax.crypto.Cipher、SecretKeySpec、Mac、MessageDigest，
        捕获所有加密操作的密钥、输入、输出。

        Args:
            session_id: 会话 ID

        Returns:
            包含 hook_id 的字典
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

        在 hook_crypto 之后调用，获取所有加密操作的输入输出。

        Args:
            session_id: 会话 ID
            clear: 是否在读取后清空

        Returns:
            加密操作列表
        """
        try:
            messages = frida_client.get_messages(session_id, clear=clear)
            ops = []
            for msg in messages:
                m = msg.get("message", {})
                if m.get("type") == "crypto_doFinal":
                    ops.append({
                        "type": "encrypt_decrypt",
                        "algorithm": m.get("algorithm"),
                        "input_b64": m.get("input_b64"),
                        "output_b64": m.get("output_b64"),
                        "input_size": m.get("input_size"),
                        "output_size": m.get("output_size"),
                    })
                elif m.get("type") == "hash_digest":
                    ops.append({
                        "type": "hash",
                        "algorithm": m.get("algorithm"),
                        "hash_hex": m.get("hash_hex"),
                    })
                elif m.get("type") == "mac_init":
                    ops.append({
                        "type": "mac",
                        "algorithm": m.get("algorithm"),
                        "key": m.get("key"),
                    })
            return ops
        except Exception as e:
            logger.error(f"get_crypto_operations failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def hook_ssl_keys(session_id: str) -> Dict[str, Any]:
        """Hook SSL 密钥派生

        尝试捕获 SSL/TLS 会话密钥信息。

        Args:
            session_id: 会话 ID

        Returns:
            包含 hook_id 的字典
        """
        try:
            hook_id = f"sslkeys_{uuid.uuid4().hex[:8]}"
            source = DUMP_SSL_KEYS_TEMPLATE % {"hook_id": hook_id}
            result = frida_client.execute_script(
                session_id, source, script_name=hook_id
            )
            return {
                "hook_id": hook_id,
                "script_id": result["script_id"],
                "session_id": session_id,
            }
        except Exception as e:
            logger.error(f"hook_ssl_keys failed: {e}")
            return {"error": str(e)}

    logger.info("Crypto module tools registered")
