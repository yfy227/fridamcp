"""logcat 捕获生命周期测试（FakePopen 模式，零 adb 依赖）

覆盖背景（旧实现缺陷）：
1. stderr=PIPE 无人读取 → 管道缓冲写满后 adb 僵死
2. stop_log 先 pop buffer、reader 线程仍写入 → KeyError
3. 进程自然死亡后字典残留 → start_log 永远拒绝重启
4. Python 退出无 atexit 兜底 → 孤儿 adb logcat 进程
5. 并发 start 检查-启动竞态 → 双进程
"""
import io
import threading
from unittest.mock import patch

import pytest

from fridamcp.modules import log as log_mod
from fridamcp.modules.log import (
    _logcat_buffers,
    _logcat_lock,
    _logcat_processes,
    _logcat_threads,
)


class FakePopen:
    """模拟 subprocess.Popen：stdout 可迭代、terminate/wait/poll 可控"""

    def __init__(self, lines=(), immortal=False):
        self.stdout = io.StringIO("\n".join(lines) + "\n" if lines else "")
        self.terminated = False
        self.killed = False
        self._poll = None
        self._immortal = immortal  # 模拟不响应 terminate 的进程

    def terminate(self):
        self.terminated = True
        if not self._immortal:
            self._poll = 0

    def kill(self):
        self.killed = True
        self._poll = 0

    def wait(self, timeout=None):
        return self._poll

    def poll(self):
        return self._poll


@pytest.fixture(autouse=True)
def clean_state():
    """每个测试前清空模块级状态，测试后兜底清理"""
    with _logcat_lock:
        _logcat_processes.clear()
        _logcat_buffers.clear()
        _logcat_threads.clear()
    yield
    with _logcat_lock:
        _logcat_processes.clear()
        _logcat_buffers.clear()
        _logcat_threads.clear()


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture()
def log_tools():
    mcp = FakeMCP()
    log_mod.register_tools(mcp)
    return mcp.tools


def _popen_with_lines(lines):
    return FakePopen(lines)


def test_start_and_stop_full_cleanup(log_tools):
    """stop_log 必须清理进程、线程、buffer 三件套"""
    fake = FakePopen(["line-1", "line-2", "line-3"])

    with patch.object(log_mod.subprocess, "Popen", return_value=fake):
        result = log_tools["start_log"](session_id="s1")
        assert result.get("success") is True
        assert "s1" in _logcat_processes

    # 等 reader 线程消费完 stdout
    t = _logcat_threads["s1"]
    t.join(timeout=3)

    stop_result = log_tools["stop_log"](session_id="s1")
    assert stop_result.get("success") is True
    assert stop_result["captured_count"] == 3

    assert fake.terminated is True
    assert "s1" not in _logcat_processes
    assert "s1" not in _logcat_buffers
    assert "s1" not in _logcat_threads


def test_stderr_not_piped(log_tools):
    """stderr 必须 DEVNULL：PIPE 而无人读会写满管道导致 adb 僵死"""
    with patch.object(
        log_mod.subprocess, "Popen", return_value=FakePopen()
    ) as mock_popen:
        log_tools["start_log"](session_id="s1")
        kwargs = mock_popen.call_args.kwargs
        assert kwargs.get("stderr") == log_mod.subprocess.DEVNULL, (
            f"stderr 应为 DEVNULL，实际: {kwargs.get('stderr')}"
        )
        assert kwargs.get("stdout") == log_mod.subprocess.PIPE
    log_tools["stop_log"](session_id="s1")


