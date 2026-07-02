"""
APK 注入器工具

将 frida-gadget 注入到目标 APK 中，使应用启动时自动加载 Frida。
支持非 root 设备。
"""

import os
import json
import shutil
import zipfile
import tempfile
import subprocess
from typing import Dict, Any, Optional

from ..config import config
from ..utils.logger import logger


# frida-gadget 配置模板
GADGET_CONFIG_TEMPLATE = {
    "interaction": {
        "type": "listen",
        "address": "127.0.0.1",
        "port": 27042,
        "on_port_conflict": "fail",
        "on_load": "wait",
    },
    "teardown": "full"
}


def get_gadget_path(arch: str) -> Optional[str]:
    """获取指定架构的 frida-gadget 路径

    Args:
        arch: 设备架构 (arm64-v8a, armeabi-v7a, x86, x86_64)

    Returns:
        gadget .so 文件路径
    """
    gadget_dir = config.GADGET_DIR
    if not os.path.isdir(gadget_dir):
        logger.warning(
            f"Gadget directory not found: {gadget_dir}\n"
            f"请下载 frida-gadget 并放置到该目录。下载地址:\n"
            f"  https://github.com/frida/frida/releases\n"
            f"  文件名格式: libfrida-gadget-{arch}.so\n"
            f"  或创建目录: mkdir -p {gadget_dir}"
        )
        return None

    # 查找对应架构的 gadget
    candidates = [
        f"libfrida-gadget-{arch}.so",
        f"frida-gadget-{arch}.so",
        f"libgadget-{arch}.so",
    ]
    for name in candidates:
        path = os.path.join(gadget_dir, name)
        if os.path.exists(path):
            return path

    # 查找子目录
    arch_dir = os.path.join(gadget_dir, arch)
    if os.path.isdir(arch_dir):
        for name in os.listdir(arch_dir):
            if name.endswith(".so") and "gadget" in name.lower():
                return os.path.join(arch_dir, name)

    return None


def detect_apk_arch(apk_path: str) -> list:
    """检测 APK 支持的架构

    Args:
        apk_path: APK 文件路径

    Returns:
        架构列表
    """
    archs = []
    with zipfile.ZipFile(apk_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("lib/") and name.endswith(".so"):
                parts = name.split("/")
                if len(parts) >= 2:
                    arch = parts[1]
                    if arch not in archs:
                        archs.append(arch)
    return archs


def inject_gadget(
    input_apk: str,
    output_apk: str,
    arch: Optional[str] = None,
    gadget_config: Optional[Dict] = None,
    sign: bool = True,
) -> Dict[str, Any]:
    """注入 frida-gadget 到 APK

    Args:
        input_apk: 输入 APK 路径
        output_apk: 输出 APK 路径
        arch: 指定架构（None 则自动检测）
        gadget_config: gadget 配置（None 使用默认）
        sign: 是否签名 APK

    Returns:
        操作结果字典
    """
    if not os.path.exists(input_apk):
        return {"error": f"Input APK not found: {input_apk}"}

    work_dir = tempfile.mkdtemp(prefix="fridamcp_inject_")
    logger.info(f"Working directory: {work_dir}")

    try:
        # 1. 检测架构
        archs = detect_apk_arch(input_apk)
        if not archs:
            return {"error": "No native libraries found in APK (pure Java app)"}

        target_archs = [arch] if arch else archs
        logger.info(f"Target architectures: {target_archs}")

        # 2. 查找 gadget
        gadget_paths = {}
        for a in target_archs:
            gp = get_gadget_path(a)
            if gp is None:
                logger.warning(f"No gadget found for arch: {a}")
                continue
            gadget_paths[a] = gp

        if not gadget_paths:
            return {
                "error": "No frida-gadget binaries found. Please download from "
                         "https://github.com/frida/frida/releases and place in "
                         f"{config.GADGET_DIR}"
            }

        # 3. 解压 APK
        extract_dir = os.path.join(work_dir, "apk")
        os.makedirs(extract_dir)
        with zipfile.ZipFile(input_apk, "r") as zf:
            zf.extractall(extract_dir)
        logger.info("APK extracted")

        # 4. 复制 gadget 到 lib 目录
        for a, gp in gadget_paths.items():
            lib_dir = os.path.join(extract_dir, "lib", a)
            os.makedirs(lib_dir, exist_ok=True)
            dest = os.path.join(lib_dir, "libfrida-gadget.so")
            shutil.copy2(gp, dest)
            logger.info(f"Injected gadget for {a}: {dest}")

            # 写入 gadget 配置
            cfg = gadget_config or GADGET_CONFIG_TEMPLATE
            cfg_path = os.path.join(lib_dir, "libfrida-gadget.config.so")
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)

        # 5. 修改 AndroidManifest.xml 添加 SYSTEM_LOAD_LIBRARY
        # 注意：真正的注入需要修改 smali 代码或使用 apktool 反编译
        # 这里提供说明，实际操作需要 apktool
        manifest_path = os.path.join(extract_dir, "AndroidManifest.xml")
        inject_instructions = (
            "注意：完整注入需要使用 apktool 反编译 APK，"
            "在 Application 类或 MainActivity 的 onCreate 中添加：\n"
            'System.loadLibrary("frida-gadget");\n'
            "然后重新编译并签名。"
        )
        logger.info(inject_instructions)

        # 6. 重新打包 APK
        repacked = os.path.join(work_dir, "repacked.apk")
        with zipfile.ZipFile(repacked, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, extract_dir)
                    zf.write(file_path, arcname)
        logger.info(f"APK repacked: {repacked}")

        # 7. 签名（使用 apksigner 或 jarsigner）
        if sign:
            signed_apk = output_apk
            sign_result = _sign_apk(repacked, signed_apk)
            if not sign_result["success"]:
                return {
                    "error": "Signing failed",
                    "detail": sign_result.get("error"),
                    "unsigned_apk": repacked,
                }
            final_apk = signed_apk
        else:
            shutil.copy2(repacked, output_apk)
            final_apk = output_apk

        return {
            "success": True,
            "input_apk": input_apk,
            "output_apk": final_apk,
            "archs": list(gadget_paths.keys()),
            "gadget_config": gadget_config or GADGET_CONFIG_TEMPLATE,
            "note": inject_instructions,
        }

    except Exception as e:
        logger.error(f"inject_gadget failed: {e}")
        return {"error": str(e)}
    finally:
        # 清理工作目录（保留以便调试）
        pass


