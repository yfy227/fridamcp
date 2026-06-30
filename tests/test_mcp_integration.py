"""
MCP 服务器集成测试

验证完整的 MCP 工具调用链路：
  - 服务器创建
  - 工具注册（无重复）
  - 工具调用（模拟模式下的完整工作流）

所有测试在模拟模式下运行，无需真实 Android 设备。
"""
import os
import json
import asyncio
import pytest
from collections import Counter

# 确保模拟模式
os.environ["FRIDAMCP_MOCK_DEVICE"] = "1"

from fridamcp.server import create_mcp_server
from fridamcp.core.session_manager import session_manager


@pytest.fixture
def mcp_server():
    """创建 MCP 服务器实例"""
    return create_mcp_server()


@pytest.fixture
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _extract_text(result):
    """从 call_tool 返回值中提取文本（拼接所有 content 项）"""
    content = result[0] if isinstance(result, tuple) else result
    if isinstance(content, list) and len(content) > 0:
        return "\n".join(c.text for c in content)
    return str(content)


def _extract_json(result):
    """从 call_tool 返回值中提取并解析 JSON

    MCP 框架对列表返回值会拆分为多个 TextContent，
    每个 TextContent 是一个 JSON 对象。此函数将它们重新组装为列表。
    """
    content = result[0] if isinstance(result, tuple) else result
    if not isinstance(content, list) or len(content) == 0:
        return None
    if len(content) == 1:
        return json.loads(content[0].text)
    # 多个 content 项 = 列表返回值
    return [json.loads(c.text) for c in content]


class TestServerCreation:
    """服务器创建测试"""

    def test_create_server(self, mcp_server):
        """应能创建服务器"""
        assert mcp_server is not None

    def test_server_has_name(self, mcp_server):
        """服务器应有名称"""
        assert mcp_server.name is not None


class TestToolRegistration:
    """工具注册测试"""

    def test_tools_registered(self, mcp_server, event_loop):
        """应注册至少 50 个工具"""
        async def _test():
            tools = await mcp_server.list_tools()
            assert len(tools) >= 50
        event_loop.run_until_complete(_test())

    def test_no_duplicate_tools(self, mcp_server, event_loop):
        """不应有重复工具名"""
        async def _test():
            tools = await mcp_server.list_tools()
            names = [t.name for t in tools]
            dupes = {n: c for n, c in Counter(names).items() if c > 1}
            assert len(dupes) == 0, f"Duplicate tools: {dupes}"
        event_loop.run_until_complete(_test())

    def test_expected_tools_present(self, mcp_server, event_loop):
        """关键工具应存在"""
        async def _test():
            tools = await mcp_server.list_tools()
            names = {t.name for t in tools}
            expected = [
                "list_devices", "list_processes", "attach_process",
                "hook_method", "hook_native", "run_hook_script",
                "validate_hook_script", "hook_crypto", "hook_native_crypto",
                "bypass_ssl_pinning", "session_manager_status",
                "list_sessions", "close_session", "get_session_info",
            ]
            missing = [e for e in expected if e not in names]
            assert len(missing) == 0, f"Missing tools: {missing}"
        event_loop.run_until_complete(_test())


class TestDeviceWorkflow:
    """设备工作流测试"""

    def test_list_devices(self, mcp_server, event_loop):
        """list_devices 应返回设备列表"""
        async def _test():
            r = await mcp_server.call_tool("list_devices", {})
            data = _extract_json(r)
            # 模拟模式下返回单个设备（dict）或列表
            if isinstance(data, list):
                assert len(data) > 0
                assert "id" in data[0]
                assert "name" in data[0]
            else:
                assert "id" in data
                assert "name" in data
        event_loop.run_until_complete(_test())

    def test_list_processes(self, mcp_server, event_loop):
        """list_processes 应返回进程列表"""
        async def _test():
            r = await mcp_server.call_tool("list_processes", {})
            data = _extract_json(r)
            assert isinstance(data, list)
            assert len(data) > 0
            assert "pid" in data[0]
            assert "name" in data[0]
        event_loop.run_until_complete(_test())

    def test_session_manager_status(self, mcp_server, event_loop):
        """session_manager_status 应返回状态"""
        async def _test():
            r = await mcp_server.call_tool("session_manager_status", {})
            data = _extract_json(r)
            assert "total_sessions" in data
            assert "active_sessions" in data
            assert "max_sessions" in data
        event_loop.run_until_complete(_test())


