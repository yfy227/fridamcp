"""
日志捕获模块

提供应用日志捕获、Frida 脚本日志、logcat 日志等工具。
"""

import atexit
import subprocess
import threading
from collections import deque
from typing import Dict, Any, List, Optional

from ..core.frida_client import frida_client
from ..config import config
from ..utils.logger import logger, get_log_buffer, clear_log_buffer


# logcat 捕获状态（所有访问必须持有 _logcat_lock）
# RLock：start_log 持锁期间会调用 _stop_logcat（同样需要加锁）
# 清理已死亡的进程，普通 Lock 会死锁
_logcat_lock = threading.RLock()
_logcat_processes: Dict[str, subprocess.Popen] = {}
_logcat_buffers: Dict[str, deque] = {}
_logcat_threads: Dict[str, threading.Thread] = {}


def _start_logcat(
    session_id: str,
    package: Optional[str] = None,
    device: Optional[str] = None,
) -> subprocess.Popen:
    """启动 logcat 捕获

    由调用方保证持有 _logcat_lock 且 key 不在运行表中。
    """
    args = ["adb"]
    if device:
        args.extend(["-s", device])
    args.extend(["logcat", "-v", "time"])

    if package:
        # 通过 pid 过滤
        try:
            pid_output = subprocess.run(
                args[:1] + (["-s", device] if device else []) + ["shell", "pidof", package],
                capture_output=True,
                text=True,
                timeout=10,
            )
            pid = pid_output.stdout.strip()
            if pid:
                args.extend(["--pid", pid])
        except Exception:
            pass

    # stderr 丢弃：若保持 PIPE 而无人读取，adb 写满管道缓冲区后
    # 会永久阻塞（经典 subprocess 陷阱）
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    _logcat_processes[session_id] = proc
    _logcat_buffers[session_id] = deque(maxlen=config.LOG_BUFFER_SIZE)

    def reader():
        try:
            for line in proc.stdout:
                # stop_log 清理后 buffer 可能已移除：.get 防御，
                # 避免清理竞态导致 reader 以 KeyError 崩掉
                buf = _logcat_buffers.get(session_id)
                if buf is None:
                    break
                buf.append(line.rstrip())
        except Exception as e:
            logger.error(f"logcat reader error: {e}")

    t = threading.Thread(target=reader, daemon=True)
    _logcat_threads[session_id] = t
    t.start()
    return proc


def _stop_logcat(key: str) -> int:
    """停止并清理一个 logcat 捕获（线程安全）

    清理顺序：进程(terminate→kill) → reader 线程(join) → buffer。
    返回停止前捕获的行数。
    """
    with _logcat_lock:
        proc = _logcat_processes.pop(key, None)
        if proc is not None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
            except Exception as e:
                logger.warning(f"logcat terminate error: {e}")

        t = _logcat_threads.pop(key, None)
        if t is not None and t.is_alive():
            t.join(timeout=3)

        buf = _logcat_buffers.pop(key, None)
        return len(buf) if buf else 0


def _sweep_dead_logcat():
    """清理已自然退出的 logcat 条目（设备拔出时 adb 会自杀）"""
    for key in list(_logcat_processes.keys()):
        proc = _logcat_processes.get(key)
        if proc is not None and proc.poll() is not None:
            logger.info(f"logcat for {key} exited (code={proc.returncode}), sweeping")
            _stop_logcat(key)


@atexit.register
def _cleanup_all_logcat():
    """进程退出兜底：不留孤儿 adb logcat 进程"""
    for key in list(_logcat_processes.keys()):
        try:
            _stop_logcat(key)
        except Exception:
            pass


