"""
Hook 沙箱模块单元测试
"""
import pytest
from fridamcp.utils.hook_sandbox import (
    validate_script,
    wrap_script_safely,
    extract_sandbox_errors,
    is_sandbox_ready,
)


class TestValidateScript:
    """脚本静态校验测试"""

    def test_valid_script_passes(self):
        """合法脚本应通过校验"""
        source = 'Java.perform(function(){ send({type:"test"}); });'
        is_valid, errors, warnings = validate_script(source)
        assert is_valid is True
        assert len(errors) == 0

    def test_empty_script_fails(self):
        """空脚本应校验失败"""
        is_valid, errors, warnings = validate_script("")
        assert is_valid is False
        assert len(errors) > 0

    def test_dangerous_process_kill_warns(self):
        """Process.kill 应产生警告"""
        source = "Process.kill(0);"
        is_valid, errors, warnings = validate_script(source)
        assert is_valid is True  # 警告不阻断
        assert len(warnings) > 0
        assert any("Process.kill" in w for w in warnings)

    def test_dangerous_backtracer_warns(self):
        """Backtracer.ACCURATE 应产生警告"""
        source = 'Thread.backtrace(this.context, Backtracer.ACCURATE);'
        is_valid, errors, warnings = validate_script(source)
        assert is_valid is True
        assert len(warnings) > 0

    def test_forbidden_infinite_loop_errors(self):
        """无 sleep 的无限循环应报错"""
        source = "while(true){ doSomething(); }"
        is_valid, errors, warnings = validate_script(source)
        assert is_valid is False
        assert len(errors) > 0

    def test_returns_tuple(self):
        """应返回三元组"""
        result = validate_script("test")
        assert len(result) == 3
        is_valid, errors, warnings = result
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestWrapScriptSafely:
    """脚本沙箱包装测试"""

    def test_wrap_returns_string(self):
        """包装后应返回字符串"""
        wrapped = wrap_script_safely("send({type:'test'});")
        assert isinstance(wrapped, str)

    def test_wrap_contains_try_catch(self):
        """包装后应包含 try-catch"""
        wrapped = wrap_script_safely("send({type:'test'});")
        assert "try" in wrapped
        assert "catch" in wrapped

    def test_wrap_contains_sandbox_id(self):
        """包装后应包含 sandbox_id"""
        wrapped = wrap_script_safely("test", sandbox_id="test_sbx_123")
        assert "test_sbx_123" in wrapped

    def test_wrap_generates_unique_id(self):
        """未指定 sandbox_id 时应自动生成"""
        w1 = wrap_script_safely("code1")
        w2 = wrap_script_safely("code2")
        # 两个包装应包含不同的 sandbox_id
        assert w1 != w2

    def test_wrap_preserves_user_code(self):
        """包装后应保留用户代码"""
        user_code = 'send({type:"my_unique_marker"});'
        wrapped = wrap_script_safely(user_code)
        assert "my_unique_marker" in wrapped

    def test_wrap_contains_send_error(self):
        """包装后应包含错误上报逻辑"""
        wrapped = wrap_script_safely("test")
        assert "sandbox_error" in wrapped


class TestExtractSandboxErrors:
    """沙箱错误提取测试"""

    def test_extract_sandbox_error(self):
        """应能提取 sandbox_error 类型消息"""
        messages = [
            {"message": {"type": "sandbox_error", "error": "test error"}},
        ]
        errors = extract_sandbox_errors(messages)
        assert len(errors) == 1
        assert errors[0]["error"] == "test error"

    def test_extract_sandbox_error_limit(self):
        """应能提取 sandbox_error_limit 类型消息"""
        messages = [
            {"message": {"type": "sandbox_error_limit", "count": 100}},
        ]
        errors = extract_sandbox_errors(messages)
        assert len(errors) == 1

    def test_extract_empty_messages(self):
        """空消息列表应返回空列表"""
        assert extract_sandbox_errors([]) == []

    def test_extract_no_sandbox_messages(self):
        """无沙箱消息时应返回空列表"""
        messages = [
            {"message": {"type": "other"}},
            {"message": {"type": "crypto_doFinal"}},
        ]
        assert extract_sandbox_errors(messages) == []


class TestIsSandboxReady:
    """沙箱就绪检查测试"""

    def test_ready_message_present(self):
        """存在 ready 消息时应返回 True"""
        messages = [
            {"message": {"type": "sandbox_ready", "sandbox_id": "sbx1"}},
        ]
        assert is_sandbox_ready(messages, "sbx1") is True

    def test_ready_message_absent(self):
        """不存在 ready 消息时应返回 False"""
        messages = [
            {"message": {"type": "other"}},
        ]
        assert is_sandbox_ready(messages, "sbx1") is False

    def test_ready_wrong_sandbox_id(self):
        """sandbox_id 不匹配时应返回 False"""
        messages = [
            {"message": {"type": "sandbox_ready", "sandbox_id": "sbx2"}},
        ]
        assert is_sandbox_ready(messages, "sbx1") is False
