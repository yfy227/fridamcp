"""
FridaMCP 模块包

包含 9 个 MCP 模块：
- process: 进程管理
- hook: Hook 管理
- memory: 内存检查
- network: 网络监控
- filesystem: 文件系统
- ui_automation: UI 自动化
- crypto: 加密分析
- log: 日志捕获
- script: 自定义脚本执行（核心：让 AI 直接运行 Frida JS 脚本）
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
    script,
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
    script,
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
    "script",
    "ALL_MODULES",
]
