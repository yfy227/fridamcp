"""FridaMCP APK 注入器包。

提供将 frida-gadget 注入目标 APK 的工具，
支持非 root 设备的动态分析。
"""

from .inject_apk import main

__all__ = ["main"]
