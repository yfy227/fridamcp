"""
网络监控模块

提供网络捕获、SSL Hook、HTTP 请求监控等工具。
"""

import uuid
from collections import deque
from typing import Dict, Any, List, Optional

from ..core.frida_client import frida_client
from ..config import config
from ..utils.logger import logger


# 网络类消息类型（send() 消息 type 字段）
NETWORK_MSG_TYPES = (
    "ssl_write", "ssl_read",
    "socket_connect", "socket_send", "socket_recv",
)

# 捕获状态标记（数据本体经 frida send() 进入会话消息缓冲，
# 由 get_capture_impl 读取——旧 _capture_buffer 从未有写入方，
# 是恒空死缓冲，已删除）
_capture_active: Dict[str, bool] = {}


SSL_HOOK_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";

    rpc.exports = {
        info: function() {
            return { hookId: hookId, type: "ssl" };
        }
    };

    function findSSLExport(name) {
        // 先做全局符号查找：能覆盖动态链接 libssl.so 以及
        // 静态链接 BoringSSL（符号在主二进制/其他 .so）的场景
        var addr = Module.findExportByName(null, name);
        if (addr === null) {
            addr = Module.findExportByName("libssl.so", name);
        }
        return addr;
    }

    function hookSSL() {
        // Hook SSL_write
        var SSL_write = findSSLExport("SSL_write");
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
        var SSL_read = findSSLExport("SSL_read");
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
            onLeave: function(retval) {
                // 数据在 onEnter 中无法获取，需要在此处读取
            }
        });
    }

    send({ type: "hook_attached", hookId: hookId });
})();
"""



# ============================================================
# 共享实现层：MCP 工具与 GUI（app.py）复用同一份逻辑
# （与 hook 模块的 impl 层同一模式）
# ============================================================


def start_capture_impl(
    session_id: str,
    capture_ssl: bool = True,
    capture_socket: bool = False,
) -> Dict[str, Any]:
    """开始网络捕获（SSL / Socket Hook 注入）"""
    try:
        _capture_active[session_id] = True

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


def stop_capture_impl(session_id: str) -> Dict[str, Any]:
    """停止网络捕获，返回本次捕获条数"""
    try:
        _capture_active.pop(session_id, None)
        # 数据在会话消息里（旧实现读恒空的死缓冲，永远返回 0）
        count = 0
        try:
            messages = frida_client.get_messages(session_id, clear=False)
            count = sum(
                1 for msg in messages
                if msg.get("message", {}).get("type") in NETWORK_MSG_TYPES
            )
        except Exception:
            pass
        return {
            "success": True,
            "session_id": session_id,
            "captured_count": count,
        }
    except Exception as e:
        logger.error(f"stop_capture failed: {e}")
        return {"error": str(e)}


def get_capture_impl(
    session_id: str,
    clear: bool = False,
    filter_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """获取捕获的网络数据（来自会话消息缓冲）"""
    try:
        messages = frida_client.get_messages(session_id, clear=clear)
        captures = []
        for msg in messages:
            m = msg.get("message", {})
            if m.get("type") in NETWORK_MSG_TYPES:
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
        return start_capture_impl(session_id, capture_ssl, capture_socket)

    @mcp.tool()
    def stop_capture(session_id: str) -> Dict[str, Any]:
        """停止网络捕获

        Args:
            session_id: 会话 ID

        Returns:
            操作结果，包含已捕获的条目数
        """
        return stop_capture_impl(session_id)

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
        return get_capture_impl(session_id, clear, filter_type)

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

    logger.info("Network module tools registered")
