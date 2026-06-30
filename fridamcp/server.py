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
from . import __version__


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
            "version": __version__,
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
    def cleanup_sessions() -> dict:
        """清理已分离的会话

        移除所有处于 DETACHED 或 ERROR 状态的会话，释放资源。

        Returns:
            操作结果，包含清理的会话数量
        """
        try:
            before = len(session_manager.list_sessions())
            session_manager._cleanup_detached()
            session_manager._cleanup_expired()
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

    @mcp.tool()
    def get_session_info(session_id: str) -> dict:
        """获取指定会话的详细信息（生命周期/脚本/Hook/消息计数/时间戳）

        Args:
            session_id: 会话 ID

        Returns:
            会话详细信息，包括状态、脚本、Hook、消息计数、时间戳等
        """
        session = session_manager.get_session(session_id)
        if session is None:
            return {"error": f"Session not found: {session_id}"}
        return session.get_info()

    @mcp.tool()
    def session_manager_status() -> dict:
        """获取会话管理器状态

        返回会话管理器的运行状态，包括：
        - total/active/detached/expired sessions 数量
        - max_sessions 上限
        - idle_timeout 空闲超时配置
        - keepalive_interval 保活检查间隔
        - keepalive_running 保活线程是否运行

        Returns:
            会话管理器状态字典
        """
        return session_manager.get_status()

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
                "version": __version__,
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


async def _print_tools(mcp):
    """打印所有已注册的 MCP 工具"""
    tools = await mcp.list_tools()
    print(f"\n{'='*60}")
    print(f"FridaMCP - {len(tools)} registered tools")
    print(f"{'='*60}")
    for t in sorted(tools, key=lambda x: x.name):
        desc = (t.description or "").split("\n")[0][:70]
        print(f"  {t.name:<30} {desc}")
    print(f"{'='*60}\n")


