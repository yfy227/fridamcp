"""
FridaMCP 服务器入口

启动 MCP 服务器，监听端口 8768，注册所有 MCP 模块。
支持优雅关闭、自动重启和健康检查。
"""

import sys
import os
import signal
import asyncio
import argparse
from typing import Optional

from .config import config
from .utils.logger import setup_logging, logger
from .modules import ALL_MODULES
from .core.session_manager import session_manager
from .core.device_manager import device_manager


# 全局关闭事件
_shutdown_event: Optional[asyncio.Event] = None


def create_mcp_server():
    """创建并配置 MCP 服务器"""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        try:
            from mcp.server import Server
            logger.warning("FastMCP not available, using basic Server")
            return _create_basic_server()
        except ImportError:
            logger.error("mcp package not installed. Run: pip install mcp")
            sys.exit(1)

    mcp = FastMCP(
        name="FridaMCP",
        instructions=(
            "FridaMCP - AI-Powered Frida MCP Server for Android. "
            "This server provides tools to control Frida on Android devices "
            "for dynamic analysis, hooking, memory inspection, network monitoring, "
            "and more. Listen on port 8768."
        ),
    )

    # 注册所有模块的工具
    registered_modules = []
    for module in ALL_MODULES:
        try:
            module.register_tools(mcp)
            registered_modules.append(module.__name__.split(".")[-1])
            logger.info(f"Module registered: {module.__name__}")
        except Exception as e:
            logger.error(f"Failed to register module {module.__name__}: {e}")

    # 注册健康检查工具
    @mcp.tool()
    def ping() -> str:
        """健康检查工具，返回 pong"""
        return "pong"

    @mcp.tool()
    def server_info() -> dict:
        """获取 MCP 服务器信息

        返回服务器版本、监听端口、已注册模块、设备状态、会话状态等信息。
        """
        return {
            "name": "FridaMCP",
            "version": "1.0.0",
            "port": config.MCP_PORT,
            "host": config.MCP_HOST,
            "modules": registered_modules,
            "device": device_manager.get_status(),
            "sessions": session_manager.get_status(),
        }

    @mcp.tool()
    def health_check() -> dict:
        """全面健康检查

        检查服务器、设备连接、会话状态等，返回详细健康报告。
        """
        device_connected = device_manager.is_connected()
        session_status = session_manager.get_status()

        all_healthy = device_connected or not session_status["active_sessions"]

        return {
            "healthy": all_healthy,
            "server": {
                "running": True,
                "port": config.MCP_PORT,
            },
            "device": {
                "connected": device_connected,
                "status": device_manager.get_status(),
            },
            "sessions": session_status,
        }

    @mcp.tool()
    def reconnect_device() -> dict:
        """重新连接设备

        当设备连接断开时，强制重新连接。

        Returns:
            操作结果
        """
        try:
            device = device_manager.refresh()
            return {
                "success": True,
                "device": {
                    "id": device.id,
                    "name": device.name,
                    "type": device.type,
                },
            }
        except Exception as e:
            logger.error(f"reconnect_device failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def cleanup_sessions() -> dict:
        """清理已分离的会话

        移除所有处于 DETACHED 或 ERROR 状态的会话，释放资源。

        Returns:
            操作结果，包含清理的会话数量
        """
        try:
            before = len(session_manager.list_sessions())
            session_manager._cleanup_detached()
            after = len(session_manager.list_sessions())
            cleaned = before - after
            return {
                "success": True,
                "cleaned_count": cleaned,
                "remaining_count": after,
            }
        except Exception as e:
            logger.error(f"cleanup_sessions failed: {e}")
            return {"error": str(e)}

    return mcp


def _create_basic_server():
    """创建基础 MCP 服务器（当 FastMCP 不可用时）"""
    from mcp.server import Server

    server = Server("FridaMCP")

    @server.list_tools()
    async def list_tools():
        from mcp.types import Tool
        return [
            Tool(
                name="ping",
                description="Health check",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="server_info",
                description="Get server info",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        from mcp.types import TextContent
        if name == "ping":
            return [TextContent(type="text", text="pong")]
        elif name == "server_info":
            import json
            info = {
                "name": "FridaMCP",
                "version": "1.0.0",
                "port": config.MCP_PORT,
                "note": "Running in basic mode (FastMCP not available)",
            }
            return [TextContent(type="text", text=json.dumps(info, indent=2))]
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


def _signal_handler(signum, frame):
    """信号处理器，用于优雅关闭"""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received signal {sig_name}, initiating graceful shutdown...")
    if _shutdown_event:
        _shutdown_event.set()


def _setup_signal_handlers():
    """设置信号处理器"""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


async def run_sse_server(mcp, host: str, port: int):
    """以 SSE 模式运行 MCP 服务器（带自动重启）"""
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    _setup_signal_handlers()

    restart_count = 0
    max_restarts = config.SERVER_AUTO_RESTART_MAX

    while not _shutdown_event.is_set():
        try:
            if hasattr(mcp, "run_sse_async"):
                logger.info(f"Starting SSE server on {host}:{port}")
                await mcp.run_sse_async(host=host, port=port)
            elif hasattr(mcp, "sse_app"):
                import uvicorn
                app = mcp.sse_app()
                config_uv = uvicorn.Config(
                    app,
                    host=host,
                    port=port,
                    log_level="info",
                )
                server = uvicorn.Server(config_uv)
                # 关联关闭事件
                server.install_signal_handlers = lambda: None
                await server.serve()
            else:
                logger.error("SSE mode not supported by this MCP version")
                sys.exit(1)
            break  # 正常退出

        except asyncio.CancelledError:
            logger.info("Server task cancelled")
            break
        except Exception as e:
            if _shutdown_event.is_set():
                break
            restart_count += 1
            if restart_count > max_restarts:
                logger.error(
                    f"Server exceeded max restarts ({max_restarts}), giving up: {e}"
                )
                raise
            logger.error(
                f"Server error (restart {restart_count}/{max_restarts}): {e}"
            )
            await asyncio.sleep(2)

    # 优雅关闭：清理所有会话
    logger.info("Cleaning up sessions...")
    session_manager.close_all()
    logger.info("Server shutdown complete")


async def run_streamable_http_server(mcp, host: str, port: int):
    """以 Streamable HTTP 模式运行 MCP 服务器"""
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    _setup_signal_handlers()

    try:
        if hasattr(mcp, "streamable_http_app"):
            import uvicorn
            app = mcp.streamable_http_app()
            config_uv = uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level="info",
            )
            server = uvicorn.Server(config_uv)
            server.install_signal_handlers = lambda: None
            await server.serve()
        else:
            logger.warning("Streamable HTTP not available, falling back to SSE")
            await run_sse_server(mcp, host, port)
    except asyncio.CancelledError:
        logger.info("Server task cancelled")
    except Exception as e:
        logger.error(f"HTTP server error: {e}")
        raise
    finally:
        logger.info("Cleaning up sessions...")
        session_manager.close_all()
        logger.info("Server shutdown complete")


def run_stdio_server(mcp):
    """以 stdio 模式运行 MCP 服务器"""
    _setup_signal_handlers()
    try:
        if hasattr(mcp, "run"):
            mcp.run()
        else:
            logger.error("stdio mode not supported")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        session_manager.close_all()
        logger.info("Server shutdown complete")


def main():
    """主入口函数"""
    global _shutdown_event

    parser = argparse.ArgumentParser(
        description="FridaMCP - AI-Powered Frida MCP Server for Android"
    )
    parser.add_argument(
        "--host",
        default=config.MCP_HOST,
        help=f"Host to bind (default: {config.MCP_HOST})",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=config.MCP_PORT,
        help=f"Port to listen (default: {config.MCP_PORT})",
    )
    parser.add_argument(
        "--transport", "-t",
        choices=["sse", "http", "stdio"],
        default="sse",
        help="Transport type (default: sse)",
    )
    parser.add_argument(
        "--log-level",
        default=config.LOG_LEVEL,
        help=f"Log level (default: {config.LOG_LEVEL})",
    )
    parser.add_argument(
        "--device-type",
        choices=["usb", "remote", "local"],
        default=config.FRIDA_DEVICE_TYPE,
        help="Frida device type (default: usb)",
    )
    parser.add_argument(
        "--device-id",
        default=None,
        help="Frida device ID",
    )
    parser.add_argument(
        "--no-auto-restart",
        action="store_true",
        help="Disable server auto-restart on crash",
    )

    args = parser.parse_args()

    # 更新配置
    os.environ["FRIDAMCP_HOST"] = args.host
    os.environ["FRIDAMCP_PORT"] = str(args.port)
    os.environ["FRIDA_DEVICE_TYPE"] = args.device_type
    if args.device_id:
        os.environ["FRIDA_DEVICE_ID"] = args.device_id
    if args.no_auto_restart:
        os.environ["FRIDAMCP_AUTO_RESTART_MAX"] = "0"

    # 重新加载配置
    from importlib import reload
    from . import config as config_module
    reload(config_module)

    # 初始化日志
    setup_logging()

    logger.info("=" * 60)
    logger.info("FridaMCP - AI-Powered Frida MCP Server for Android")
    logger.info("=" * 60)
    logger.info(f"Host: {args.host}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Transport: {args.transport}")
    logger.info(f"Device type: {args.device_type}")
    if args.device_id:
        logger.info(f"Device ID: {args.device_id}")
    logger.info(f"Auto-restart: {'disabled' if args.no_auto_restart else 'enabled'}")
    logger.info("=" * 60)

    # 创建 MCP 服务器
    mcp = create_mcp_server()

    # 启动服务器
    if args.transport == "stdio":
        logger.info("Starting MCP server in stdio mode")
        run_stdio_server(mcp)
    elif args.transport == "sse":
        logger.info(f"Starting MCP server in SSE mode on {args.host}:{args.port}")
        asyncio.run(run_sse_server(mcp, args.host, args.port))
    elif args.transport == "http":
        logger.info(
            f"Starting MCP server in Streamable HTTP mode on {args.host}:{args.port}"
        )
        asyncio.run(run_streamable_http_server(mcp, args.host, args.port))


if __name__ == "__main__":
    main()
