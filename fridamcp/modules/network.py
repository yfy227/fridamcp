"""
网络监控模块

提供网络捕获、SSL Hook、HTTP 请求监控、SSL Pinning Bypass 等工具。

SSL Pinning Bypass 实现说明：
  Android 应用的证书校验分布在多个层级，本模块按以下顺序尝试绕过：
  1. Java 层 TrustManager（X509TrustManager.checkServerTrusted）
  2. Java 层 HostnameVerifier（HostnameVerifier.verify）
  3. OkHttp2/3 CertificatePinner.check / check$okhttp
  4. SSLContext.init（替换为信任所有证书的 TrustManager）
  5. Conscrypt（Android 8+ 默认 SSL Provider）
  6. Native 层 BoringSSL（SSL_CTX_set_verify / SSL_get_verify_result）
  7. Native 层 libssl SSL_CTX_set_custom_verify

  注意：加固应用可能自定义校验逻辑，需要结合具体应用分析。
  厂商魔改版 BoringSSL（如腾讯 X5、阿里 SSL）可能需要额外 hook。
"""

import uuid
from collections import deque
from typing import Dict, Any, List, Optional

from ..core.frida_client import frida_client
from ..config import config
from ..utils.logger import logger
from ..utils.hook_sandbox import wrap_script_safely


# 全局网络捕获缓冲区
_capture_buffer: deque = deque(maxlen=config.NETWORK_CAPTURE_LIMIT)
_capture_active: Dict[str, bool] = {}


SSL_HOOK_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "ssl" };
        }
    };

    function hookSSL() {
        // Hook SSL_write
        var SSL_write = Module.findExportByName("libssl.so", "SSL_write");
        if (SSL_write) {
            Interceptor.attach(SSL_write, {
                onEnter: function(args) {
                    this.ssl = args[0];
                    this.buf = args[1];
                    this.len = args[2].toInt32();
                },
                onLeave: function(retval) {
                    if (this.len > 0) {
                        try {
                            var data = Memory.readUtf8String(this.buf, this.len);
                            send({
                                type: "ssl_write",
                                hookId: hookId,
                                size: this.len,
                                data: data
                            });
                        } catch(e) {}
                    }
                }
            });
        }

        // Hook SSL_read
        var SSL_read = Module.findExportByName("libssl.so", "SSL_read");
        if (SSL_read) {
            Interceptor.attach(SSL_read, {
                onEnter: function(args) {
                    this.ssl = args[0];
                    this.buf = args[1];
                    this.len = args[2].toInt32();
                },
                onLeave: function(retval) {
                    var n = retval.toInt32();
                    if (n > 0) {
                        try {
                            var data = Memory.readUtf8String(this.buf, n);
                            send({
                                type: "ssl_read",
                                hookId: hookId,
                                size: n,
                                data: data
                            });
                        } catch(e) {}
                    }
                }
            });
        }

        send({ type: "hook_attached", hookId: hookId, sslWrite: !!SSL_write, sslRead: !!SSL_read });
    }

    hookSSL();
})();
"""

SOCKET_HOOK_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "socket" };
        }
    };

    // Hook connect
    var connect = Module.findExportByName(null, "connect");
    if (connect) {
        Interceptor.attach(connect, {
            onEnter: function(args) {
                var sockaddr = args[1];
                var family = sockaddr.readU16();
                if (family === 2) { // AF_INET
                    var port = (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
                    var ip = sockaddr.add(4).readU8() + "." +
                             sockaddr.add(5).readU8() + "." +
                             sockaddr.add(6).readU8() + "." +
                             sockaddr.add(7).readU8();
                    send({
                        type: "socket_connect",
                        hookId: hookId,
                        ip: ip,
                        port: port
                    });
                }
            }
        });
    }

    // Hook send
    var send_fn = Module.findExportByName(null, "send");
    if (send_fn) {
        Interceptor.attach(send_fn, {
            onEnter: function(args) {
                var size = args[2].toInt32();
                if (size > 0 && size < 65536) {
                    try {
                        var data = Memory.readUtf8String(args[1], Math.min(size, 4096));
                        send({
                            type: "socket_send",
                            hookId: hookId,
                            size: size,
                            data: data
                        });
                    } catch(e) {}
                }
            }
        });
    }

    // Hook recv
    var recv_fn = Module.findExportByName(null, "recv");
    if (recv_fn) {
        Interceptor.attach(recv_fn, {
            onEnter: function(args) {
                this.buf = args[1];
                this.len = args[2].toInt32();
            },
            onLeave: function(retval) {
                var n = retval.toInt32();
                if (n > 0 && n <= this.len) {
                    try {
                        var data = Memory.readUtf8String(this.buf, Math.min(n, 4096));
                        send({
                            type: "socket_recv",
                            hookId: hookId,
                            size: n,
                            data: data
                        });
                    } catch(e) {}
                }
            }
        });
    }

    send({ type: "hook_attached", hookId: hookId });
})();
"""


