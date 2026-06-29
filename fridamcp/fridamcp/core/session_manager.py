"""
会话管理模块

管理 Frida 会话和脚本，支持多会话、脚本加载、消息处理。
"""

import threading
import uuid
from collections import deque
from typing import Dict, Any, Optional, Callable, List

import frida

from ..config import config
from ..utils.logger import logger
from .device_manager import device_manager


class Session:
    """单个 Frida 会话封装"""

    def __init__(self, session_id: str, pid: int, name: str):
        self.id = session_id
        self.pid = pid
        self.name = name
        self.session: Optional[frida.core.Session] = None
        self.scripts: Dict[str, frida.core.Script] = {}
        # 消息缓冲区，存储脚本发送的消息
        self.messages: deque = deque(maxlen=config.LOG_BUFFER_SIZE)
        # Hook 记录
        self.hooks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def attach(self, device: frida.core.Device):
        """附加到进程"""
        logger.info(f"Attaching to pid={self.pid} (session={self.id})")
        self.session = device.attach(self.pid)
        self.session.on("detached", self._on_detached)

    def _on_detached(self, reason, crash):
        """会话分离回调"""
        logger.warning(
            f"Session {self.id} detached: reason={reason}, crash={crash}"
        )

    def load_script(
        self,
        source: str,
        name: Optional[str] = None,
        on_message: Optional[Callable] = None,
    ) -> str:
        """加载 Frida 脚本

        Args:
            source: JavaScript 脚本源码
            name: 脚本名称，None 则自动生成
            on_message: 消息回调函数

        Returns:
            脚本 ID
        """
        if self.session is None:
            raise RuntimeError("Session not attached")

        script_id = name or f"script_{uuid.uuid4().hex[:8]}"
        logger.info(f"Loading script '{script_id}' in session {self.id}")

        script = self.session.create_script(source)
        script.on(
            "message",
            on_message or (lambda message, data: self._default_on_message(
                script_id, message, data
            )),
        )
        script.load()
        self.scripts[script_id] = script
        return script_id

    def _default_on_message(self, script_id: str, message: Dict, data: Any):
        """默认消息处理"""
        with self._lock:
            self.messages.append(
                {
                    "script_id": script_id,
                    "message": message,
                    "data": data.hex() if isinstance(data, bytes) else data,
                }
            )
        if message.get("type") == "error":
            logger.error(
                f"Script {script_id} error: {message.get('description')}"
            )
        else:
            logger.debug(f"Script {script_id} message: {message}")

    def unload_script(self, script_id: str) -> bool:
        """卸载脚本"""
        if script_id not in self.scripts:
            return False
        try:
            self.scripts[script_id].unload()
            del self.scripts[script_id]
            logger.info(f"Unloaded script '{script_id}'")
            return True
        except Exception as e:
            logger.error(f"Failed to unload script {script_id}: {e}")
            return False

    def unload_all_scripts(self):
        """卸载所有脚本"""
        for sid in list(self.scripts.keys()):
            self.unload_script(sid)

    def get_messages(self, clear: bool = False) -> list:
        """获取所有消息"""
        with self._lock:
            msgs = list(self.messages)
            if clear:
                self.messages.clear()
        return msgs

    def add_hook(self, hook_id: str, hook_info: Dict[str, Any]):
        """记录 Hook 信息"""
        self.hooks[hook_id] = hook_info

    def remove_hook(self, hook_id: str) -> bool:
        """移除 Hook 记录"""
        if hook_id in self.hooks:
            del self.hooks[hook_id]
            return True
        return False

    def detach(self):
        """分离会话"""
        try:
            self.unload_all_scripts()
            if self.session:
                self.session.detach()
            logger.info(f"Session {self.id} detached")
        except Exception as e:
            logger.error(f"Error detaching session {self.id}: {e}")


class SessionManager:
    """会话管理器（单例）"""

    _instance: Optional["SessionManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions: Dict[str, Session] = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_session(self, pid: int, name: str = "") -> Session:
        """创建新会话"""
        if len(self._sessions) >= config.MAX_SESSIONS:
            raise RuntimeError(
                f"Max sessions ({config.MAX_SESSIONS}) reached"
            )

        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        session = Session(session_id, pid, name or f"pid_{pid}")

        device = device_manager.get_current_device()
        if device is None:
            device = device_manager.get_device()

        session.attach(device)
        with self._lock:
            self._sessions[session_id] = session
        logger.info(f"Created session {session_id} for pid={pid}")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        return [
            {
                "id": s.id,
                "pid": s.pid,
                "name": s.name,
                "scripts": list(s.scripts.keys()),
                "hooks": list(s.hooks.keys()),
                "message_count": len(s.messages),
            }
            for s in self._sessions.values()
        ]

    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.detach()
            del self._sessions[session_id]
            return True

    def close_all(self):
        """关闭所有会话"""
        with self._lock:
            for sid in list(self._sessions.keys()):
                self._sessions[sid].detach()
            self._sessions.clear()


# 全局会话管理器单例
session_manager = SessionManager.get_instance()
