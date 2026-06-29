"""
UI 自动化模块

提供点击、输入文本、截图、UI 元素列表等工具，通过 adb 实现。
"""

import os
import time
import base64
import subprocess
from typing import Dict, Any, List, Optional

from ..config import config
from ..utils.logger import logger


def _run_adb_shell(cmd: str, device: Optional[str] = None) -> str:
    """执行 adb shell 命令"""
    args = []
    if device:
        args.extend(["-s", device])
    args.extend(["shell", cmd])
    result = subprocess.run(
        ["adb"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"adb shell failed: {result.stderr}")
    return result.stdout


def _run_adb(args: List[str]) -> subprocess.CompletedProcess:
    """执行 adb 命令"""
    return subprocess.run(
        ["adb"] + args,
        capture_output=True,
        timeout=30,
    )


def register_tools(mcp):
    """向 MCP 服务器注册 UI 自动化工具"""

    @mcp.tool()
    def tap(
        x: int,
        y: int,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在屏幕指定坐标点击

        Args:
            x: X 坐标
            y: Y 坐标
            device: 设备序列号（可选）

        Returns:
            操作结果
        """
        try:
            _run_adb_shell(f"input tap {x} {y}", device)
            return {"success": True, "x": x, "y": y}
        except Exception as e:
            logger.error(f"tap failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def swipe(
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: int = 300,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """滑动屏幕

        Args:
            x1: 起点 X
            y1: 起点 Y
            x2: 终点 X
            y2: 终点 Y
            duration: 滑动时长（毫秒，默认 300）
            device: 设备序列号（可选）

        Returns:
            操作结果
        """
        try:
            _run_adb_shell(
                f"input swipe {x1} {y1} {x2} {y2} {duration}", device
            )
            return {"success": True, "from": [x1, y1], "to": [x2, y2]}
        except Exception as e:
            logger.error(f"swipe failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def input_text(
        text: str,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输入文本

        注意：不支持中文等非 ASCII 字符，需要使用输入法输入。

        Args:
            text: 要输入的文本
            device: 设备序列号（可选）

        Returns:
            操作结果
        """
        try:
            # 转义特殊字符
            escaped = text.replace(" ", "%s").replace("&", "\\&")
            escaped = escaped.replace("<", "\\<").replace(">", "\\>")
            escaped = escaped.replace("|", "\\|")
            _run_adb_shell(f'input text "{escaped}"', device)
            return {"success": True, "text": text}
        except Exception as e:
            logger.error(f"input_text failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def press_key(
        keycode: str,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按下按键

        常用 keycode: KEYCODE_HOME, KEYCODE_BACK, KEYCODE_MENU,
        KEYCODE_ENTER, KEYCODE_VOLUME_UP, KEYCODE_VOLUME_DOWN,
        KEYCODE_POWER

        Args:
            keycode: 按键代码
            device: 设备序列号（可选）

        Returns:
            操作结果
        """
        try:
            _run_adb_shell(f"input keyevent {keycode}", device)
            return {"success": True, "keycode": keycode}
        except Exception as e:
            logger.error(f"press_key failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def screenshot(
        device: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """截取屏幕截图

        Args:
            device: 设备序列号（可选）
            filename: 保存文件名（可选，自动生成）

        Returns:
            包含文件路径和 base64 数据的字典
        """
        try:
            os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)
            if not filename:
                filename = f"screenshot_{int(time.time())}.png"
            local_path = os.path.join(config.SCREENSHOT_DIR, filename)
            remote_path = f"/sdcard/{filename}"

            # 截图到设备
            _run_adb_shell(f"screencap -p {remote_path}", device)

            # 拉取到本地
            args = []
            if device:
                args.extend(["-s", device])
            args.extend(["pull", remote_path, local_path])
            result = _run_adb(args)
            if result.returncode != 0:
                return {"error": result.stderr.decode()}

            # 清理设备上的临时文件
            try:
                _run_adb_shell(f"rm {remote_path}", device)
            except Exception:
                pass

            # 读取为 base64
            with open(local_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode()

            return {
                "success": True,
                "path": local_path,
                "filename": filename,
                "base64": b64_data,
                "size": os.path.getsize(local_path),
            }
        except Exception as e:
            logger.error(f"screenshot failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def list_ui(
        device: Optional[str] = None,
        package: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出当前屏幕的 UI 元素

        通过 uiautomator dump 获取 UI 层次结构。

        Args:
            device: 设备序列号（可选）
            package: 可选，只返回指定包名的元素

        Returns:
            包含 UI XML 和解析后的元素列表
        """
        try:
            remote_path = "/sdcard/ui_dump.xml"
            _run_adb_shell(
                f"uiautomator dump --compressed {remote_path}", device
            )
            output = _run_adb_shell(f"cat {remote_path}", device)

            # 清理
            try:
                _run_adb_shell(f"rm {remote_path}", device)
            except Exception:
                pass

            # 简单解析 XML
            elements = []
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(output)
                for elem in root.iter("node"):
                    bounds = elem.get("bounds", "")
                    el_package = elem.get("package", "")
                    if package and el_package != package:
                        continue
                    elements.append({
                        "index": elem.get("index"),
                        "text": elem.get("text", ""),
                        "resource_id": elem.get("resource-id", ""),
                        "class": elem.get("class", ""),
                        "package": el_package,
                        "content_desc": elem.get("content-desc", ""),
                        "clickable": elem.get("clickable") == "true",
                        "enabled": elem.get("enabled") == "true",
                        "bounds": bounds,
                    })
            except ET.ParseError:
                pass

            return {
                "xml": output,
                "elements": elements,
                "count": len(elements),
            }
        except Exception as e:
            logger.error(f"list_ui failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_current_activity(
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取当前前台 Activity

        Args:
            device: 设备序列号（可选）

        Returns:
            包含 activity、package 信息的字典
        """
        try:
            output = _run_adb_shell(
                "dumpsys activity activities | grep mResumedActivity", device
            )
            # 解析类似: mResumedActivity: ActivityRecord{... com.example.app/.MainActivity ...}
            activity = ""
            package = ""
            if "u0" in output or "ActivityRecord" in output:
                parts = output.split()
                for part in parts:
                    if "/" in part and "." in part:
                        activity = part
                        if "/" in part:
                            package = part.split("/")[0]
                        break
            return {
                "raw": output.strip(),
                "activity": activity,
                "package": package,
            }
        except Exception as e:
            logger.error(f"get_current_activity failed: {e}")
            return {"error": str(e)}

    logger.info("UI automation module tools registered")
