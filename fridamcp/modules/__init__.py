"""
FridaMCP 模块包

包含 8 个 MCP 模块：
- process: 进程管理
- hook: Hook 管理
- memory: 内存检查
- network: 网络监控
- filesystem: 文件系统
- ui_automation: UI 自动化
- crypto: 加密分析
- log: 日志捕获
"""

from . import (
    process,
    hook,
    memory,
    network,
    filesystem,
    ui_automation,
    crypto,
    log,
)

# 所有模块列表
ALL_MODULES = [
    process,
    hook,
    memory,
    network,
    filesystem,
    ui_automation,
    crypto,
    log,
]

__all__ = [
    "process",
    "hook",
    "memory",
    "network",
    "filesystem",
    "ui_automation",
    "crypto",
    "log",
    "ALL_MODULES",
]
