"""
FridaMCP 配置模块

集中管理所有配置项，支持环境变量覆盖。
监听端口固定为 8768（可通过环境变量 FRIDAMCP_PORT 覆盖）。
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """FridaMCP 全局配置"""

    # ===== MCP 服务器配置 =====
    # 监听端口（默认 8768，与项目要求一致）
    MCP_HOST: str = field(
        default_factory=lambda: os.getenv("FRIDAMCP_HOST", "0.0.0.0")
    )
    MCP_PORT: int = field(
        default_factory=lambda: int(os.getenv("FRIDAMCP_PORT", "8768"))
    )
    # MCP 服务器路径
    MCP_PATH: str = "/mcp"

    # ===== 持久性与可靠性配置 =====
    # 设备重连最大重试次数
    DEVICE_RECONNECT_MAX_RETRIES: int = field(
        default_factory=lambda: int(os.getenv("FRIDAMCP_RECONNECT_RETRIES", "5"))
    )
    # 设备重连间隔（秒）
    DEVICE_RECONNECT_INTERVAL: float = field(
        default_factory=lambda: float(os.getenv("FRIDAMCP_RECONNECT_INTERVAL", "2.0"))
    )
    # 会话保活检查间隔（秒，0 表示禁用）
    SESSION_KEEPALIVE_INTERVAL: float = field(
        default_factory=lambda: float(os.getenv("FRIDAMCP_KEEPALIVE_INTERVAL", "30.0"))
    )
    # 会话空闲超时（秒，0 表示永不超时）
    # 空闲超过此值的会话会被保活线程自动分离回收
    SESSION_IDLE_TIMEOUT: float = field(
        default_factory=lambda: float(os.getenv("FRIDAMCP_SESSION_IDLE_TIMEOUT", "600.0"))
    )
    # 会话操作锁获取超时（秒，0 表示阻塞等待）
    # 防止多 AI 并发调用同一会话时无限等待
    SESSION_LOCK_TIMEOUT: float = field(
        default_factory=lambda: float(os.getenv("FRIDAMCP_SESSION_LOCK_TIMEOUT", "30.0"))
    )
    # 优雅关闭超时（秒）
    GRACEFUL_SHUTDOWN_TIMEOUT: float = field(
        default_factory=lambda: float(os.getenv("FRIDAMCP_SHUTDOWN_TIMEOUT", "10.0"))
    )
    # 服务器自动重启最大次数（0 表示不自动重启）
    SERVER_AUTO_RESTART_MAX: int = field(
        default_factory=lambda: int(os.getenv("FRIDAMCP_AUTO_RESTART_MAX", "3"))
    )

    # ===== MCP 传输层配置 =====
    # 传输方式: stdio / sse / streamable_http
    # stdio: 本地工具标准方式（Claude Desktop / Cursor 推荐），延迟最低
    # sse: 远程调用，Server-Sent Events
    # streamable_http: 远程调用，HTTP 流式传输
    MCP_TRANSPORT: str = field(
        default_factory=lambda: os.getenv("FRIDAMCP_TRANSPORT", "stdio")
    )

    # ===== Frida 配置 =====
    # 设备类型: usb / remote / local
    FRIDA_DEVICE_TYPE: str = field(
        default_factory=lambda: os.getenv("FRIDA_DEVICE_TYPE", "usb")
    )
    # 设备 ID（None 表示自动选择第一个可用设备）
    FRIDA_DEVICE_ID: Optional[str] = field(
        default_factory=lambda: os.getenv("FRIDA_DEVICE_ID") or None
    )
    # 远程设备地址（当 FRIDA_DEVICE_TYPE=remote 时使用）
    FRIDA_REMOTE_HOST: str = field(
        default_factory=lambda: os.getenv("FRIDA_REMOTE_HOST", "127.0.0.1")
    )
    FRIDA_REMOTE_PORT: int = field(
        default_factory=lambda: int(os.getenv("FRIDA_REMOTE_PORT", "27042"))
    )

    # ===== 脚本执行配置 =====
    # 脚本执行超时（秒）
    SCRIPT_TIMEOUT: int = field(
        default_factory=lambda: int(os.getenv("FRIDAMCP_SCRIPT_TIMEOUT", "30"))
    )
    # 最大并发会话数
    MAX_SESSIONS: int = field(
        default_factory=lambda: int(os.getenv("FRIDAMCP_MAX_SESSIONS", "10"))
    )

    # ===== 日志配置 =====
    LOG_LEVEL: str = field(
        default_factory=lambda: os.getenv("FRIDAMCP_LOG_LEVEL", "INFO")
    )
    LOG_FILE: Optional[str] = field(
        default_factory=lambda: os.getenv("FRIDAMCP_LOG_FILE") or None
    )
    # 日志缓冲区大小（条数）
    LOG_BUFFER_SIZE: int = field(
        default_factory=lambda: int(os.getenv("FRIDAMCP_LOG_BUFFER_SIZE", "1000"))
    )

    # ===== APK 注入器配置 =====
    # frida-gadget 二进制目录
    GADGET_DIR: str = field(
        default_factory=lambda: os.getenv(
            "FRIDAMCP_GADGET_DIR",
            os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "injector",
                "frida_gadget",
            ),
        )
    )
    # 注入后的 APK 签名配置
    SIGN_KEYSTORE: Optional[str] = field(
        default_factory=lambda: os.getenv("FRIDAMCP_SIGN_KEYSTORE") or None
    )
    SIGN_KEY_ALIAS: str = field(
        default_factory=lambda: os.getenv("FRIDAMCP_SIGN_KEY_ALIAS", "fridamcp")
    )
    SIGN_KEY_PASSWORD: str = field(
        default_factory=lambda: os.getenv("FRIDAMCP_SIGN_KEY_PASSWORD", "fridamcp")
    )

    # ===== 网络捕获配置 =====
    # 最大捕获条目数
    NETWORK_CAPTURE_LIMIT: int = field(
        default_factory=lambda: int(os.getenv("FRIDAMCP_NET_CAPTURE_LIMIT", "5000"))
    )

    # ===== UI 自动化配置 =====
    # 截图保存目录
    SCREENSHOT_DIR: str = field(
        default_factory=lambda: os.getenv(
            "FRIDAMCP_SCREENSHOT_DIR", "/tmp/fridamcp_screenshots"
        )
    )

    @property
    def frida_device_spec(self) -> str:
        """获取 Frida 设备标识符"""
        if self.FRIDA_DEVICE_TYPE == "remote":
            return f"remote@{self.FRIDA_REMOTE_HOST}:{self.FRIDA_REMOTE_PORT}"
        elif self.FRIDA_DEVICE_ID:
            return self.FRIDA_DEVICE_ID
        else:
            return self.FRIDA_DEVICE_TYPE

    def update(self, **kwargs):
        """就地更新配置项（供 CLI 参数覆盖使用）

        仅更新非 None 的值，避免覆盖环境变量默认值。
        """
        for key, value in kwargs.items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)


# 全局配置单例
config = Config()
