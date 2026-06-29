"""
会话管理模块（增强版）

管理 Frida 会话和脚本，支持多会话、脚本加载、消息处理。
新增特性：
  - 显式 Session 生命周期（CREATED → ATTACHED → IDLE → DETACHED）
  - 会话复用：同一 PID 默认复用现有活动会话，避免重复 attach
  - 会话超时：空闲超过 SESSION_IDLE_TIMEOUT 自动分离释放
  - 并发锁：每个会话持有独立 RLock，防止多 AI 并发调用冲突
  - 保活线程：周期性检查会话状态、清理超时会话
  - 分离恢复：进程崩溃后自动标记并允许重新 attach

设计要点：
  - SessionManager 自身使用全局 RLock 保护 _sessions 字典
  - 每个 Session 实例持有独立 _lock，保护脚本/消息/hook 操作
  - 这两层锁粒度不同，避免长操作阻塞会话创建/查询
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


# 注意: 使用 threading.RLock 替代 Lock，以允许同一线程内嵌套加锁
# （如 unload_all_scripts -> unload_script）


class SessionState(Enum):
    """会话状态枚举（显式生命周期）"""
    CREATED = "created"        # 已创建，未附加
    ATTACHED = "attached"      # 已附加到进程
    DETACHED = "detached"      # 已分离（进程退出或手动分离）
    ERROR = "error"            # 出错
    EXPIRED = "expired"        # 因空闲超时被回收


class Session:
    """单个 Frida 会话封装

    负责管理一个 Frida 会话的生命周期，包括脚本加载、消息处理、
    状态追踪和资源清理。

    并发模型：
      - self._lock 保护 scripts / messages / hooks / state 等可变字段
      - 通过 acquire()/release() 提供操作级别的串行化，
        防止多 AI 并发调用同一会话时产生竞态
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
        # 最后活动时间（用于空闲超时判断）
        self.last_active_at: float = time.time()
        # 错误信息
        self.last_error: Optional[str] = None
        # 数据锁：保护可变字段
        self._lock = threading.RLock()
        # 操作锁：串行化对 Frida session 的并发调用
        # 使用 RLock 允许同一线程嵌套（如 hook -> execute_script）
        self._op_lock = threading.RLock()
        # 引用计数：用于会话复用场景
        self._ref_count: int = 1

    # ============ 生命周期 ============

    def attach(self, device: frida.core.Device):
        """附加到进程"""
        logger.info(f"Attaching to pid={self.pid} (session={self.id})")
        try:
            self.session = device.attach(self.pid)
            self.session.on("detached", self._on_detached)
            self.state = SessionState.ATTACHED
            self.attached_at = time.time()
            self.last_active_at = time.time()
            logger.info(f"Session {self.id} attached to pid={self.pid}")
        except Exception as e:
            self.state = SessionState.ERROR
            self.last_error = str(e)
            logger.error(f"Failed to attach session {self.id}: {e}")
            raise

    def _on_detached(self, reason, crash):
        """会话分离回调（Frida 在目标进程退出/崩溃时触发）"""
        self.state = SessionState.DETACHED
        self.detach_reason = str(reason)
        self.detached_at = time.time()
        logger.warning(
            f"Session {self.id} detached: reason={reason}, crash={crash}"
        )
        # 清理脚本引用
        with self._lock:
            self.scripts.clear()

    def touch(self):
        """更新最后活动时间（每次成功操作后调用）"""
        self.last_active_at = time.time()

    def is_active(self) -> bool:
        """检查会话是否处于活动状态"""
        return self.state == SessionState.ATTACHED and self.session is not None

    def is_expired(self) -> bool:
        """检查会话是否已空闲超时"""
        if not self.is_active():
            return False
        timeout = config.SESSION_IDLE_TIMEOUT
        if timeout <= 0:
            return False
        idle = time.time() - self.last_active_at
        return idle > timeout

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

    # ============ 并发控制 ============

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取会话操作锁

        用于串行化对同一会话的并发操作，防止多 AI 调用冲突。
        嵌套调用（同一线程）会直接成功。

        Args:
            timeout: 获取锁的超时时间（秒），None 表示阻塞等待

        Returns:
            是否成功获取锁
        """
        if timeout is None:
            self._op_lock.acquire()
            return True
        return self._op_lock.acquire(timeout=timeout)

    def release(self):
        """释放会话操作锁"""
        try:
            self._op_lock.release()
        except RuntimeError:
            # 防止重复释放
            pass

    # ============ 引用计数（会话复用） ============

    def incref(self) -> int:
        """增加引用计数"""
        with self._lock:
            self._ref_count += 1
            return self._ref_count

    def decref(self) -> int:
        """减少引用计数，返回当前计数"""
        with self._lock:
            self._ref_count = max(0, self._ref_count - 1)
            return self._ref_count

    @property
    def ref_count(self) -> int:
        return self._ref_count

    # ============ 脚本管理 ============

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
            with self._lock:
                self.scripts[script_id] = script
            self.touch()
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
                self.touch()
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
        self.touch()
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

    def get_info(self) -> Dict[str, Any]:
        """获取会话信息摘要"""
        with self._lock:
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
                "last_active_at": self.last_active_at,
                "idle_seconds": round(time.time() - self.last_active_at, 1),
                "detach_reason": self.detach_reason,
                "last_error": self.last_error,
                "ref_count": self._ref_count,
            }


class SessionManager:
    """会话管理器（单例）

    管理所有 Frida 会话的生命周期，提供创建、查询、关闭、复用等功能。
    支持自动清理已分离/超时的会话，并启动后台保活线程。

    线程安全：
      - _lock 保护 _sessions 字典的读写
      - 每个 Session 内部有自己的锁，互不影响
    """

    _instance: Optional["SessionManager"] = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions: Dict[str, Session] = {}
            cls._instance._cleanup_thread: Optional[threading.Thread] = None
            cls._instance._shutdown = False
            cls._instance._keepalive_started = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ============ 会话创建/复用 ============

    def create_session(
        self,
        pid: int,
        name: str = "",
        reuse: bool = True,
    ) -> Session:
        """创建新会话或复用现有会话

        Args:
            pid: 目标进程 PID
            name: 会话名称
            reuse: 是否复用同一 PID 的现有活动会话（默认 True）

        Returns:
            Session 实例
        """
        with self._lock:
            # 启动保活线程（首次创建时）
            self._ensure_keepalive()

            # 尝试复用
            if reuse:
                for sess in self._sessions.values():
                    if sess.pid == pid and sess.is_active():
                        sess.incref()
                        logger.info(
                            f"Reused session {sess.id} for pid={pid} "
                            f"(ref_count={sess.ref_count})"
                        )
                        return sess

            if len(self._sessions) >= config.MAX_SESSIONS:
                # 尝试清理已分离/超时的会话
                self._cleanup_detached()
                self._cleanup_expired()
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

    def close_session(self, session_id: str, force: bool = False) -> bool:
        """关闭会话

        Args:
            session_id: 会话 ID
            force: 是否强制关闭（忽略引用计数）

        Returns:
            是否成功关闭
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False

            # 引用计数 > 1 时，仅减少计数
            if not force and session.decref() > 0:
                logger.info(
                    f"Session {session_id} ref_count decremented to "
                    f"{session.ref_count}, not closing"
                )
                return True

            session.detach()
            del self._sessions[session_id]
            return True

    # ============ 自动清理 ============

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

    def _cleanup_expired(self):
        """清理空闲超时的会话"""
        if config.SESSION_IDLE_TIMEOUT <= 0:
            return
        expired_ids = [
            sid for sid, s in self._sessions.items()
            if s.is_expired()
        ]
        for sid in expired_ids:
            session = self._sessions.pop(sid, None)
            if session:
                try:
                    session.state = SessionState.EXPIRED
                    session.detach()
                    logger.info(
                        f"Expired idle session: {sid} "
                        f"(idle={int(time.time() - session.last_active_at)}s)"
                    )
                except Exception as e:
                    logger.error(f"Error expiring session {sid}: {e}")

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

    # ============ 保活线程 ============

    def _ensure_keepalive(self):
        """确保保活线程已启动"""
        if self._keepalive_started:
            return
        if config.SESSION_KEEPALIVE_INTERVAL <= 0:
            return
        self._keepalive_started = True
        self._cleanup_thread = threading.Thread(
            target=self._keepalive_loop,
            name="fridamcp-keepalive",
            daemon=True,
        )
        self._cleanup_thread.start()
        logger.info(
            f"Session keepalive thread started "
            f"(interval={config.SESSION_KEEPALIVE_INTERVAL}s, "
            f"idle_timeout={config.SESSION_IDLE_TIMEOUT}s)"
        )

    def _keepalive_loop(self):
        """保活线程主循环：周期性清理超时/分离会话"""
        interval = config.SESSION_KEEPALIVE_INTERVAL
        while not self._shutdown:
            time.sleep(interval)
            try:
                with self._lock:
                    if self._shutdown:
                        break
                    before = len(self._sessions)
                    self._cleanup_detached()
                    self._cleanup_expired()
                    after = len(self._sessions)
                    if before != after:
                        logger.info(
                            f"Keepalive cleanup: {before} -> {after} sessions"
                        )
            except Exception as e:
                logger.error(f"Keepalive loop error: {e}")

    # ============ 状态查询 ============

    def get_status(self) -> Dict[str, Any]:
        """获取会话管理器状态"""
        active_count = sum(1 for s in self._sessions.values() if s.is_active())
        detached_count = sum(
            1 for s in self._sessions.values()
            if s.state == SessionState.DETACHED
        )
        expired_count = sum(
            1 for s in self._sessions.values()
            if s.state == SessionState.EXPIRED
        )
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active_count,
            "detached_sessions": detached_count,
            "expired_sessions": expired_count,
            "max_sessions": config.MAX_SESSIONS,
            "idle_timeout": config.SESSION_IDLE_TIMEOUT,
            "keepalive_interval": config.SESSION_KEEPALIVE_INTERVAL,
            "keepalive_running": self._keepalive_started and not self._shutdown,
        }


# 全局会话管理器单例
session_manager = SessionManager.get_instance()