def test_restart_after_process_death(log_tools):
    """进程自然死亡（设备拔出）后应能直接重启，不再永久拒绝"""
    dead = FakePopen()
    dead._poll = 1  # 已死（非 None 即已退出）

    with patch.object(log_mod.subprocess, "Popen", return_value=dead):
        result = log_tools["start_log"](session_id="s1")
        assert result.get("success") is True
        assert "s1" in _logcat_processes

    # 第二次 start：旧进程已死，应自动清理并重启
    alive = FakePopen(["after-restart"])
    with patch.object(log_mod.subprocess, "Popen", return_value=alive):
        result = log_tools["start_log"](session_id="s1")
        assert result.get("success") is True, f"重启被拒绝: {result}"
        assert _logcat_processes["s1"] is alive

    log_tools["stop_log"](session_id="s1")


def test_duplicate_start_rejected(log_tools):
    """活跃捕获期间重复 start 应被拒绝（防双进程）"""
    alive = FakePopen()

    with patch.object(log_mod.subprocess, "Popen", return_value=alive):
        log_tools["start_log"](session_id="s1")
        result = log_tools["start_log"](session_id="s1")
        assert "error" in result

    log_tools["stop_log"](session_id="s1")


def test_reader_survives_buffer_removal(log_tools):
    """reader 写入时 buffer 已被移除不得抛 KeyError（清理竞态）"""
    slow_stream = io.StringIO()
    fake = FakePopen()
    fake.stdout = slow_stream

    # 用阻塞式 stdout 模拟持续输出的 logcat
    class SlowStream:
        def __iter__(self):
            yield "first-line\n"
            # buffer 被移除后再产出数据 → reader 应安静退出
            while _logcat_buffers.get("s1") is not None:
                import time
                time.sleep(0.01)
            yield "orphan-line\n"

    fake.stdout = SlowStream()

    with patch.object(log_mod.subprocess, "Popen", return_value=fake):
        log_tools["start_log"](session_id="s1")
        t = _logcat_threads["s1"]
        # reader 正阻塞在持续输出流上（buffer 仍存在）
        t.join(timeout=1)
        assert t.is_alive(), "reader 应仍在等待流输出"

        # stop：buffer 被移除 → reader 应感知并安静退出（不得 KeyError）
        log_tools["stop_log"](session_id="s1")

    t.join(timeout=3)
    # reader 已因 buffer 消失而退出且未崩溃
    assert not t.is_alive()


def test_atexit_cleanup_registered():
    """atexit 兜底：_cleanup_all_logcat 能清干净所有捕获

    注册本身由 @atexit.register 装饰器保证（声明式）；
    Python 3.12 的 atexit 为 C 实现，回调列表在 Python 层不可见，
    因此这里验证兜底函数的实际清理行为。
    """
    from fridamcp.modules.log import _cleanup_all_logcat

    # 塞入两个"存活"的假进程（保存引用以便断言 terminate）
    fakes = {}
    for key in ("s1", "s2"):
        fake = FakePopen(["x"])
        fakes[key] = fake
        _logcat_processes[key] = fake
        _logcat_buffers[key] = __import__("collections").deque(["x"])
        _logcat_threads[key] = threading.Thread(target=lambda: None)

    _cleanup_all_logcat()

    assert len(_logcat_processes) == 0, "孤儿进程残留"
    assert len(_logcat_buffers) == 0
    assert len(_logcat_threads) == 0
    assert all(f.terminated for f in fakes.values()), "进程未被 terminate"


def test_concurrent_start_single_process(log_tools):
    """并发 start 竞态：只允许一个进程（锁保护）"""
    created = []
    lock = threading.Lock()

    def fake_factory(*a, **kw):
        p = FakePopen(["x"])
        with lock:
            created.append(p)
        return p

    with patch.object(log_mod.subprocess, "Popen", side_effect=fake_factory):
        results = []

        def starter():
            results.append(log_tools["start_log"](session_id="s1"))

        threads = [threading.Thread(target=starter) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

    successes = sum(1 for r in results if r.get("success"))
    assert successes == 1, f"并发 start 产生了 {successes} 个'成功'"
    assert len(created) == 1, f"实际创建了 {len(created)} 个进程"
    log_tools["stop_log"](session_id="s1")
