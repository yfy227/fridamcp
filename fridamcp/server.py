"""
FridaMCP 服务器入口

启动 MCP 服务器，监听端口 8768，注册所有 MCP 模块。
"""

import sys
import asyncio
import argparse
from typing import Optional

from .config import config
from .utils.logger import setup_logging, logger
from .modules import ALL_MODULES


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

    # 创建 FastMCP 服务器
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
    for module in ALL_MODULES:
        try:
            module.register_tools(mcp)
            logger.info(f"Module registered: {module.__name__}")
        except Exception as e:
            logger.error(f"Failed to register module {module.__name__}: {e}")

    # 注册一个 ping 工具用于健康检查
    @mcp.tool()
    def ping() -> str:
        """健康检查工具，返回 pong"""
        return "pong"

    # 注册服务器信息工具
    @mcp.tool()
    def server_info() -> dict:
        """获取 MCP 服务器信息

        返回服务器版本、监听端口、已注册模块等信息。
        """
        return {
            "name": "FridaMCP",
            "version": "1.0.0",
            "port": config.MCP_PORT,
            "host": config.MCP_HOST,
            "modules": [m.__name__.split(".")[-1] for m in ALL_MODULES],
            "device_type": config.FRIDA_DEVICE_TYPE,
        }

    return mcp


def _create_basic_server():
    """创建基础 MCP 服务器（当 FastMCP 不可用时）"""
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

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


async def run_sse_server(mcp, host: str, port: int):
    """以 SSE 模式运行 MCP 服务器"""
    try:
        # FastMCP 的 SSE 模式
        if hasattr(mcp, "run_sse_async"):
            await mcp.run_sse_async(host=host, port=port)
        elif hasattr(mcp, "sse_app"):
            # 使用 ASGI 应用
            import uvicorn
            app = mcp.sse_app()
            config_uv = uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level="info",
            )
            server = uvicorn.Server(config_uv)
            await server.serve()
        else:
            logger.error("SSE mode not supported by this MCP version")
            sys.exit(1)
    except Exception as e:
        logger.error(f"SSE server error: {e}")
        raise


async def run_streamable_http_server(mcp, host: str, port: int):
    """以 Streamable HTTP 模式运行 MCP 服务器"""
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
            await server.serve()
        else:
            # 回退到 SSE
            logger.warning("Streamable HTTP not available, falling back to SSE")
            await run_sse_server(mcp, host, port)
    except Exception as e:
        logger.error(f"HTTP server error: {e}")
        raise


def run_stdio_server(mcp):
    """以 stdio 模式运行 MCP 服务器"""
    if hasattr(mcp, "run"):
        mcp.run()
    else:
        logger.error("stdio mode not supported")
        sys.exit(1)


def main():
    """主入口函数"""
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

    args = parser.parse_args()

    # 更新配置
    import os
    os.environ["FRIDAMCP_HOST"] = args.host
    os.environ["FRIDAMCP_PORT"] = str(args.port)
    os.environ["FRIDA_DEVICE_TYPE"] = args.device_type
    if args.device_id:
        os.environ["FRIDA_DEVICE_ID"] = args.device_id

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
