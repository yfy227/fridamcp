"""
FridaMCP 日志工具

基于 loguru 的日志封装，支持文件输出和缓冲区。
"""

import sys
from collections import deque
from typing import Optional

from loguru import logger

from ..config import config


# 全局日志缓冲区，供 log 模块读取
_log_buffer: deque = deque(maxlen=config.LOG_BUFFER_SIZE)


def _buffer_sink(message):
    """loguru sink: 将日志写入缓冲区"""
    _log_buffer.append(message.record)


def setup_logging():
    """初始化日志系统"""
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        level=config.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件输出（可选）
    if config.LOG_FILE:
        logger.add(
            config.LOG_FILE,
            level=config.LOG_LEVEL,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{function}:{line} - {message}"
            ),
            rotation="10 MB",
            retention="7 days",
        )

    # 缓冲区 sink（用于 log 模块读取）
    logger.add(_buffer_sink, level="DEBUG")


def get_log_buffer() -> deque:
    """获取日志缓冲区"""
    return _log_buffer


def clear_log_buffer():
    """清空日志缓冲区"""
    _log_buffer.clear()


# 导出 logger 实例
__all__ = ["logger", "setup_logging", "get_log_buffer", "clear_log_buffer"]
