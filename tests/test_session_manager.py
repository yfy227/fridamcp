"""会话管理器测试：死锁回归与单例行为

回归背景：Session._lock 原为 threading.Lock，
unload_all_scripts() 持锁调用 unload_script()（二次加锁），
导致所有 close_session/close_all 永久挂死。
"""
import threading
import time

from fridamcp.core.session_manager import Session, SessionManager


class FakeScript:
    """替代 frida.core.Script 的桩对象"""

    def __init__(self):
        self.unloaded = 0

    def unload(self):
        self.unloaded += 1


def _make_session() -> Session:
    s = Session("sess_test", 12345, "com.test.app")
    s.scripts["scr_a"] = FakeScript()
    s.scripts["scr_b"] = FakeScript()
    return s


def test_unload_all_scripts_no_deadlock():
    """RLock 回归：持锁调用 unload_script 不得死锁"""
    s = _make_session()
    watchdog = threading.Thread(target=s.unload_all_scripts, daemon=True)
    watchdog.start()
    watchdog.join(timeout=5)
    assert not watchdog.is_alive(), (
        "unload_all_scripts() 死锁——_lock 应为 threading.RLock"
    )
    assert len(s.scripts) == 0


def test_unload_script_then_all_no_deadlock():
    s = _make_session()
    watchdog = threading.Thread(
        target=lambda: (s.unload_script("scr_a"), s.unload_all_scripts()),
        daemon=True,
    )
    watchdog.start()
    watchdog.join(timeout=5)
    assert not watchdog.is_alive(), "unload_script + unload_all_scripts 死锁"


def test_detach_cleans_scripts():
    s = _make_session()
    watchdog = threading.Thread(target=s.detach, daemon=True)
    watchdog.start()
    watchdog.join(timeout=5)
    assert not watchdog.is_alive(), "detach() 死锁"
    assert s.state is not None


def test_session_manager_singleton():
    a = SessionManager.get_instance()
    b = SessionManager()
    assert a is b


def test_session_manager_new_thread_safe():
    """并发首次实例化只产生一个单例（__new__ 类锁回归）"""
    results = []

    def make():
        results.append(SessionManager())

    threads = [threading.Thread(target=make) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert all(r is results[0] for r in results), "并发实例化产生了多个单例"
