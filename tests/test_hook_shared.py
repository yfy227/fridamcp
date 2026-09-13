"""GUI 与 MCP 共享实现层测试（模板填充回归）

背景：hook 模板协议改为 JSON 字面量注入时只改了 MCP 侧，
app.py 的 GUI 复制品仍用裸 % 填充 → 生成无引号的非法 JS，
GUI 的 Hook 功能整体损坏。本测试验证两条路径共用同一实现
且恶意输入下 JS 语法合法。
"""
import subprocess
import shutil
from unittest.mock import patch

import pytest

from fridamcp.modules import hook as hook_mod
from fridamcp.modules.hook import (
    hook_java_method_impl,
    hook_native_impl,
    trace_method_impl,
)

NODE = shutil.which("node")

EVIL = 'com.x"; process.kill()'


class FakeFridaClient:
    """捕获注入的脚本源码；模拟无活动会话"""

    def __init__(self):
        self.sources = []

    def execute_script(self, session_id, source, script_name=None):
        self.sources.append(source)
        return {"script_id": f"scr_{len(self.sources)}"}


@pytest.fixture()
def fake_client():
    fc = FakeFridaClient()
    with patch.object(hook_mod, "frida_client", fc):
        yield fc


def node_check(js: str):
    if NODE is None:
        pytest.skip("node not available")
    p = subprocess.run([NODE, "--check"], input=js.encode(), capture_output=True)
    assert p.returncode == 0, f"invalid JS:\n{p.stderr.decode()[:300]}\n{js[:200]}"


def test_impl_java_hook_valid_js(fake_client):
    result = hook_java_method_impl("s1", EVIL, EVIL)
    assert "error" not in result
    assert len(fake_client.sources) == 1
    node_check(fake_client.sources[0])


def test_impl_native_hook_valid_js(fake_client):
    result = hook_native_impl("s1", EVIL, EVIL, offset=4096)
    assert "error" not in result
    node_check(fake_client.sources[0])


def test_impl_trace_valid_js(fake_client):
    result = trace_method_impl("s1", EVIL)
    assert "error" not in result
    node_check(fake_client.sources[0])


def test_mcp_tool_uses_shared_impl():
    """MCP 工具闭包必须是共享实现的薄壳（防再分叉）"""
    from tests.test_tools import FakeMCP  # 复用通用 FakeMCP

    mcp = FakeMCP()
    hook_mod.register_tools(mcp)

    calls = []
    real_impl = hook_mod.hook_java_method_impl

    def spy(session_id, class_name, method_name):
        calls.append((session_id, class_name, method_name))
        return real_impl(session_id, class_name, method_name)

    fc = FakeFridaClient()
    with patch.object(hook_mod, "frida_client", fc), \
         patch.object(hook_mod, "hook_java_method_impl", spy):
        r1 = mcp.tools["hook_method"]("s1", "a.b.C", "run")

    assert calls == [("s1", "a.b.C", "run")], "MCP 工具未透传到共享实现"
    assert "error" not in r1
    assert r1["class_name"] == "a.b.C"


def test_gui_uses_shared_impl(fake_client):
    """GUI 路径（app.py）必须走共享实现——裸 % 填充回归"""
    import app  # noqa: F401  (gradio 依赖较重，仅此处 import)

    out = app.hook_java_method("s1", "com.example.App", "check")
    assert out.startswith("✅"), out
    assert len(fake_client.sources) == 1
    node_check(fake_client.sources[0])

    out2 = app.hook_native_func("s1", "libnative.so", "Java_fn", 0)
    assert out2.startswith("✅"), out2
    node_check(fake_client.sources[1])


def test_gui_reports_errors(fake_client):
    """共享实现抛错时 GUI 给出 ❌ 前缀而非 traceback"""
    import app

    def boom(*a, **kw):
        raise RuntimeError("device gone")

    with patch.object(hook_mod, "frida_client", boom):
        # impl 内部 except 捕获后返回 error dict
        out = app.hook_java_method("s1", "a.b.C", "m")
    assert out.startswith("❌"), out
