"""桌面独立应用（desktop_app）测试

零 GUI 依赖：mock 掉 gradio launch/webview/browser，验证：
1. 模块可导入且不触发窗口逻辑
2. 降级路径：无 pywebview → 系统浏览器 + block_thread
3. 退出契约：关窗/退出时停止 MCP、注册 PWA 路由
"""
import os
from unittest.mock import MagicMock, patch

import pytest

gradio = pytest.importorskip("gradio", reason="desktop_app depends on app.py/gradio")

import desktop_app  # noqa: E402


class FakeBlocks:
    def launch(self, **kwargs):
        # 断言关键 launch 参数由 run_desktop 正确传递
        self.launch_kwargs = kwargs
        fake_fastapi = MagicMock()
        return (fake_fastapi, "http://127.0.0.1:7860", None)

    def block_thread(self):
        self.blocked = True


@pytest.fixture()
def fake_gui():
    blocks = FakeBlocks()
    with patch.object(desktop_app.gui_app, "create_app", return_value=blocks), \
         patch.object(desktop_app.gui_app, "start_mcp_server_background") as sm, \
         patch.object(desktop_app.gui_app, "stop_mcp_server") as stop, \
         patch.object(desktop_app.gui_app, "_register_pwa_routes") as routes, \
         patch.object(desktop_app.webbrowser, "open") as open_url:
        yield blocks, sm, stop, routes, open_url


def test_module_importable():
    assert hasattr(desktop_app, "run_desktop")
    assert hasattr(desktop_app, "main")


def test_fallback_browser_mode(fake_gui, monkeypatch):
    """无原生窗口环境 → 系统浏览器 + 干退出契约"""
    blocks, sm, stop, routes, open_url = fake_gui
    monkeypatch.setenv("FRIDAMCP_NO_WINDOW", "1")

    rc = desktop_app.run_desktop(start_mcp=True, port=7861)

    assert rc == 0
    sm.assert_called_once()                # MCP 已随应用内部启动
    stop.assert_called_once()              # 退出时停止 MCP
    routes.assert_called_once()            # PWA 路由已注册
    open_url.assert_called_once_with("http://127.0.0.1:7861")
    assert blocks.blocked is True          # 主线程生命周期正确
    assert blocks.launch_kwargs["inbrowser"] is False
    assert blocks.launch_kwargs["prevent_thread_lock"] is True
    assert blocks.launch_kwargs["server_port"] == 7861


def test_no_mcp_mode_cleans_sessions(fake_gui, monkeypatch):
    """--no-mcp 模式退出时清理会话而非调 stop_mcp_server"""
    blocks, sm, stop, routes, open_url = fake_gui
    monkeypatch.setenv("FRIDAMCP_NO_WINDOW", "1")

    from fridamcp.core.session_manager import session_manager
    with patch.object(session_manager, "close_all") as close_all:
        rc = desktop_app.run_desktop(start_mcp=False, port=7862)
        assert rc == 0
        stop.assert_not_called()
        close_all.assert_called_once()