def register_tools(mcp):
    """向 MCP 服务器注册日志捕获工具"""

    @mcp.tool()
    def start_log(
        session_id: Optional[str] = None,
        package: Optional[str] = None,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """开始捕获 logcat 日志

        Args:
            session_id: 会话 ID（可选，用于关联）
            package: 应用包名（可选，只捕获该应用日志）
            device: 设备序列号（可选）

        Returns:
            操作结果
        """
        try:
            key = session_id or "default"
            with _logcat_lock:
                # 先清理已自然死亡的条目：设备拔出后 adb logcat 自杀，
                # 旧实现只查字典存在性，导致永远无法重新开始捕获
                existing = _logcat_processes.get(key)
                if existing is not None and existing.poll() is not None:
                    _stop_logcat(key)
                    existing = None
                if existing is not None or key in _logcat_processes:
                    return {"error": "Log already running for this session"}
                _start_logcat(key, package, device)
            return {
                "success": True,
                "session_id": key,
                "package": package,
                "status": "capturing",
            }
        except Exception as e:
            logger.error(f"start_log failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_logs(
        session_id: Optional[str] = None,
        clear: bool = False,
        filter_text: Optional[str] = None,
        max_lines: int = 100,
    ) -> Dict[str, Any]:
        """获取捕获的日志

        Args:
            session_id: 会话 ID（可选）
            clear: 是否在读取后清空
            filter_text: 可选，过滤包含此文本的日志
            max_lines: 最大返回行数（默认 100）

        Returns:
            包含日志行的字典
        """
        try:
            key = session_id or "default"
            with _logcat_lock:
                buf = _logcat_buffers.get(key)
                if buf is None:
                    return {"error": "No log capture for this session"}
                lines = list(buf)
            if filter_text:
                lines = [l for l in lines if filter_text in l]
            lines = lines[-max_lines:]
            if clear:
                with _logcat_lock:
                    buf = _logcat_buffers.get(key)
                    if buf is not None:
                        buf.clear()
            return {
                "session_id": key,
                "count": len(lines),
                "logs": lines,
            }
        except Exception as e:
            logger.error(f"get_logs failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def stop_log(session_id: Optional[str] = None) -> Dict[str, Any]:
        """停止日志捕获

        Args:
            session_id: 会话 ID（可选）

        Returns:
            操作结果
        """
        try:
            key = session_id or "default"
            count = _stop_logcat(key)
            return {"success": True, "session_id": key, "captured_count": count}
        except Exception as e:
            logger.error(f"stop_log failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_frida_messages(
        session_id: str,
        clear: bool = False,
    ) -> List[Dict[str, Any]]:
        """获取 Frida 脚本发送的消息

        获取通过 send() 发送的所有消息，包括 Hook 捕获的数据。

        Args:
            session_id: 会话 ID
            clear: 是否在读取后清空

        Returns:
            消息列表
        """
        try:
            return frida_client.get_messages(session_id, clear=clear)
        except Exception as e:
            logger.error(f"get_frida_messages failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def get_server_logs(
        clear: bool = False,
        max_entries: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取 MCP 服务器自身的日志

        Args:
            clear: 是否在读取后清空
            max_entries: 最大返回条数

        Returns:
            日志条目列表
        """
        try:
            buf = get_log_buffer()
            entries = list(buf)[-max_entries:]
            if clear:
                clear_log_buffer()
            return [
                {
                    "time": e.get("time", {}).isoformat() if hasattr(e.get("time"), "isoformat") else str(e.get("time")),
                    "level": e.get("level", {}).name if hasattr(e.get("level"), "name") else str(e.get("level")),
                    "name": e.get("name"),
                    "function": e.get("function"),
                    "line": e.get("line"),
                    "message": e.get("message"),
                }
                for e in entries
            ]
        except Exception as e:
            logger.error(f"get_server_logs failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def clear_all_logs() -> Dict[str, Any]:
        """清空所有日志缓冲区

        Returns:
            操作结果
        """
        try:
            clear_log_buffer()
            with _logcat_lock:
                for buf in _logcat_buffers.values():
                    buf.clear()
            return {"success": True}
        except Exception as e:
            logger.error(f"clear_all_logs failed: {e}")
            return {"error": str(e)}

    logger.info("Log module tools registered")
