"""
Frida 客户端封装

提供对 Frida 核心功能的高层封装，供 MCP 模块调用。
"""

import time
import uuid
from typing import Dict, Any, Optional, List

import frida

from ..config import config
from ..utils.logger import logger
from .device_manager import device_manager
from .session_manager import session_manager, Session


class FridaClient:
    """Frida 客户端，封装常用操作"""

    _instance: Optional["FridaClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "FridaClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ============ 进程管理 ============

    def _get_device(self):
        """获取当前设备，如果未连接则抛出清晰错误

        不再自动触发阻塞式重连，调用方应先调用 select_device。
        """
        device = device_manager.get_current_device()
        if device is None:
            raise RuntimeError(
                "设备未连接。请先调用 select_device 工具选择设备 "
                "(例如 select_device(device_type='local') 或 "
                "select_device(device_type='usb'))"
            )
        return device

    def list_processes(self) -> List[Dict[str, Any]]:
        """列出设备上所有进程"""
        device = self._get_device()
        try:
            procs = device.enumerate_processes()
            return [{"pid": p.pid, "name": p.name} for p in procs]
        except Exception as e:
            logger.error(f"Failed to list processes: {e}")
            raise

    def list_applications(self) -> List[Dict[str, Any]]:
        """列出设备上所有已安装应用"""
        device = self._get_device()
        try:
            apps = device.enumerate_applications()
            return [
                {
                    "identifier": a.identifier,
                    "name": a.name,
                    "pid": a.pid,
                }
                for a in apps
            ]
        except Exception as e:
            logger.error(f"Failed to list applications: {e}")
            raise

    def spawn(self, package: str, paused: bool = True) -> Dict[str, Any]:
        """启动应用（默认暂停）

        Args:
            package: 应用包名
            paused: 是否暂停启动

        Returns:
            包含 pid 和 session_id 的字典
        """
        device = self._get_device()

        logger.info(f"Spawning {package} (paused={paused})")
        pid = device.spawn([package])

        session = session_manager.create_session(pid, package)

        if not paused:
            device.resume(pid)

        return {"pid": pid, "session_id": session.id, "package": package}

    def attach(self, target) -> Dict[str, Any]:
        """附加到运行中的进程

        Args:
            target: 进程 PID (int) 或包名/进程名 (str)

        Returns:
            包含 session_id 的字典
        """
        device = self._get_device()

        if isinstance(target, int):
            pid = target
            name = f"pid_{pid}"
        else:
            # 通过名称查找 PID
            procs = device.enumerate_processes()
            pid = None
            exact = [p for p in procs if p.name == target]
            prefix = [p for p in procs if p.name.startswith(str(target))]
            matches = exact or prefix
            if len(matches) > 1 and not exact:
                raise RuntimeError(
                    f"Ambiguous process target {target!r}: "
                    + ", ".join(f"{p.name}({p.pid})" for p in matches[:10])
                )
            if matches:
                pid = matches[0].pid
                name = matches[0].name
            if pid is None:
                raise RuntimeError(f"Process not found: {target}")

        session = session_manager.create_session(pid, name)
        return {"pid": pid, "session_id": session.id, "name": name}

    def resume(self, pid: int):
        """恢复暂停的进程"""
        device = self._get_device()
        device.resume(pid)
        logger.info(f"Resumed pid={pid}")

    def kill(self, pid: int):
        """杀死进程"""
        device = self._get_device()
        device.kill(pid)
        logger.info(f"Killed pid={pid}")

    # ============ 脚本执行 ============

    def execute_script(
        self,
        session_id: str,
        source: str,
        script_name: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """在指定会话中执行 Frida 脚本

        Args:
            session_id: 会话 ID
            source: JavaScript 脚本源码
            script_name: 脚本名称
            timeout: 超时时间（秒）

        Returns:
            包含 script_id 的字典
        """
        session = session_manager.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")

        script_id = session.load_script(source, script_name)
        return {"script_id": script_id, "session_id": session_id}

    def call_script_function(
        self,
        session_id: str,
        script_id: str,
        function_name: str,
        args: Optional[list] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        """调用脚本中的导出函数 (rpc.exports)

        Args:
            session_id: 会话 ID
            script_id: 脚本 ID
            function_name: rpc.exports 中的函数名
            args: 参数列表
            timeout: 超时时间

        Returns:
            函数返回值
        """
        session = session_manager.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")

        script = session.scripts.get(script_id)
        if script is None:
            raise RuntimeError(f"Script not found: {script_id}")

        to = timeout or config.SCRIPT_TIMEOUT
        logger.info(
            f"Calling script function: {function_name}(args={args}) "
            f"timeout={to}s"
        )

        # Frida 的 rpc.exports 调用
        exports = script.exports_sync
        fn = getattr(exports, function_name)
        result = fn(*(args or []))
        return result

    def unload_script(self, session_id: str, script_id: str) -> bool:
        """卸载脚本"""
        session = session_manager.get_session(session_id)
        if session is None:
            return False
        return session.unload_script(script_id)

    def get_messages(
        self, session_id: str, clear: bool = False
    ) -> List[Dict[str, Any]]:
        """获取会话消息"""
        session = session_manager.get_session(session_id)
        if session is None:
            return []
        return session.get_messages(clear)

    # ============ 会话管理 ============

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        return session_manager.list_sessions()

    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        return session_manager.close_session(session_id)

    # ============ 设备信息 ============

    def get_device_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        return device_manager.get_device_info()

    def list_devices(self) -> List[Dict[str, Any]]:
        """列出所有设备"""
        return device_manager.list_devices()

    def select_device(
        self, device_id: Optional[str] = None, device_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """选择设备"""
        device = device_manager.get_device(device_id, device_type)
        return {"id": device.id, "name": device.name, "type": device.type}


# 全局 Frida 客户端单例
frida_client = FridaClient.get_instance()