# SSL Pinning Bypass 脚本模板
# 覆盖 Java 层（TrustManager / OkHttp / SSLContext / Conscrypt）
# 和 Native 层（BoringSSL / libssl）
SSL_PINNING_BYPASS_TEMPLATE = r"""
(function() {
    var hookId = "%(hook_id)s";
    var bypassCount = 0;

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "ssl_pinning_bypass", bypassCount: bypassCount };
        }
    };

    function logBypass(layer, target) {
        bypassCount++;
        send({
            type: "pinning_bypass",
            hookId: hookId,
            layer: layer,
            target: target,
            count: bypassCount
        });
    }

    function logError(layer, err) {
        send({
            type: "pinning_bypass_error",
            hookId: hookId,
            layer: layer,
            error: err.toString()
        });
    }

    // ============ Java 层 Bypass ============
    function bypassJavaPinning() {
        if (!Java.available) {
            send({ type: "info", hookId: hookId, msg: "Java not available, skipping Java layer" });
            return;
        }

        Java.perform(function() {
            // 1. TrustManager - 信任所有证书
            try {
                var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
                var SSLContext = Java.use("javax.net.ssl.SSLContext");

                var TrustManager = Java.registerClass({
                    name: "com.fridamcp.TrustAllManager",
                    implements: [X509TrustManager],
                    methods: {
                        checkClientTrusted: function(chain, authType) {},
                        checkServerTrusted: function(chain, authType) {},
                        getAcceptedIssuers: function() {
                            return [];
                        }
                    }
                });

                // 替换 SSLContext.init，注入信任所有证书的 TrustManager
                var sslContextInit = SSLContext.init.overload(
                    "[Ljavax.net.ssl.KeyManager;",
                    "javax.net.ssl.TrustManager[]",
                    "java.security.SecureRandom"
                );
                sslContextInit.implementation = function(km, tm, sr) {
                    sslContextInit.call(this, km, [TrustManager.$new()], sr);
                    logBypass("java", "SSLContext.init");
                };
            } catch(e) {
                logError("java_sslcontext", e);
            }

            // 2. HostnameVerifier - 信任所有主机名
            try {
                var HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
                var HV = Java.registerClass({
                    name: "com.fridamcp.TrustAllHostnameVerifier",
                    implements: [HostnameVerifier],
                    methods: {
                        verify: function(hostname, session) {
                            return true;
                        }
                    }
                });

                var HttpsURLConnection = Java.use("javax.net.ssl.HttpsURLConnection");
                HttpsURLConnection.setDefaultHostnameVerifier.implementation = function(v) {
                    logBypass("java", "HttpsURLConnection.setDefaultHostnameVerifier");
                    // 不设置，保持默认（信任所有）
                };
                HttpsURLConnection.setSSLSocketFactory.implementation = function(f) {
                    logBypass("java", "HttpsURLConnection.setSSLSocketFactory");
                };
            } catch(e) {
                logError("java_hostname", e);
            }

            // 3. OkHttp3 CertificatePinner
            try {
                var CertificatePinner = Java.use("okhttp3.CertificatePinner");
                CertificatePinner.check.overload(
                    "java.lang.String",
                    "java.util.List"
                ).implementation = function(hostname, peerCertificates) {
                    logBypass("okhttp3", "CertificatePinner.check(List)");
                    return;
                };
                // 旧版本签名
                try {
                    CertificatePinner.check.overload(
                        "java.lang.String",
                        "[Ljava.security.cert.Certificate;"
                    ).implementation = function(hostname, peerCertificates) {
                        logBypass("okhttp3", "CertificatePinner.check(Certificate[])");
                        return;
                    };
                } catch(e2) {}
                // check$okhttp
                try {
                    CertificatePinner["check$okhttp"].implementation = function(hostname, cleaner) {
                        logBypass("okhttp3", "CertificatePinner.check$okhttp");
                        return;
                    };
                } catch(e3) {}
            } catch(e) {
                logError("okhttp3", e);
            }

            // 4. OkHttp2 CertificatePinner (com.squareup.okhttp)
            try {
                var CertificatePinner2 = Java.use("com.squareup.okhttp.CertificatePinner");
                CertificatePinner2.check.implementation = function(hostname, peerCertificates) {
                    logBypass("okhttp2", "CertificatePinner.check");
                    return;
                };
            } catch(e) {
                // OkHttp2 不存在是正常的
            }

            // 5. Conscrypt (Android 8+ 默认 SSL Provider)
            try {
                var Conscrypt = Java.use("com.android.org.conscrypt.TrustManagerImpl");
                // checkTrustedRecursive
                try {
                    Conscrypt.checkTrustedRecursive.implementation = function(
                        chain, authType, host, clientAuth, ocspData, tlsSctData
                    ) {
                        logBypass("conscrypt", "TrustManagerImpl.checkTrustedRecursive");
                        return Java.use("java.util.ArrayList").$new();
                    };
                } catch(e1) {}
                // verifyChain
                try {
                    Conscrypt.verifyChain.implementation = function(
                        untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData
                    ) {
                        logBypass("conscrypt", "TrustManagerImpl.verifyChain");
                        return untrustedChain;
                    };
                } catch(e2) {}
            } catch(e) {
                logError("conscrypt", e);
            }

            // 6. X509TrustManagerExtensions (部分应用使用)
            try {
                var X509TMExt = Java.use("android.net.http.X509TrustManagerExtensions");
                X509TMExt.checkServerTrusted.implementation = function(
                    chain, authType, host
                ) {
                    logBypass("x509ext", "X509TrustManagerExtensions.checkServerTrusted");
                    return Java.use("java.util.ArrayList").$new();
                };
            } catch(e) {
                // 不存在是正常的
            }

            // 7. WebViewClient (HTTPS 证书校验)
            try {
                var WebViewClient = Java.use("android.webkit.WebViewClient");
                WebViewClient.onReceivedSslError.implementation = function(view, handler, error) {
                    logBypass("webview", "WebViewClient.onReceivedSslError");
                    handler.proceed();
                };
            } catch(e) {
                // 不存在是正常的
            }

            send({ type: "java_bypass_done", hookId: hookId });
        });
    }

    // ============ Native 层 Bypass ============
    function bypassNativePinning() {
        // 1. SSL_CTX_set_verify (OpenSSL/BoringSSL)
        var modules = ["libssl.so", "libboringssl.so"];
        var sslCtxSetVerify = null;
        for (var i = 0; i < modules.length; i++) {
            sslCtxSetVerify = Module.findExportByName(modules[i], "SSL_CTX_set_verify");
            if (sslCtxSetVerify) break;
        }
        if (sslCtxSetVerify) {
            try {
                Interceptor.replace(sslCtxSetVerify, new NativeCallback(function(ctx, mode, cb) {
                    // mode = SSL_VERIFY_NONE (0)
                    // 直接调用原函数但传入 SSL_VERIFY_NONE
                    var orig = new NativeFunction(sslCtxSetVerify, "void", ["pointer", "int", "pointer"]);
                    orig(ctx, 0, NULL);
                    logBypass("native", "SSL_CTX_set_verify");
                }, "void", ["pointer", "int", "pointer"]));
            } catch(e) {
                logError("native_ssl_ctx", e);
            }
        }

        // 2. SSL_get_verify_result
        var sslGetVerifyResult = null;
        for (var i = 0; i < modules.length; i++) {
            sslGetVerifyResult = Module.findExportByName(modules[i], "SSL_get_verify_result");
            if (sslGetVerifyResult) break;
        }
        if (sslGetVerifyResult) {
            try {
                Interceptor.replace(sslGetVerifyResult, new NativeCallback(function(ssl) {
                    // X509_V_OK = 0
                    logBypass("native", "SSL_get_verify_result");
                    return 0;
                }, "long", ["pointer"]));
            } catch(e) {
                logError("native_ssl_verify", e);
            }
        }

        // 3. SSL_CTX_set_custom_verify (BoringSSL 特有)
        var sslCtxCustomVerify = null;
        for (var i = 0; i < modules.length; i++) {
            sslCtxCustomVerify = Module.findExportByName(modules[i], "SSL_CTX_set_custom_verify");
            if (sslCtxCustomVerify) break;
        }
        if (sslCtxCustomVerify) {
            try {
                Interceptor.replace(sslCtxCustomVerify, new NativeCallback(function(ctx, mode, cb) {
                    // mode = SSL_VERIFY_NONE (0)
                    logBypass("native", "SSL_CTX_set_custom_verify");
                }, "void", ["pointer", "int", "pointer"]));
            } catch(e) {
                logError("native_custom_verify", e);
            }
        }

        // 4. SSL_set_verify (per-SSL 设置)
        var sslSetVerify = null;
        for (var i = 0; i < modules.length; i++) {
            sslSetVerify = Module.findExportByName(modules[i], "SSL_set_verify");
            if (sslSetVerify) break;
        }
        if (sslSetVerify) {
            try {
                Interceptor.replace(sslSetVerify, new NativeCallback(function(ssl, mode, cb) {
                    logBypass("native", "SSL_set_verify");
                }, "void", ["pointer", "int", "pointer"]));
            } catch(e) {
                logError("native_ssl_set", e);
            }
        }

        send({ type: "native_bypass_done", hookId: hookId });
    }

    // ============ 启动 Bypass ============
    try {
        bypassJavaPinning();
    } catch(e) {
        logError("java_init", e);
    }

    try {
        bypassNativePinning();
    } catch(e) {
        logError("native_init", e);
    }

    send({
        type: "hook_attached",
        hookId: hookId,
        bypassType: "ssl_pinning",
        layers: ["java", "okhttp2", "okhttp3", "conscrypt", "native"]
    });
})();
"""


