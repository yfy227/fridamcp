#!/usr/bin/env python3
"""
FridaMCP 桌面独立应用

以原生桌面窗口运行 FridaMCP，无需终端、无需浏览器地址栏：

    python desktop_app.py            # 打开原生应用窗口（内部自动启动 GUI + MCP）

能力：
- 内部启动 Gradio GUI 与 MCP 服务器（默认全功能，无参数）
- 有 pywebview 时使用原生窗口（Windows: WebView2 / macOS: WKWebView /
  Linux: GTK），拥有独立任务栏图标与窗口标题
- 无 pywebview / 无图形环境时自动降级为系统浏览器
- 关闭窗口即干净退出（MCP 停止、会话清理）

可选依赖：
    pip install pywebview          # 原生窗口（强烈推荐）

打包为单文件可执行（见 build_desktop.sh）：
    pyinstaller fridamcp_desktop.spec
"""

import argparse
import os
import sys
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import webview  # pywebview

    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False

import app as gui_app  # noqa: E402  复用 create_app / MCP 生命周期管理


def run_desktop(
    host: str = "127.0.0.1",
    port: int = 7860,
    start_mcp: bool = True,
    mcp_port: int = 8768,
    device_type: str = "usb",
    start_rest: bool = True,
    rest_port: int = 8770,
) -> int:
    """以独立应用形态运行 FridaMCP，返回进程退出码"""

    os.environ["FRIDA_DEVICE_TYPE"] = device_type
    gui_app.setup_logging()

    # ---- REST API（供 Android 原生 App 连接）----
    if start_rest:
        from fridamcp.rest_api import start_rest_background
        start_rest_background(port=rest_port)

    # ---- 内部启动 MCP 服务器（独立应用默认全功能）----
    if start_mcp:
        gui_app.start_mcp_server_background(port=mcp_port)

    # ---- 启动 GUI 服务器（不锁线程，稍后注册 PWA 路由）----
    gradio_app = gui_app.create_app()
    launch_kwargs = dict(
        server_name=host,
        server_port=port,
        share=False,
        inbrowser=False,  # 我们自己管理窗口/浏览器
        favicon_path=os.path.join(PROJECT_ROOT, "static", "icon-192.png"),
        prevent_thread_lock=True,
    )
    if gui_app._GRADIO_MAJOR >= 6:
        launch_kwargs.update(theme=gui_app.GUI_THEME, css=gui_app.GUI_CSS)
    launch_result = gradio_app.launch(**launch_kwargs)

    fastapi_app = launch_result[0] if isinstance(launch_result, tuple) else None
    if fastapi_app is not None:
        gui_app._register_pwa_routes(fastapi_app)

    url = f"http://{host}:{port}"

    def _shutdown(code: int = 0) -> int:
        """干净退出：停 MCP、关会话"""
        try:
            if start_mcp:
                gui_app.stop_mcp_server()
            else:
                from fridamcp.core.session_manager import session_manager

                session_manager.close_all()
        except Exception:
            pass
        return code

    use_window = HAS_WEBVIEW and os.environ.get("FRIDAMCP_NO_WINDOW") != "1"

    if use_window:
        try:
            webview.create_window(
                title="FridaMCP - Android Frida 动态分析平台",
                url=url,
                width=1280,
                height=860,
                min_size=(420, 640),  # 移动端尺寸也能开
                text_select=True,
            )
            # 阻塞直到窗口关闭
            webview.start()
            print("FridaMCP window closed, shutting down")
            return _shutdown(0)
        except Exception as e:
            # 无头/无 GUI backend 环境：降级为系统浏览器
            print(f"native window unavailable ({e}), falling back to browser")

    # ---- 降级路径：系统浏览器 ----
    print(f"FridaMCP running at {url} (browser mode)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        gradio_app.block_thread()
    except (KeyboardInterrupt, OSError):
        pass
    return _shutdown(0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FridaMCP 桌面独立应用（原生窗口，内部集成 GUI + MCP）"
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="监听地址（默认 127.0.0.1；局域网访问用 0.0.0.0）",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=7860,
        help="GUI 端口（默认 7860）",
    )
    parser.add_argument(
        "--no-mcp", action="store_true",
        help="不启动内置 MCP 服务器（默认启动，端口 8768）",
    )
    parser.add_argument(
        "--mcp-port", type=int, default=8768,
        help="MCP 服务器端口（默认 8768）",
    )
    parser.add_argument(
        "--device-type", default="usb",
        choices=["usb", "remote", "local"],
        help="Frida 设备类型（默认 usb）",
    )
    args = parser.parse_args()
    sys.exit(
        run_desktop(
            host=args.host,
            port=args.port,
            start_mcp=not args.no_mcp,
            mcp_port=args.mcp_port,
            device_type=args.device_type,
        )
    )


if __name__ == "__main__":
    main()
