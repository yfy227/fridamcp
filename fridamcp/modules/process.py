"""
进程管理模块

提供进程列表、应用列表、启动应用、附加进程、杀死进程、恢复进程等工具。
"""

from typing import Dict, Any, List, Optional, Union

from ..core.frida_client import frida_client
from ..config import config
from ..utils.logger import logger


def register_tools(mcp):
    """向 MCP 服务器注册进程管理工具"""

    @mcp.tool()
    def list_devices() -> List[Dict[str, Any]]:
        """列出所有可用的 Frida 设备

        返回设备列表，每个设备包含 id、name、type 字段。
        用于在多设备环境下选择目标设备。
        """
        try:
            return frida_client.list_devices()
        except Exception as e:
            logger.error(f"list_devices failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def select_device(
        device_id: Optional[str] = None,
        device_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """选择 Frida 设备

        Args:
            device_id: 设备 ID（可选，优先使用）
            device_type: 设备类型 usb/remote/local（可选）

        Returns:
            选中的设备信息
        """
        try:
            return frida_client.select_device(device_id, device_type)
        except Exception as e:
            logger.error(f"select_device failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_device_info() -> Dict[str, Any]:
        """获取当前设备的详细信息

        返回设备 id、name、type、os、arch、frida_version、hostname 等。
        """
        try:
            return frida_client.get_device_info()
        except Exception as e:
            logger.error(f"get_device_info failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def list_processes() -> List[Dict[str, Any]]:
        """列出设备上所有正在运行的进程

        返回进程列表，每个进程包含 pid 和 name 字段。
        """
        try:
            return frida_client.list_processes()
        except Exception as e:
            logger.error(f"list_processes failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def list_applications() -> List[Dict[str, Any]]:
        """列出设备上所有已安装的应用

        返回应用列表，每个应用包含 identifier（包名）、name、pid 字段。
        pid 为 0 表示应用未运行。
        """
        try:
            return frida_client.list_applications()
        except Exception as e:
            logger.error(f"list_applications failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def spawn_app(
        package: str,
        paused: bool = True,
    ) -> Dict[str, Any]:
        """启动一个应用（spawn 模式）

        Args:
            package: 应用包名，例如 com.example.app
            paused: 是否在启动时暂停（默认 True，便于在启动早期注入 Hook）

        Returns:
            包含 pid、session_id、package 的字典
        """
        try:
            return frida_client.spawn(package, paused)
        except Exception as e:
            logger.error(f"spawn_app failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def attach_process(target: Union[int, str]) -> Dict[str, Any]:
        """附加到正在运行的进程

        Args:
            target: 进程 PID（整数）或进程名/包名（字符串）

        Returns:
            包含 pid、session_id、name 的字典
        """
        try:
            return frida_client.attach(target)
        except Exception as e:
            logger.error(f"attach_process failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def resume_process(pid: int) -> Dict[str, Any]:
        """恢复暂停的进程

        在 spawn_app(paused=True) 之后调用此函数让应用继续运行。

        Args:
            pid: 进程 PID

        Returns:
            操作结果
        """
        try:
            frida_client.resume(pid)
            return {"success": True, "pid": pid}
        except Exception as e:
            logger.error(f"resume_process failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def kill_process(pid: int) -> Dict[str, Any]:
        """杀死指定进程

        Args:
            pid: 进程 PID

        Returns:
            操作结果
        """
        try:
            frida_client.kill(pid)
            return {"success": True, "pid": pid}
        except Exception as e:
            logger.error(f"kill_process failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def list_sessions() -> List[Dict[str, Any]]:
        """列出所有 Frida 会话及其生命周期状态

        返回每个会话的详细信息，包括：
        - id / pid / name
        - state: created / attached / detached / error / expired
        - scripts: 已加载脚本列表
        - hooks: 已注册 Hook 列表
        - created_at / attached_at / detached_at
        - last_active_at / idle_seconds: 用于判断空闲超时
        - detach_reason: 分离原因（进程退出/崩溃等）
        - ref_count: 引用计数（会话复用场景）
        """
        try:
            from ..core.session_manager import session_manager
            return session_manager.list_sessions()
        except Exception as e:
            logger.error(f"list_sessions failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def close_session(session_id: str, force: bool = False) -> Dict[str, Any]:
        """关闭指定会话，释放 Frida 资源

        会话采用引用计数机制：当多个调用者复用同一会话时，
        仅当引用计数降为 0 才真正分离。设置 force=True 可强制关闭。

        Args:
            session_id: 会话 ID
            force: 是否强制关闭（忽略引用计数）

        Returns:
            操作结果
        """
        try:
            from ..core.session_manager import session_manager
            success = session_manager.close_session(session_id, force=force)
            return {"success": success, "session_id": session_id, "force": force}
        except Exception as e:
            logger.error(f"close_session failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def close_all_sessions() -> Dict[str, Any]:
        """关闭所有活跃会话

        用于清理资源或重置状态。会关闭所有 Frida 会话并卸载脚本。

        Returns:
            操作结果，包含关闭的会话数量
        """
        try:
            from ..core.session_manager import session_manager
            count = len(session_manager.list_sessions())
            session_manager.close_all()
            return {"success": True, "closed_count": count}
        except Exception as e:
            logger.error(f"close_all_sessions failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_system_status() -> Dict[str, Any]:
        """获取系统整体状态

        返回设备连接状态、会话状态、服务器运行时间等信息。
        用于诊断和监控。

        Returns:
            系统状态字典
        """
        try:
            from ..core.session_manager import session_manager
            from ..core.device_manager import device_manager
            return {
                "device": device_manager.get_status(),
                "sessions": session_manager.get_status(),
                "server_info": {
                    "name": "FridaMCP",
                    "version": "1.0.0",
                    "port": config.MCP_PORT,
                },
            }
        except Exception as e:
            logger.error(f"get_system_status failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def reconnect_device() -> Dict[str, Any]:
        """重新连接 Frida 设备

        当设备连接断开或异常时，强制重新连接。

        Returns:
            操作结果
        """
        try:
            from ..core.device_manager import device_manager
            device = device_manager.refresh()
            return {
                "success": True,
                "device": {
                    "id": device.id,
                    "name": device.name,
                    "type": device.type,
                },
            }
        except Exception as e:
            logger.error(f"reconnect_device failed: {e}")
            return {"error": str(e)}

    logger.info("Process module tools registered")
