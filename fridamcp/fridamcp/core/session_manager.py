"""
会话管理模块

管理 Frida 会话和脚本，支持多会话、脚本加载、消息处理。
包含会话状态追踪、自动清理和分离恢复机制。
"""

import threading
import time
import uuid
from collections import deque
from enum import Enum
from typing import Dict, Any, Optional, Callable, List

import frida

from ..config import config
from ..utils.logger import logger
from .device_manager import device_manager


class SessionState(Enum):
    """会话状态枚举"""
    CREATED = "created"        # 已创建，未附加
    ATTACHED = "attached"      # 已附加到进程
    DETACHED = "detached"      # 已分离（进程退出或手动分离）
    ERROR = "error"            # 出错


class Session:
    """单个 Frida 会话封装

    负责管理一个 Frida 会话的生命周期，包括脚本加载、消息处理、
    状态追踪和资源清理。
    """

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
        # 会话状态
        self.state: SessionState = SessionState.CREATED
        # 分离原因
        self.detach_reason: Optional[str] = None
        # 时间戳
        self.created_at: float = time.time()
        self.attached_at: Optional[float] = None
        self.detached_at: Optional[float] = None
        # 错误信息
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    def attach(self, device: frida.core.Device):
        """附加到进程"""
        logger.info(f"Attaching to pid={self.pid} (session={self.id})")
        try:
            self.session = device.attach(self.pid)
            self.session.on("detached", self._on_detached)
            self.state = SessionState.ATTACHED
            self.attached_at = time.time()
            logger.info(f"Session {self.id} attached to pid={self.pid}")
        except Exception as e:
            self.state = SessionState.ERROR
            self.last_error = str(e)
            logger.error(f"Failed to attach session {self.id}: {e}")
            raise

    def _on_detached(self, reason, crash):
        """会话分离回调"""
        self.state = SessionState.DETACHED
        self.detach_reason = str(reason)
        self.detached_at = time.time()
        logger.warning(
            f"Session {self.id} detached: reason={reason}, crash={crash}"
        )
        # 清理脚本引用
        with self._lock:
            self.scripts.clear()

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

        Raises:
            RuntimeError: 当会话未附加或已分离时
        """
        if self.session is None:
            raise RuntimeError("Session not attached")
        if self.state != SessionState.ATTACHED:
            raise RuntimeError(f"Session is not active (state={self.state.value})")

        script_id = name or f"script_{uuid.uuid4().hex[:8]}"
        logger.info(f"Loading script '{script_id}' in session {self.id}")

        try:
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
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed to load script '{script_id}': {e}")
            raise

    def _default_on_message(self, script_id: str, message: Dict, data: Any):
        """默认消息处理"""
        with self._lock:
            self.messages.append(
                {
                    "script_id": script_id,
                    "message": message,
                    "data": data.hex() if isinstance(data, bytes) else data,
                    "timestamp": time.time(),
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
        with self._lock:
            if script_id not in self.scripts:
                return False
            try:
                self.scripts[script_id].unload()
                del self.scripts[script_id]
                logger.info(f"Unloaded script '{script_id}'")
                return True
            except Exception as e:
                logger.error(f"Failed to unload script {script_id}: {e}")
                # 即使卸载失败也移除引用
                del self.scripts[script_id]
                return False

    def unload_all_scripts(self):
        """卸载所有脚本"""
        with self._lock:
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
        with self._lock:
            self.hooks[hook_id] = hook_info

    def remove_hook(self, hook_id: str) -> bool:
        """移除 Hook 记录"""
        with self._lock:
            if hook_id in self.hooks:
                del self.hooks[hook_id]
                return True
            return False

    def is_active(self) -> bool:
        """检查会话是否处于活动状态"""
        return self.state == SessionState.ATTACHED and self.session is not None

    def detach(self):
        """分离会话"""
        try:
            self.unload_all_scripts()
            if self.session and self.state == SessionState.ATTACHED:
                self.session.detach()
            logger.info(f"Session {self.id} detached")
        except Exception as e:
            logger.error(f"Error detaching session {self.id}: {e}")
        finally:
            self.state = SessionState.DETACHED
            self.detached_at = time.time()
            self.session = None

    def get_info(self) -> Dict[str, Any]:
        """获取会话信息摘要"""
        return {
            "id": self.id,
            "pid": self.pid,
            "name": self.name,
            "state": self.state.value,
            "scripts": list(self.scripts.keys()),
            "hooks": list(self.hooks.keys()),
            "message_count": len(self.messages),
            "created_at": self.created_at,
            "attached_at": self.attached_at,
            "detached_at": self.detached_at,
            "detach_reason": self.detach_reason,
            "last_error": self.last_error,
        }


class SessionManager:
    """会话管理器（单例）

    管理所有 Frida 会话的生命周期，提供创建、查询、关闭会话等功能。
    支持自动清理已分离的会话。
    """

    _instance: Optional["SessionManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions: Dict[str, Session] = {}
            cls._instance._cleanup_thread: Optional[threading.Thread] = None
            cls._instance._shutdown = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_session(self, pid: int, name: str = "") -> Session:
        """创建新会话"""
        with self._lock:
            if len(self._sessions) >= config.MAX_SESSIONS:
                # 尝试清理已分离的会话
                self._cleanup_detached()
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
            self._sessions[session_id] = session
            logger.info(f"Created session {session_id} for pid={pid}")
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        return self._sessions.get(session_id)

    def get_active_session(self, session_id: str) -> Optional[Session]:
        """获取活动状态的会话

        如果会话已分离，返回 None 并记录警告。
        """
        session = self._sessions.get(session_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None
        if not session.is_active():
            logger.warning(
                f"Session {session_id} is not active (state={session.state.value})"
            )
            return None
        return session

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        return [s.get_info() for s in self._sessions.values()]

    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.detach()
            del self._sessions[session_id]
            return True

    def _cleanup_detached(self):
        """清理已分离的会话"""
        detached_ids = [
            sid for sid, s in self._sessions.items()
            if s.state in (SessionState.DETACHED, SessionState.ERROR)
        ]
        for sid in detached_ids:
            session = self._sessions.pop(sid, None)
            if session:
                logger.info(f"Cleaned up detached session: {sid}")

    def close_all(self):
        """关闭所有会话"""
        with self._lock:
            self._shutdown = True
            for sid in list(self._sessions.keys()):
                session = self._sessions.get(sid)
                if session:
                    try:
                        session.detach()
                    except Exception as e:
                        logger.error(f"Error detaching session {sid}: {e}")
            self._sessions.clear()
            logger.info("All sessions closed")

    def get_status(self) -> Dict[str, Any]:
        """获取会话管理器状态"""
        active_count = sum(1 for s in self._sessions.values() if s.is_active())
        detached_count = sum(
            1 for s in self._sessions.values()
            if s.state == SessionState.DETACHED
        )
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active_count,
            "detached_sessions": detached_count,
            "max_sessions": config.MAX_SESSIONS,
        }


# 全局会话管理器单例
session_manager = SessionManager.get_instance()
