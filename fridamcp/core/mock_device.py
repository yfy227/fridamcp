"""
模拟设备模块

提供 Frida 设备/会话/脚本的模拟实现，用于：
  - 无 Android 设备环境下的开发与测试
  - CI/CD 流水线中的自动化测试
  - AI 客户端的功能演示

启用方式：
  环境变量 FRIDAMCP_MOCK_DEVICE=1 或 config.MOCK_DEVICE = True

模拟行为：
  - list_devices: 返回一个虚拟 USB 设备
  - list_processes: 返回一组常见 Android 进程
  - attach: 返回 MockSession
  - spawn: 返回虚拟 PID
  - execute_script: 返回 MockScript，模拟消息回传
"""

import time
import uuid
import threading
from typing import List, Dict, Any, Optional, Callable

from ..utils.logger import logger


class MockProcess:
    """模拟 Frida 进程对象（具有 .pid / .name 属性，兼容 frida_client）"""

    def __init__(self, pid: int, name: str, parameters: Optional[dict] = None):
        self.pid = pid
        self.name = name
        self.parameters = parameters or {}

    def __repr__(self):
        return f"MockProcess(pid={self.pid}, name={self.name})"


# 模拟的 Android 进程列表
_MOCK_PROCESS_DATA = [
    (1234, "com.android.systemui"),
    (2345, "com.android.settings"),
    (3456, "com.example.targetapp"),
    (4567, "com.tencent.mm"),
    (5678, "com.android.chrome"),
    (6789, "com.android.phone"),
    (7890, "frida-server"),
]

MOCK_PROCESSES = [MockProcess(pid, name) for pid, name in _MOCK_PROCESS_DATA]

# 模拟设备系统参数
MOCK_SYSTEM_PARAMETERS = {
    "os": {"id": "android", "kernel": "Linux 5.15.0", "version": "13"},
    "arch": "arm64",
    "frida-version": "16.5.1",
    "hostname": "mock-android-device",
}


class MockScript:
    """模拟 Frida 脚本"""

    def __init__(self, source: str, name: str = ""):
        self.id = str(uuid.uuid4())[:8]
        self.source = source
        self.name = name
        self._loaded = True
        self._message_handler: Optional[Callable] = None
        self._exports = {}

    @property
    def is_destroyed(self) -> bool:
        return not self._loaded

    def on(self, event: str, handler: Callable):
        if event == "message":
            self._message_handler = handler

    def load(self):
        self._loaded = True
        # 模拟脚本加载后发送一条 ready 消息
        if self._message_handler:
            threading.Timer(
                0.05,
                lambda: self._message_handler(
                    {"type": "send", "payload": {"type": "script_ready", "script_id": self.id}},
                    None,
                ),
            ).start()

    def unload(self):
        self._loaded = False

    def eternalize(self):
        pass

    def post(self, message):
        pass

    def exports_sync(self):
        return self._exports


class MockSession:
    """模拟 Frida 会话"""

    def __init__(self, pid: int):
        self.pid = pid
        self._detached = False
        self._detach_handler: Optional[Callable] = None
        self._scripts: List[MockScript] = []

    @property
    def is_detached(self) -> bool:
        return self._detached

    def on(self, event: str, handler: Callable):
        if event == "detached":
            self._detach_handler = handler

    def detach(self):
        self._detached = True
        for script in self._scripts:
            script.unload()
        self._scripts.clear()
        if self._detach_handler:
            try:
                self._detach_handler("mock-detach")
            except Exception:
                pass

    def create_script(self, source: str, name: str = "") -> MockScript:
        script = MockScript(source, name)
        self._scripts.append(script)
        return script

    def resume(self):
        pass


class MockDevice:
    """模拟 Frida 设备"""

    def __init__(self):
        self.id = "mock-device"
        self.name = "Mock Android Device"
        self.type = "usb"
        self._sessions: Dict[int, MockSession] = {}
        self._next_pid = 10000

    def query_system_parameters(self) -> Dict[str, Any]:
        return dict(MOCK_SYSTEM_PARAMETERS)

    def enumerate_processes(self) -> List[MockProcess]:
        """枚举所有进程（返回 MockProcess 对象，兼容 frida_client）"""
        return list(MOCK_PROCESSES)

    def get_process(self, name: str) -> MockProcess:
        """按名称获取进程"""
        for p in MOCK_PROCESSES:
            if p.name == name:
                return p
        raise ValueError(f"Process not found: {name}")

    def get_frontmost_application(self):
        """获取前台应用"""
        class MockApp:
            def __init__(self):
                self.identifier = "com.example.targetapp"
                self.name = "TargetApp"
                self.pid = 3456
        return MockApp()

    def attach(self, target) -> MockSession:
        if isinstance(target, int):
            pid = target
        elif isinstance(target, str):
            try:
                proc = self.get_process(target)
                pid = proc.pid
            except ValueError:
                pid = self._next_pid
                self._next_pid += 1
        else:
            pid = self._next_pid
            self._next_pid += 1

        if pid in self._sessions and not self._sessions[pid].is_detached:
            return self._sessions[pid]

        session = MockSession(pid)
        self._sessions[pid] = session
        logger.info(f"[MOCK] Attached to pid {pid}")
        return session

    def spawn(self, package: str) -> int:
        pid = self._next_pid
        self._next_pid += 1
        logger.info(f"[MOCK] Spawned {package} -> pid {pid}")
        return pid

    def resume(self, pid: int):
        logger.info(f"[MOCK] Resumed pid {pid}")

    def kill(self, pid: int):
        logger.info(f"[MOCK] Killed pid {pid}")
        if pid in self._sessions:
            self._sessions[pid].detach()


# 全局模拟设备单例
_mock_device: Optional[MockDevice] = None


def get_mock_device() -> MockDevice:
    """获取模拟设备单例"""
    global _mock_device
    if _mock_device is None:
        _mock_device = MockDevice()
    return _mock_device


def is_mock_mode() -> bool:
    """检查是否处于模拟模式"""
    import os
    return os.getenv("FRIDAMCP_MOCK_DEVICE", "").lower() in ("1", "true", "yes")
