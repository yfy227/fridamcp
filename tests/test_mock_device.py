"""
模拟设备模块单元测试
"""
import pytest
from fridamcp.core.mock_device import (
    MockDevice,
    MockSession,
    MockScript,
    MockProcess,
    MOCK_PROCESSES,
    get_mock_device,
    is_mock_mode,
)


class TestMockProcess:
    """MockProcess 测试"""

    def test_attributes(self):
        """MockProcess 应有 pid 和 name 属性"""
        p = MockProcess(1234, "com.test.app")
        assert p.pid == 1234
        assert p.name == "com.test.app"

    def test_repr(self):
        """repr 应包含 pid 和 name"""
        p = MockProcess(1234, "com.test.app")
        r = repr(p)
        assert "1234" in r
        assert "com.test.app" in r


class TestMockScript:
    """MockScript 测试"""

    def test_script_load(self):
        """脚本加载后 is_destroyed 应为 False"""
        s = MockScript("send({type:'test'});", "test_script")
        assert s.is_destroyed is False

    def test_script_unload(self):
        """卸载后 is_destroyed 应为 True"""
        s = MockScript("send({type:'test'});", "test_script")
        s.unload()
        assert s.is_destroyed is True

    def test_script_id_unique(self):
        """每个脚本应有唯一 id"""
        s1 = MockScript("code1", "s1")
        s2 = MockScript("code2", "s2")
        assert s1.id != s2.id

    def test_script_message_handler(self):
        """应能设置消息处理器"""
        s = MockScript("send({type:'test'});", "test_script")
        received = []
        s.on("message", lambda msg, data: received.append(msg))
        s.load()
        import time
        time.sleep(0.1)  # 等待异步消息
        assert len(received) >= 1

    def test_script_eternalize(self):
        """eternalize 应不报错"""
        s = MockScript("code", "test")
        s.eternalize()  # 不应抛异常

    def test_script_post(self):
        """post 应不报错"""
        s = MockScript("code", "test")
        s.post({"type": "test"})  # 不应抛异常


class TestMockSession:
    """MockSession 测试"""

    def test_session_pid(self):
        """会话应有 pid"""
        s = MockSession(1234)
        assert s.pid == 1234

    def test_session_create_script(self):
        """应能创建脚本"""
        s = MockSession(1234)
        script = s.create_script("send({type:'test'});", "test")
        assert isinstance(script, MockScript)

    def test_session_detach_handler(self):
        """应能设置 detach 处理器"""
        s = MockSession(1234)
        called = []
        s.on("detached", lambda reason: called.append(reason))
        s.detach()
        assert len(called) == 1


class TestMockDevice:
    """MockDevice 测试"""

    def test_device_attributes(self):
        """设备应有 id/name/type 属性"""
        d = MockDevice()
        assert d.id is not None
        assert d.name is not None
        assert d.type is not None

    def test_enumerate_processes(self):
        """应返回进程列表"""
        d = MockDevice()
        procs = d.enumerate_processes()
        assert len(procs) > 0
        assert all(isinstance(p, MockProcess) for p in procs)

    def test_get_process_by_name(self):
        """应能按名称获取进程"""
        d = MockDevice()
        p = d.get_process("com.example.targetapp")
        assert p.name == "com.example.targetapp"

    def test_get_process_not_found(self):
        """不存在的进程应抛出 ValueError"""
        d = MockDevice()
        with pytest.raises(ValueError):
            d.get_process("nonexistent.process")

    def test_attach_by_pid(self):
        """应能按 pid attach"""
        d = MockDevice()
        s = d.attach(3456)
        assert isinstance(s, MockSession)
        assert s.pid == 3456

    def test_attach_by_name(self):
        """应能按名称 attach"""
        d = MockDevice()
        s = d.attach("com.example.targetapp")
        assert isinstance(s, MockSession)

    def test_attach_reuse_session(self):
        """同一 pid 的多次 attach 应复用会话"""
        d = MockDevice()
        s1 = d.attach(3456)
        s2 = d.attach(3456)
        assert s1 is s2

    def test_spawn(self):
        """spawn 应返回 pid"""
        d = MockDevice()
        pid = d.spawn("com.test.app")
        assert isinstance(pid, int)
        assert pid > 0

    def test_get_frontmost_application(self):
        """应返回前台应用"""
        d = MockDevice()
        app = d.get_frontmost_application()
        assert app is not None
        assert hasattr(app, "identifier")
        assert hasattr(app, "name")
        assert hasattr(app, "pid")


class TestMockModeDetection:
    """模拟模式检测测试"""

    def test_is_mock_mode_with_env(self, monkeypatch):
        """环境变量设置时应返回 True"""
        monkeypatch.setenv("FRIDAMCP_MOCK_DEVICE", "1")
        assert is_mock_mode() is True

    def test_is_mock_mode_without_env(self, monkeypatch):
        """环境变量未设置时应返回 False"""
        monkeypatch.delenv("FRIDAMCP_MOCK_DEVICE", raising=False)
        assert is_mock_mode() is False

    def test_get_mock_device_singleton(self):
        """get_mock_device 应返回单例"""
        d1 = get_mock_device()
        d2 = get_mock_device()
        assert d1 is d2
