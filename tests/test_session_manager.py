"""
会话管理模块单元测试
"""
import time
import threading
import pytest
from fridamcp.core.session_manager import Session, SessionState, SessionManager
from fridamcp.core.mock_device import MockDevice, MockSession


class TestSession:
    """Session 类测试"""

    def test_session_initial_state(self):
        """新会话应为 CREATED 状态"""
        s = Session("test_id", 1234, "test_process")
        assert s.state == SessionState.CREATED
        assert s.pid == 1234
        assert s.name == "test_process"
        assert s._ref_count == 1  # 初始引用计数为 1

    def test_session_attach_changes_state(self):
        """attach 后状态应为 ATTACHED"""
        s = Session("test_id", 1234, "test_process")
        device = MockDevice()
        s.attach(device)
        assert s.state == SessionState.ATTACHED
        assert s.session is not None

    def test_session_touch_updates_time(self):
        """touch 应更新最后活动时间"""
        s = Session("test_id", 1234, "test_process")
        old_time = s.last_active_at
        time.sleep(0.01)
        s.touch()
        assert s.last_active_at > old_time

    def test_session_add_hook(self):
        """应能添加 hook"""
        s = Session("test_id", 1234, "test_process")
        s.add_hook("hook_1", {"type": "java_method"})
        info = s.get_info()
        assert "hook_1" in info["hooks"]

    def test_session_remove_hook(self):
        """应能移除 hook"""
        s = Session("test_id", 1234, "test_process")
        s.add_hook("hook_1", {"type": "java_method"})
        assert s.remove_hook("hook_1") is True
        info = s.get_info()
        assert "hook_1" not in info["hooks"]

    def test_session_remove_nonexistent_hook(self):
        """移除不存在的 hook 应返回 False"""
        s = Session("test_id", 1234, "test_process")
        assert s.remove_hook("nonexistent") is False

    def test_session_is_active_before_attach(self):
        """attach 前应不活跃"""
        s = Session("test_id", 1234, "test_process")
        assert s.is_active() is False

    def test_session_is_active_after_attach(self):
        """attach 后应活跃"""
        s = Session("test_id", 1234, "test_process")
        device = MockDevice()
        s.attach(device)
        assert s.is_active() is True

    def test_session_is_expired_default(self):
        """新会话不应超时"""
        s = Session("test_id", 1234, "test_process")
        device = MockDevice()
        s.attach(device)
        assert s.is_expired() is False

    def test_session_get_info(self):
        """get_info 应返回完整信息"""
        s = Session("test_id", 1234, "test_process")
        info = s.get_info()
        assert info["id"] == "test_id"
        assert info["pid"] == 1234
        assert info["name"] == "test_process"
        assert info["state"] == "created"
        assert "created_at" in info
        assert "scripts" in info
        assert "hooks" in info
        assert "ref_count" in info
        assert "idle_seconds" in info


class TestSessionManager:
    """SessionManager 类测试"""

    def test_singleton(self):
        """SessionManager 应为单例"""
        m1 = SessionManager.get_instance()
        m2 = SessionManager.get_instance()
        assert m1 is m2

    def test_get_status(self):
        """get_status 应返回状态字典"""
        mgr = SessionManager.get_instance()
        status = mgr.get_status()
        assert "total_sessions" in status
        assert "active_sessions" in status
        assert "max_sessions" in status
        assert "idle_timeout" in status
        assert "keepalive_interval" in status
        assert "keepalive_running" in status