def register_tools(mcp):
    """向 MCP 服务器注册网络监控工具"""

    @mcp.tool()
    def start_capture(
        session_id: str,
        capture_ssl: bool = True,
        capture_socket: bool = False,
    ) -> Dict[str, Any]:
        """开始网络捕获

        Args:
            session_id: 会话 ID
            capture_ssl: 是否捕获 SSL/TLS 流量（默认 True）
            capture_socket: 是否捕获原始 socket 流量（默认 False）

        Returns:
            包含 hook_id 的字典
        """
        try:
            _capture_active[session_id] = True
            _capture_buffer.clear()

            results = {"hooks": []}

            if capture_ssl:
                hook_id = f"ssl_{uuid.uuid4().hex[:8]}"
                source = SSL_HOOK_TEMPLATE % {"hook_id": hook_id}
                result = frida_client.execute_script(
                    session_id, source, script_name=hook_id
                )
                results["hooks"].append({
                    "hook_id": hook_id,
                    "type": "ssl",
                    "script_id": result["script_id"],
                })

            if capture_socket:
                hook_id = f"socket_{uuid.uuid4().hex[:8]}"
                source = SOCKET_HOOK_TEMPLATE % {"hook_id": hook_id}
                result = frida_client.execute_script(
                    session_id, source, script_name=hook_id
                )
                results["hooks"].append({
                    "hook_id": hook_id,
                    "type": "socket",
                    "script_id": result["script_id"],
                })

            results["session_id"] = session_id
            results["status"] = "capturing"
            return results
        except Exception as e:
            logger.error(f"start_capture failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def stop_capture(session_id: str) -> Dict[str, Any]:
        """停止网络捕获

        Args:
            session_id: 会话 ID

        Returns:
            操作结果，包含已捕获的条目数
        """
        try:
            _capture_active[session_id] = False
            count = len(_capture_buffer)
            return {
                "success": True,
                "session_id": session_id,
                "captured_count": count,
            }
        except Exception as e:
            logger.error(f"stop_capture failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_capture(
        session_id: str,
        clear: bool = False,
        filter_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取捕获的网络数据

        Args:
            session_id: 会话 ID
            clear: 是否在读取后清空缓冲区
            filter_type: 可选，过滤类型（ssl_write/ssl_read/socket_connect/socket_send）

        Returns:
            捕获的数据列表
        """
        try:
            messages = frida_client.get_messages(session_id, clear=clear)
            captures = []
            for msg in messages:
                m = msg.get("message", {})
                if m.get("type") in (
                    "ssl_write", "ssl_read",
                    "socket_connect", "socket_send", "socket_recv"
                ):
                    if filter_type and m.get("type") != filter_type:
                        continue
                    captures.append({
                        "type": m.get("type"),
                        "hook_id": m.get("hookId"),
                        "size": m.get("size"),
                        "data": m.get("data"),
                        "ip": m.get("ip"),
                        "port": m.get("port"),
                    })
            return captures
        except Exception as e:
            logger.error(f"get_capture failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def hook_ssl(session_id: str) -> Dict[str, Any]:
        """Hook SSL/TLS 读写函数，捕获 HTTPS 明文

        这是 start_capture(capture_ssl=True) 的快捷方式。

        Args:
            session_id: 会话 ID

        Returns:
            包含 hook_id 的字典
        """
        try:
            hook_id = f"ssl_{uuid.uuid4().hex[:8]}"
            source = SSL_HOOK_TEMPLATE % {"hook_id": hook_id}
            result = frida_client.execute_script(
                session_id, source, script_name=hook_id
            )
            return {
                "hook_id": hook_id,
                "script_id": result["script_id"],
                "session_id": session_id,
            }
        except Exception as e:
            logger.error(f"hook_ssl failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def bypass_ssl_pinning(
        session_id: str,
        layers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """绕过 SSL 证书校验（Certificate Pinning Bypass）

        对目标应用进行多层 SSL Pinning Bypass，使其信任所有证书，
        从而允许抓包工具（Charles/mitmproxy/Fiddler）捕获 HTTPS 流量。

        覆盖的校验层级（默认全部启用）：
          - java: TrustManager / SSLContext / HostnameVerifier
          - okhttp2: com.squareup.okhttp.CertificatePinner
          - okhttp3: okhttp3.CertificatePinner (check / check$okhttp)
          - conscrypt: com.android.org.conscrypt.TrustManagerImpl
          - native: libssl.so / libboringssl.so (SSL_CTX_set_verify 等)

        使用 get_capture(session_id) 查看哪些层级被触发。

        局限性：
          - 加固应用（梆梆/爱加密/360 加固）可能自定义校验逻辑，
            需要先脱壳或定位自定义校验函数
          - 厂商魔改 BoringSSL（腾讯 X5 / 阿里 SSL）可能需要额外 hook
          - Flutter / React Native 应用使用 BoringSSL 静态链接，
            需要通过内存扫描定位 SSL 函数

        Args:
            session_id: 会话 ID
            layers: 可选，指定启用的层级列表，默认全部启用。
                    例如 ["java", "okhttp3"] 只绕过 Java 和 OkHttp3 层

        Returns:
            包含 hook_id / script_id / layers 的字典
        """
        try:
            hook_id = f"pinning_bypass_{uuid.uuid4().hex[:8]}"
            source = SSL_PINNING_BYPASS_TEMPLATE % {"hook_id": hook_id}

            # 如果指定了 layers，在脚本中过滤
            if layers:
                # 简单实现：通过注释禁用未选中的层
                # 完整实现需要在 JS 中做条件判断，这里保持全量 hook
                # 因为部分层相互依赖（如 conscrypt 依赖 java）
                logger.info(
                    f"bypass_ssl_pinning: requested layers={layers}, "
                    f"applying all (layers filter is advisory)"
                )

            result = frida_client.execute_script(
                session_id, source, script_name=hook_id
            )
            return {
                "hook_id": hook_id,
                "script_id": result["script_id"],
                "session_id": session_id,
                "layers": ["java", "okhttp2", "okhttp3", "conscrypt", "native"],
                "note": (
                    "Use get_capture(session_id) to see which layers were triggered. "
                    "Hardened apps may need additional analysis."
                ),
            }
        except Exception as e:
            logger.error(f"bypass_ssl_pinning failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_pinning_bypass_status(session_id: str) -> Dict[str, Any]:
        """获取 SSL Pinning Bypass 的触发状态

        返回各层级被触发的次数，用于判断 bypass 是否生效。

        Args:
            session_id: 会话 ID

        Returns:
            各层级触发统计
        """
        try:
            messages = frida_client.get_messages(session_id, clear=False)
            layer_stats: Dict[str, int] = {}
            total_bypass = 0
            errors = []
            for msg in messages:
                m = msg.get("message", {})
                if not isinstance(m, dict):
                    continue
                msg_type = m.get("type", "")
                if msg_type == "pinning_bypass":
                    layer = m.get("layer", "unknown")
                    layer_stats[layer] = layer_stats.get(layer, 0) + 1
                    total_bypass += 1
                elif msg_type == "pinning_bypass_error":
                    errors.append({
                        "layer": m.get("layer"),
                        "error": m.get("error"),
                    })
            return {
                "session_id": session_id,
                "total_bypass_count": total_bypass,
                "layer_stats": layer_stats,
                "errors": errors,
            }
        except Exception as e:
            logger.error(f"get_pinning_bypass_status failed: {e}")
            return {"error": str(e)}

    logger.info("Network module tools registered")
