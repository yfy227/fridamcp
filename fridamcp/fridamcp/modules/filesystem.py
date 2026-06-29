"""
文件系统模块

提供设备文件列表、读取、推送、拉取等工具，主要通过 adb 操作。
"""

import os
import base64
import subprocess
from typing import Dict, Any, List, Optional

from ..utils.logger import logger


def _run_adb(args: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """执行 adb 命令"""
    cmd = ["adb"] + args
    logger.debug(f"Running: {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        timeout=60,
    )


def _run_adb_shell(cmd: str, device: Optional[str] = None) -> str:
    """执行 adb shell 命令"""
    args = []
    if device:
        args.extend(["-s", device])
    args.extend(["shell", cmd])
    result = _run_adb(args)
    if result.returncode != 0:
        raise RuntimeError(f"adb shell failed: {result.stderr}")
    return result.stdout


def register_tools(mcp):
    """向 MCP 服务器注册文件系统工具"""

    @mcp.tool()
    def list_files(
        path: str = "/sdcard/",
        device: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出设备上的文件和目录

        Args:
            path: 设备上的路径（默认 /sdcard/）
            device: 设备序列号（可选，多设备时使用）

        Returns:
            文件列表，每个条目包含 name、type、size、perms
        """
        try:
            output = _run_adb_shell(f'ls -la "{path}"', device)
            files = []
            for line in output.strip().split("\n")[1:]:  # skip total line
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) < 8:
                    continue
                perms = parts[0]
                size = parts[4]
                name = " ".join(parts[7:])
                ftype = "dir" if perms.startswith("d") else "file"
                if name in (".", ".."):
                    continue
                files.append({
                    "name": name,
                    "type": ftype,
                    "size": int(size) if size.isdigit() else 0,
                    "perms": perms,
                    "path": os.path.join(path, name),
                })
            return files
        except Exception as e:
            logger.error(f"list_files failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def read_file(
        path: str,
        device: Optional[str] = None,
        max_size: int = 65536,
    ) -> Dict[str, Any]:
        """读取设备上的文件内容

        Args:
            path: 设备上的文件路径
            device: 设备序列号（可选）
            max_size: 最大读取字节数（默认 65536）

        Returns:
            包含 path、content、size、encoding 的字典
        """
        try:
            # 先检查文件大小
            size_output = _run_adb_shell(f'stat -c %s "{path}"', device)
            size = int(size_output.strip()) if size_output.strip().isdigit() else 0

            if size > max_size:
                return {
                    "error": f"File too large ({size} bytes), max_size={max_size}",
                    "path": path,
                    "size": size,
                }

            # 读取文件
            output = _run_adb_shell(f'cat "{path}"', device)

            return {
                "path": path,
                "content": output,
                "size": size,
                "encoding": "utf-8",
            }
        except Exception as e:
            logger.error(f"read_file failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def pull_file(
        remote_path: str,
        local_path: str,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从设备拉取文件到本地

        Args:
            remote_path: 设备上的文件路径
            local_path: 本地保存路径
            device: 设备序列号（可选）

        Returns:
            操作结果
        """
        try:
            args = []
            if device:
                args.extend(["-s", device])
            args.extend(["pull", remote_path, local_path])
            result = _run_adb(args)
            if result.returncode != 0:
                return {"error": result.stderr}
            return {
                "success": True,
                "remote_path": remote_path,
                "local_path": local_path,
                "output": result.stdout,
            }
        except Exception as e:
            logger.error(f"pull_file failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def push_file(
        local_path: str,
        remote_path: str,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """推送本地文件到设备

        Args:
            local_path: 本地文件路径
            remote_path: 设备上的目标路径
            device: 设备序列号（可选）

        Returns:
            操作结果
        """
        try:
            if not os.path.exists(local_path):
                return {"error": f"Local file not found: {local_path}"}
            args = []
            if device:
                args.extend(["-s", device])
            args.extend(["push", local_path, remote_path])
            result = _run_adb(args)
            if result.returncode != 0:
                return {"error": result.stderr}
            return {
                "success": True,
                "local_path": local_path,
                "remote_path": remote_path,
                "output": result.stdout,
            }
        except Exception as e:
            logger.error(f"push_file failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def list_app_data(
        package: str,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出应用的私有数据目录

        需要 root 权限。

        Args:
            package: 应用包名
            device: 设备序列号（可选）

        Returns:
            包含路径和文件列表的字典
        """
        try:
            # 获取应用数据路径
            base_path = f"/data/data/{package}"
            try:
                output = _run_adb_shell(
                    f'ls -la "{base_path}"', device
                )
            except RuntimeError:
                # 可能需要 root
                output = _run_adb_shell(
                    f'su -c \'ls -la "{base_path}"\'', device
                )

            files = []
            for line in output.strip().split("\n")[1:]:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) < 8:
                    continue
                perms = parts[0]
                size = parts[4]
                name = " ".join(parts[7:])
                ftype = "dir" if perms.startswith("d") else "file"
                if name in (".", ".."):
                    continue
                files.append({
                    "name": name,
                    "type": ftype,
                    "size": int(size) if size.isdigit() else 0,
                    "perms": perms,
                })
            return {
                "package": package,
                "path": base_path,
                "files": files,
            }
        except Exception as e:
            logger.error(f"list_app_data failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_app_info(
        package: str,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取应用信息

        Args:
            package: 应用包名
            device: 设备序列号（可选）

        Returns:
            应用信息字典
        """
        try:
            output = _run_adb_shell(
                f'dumpsys package {package}', device
            )
            info = {"package": package, "raw": output[:8192]}
            # 解析关键字段
            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("versionName="):
                    info["version_name"] = line.split("=")[1]
                elif line.startswith("versionCode="):
                    info["version_code"] = line.split("=")[1]
                elif "targetSdk" in line:
                    info["target_sdk"] = line.split("=")[-1].strip()
                elif "dataDir=" in line:
                    info["data_dir"] = line.split("dataDir=")[1].strip()
                elif "applicationInfo" in line and "flags" in line:
                    info["flags_line"] = line
            return info
        except Exception as e:
            logger.error(f"get_app_info failed: {e}")
            return {"error": str(e)}

    logger.info("Filesystem module tools registered")