def _sign_apk(
    input_apk: str,
    output_apk: str,
) -> Dict[str, Any]:
    """签名 APK

    优先使用 apksigner，其次 jarsigner。
    """
    # 生成临时密钥（如果没有提供）
    keystore = config.SIGN_KEYSTORE
    if not keystore or not os.path.exists(keystore):
        keystore = os.path.join(tempfile.gettempdir(), "fridamcp_debug.keystore")
        if not os.path.exists(keystore):
            logger.info("Generating debug keystore")
            result = subprocess.run(
                [
                    "keytool", "-genkeypair",
                    "-alias", config.SIGN_KEY_ALIAS,
                    "-keyalg", "RSA",
                    "-keysize", "2048",
                    "-validity", "10000",
                    "-keystore", keystore,
                    "-storepass", config.SIGN_KEY_PASSWORD,
                    "-keypass", config.SIGN_KEY_PASSWORD,
                    "-dname", "CN=FridaMCP, OU=Dev, O=FridaMCP, L=NA, ST=NA, C=NA",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return {"success": False, "error": result.stderr}

    # 尝试 apksigner
    try:
        result = subprocess.run(
            [
                "apksigner", "sign",
                "--ks", keystore,
                "--ks-key-alias", config.SIGN_KEY_ALIAS,
                "--ks-pass", f"pass:{config.SIGN_KEY_PASSWORD}",
                "--key-pass", f"pass:{config.SIGN_KEY_PASSWORD}",
                "--out", output_apk,
                input_apk,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info(f"APK signed with apksigner: {output_apk}")
            return {"success": True, "method": "apksigner"}
        logger.warning(f"apksigner failed: {result.stderr}")
    except FileNotFoundError:
        logger.warning("apksigner not found, trying jarsigner")

    # 回退到 jarsigner
    try:
        result = subprocess.run(
            [
                "jarsigner",
                "-keystore", keystore,
                "-storepass", config.SIGN_KEY_PASSWORD,
                "-keypass", config.SIGN_KEY_PASSWORD,
                "-signedjar", output_apk,
                input_apk,
                config.SIGN_KEY_ALIAS,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info(f"APK signed with jarsigner: {output_apk}")
            return {"success": True, "method": "jarsigner"}
        return {"success": False, "error": result.stderr}
    except FileNotFoundError:
        return {
            "success": False,
            "error": "Neither apksigner nor jarsigner found. Please install Android SDK build-tools.",
        }


def inject_with_apktool(
    input_apk: str,
    output_apk: str,
    arch: Optional[str] = None,
    application_class: Optional[str] = None,
) -> Dict[str, Any]:
    """使用 apktool 进行完整注入（推荐）

    此方法会反编译 APK，修改 smali 代码注入 loadLibrary 调用，
    然后重新编译并签名。

    Args:
        input_apk: 输入 APK
        output_apk: 输出 APK
        arch: 架构
        application_class: 自定义 Application 类名（None 则自动检测）

    Returns:
        操作结果
    """
    work_dir = tempfile.mkdtemp(prefix="fridamcp_apktool_")

    try:
        # 1. 反编译
        decompiled = os.path.join(work_dir, "decompiled")
        result = subprocess.run(
            ["apktool", "d", "-f", "-o", decompiled, input_apk],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {"error": f"apktool decode failed: {result.stderr}"}
        logger.info("APK decompiled")

        # 2. 检测架构并复制 gadget
        archs = []
        lib_dir = os.path.join(decompiled, "lib")
        if os.path.isdir(lib_dir):
            archs = os.listdir(lib_dir)

        target_archs = [arch] if arch else archs
        for a in target_archs:
            gp = get_gadget_path(a)
            if gp is None:
                continue
            dest_dir = os.path.join(lib_dir, a)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(gp, os.path.join(dest_dir, "libfrida-gadget.so"))

            # gadget 配置
            cfg_path = os.path.join(dest_dir, "libfrida-gadget.config.so")
            with open(cfg_path, "w") as f:
                json.dump(GADGET_CONFIG_TEMPLATE, f, indent=2)

        # 3. 修改 smali 注入 loadLibrary
        # 查找 Application 类
        manifest = os.path.join(decompiled, "AndroidManifest.xml")
        inject_target = application_class or _find_application_class(manifest)

        if inject_target:
            smali_path = _class_to_smali(decompiled, inject_target)
            if smali_path and os.path.exists(smali_path):
                _patch_smali(smali_path)
                logger.info(f"Patched smali: {smali_path}")
            else:
                logger.warning(f"Application smali not found: {smali_path}")

        # 4. 重新编译
        rebuilt = os.path.join(work_dir, "rebuilt.apk")
        result = subprocess.run(
            ["apktool", "b", "-o", rebuilt, decompiled],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {"error": f"apktool build failed: {result.stderr}"}
        logger.info("APK rebuilt")

        # 5. 签名
        sign_result = _sign_apk(rebuilt, output_apk)
        if not sign_result["success"]:
            return {
                "error": "Signing failed",
                "detail": sign_result.get("error"),
                "unsigned_apk": rebuilt,
            }

        return {
            "success": True,
            "input_apk": input_apk,
            "output_apk": output_apk,
            "archs": target_archs,
            "application_class": inject_target,
            "sign_method": sign_result.get("method"),
        }

    except FileNotFoundError as e:
        return {"error": f"Required tool not found: {e}. Please install apktool."}
    except Exception as e:
        logger.error(f"inject_with_apktool failed: {e}")
        return {"error": str(e)}


def _find_application_class(manifest_path: str) -> Optional[str]:
    """从 AndroidManifest.xml 查找 Application 类名"""
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        app = root.find("application")
        if app is not None:
            name = app.get("{http://schemas.android.com/apk/res/android}name")
            if name:
                return name.lstrip(".")
        return None
    except Exception:
        return None


def _class_to_smali(base_dir: str, class_name: str) -> str:
    """将类名转换为 smali 文件路径"""
    # com.example.app.MyApp -> smali/com/example/app/MyApp.smali
    # 处理多 dex 情况
    parts = class_name.split(".")
    rel_path = os.path.join(*parts) + ".smali"

    # 检查 smali, smali_classes2, smali_classes3 等
    for smali_dir in ["smali", "smali_classes2", "smali_classes3", "smali_classes4"]:
        path = os.path.join(base_dir, smali_dir, rel_path)
        if os.path.exists(path):
            return path
    return os.path.join(base_dir, "smali", rel_path)


def _patch_smali(smali_path: str):
    """在 smali 文件的 onCreate 方法开头注入 loadLibrary 调用"""
    with open(smali_path, "r") as f:
        content = f.read()

    # 查找 onCreate 方法
    onCreate_marker = ".method public onCreate()V"
    if onCreate_marker not in content:
        logger.warning("onCreate not found in smali, trying to add to <clinit>")
        # 添加到静态初始化块
        clinit_marker = ".method static constructor <clinit>()V"
        if clinit_marker not in content:
            # 创建一个
            inject_code = (
                '\n.method static constructor <clinit>()V\n'
                '    .locals 1\n\n'
                '    const-string v0, "frida-gadget"\n\n'
                '    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n\n'
                '    return-void\n'
                '.end method\n'
            )
            content += inject_code
        else:
            # 在现有 clinit 开头插入
            inject_code = (
                '    const-string v0, "frida-gadget"\n\n'
                '    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n\n'
            )
            idx = content.find(clinit_marker) + len(clinit_marker)
            # 找到 .locals 行之后
            locals_end = content.find("\n", idx)
            content = content[:locals_end + 1] + inject_code + content[locals_end + 1:]
    else:
        # 在 onCreate 中插入
        inject_code = (
            '    const-string v0, "frida-gadget"\n\n'
            '    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n\n'
        )
        idx = content.find(onCreate_marker) + len(onCreate_marker)
        # 找到 .locals 行之后
        locals_end = content.find("\n", idx)
        content = content[:locals_end + 1] + inject_code + content[locals_end + 1:]

    with open(smali_path, "w") as f:
        f.write(content)