def run_self_test() -> int:
    """运行自测

    验证以下内容：
      1. 所有模块可正常导入
      2. MCP 服务器可创建
      3. 所有工具已注册（无重复）
      4. 模拟模式下可完成完整工作流：
         list_devices → list_processes → attach → hook → list_hooks → close
      5. Hook 沙箱可正常包装脚本
      6. 配置项可正常读取

    Returns:
        0 表示全部通过，1 表示有失败项
    """
    import json
    from .utils.hook_sandbox import validate_script, wrap_script_safely

    # 强制启用模拟模式
    os.environ["FRIDAMCP_MOCK_DEVICE"] = "1"

    results = []
    passed = 0
    failed = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, failed
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        line = f"  [{status}] {name}"
        if detail:
            line += f" - {detail}"
        print(line)
        results.append((name, ok, detail))

    print("\n" + "=" * 60)
    print("FridaMCP Self-Test")
    print("=" * 60)

    # 1. 导入测试
    print("\n[1/6] Module imports...")
    try:
        import fridamcp
        import fridamcp.config
        import fridamcp.server
        import fridamcp.core.session_manager
        import fridamcp.core.frida_client
        import fridamcp.core.device_manager
        import fridamcp.core.mock_device
        import fridamcp.modules.process
        import fridamcp.modules.hook
        import fridamcp.modules.memory
        import fridamcp.modules.network
        import fridamcp.modules.filesystem
        import fridamcp.modules.ui_automation
        import fridamcp.modules.crypto
        import fridamcp.modules.log
        import fridamcp.modules.script
        import fridamcp.utils.hook_sandbox
        import fridamcp.utils.apk_injector
        import fridamcp.utils.logger
        check("All modules import", True)
    except Exception as e:
        check("All modules import", False, str(e))
        print("\n" + "=" * 60)
        print(f"SELF-TEST FAILED: {failed} failed, {passed} passed")
        print("=" * 60)
        return 1

    # 2. 服务器创建
    print("\n[2/6] MCP server creation...")
    try:
        mcp = create_mcp_server()
        check("create_mcp_server()", True)
    except Exception as e:
        check("create_mcp_server()", False, str(e))
        return 1

    # 3. 工具注册
    print("\n[3/6] Tool registration...")
    try:
        loop = asyncio.new_event_loop()
        tools = loop.run_until_complete(mcp.list_tools())
        check(f"Tools registered ({len(tools)})", len(tools) > 0, f"{len(tools)} tools")
        # 检查重复
        names = [t.name for t in tools]
        from collections import Counter
        dupes = {n: c for n, c in Counter(names).items() if c > 1}
        check("No duplicate tools", len(dupes) == 0, str(dupes) if dupes else "")
    except Exception as e:
        check("Tool registration", False, str(e))

    # 4. 模拟设备工作流
    print("\n[4/6] Mock device workflow...")
    try:
        async def _workflow():
            # list_devices
            r = await mcp.call_tool("list_devices", {})
            content = r[0] if isinstance(r, tuple) else r
            data = json.loads(content[0].text)
            assert len(data) > 0, "no devices"
            # list_processes
            r = await mcp.call_tool("list_processes", {})
            content = r[0] if isinstance(r, tuple) else r
            procs = json.loads(content[0].text)
            assert len(procs) > 0, "no processes"
            # attach
            r = await mcp.call_tool("attach_process", {"target": "com.example.targetapp"})
            content = r[0] if isinstance(r, tuple) else r
            attach_data = json.loads(content[0].text)
            sid = attach_data["session_id"]
            # hook
            r = await mcp.call_tool("hook_method", {
                "session_id": sid,
                "class_name": "com.example.Login",
                "method_name": "check",
            })
            content = r[0] if isinstance(r, tuple) else r
            hook_data = json.loads(content[0].text)
            assert "hook_id" in hook_data, f"no hook_id: {hook_data}"
            assert "sandbox_id" in hook_data, f"no sandbox_id: {hook_data}"
            # list_hooks
            r = await mcp.call_tool("list_hooks", {"session_id": sid})
            content = r[0] if isinstance(r, tuple) else r
            hooks = json.loads(content[0].text)
            assert len(hooks) > 0, "no hooks"
            # close
            r = await mcp.call_tool("close_session", {"session_id": sid, "force": True})
            return sid
        loop.run_until_complete(_workflow())
        check("list_devices → attach → hook → list_hooks → close", True)
        loop.close()
    except Exception as e:
        check("Mock workflow", False, str(e))

    # 5. Hook 沙箱
    print("\n[5/6] Hook sandbox...")
    try:
        # valid script
        valid = 'Java.perform(function(){ send({type:"test"}); });'
        is_valid, errors, warnings = validate_script(valid)
        check("Valid script passes", is_valid, f"errors={errors}")
        # dangerous
        dangerous = "Process.kill(0);"
        is_valid, errors, warnings = validate_script(dangerous)
        check("Dangerous API warning", len(warnings) > 0, f"warnings={warnings}")
        # wrap
        wrapped = wrap_script_safely(valid)
        check("Sandbox wrap produces try-catch", "try" in wrapped and "catch" in wrapped)
    except Exception as e:
        check("Hook sandbox", False, str(e))

    # 6. 配置
    print("\n[6/6] Configuration...")
    try:
        check("MCP_TRANSPORT config", hasattr(config, "MCP_TRANSPORT"))
        check("SESSION_IDLE_TIMEOUT config", hasattr(config, "SESSION_IDLE_TIMEOUT"))
        check("SESSION_LOCK_TIMEOUT config", hasattr(config, "SESSION_LOCK_TIMEOUT"))
        check("MAX_SESSIONS config", hasattr(config, "MAX_SESSIONS"))
    except Exception as e:
        check("Configuration", False, str(e))

    # 清理
    session_manager.close_all()

    print("\n" + "=" * 60)
    print(f"SELF-TEST RESULT: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL CHECKS PASSED")
    else:
        print(f"{failed} CHECK(S) FAILED")
    print("=" * 60 + "\n")
    return 0 if failed == 0 else 1


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
        choices=["stdio", "sse", "http"],
        default=config.MCP_TRANSPORT,
        help=(
            "Transport type (default: stdio). "
            "stdio: local tool standard (Claude Desktop/Cursor), lowest latency. "
            "sse: remote via Server-Sent Events. "
            "http: remote via Streamable HTTP."
        ),
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
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock device (no real Android device needed, for testing/CI)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test (verify imports, tool registration, mock workflow) and exit",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List all registered MCP tools and exit",
    )

    args = parser.parse_args()

    # 模拟模式
    if args.mock:
        os.environ["FRIDAMCP_MOCK_DEVICE"] = "1"

    # 初始化日志
    setup_logging()

    # 自测模式
    if args.self_test:
        sys.exit(run_self_test())

    # 列出工具模式
    if args.list_tools:
        mcp = create_mcp_server()
        asyncio.run(_print_tools(mcp))
        sys.exit(0)

    # 就地更新配置单例（其他模块已持有同一引用，会立即生效）
    config.update(
        MCP_HOST=args.host,
        MCP_PORT=args.port,
        LOG_LEVEL=args.log_level,
        FRIDA_DEVICE_TYPE=args.device_type,
        FRIDA_DEVICE_ID=args.device_id,
        SERVER_AUTO_RESTART_MAX=0 if args.no_auto_restart else None,
    )

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