class TestSessionWorkflow:
    """会话工作流测试"""

    def test_attach_and_close(self, mcp_server, event_loop):
        """attach → close 完整流程"""
        async def _test():
            r = await mcp_server.call_tool("attach_process", {
                "target": "com.example.targetapp"
            })
            data = _extract_json(r)
            sid = data["session_id"]
            assert sid.startswith("sess_")
            # list_sessions
            r = await mcp_server.call_tool("list_sessions", {})
            sessions_text = _extract_text(r)
            assert sid in sessions_text
            # close
            r = await mcp_server.call_tool("close_session", {
                "session_id": sid, "force": True
            })
            close_data = _extract_json(r)
            assert close_data["success"] is True
        event_loop.run_until_complete(_test())

    def test_get_session_info(self, mcp_server, event_loop):
        """get_session_info 应返回会话详情"""
        async def _test():
            r = await mcp_server.call_tool("attach_process", {
                "target": "com.example.targetapp"
            })
            sid = _extract_json(r)["session_id"]
            r = await mcp_server.call_tool("get_session_info", {
                "session_id": sid
            })
            info = _extract_json(r)
            assert info["id"] == sid
            assert info["state"] == "attached"
            await mcp_server.call_tool("close_session", {
                "session_id": sid, "force": True
            })
        event_loop.run_until_complete(_test())


class TestHookWorkflow:
    """Hook 工作流测试"""

    def test_hook_method_sandboxed(self, mcp_server, event_loop):
        """hook_method 应返回 sandbox_id"""
        async def _test():
            r = await mcp_server.call_tool("attach_process", {
                "target": "com.example.targetapp"
            })
            sid = _extract_json(r)["session_id"]
            r = await mcp_server.call_tool("hook_method", {
                "session_id": sid,
                "class_name": "com.example.Login",
                "method_name": "check",
            })
            data = _extract_json(r)
            assert "hook_id" in data
            assert "sandbox_id" in data
            await mcp_server.call_tool("close_session", {
                "session_id": sid, "force": True
            })
        event_loop.run_until_complete(_test())

    def test_run_hook_script(self, mcp_server, event_loop):
        """run_hook_script 应加载自定义脚本"""
        async def _test():
            r = await mcp_server.call_tool("attach_process", {
                "target": "com.example.targetapp"
            })
            sid = _extract_json(r)["session_id"]
            r = await mcp_server.call_tool("run_hook_script", {
                "session_id": sid,
                "script_source": 'Java.perform(function(){ send({type:"test"}); });',
            })
            data = _extract_json(r)
            assert "script_id" in data
            assert "sandbox_id" in data
            await mcp_server.call_tool("close_session", {
                "session_id": sid, "force": True
            })
        event_loop.run_until_complete(_test())

    def test_validate_hook_script(self, mcp_server, event_loop):
        """validate_hook_script 应返回校验结果"""
        async def _test():
            r = await mcp_server.call_tool("validate_hook_script", {
                "script_source": 'send({type:"test"});'
            })
            data = _extract_json(r)
            assert "is_valid" in data
            assert "errors" in data
            assert "warnings" in data
        event_loop.run_until_complete(_test())


class TestCryptoWorkflow:
    """加密模块测试"""

    def test_hook_crypto(self, mcp_server, event_loop):
        """hook_crypto 应能加载"""
        async def _test():
            r = await mcp_server.call_tool("attach_process", {
                "target": "com.example.targetapp"
            })
            sid = _extract_json(r)["session_id"]
            r = await mcp_server.call_tool("hook_crypto", {
                "session_id": sid
            })
            data = _extract_json(r)
            assert "hook_id" in data
            await mcp_server.call_tool("close_session", {
                "session_id": sid, "force": True
            })
        event_loop.run_until_complete(_test())

    def test_hook_native_crypto(self, mcp_server, event_loop):
        """hook_native_crypto 应能加载"""
        async def _test():
            r = await mcp_server.call_tool("attach_process", {
                "target": "com.example.targetapp"
            })
            sid = _extract_json(r)["session_id"]
            r = await mcp_server.call_tool("hook_native_crypto", {
                "session_id": sid
            })
            data = _extract_json(r)
            assert "hook_id" in data
            await mcp_server.call_tool("close_session", {
                "session_id": sid, "force": True
            })
        event_loop.run_until_complete(_test())
