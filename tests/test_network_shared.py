"""network 捕获共享层测试（GUI/MCP 一致性 + 死缓冲回归）

背景：GUI 此前直接操作 network 模块私有 _capture_buffer——
一个从无写入方的死缓冲，导致 GUI 网络监控永远显示"无捕获数据"。
数据本体经 frida send() 进入会话消息缓冲，由共享 impl 读取。
"""
from unittest.mock import patch

import pytest

from fridamcp.modules import network as net_mod
from fridamcp.modules.network import (
    get_capture_impl,
    start_capture_impl,
    stop_capture_impl,
    NETWORK_MSG_TYPES,
)


class FakeFridaClient:
    def __init__(self, messages=None):
        self._messages = messages or []
        self.scripts = []

    def execute_script(self, session_id, source, script_name=None):
        self.scripts.append((session_id, source, script_name))
        return {"script_id": f"scr_{len(self.scripts)}"}

    def get_messages(self, session_id, clear=False):
        return self._messages


def test_network_msg_types_defined():
    assert "ssl_write" in NETWORK_MSG_TYPES
    assert "socket_recv" in NETWORK_MSG_TYPES


def test_get_capture_impl_filters_network_msgs():
    fc = FakeFridaClient(messages=[
        {"message": {"type": "ssl_write", "data": "hello", "size": 5}},
        {"message": {"type": "java_method", "args": []}},   # 非网络消息
        {"message": {"type": "socket_connect", "ip": "1.2.3.4", "port": 443}},
    ])
    with patch.object(net_mod, "frida_client", fc):
        caps = get_capture_impl("s1")
    assert len(caps) == 2
    assert caps[0]["type"] == "ssl_write"
    assert caps[1]["ip"] == "1.2.3.4"


def test_get_capture_impl_filter_type():
    fc = FakeFridaClient(messages=[
        {"message": {"type": "ssl_write", "data": "a"}},
        {"message": {"type": "ssl_read", "data": "b"}},
    ])
    with patch.object(net_mod, "frida_client", fc):
        caps = get_capture_impl("s1", filter_type="ssl_read")
    assert len(caps) == 1 and caps[0]["type"] == "ssl_read"


def test_start_capture_impl_hooks():
    fc = FakeFridaClient()
    with patch.object(net_mod, "frida_client", fc):
        result = start_capture_impl("s1", capture_ssl=True, capture_socket=True)
    assert "error" not in result
    assert len(fc.scripts) == 2  # SSL + Socket 两个脚本
    assert net_mod._capture_active.get("s1") is True

    with patch.object(net_mod, "frida_client", fc):
        stop_capture_impl("s1")
    assert "s1" not in net_mod._capture_active


def test_stop_capture_counts_from_messages():
    """停止时的 captured_count 必须来自会话消息（旧实现读死缓冲恒 0）"""
    fc = FakeFridaClient(messages=[
        {"message": {"type": "ssl_write", "data": "x"}},
        {"message": {"type": "ssl_read", "data": "y"}},
        {"message": {"type": "java_method"}},  # 不计入
    ])
    with patch.object(net_mod, "frida_client", fc):
        result = stop_capture_impl("s1")
    assert result["captured_count"] == 2


def test_mcp_closure_delegates():
    """MCP 闭包必须透传到共享实现（防再分叉）"""
    from tests.test_tools import FakeMCP

    mcp = FakeMCP()
    net_mod.register_tools(mcp)

    fc = FakeFridaClient()
    with patch.object(net_mod, "frida_client", fc), \
         patch.object(net_mod, "start_capture_impl", wraps=net_mod.start_capture_impl) as spy:
        mcp.tools["start_capture"]("s1", capture_ssl=False)
    spy.assert_called_once()

    # 闭包工具集完整性
    for name in ("start_capture", "stop_capture", "get_capture", "hook_ssl"):
        assert name in mcp.tools, f"工具 {name} 缺失"


def test_gui_uses_shared_impl():
    """GUI 路径（app.py）必须走共享实现——死缓冲回归"""
    pytest.importorskip("gradio", reason="GUI shell tests require gradio")
    import app

    fc = FakeFridaClient(messages=[
        {"message": {"type": "ssl_write", "data": "GET /api"}},
    ])
    with patch.object(net_mod, "frida_client", fc):
        out = app.get_network_capture("s1")
    assert "[SSL→]" in out, out
    assert "GET /api" in out

    # 无数据时给出明确提示（而非空字符串/异常）
    empty = FakeFridaClient()
    with patch.object(net_mod, "frida_client", empty):
        out2 = app.get_network_capture("s_none")
    assert out2 == "无捕获数据"
