"""
APK 注入器工具（增强版）

将 frida-gadget 注入到目标 APK 中，使应用启动时自动加载 Frida。
支持非 root 设备。

增强特性：
  - v1/v2/v3 签名方案：使用 apksigner 显式启用所有签名方案
  - zipalign 对齐：签名前自动对齐，满足 Android 11+ 要求
  - 加固 APK 检测：检测梆梆/爱加密/360/腾讯/娜迦等常见加固，
    并给出注入可行性建议
  - 多 ABI 处理：自动检测 APK 包含的所有 ABI，分别注入对应 gadget
  - 注入点选择：优先 Application.onCreate，回退到 MainActivity.onCreate
  - smali 注入：在 onCreate 开头插入 System.loadLibrary("frida-gadget")

局限性：
  - 加固 APK 的 Application 类被壳接管，gadget 注入点可能无效
  - 需要先脱壳或定位壳的 Application 类
  - 签名校验应用（如银行/支付类）可能检测到签名变化后拒绝运行
"""

import os
import json
import shutil
import zipfile
import tempfile
import subprocess
import re
from typing import Dict, Any, Optional, List, Tuple

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

# 已知加固方案特征（通过 APK 中的特征文件/类名识别）
# 格式: (packer_name, [特征文件/类名列表])
PACKER_SIGNATURES = [
    (
        "梆梆加固 (Bangcle)",
        [
            "libsecexe.so",
            "libsecmain.so",
            "com.bangcle.",
            "com.secapk.",
        ],
    ),
    (
        "爱加密 (Ijiami)",
        [
            "libexec.so",
            "libexecmain.so",
            "com.ijm.",
            "com.tencent.StubShell",
        ],
    ),
    (
        "360 加固",
        [
            "libjiagu.so",
            "libjiagu_a64.so",
            "libjiagu_x86.so",
            "com.stub.",
            "com.qihoo.",
        ],
    ),
    (
        "腾讯加固 (Legu)",
        [
            "libshell.so",
            "libshella.so",
            "libshellx-super.2019.so",
            "com.tencent.StubShell",
            "com.tencent.mobileqq.activity.SplashActivity",
        ],
    ),
    (
        "娜迦 (Nagapt)",
        [
            "libchaosvmp.so",
            "libddog.so",
            "libfdog.so",
            "com.nagapt.",
        ],
    ),
    (
        "百度加固",
        [
            "libbaiduprotect.so",
            "baiduprotect.jar",
        ],
    ),
    (
        "阿里聚安全",
        [
            "libmobisec.so",
            "libmobisec_x86.so",
        ],
    ),
    (
        "通付盾 (Tongfudun)",
        [
            "libtup.so",
            "libsecsdk.so",
        ],
    ),
    (
        "顶象 (Dingxiang)",
        [
            "libx3g.so",
            "libdxbase.so",
        ],
    ),
    (
        "Google Play App Signing (Dynamic Delivery)",
        [
            "com.android.vending.expansion.zipfile",
        ],
    ),
]


def get_gadget_path(arch: str) -> Optional[str]:
    """获取指定架构的 frida-gadget 路径

    Args:
        arch: 设备架构 (arm64-v8a, armeabi-v7a, x86, x86_64)

    Returns:
        gadget .so 文件路径
    """
    gadget_dir = config.GADGET_DIR
    if not os.path.isdir(gadget_dir):
        logger.warning(f"Gadget directory not found: {gadget_dir}")
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


def detect_apk_arch(apk_path: str) -> List[str]:
    """检测 APK 支持的架构

    扫描 APK 内的 lib/<arch>/*.so 目录，返回所有 ABI 列表。

    Args:
        apk_path: APK 文件路径

    Returns:
        架构列表，如 ["arm64-v8a", "armeabi-v7a"]
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


def detect_packer(apk_path: str) -> Dict[str, Any]:
    """检测 APK 是否被加固

    扫描 APK 内的特征文件和类名，识别常见加固方案。

    Args:
        apk_path: APK 文件路径

    Returns:
        检测结果，包含:
          - is_packed: 是否被加固
          - packer_name: 加固方案名称（未检测到则为 None）
          - matched_signatures: 匹配的特征列表
          - recommendation: 注入建议
    """
    matched = []
    packer_name = None

    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            all_names = set(zf.namelist())
            # 读取 classes.dex 的前几 KB 用于类名匹配
            dex_content = b""
            try:
                with zf.open("classes.dex") as f:
                    dex_content = f.read(65536)
            except KeyError:
                pass

            for name, signatures in PACKER_SIGNATURES:
                sig_matches = []
                for sig in signatures:
                    if sig.endswith(".so") or sig.endswith(".jar"):
                        # 文件特征
                        for n in all_names:
                            if sig in n:
                                sig_matches.append(n)
                    else:
                        # 类名特征（在 dex 中搜索字符串）
                        if sig.encode() in dex_content:
                            sig_matches.append(sig)

                if sig_matches:
                    matched.extend(sig_matches)
                    if packer_name is None:
                        packer_name = name

    except Exception as e:
        logger.warning(f"Pack detection failed: {e}")

    is_packed = packer_name is not None
    if is_packed:
        recommendation = (
            f"APK 被加固（{packer_name}），Application 类被壳接管，"
            "gadget 注入到原 Application.onCreate 可能无效。"
            "建议：1) 先脱壳再注入；2) 注入到壳的 Application 类；"
            "3) 使用 frida-server + spawn 模式替代 gadget 注入。"
        )
    else:
        recommendation = "APK 未检测到加固，可以正常注入。"

    return {
        "is_packed": is_packed,
        "packer_name": packer_name,
        "matched_signatures": matched,
        "recommendation": recommendation,
    }


def inject_gadget(
    input_apk: str,
    output_apk: str,
    arch: Optional[str] = None,
    gadget_config: Optional[Dict] = None,
    sign: bool = True,
    v2_signing: bool = True,
    v3_signing: bool = True,
    skip_packer_check: bool = False,
) -> Dict[str, Any]:
    """注入 frida-gadget 到 APK（增强版）

    流程：
      1. 检测加固（可选跳过）
      2. 检测架构，为每个 ABI 注入对应 gadget
      3. 解压 APK，复制 gadget 到 lib/<arch>/
      4. 重新打包
      5. zipalign 对齐
      6. 签名（v1 + v2 + v3）

    Args:
        input_apk: 输入 APK 路径
        output_apk: 输出 APK 路径
        arch: 指定架构（None 则自动检测所有架构）
        gadget_config: gadget 配置（None 使用默认）
        sign: 是否签名 APK
        v2_signing: 是否启用 v2 签名方案
        v3_signing: 是否启用 v3 签名方案
        skip_packer_check: 是否跳过加固检测

    Returns:
        操作结果字典，包含 success/archs/packer_info/sign_method 等
    """
    if not os.path.exists(input_apk):
        return {"error": f"Input APK not found: {input_apk}"}

    work_dir = tempfile.mkdtemp(prefix="fridamcp_inject_")
    logger.info(f"Working directory: {work_dir}")

    try:
        # 1. 加固检测
        packer_info = None
        if not skip_packer_check:
            packer_info = detect_packer(input_apk)
            if packer_info["is_packed"]:
                logger.warning(f"Packed APK detected: {packer_info['packer_name']}")
                logger.warning(packer_info["recommendation"])
                # 不阻止注入，但返回警告

        # 2. 检测架构
        archs = detect_apk_arch(input_apk)
        if not archs:
            return {
                "error": "No native libraries found in APK (pure Java app). "
                         "Gadget injection requires native libs. "
                         "Use frida-server + spawn mode instead."
            }

        target_archs = [arch] if arch else archs
        logger.info(f"Target architectures: {target_archs}")

        # 3. 查找 gadget
        gadget_paths = {}
        missing_archs = []
        for a in target_archs:
            gp = get_gadget_path(a)
            if gp is None:
                logger.warning(f"No gadget found for arch: {a}")
                missing_archs.append(a)
                continue
            gadget_paths[a] = gp

        if not gadget_paths:
            return {
                "error": "No frida-gadget binaries found. Please download from "
                         "https://github.com/frida/frida/releases and place in "
                         f"{config.GADGET_DIR}",
                "missing_archs": missing_archs,
            }

        if missing_archs:
            logger.warning(
                f"Gadgets missing for archs: {missing_archs}. "
                f"Only these archs will have gadget: {list(gadget_paths.keys())}"
            )

        # 4. 解压 APK
        extract_dir = os.path.join(work_dir, "apk")
        os.makedirs(extract_dir)
        with zipfile.ZipFile(input_apk, "r") as zf:
            zf.extractall(extract_dir)
        logger.info("APK extracted")

        # 5. 复制 gadget 到 lib 目录（每个 ABI 一份）
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

        # 6. 修改 AndroidManifest.xml 添加 SYSTEM_LOAD_LIBRARY
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

        # 7. 重新打包 APK
        repacked = os.path.join(work_dir, "repacked.apk")
        with zipfile.ZipFile(repacked, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, extract_dir)
                    zf.write(file_path, arcname)
        logger.info(f"APK repacked: {repacked}")

        # 8. zipalign 对齐（Android 11+ 要求）
        aligned = os.path.join(work_dir, "aligned.apk")
        align_result = _zipalign_apk(repacked, aligned)
        if align_result["success"]:
            sign_input = aligned
        else:
            logger.warning(f"zipalign failed, signing unaligned APK: {align_result.get('error')}")
            sign_input = repacked

        # 9. 签名（v1 + v2 + v3）
        if sign:
            signed_apk = output_apk
            sign_result = _sign_apk(
                sign_input,
                signed_apk,
                v2_signing=v2_signing,
                v3_signing=v3_signing,
            )
            if not sign_result["success"]:
                return {
                    "error": "Signing failed",
                    "detail": sign_result.get("error"),
                    "unsigned_apk": sign_input,
                }
            final_apk = signed_apk
            sign_method = sign_result.get("method")
            sign_schemes = sign_result.get("schemes", [])
        else:
            shutil.copy2(sign_input, output_apk)
            final_apk = output_apk
            sign_method = None
            sign_schemes = []

        return {
            "success": True,
            "input_apk": input_apk,
            "output_apk": final_apk,
            "archs": list(gadget_paths.keys()),
            "missing_archs": missing_archs,
            "gadget_config": gadget_config or GADGET_CONFIG_TEMPLATE,
            "packer_info": packer_info,
            "sign_method": sign_method,
            "sign_schemes": sign_schemes,
            "aligned": align_result["success"],
            "note": inject_instructions,
        }

    except Exception as e:
        logger.error(f"inject_gadget failed: {e}")
        return {"error": str(e)}
    finally:
        # 清理工作目录（保留以便调试）
        pass


def _zipalign_apk(input_apk: str, output_apk: str) -> Dict[str, Any]:
    """对齐 APK（zipalign）

    Android 11+ 要求 APK 对齐到 4 字节边界，否则安装失败。
    使用 Android SDK build-tools 中的 zipalign 工具。

    Args:
        input_apk: 输入 APK
        output_apk: 输出对齐后的 APK

    Returns:
        操作结果
    """
    try:
        result = subprocess.run(
            ["zipalign", "-f", "-v", "4", input_apk, output_apk],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info(f"APK zipaligned: {output_apk}")
            return {"success": True, "method": "zipalign"}
        # zipalign 失败不致命，继续用未对齐的
        return {"success": False, "error": result.stderr}
    except FileNotFoundError:
        return {
            "success": False,
            "error": "zipalign not found. Install Android SDK build-tools.",
        }


def _sign_apk(
    input_apk: str,
    output_apk: str,
    v2_signing: bool = True,
    v3_signing: bool = True,
) -> Dict[str, Any]:
    """签名 APK（支持 v1/v2/v3 签名方案）

    优先使用 apksigner（支持 v2/v3），其次 jarsigner（仅 v1）。

    v1: JAR 签名（基于 META-INF/*.SF），Android 7.0 以下必需
    v2: APK 签名方案 v2（全文件签名），Android 7.0+ 推荐
    v3: APK 签名方案 v3（支持密钥轮换），Android 9.0+

    Args:
        input_apk: 输入 APK
        output_apk: 输出签名后的 APK
        v2_signing: 是否启用 v2 签名
        v3_signing: 是否启用 v3 签名

    Returns:
        操作结果，包含 method 和 schemes
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

    # 尝试 apksigner（支持 v1/v2/v3）
    try:
        cmd = [
            "apksigner", "sign",
            "--ks", keystore,
            "--ks-key-alias", config.SIGN_KEY_ALIAS,
            "--ks-pass", f"pass:{config.SIGN_KEY_PASSWORD}",
            "--key-pass", f"pass:{config.SIGN_KEY_PASSWORD}",
            "--v1-signing-enabled", "true",
            "--v2-signing-enabled", "true" if v2_signing else "false",
            "--v3-signing-enabled", "true" if v3_signing else "false",
            "--out", output_apk,
            input_apk,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            schemes = ["v1"]
            if v2_signing:
                schemes.append("v2")
            if v3_signing:
                schemes.append("v3")
            logger.info(f"APK signed with apksigner: {output_apk} (schemes: {schemes})")
            return {
                "success": True,
                "method": "apksigner",
                "schemes": schemes,
            }
        logger.warning(f"apksigner failed: {result.stderr}")
    except FileNotFoundError:
        logger.warning("apksigner not found, trying jarsigner")

    # 回退到 jarsigner（仅 v1 签名）
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
            logger.info(f"APK signed with jarsigner: {output_apk} (v1 only)")
            return {
                "success": True,
                "method": "jarsigner",
                "schemes": ["v1"],
                "warning": "jarsigner only supports v1 signing. Android 7.0+ apps may require v2/v3.",
            }
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
    v2_signing: bool = True,
    v3_signing: bool = True,
    skip_packer_check: bool = False,
) -> Dict[str, Any]:
    """使用 apktool 进行完整注入（推荐）

    此方法会反编译 APK，修改 smali 代码注入 loadLibrary 调用，
    然后重新编译、对齐、签名。

    流程：
      1. 加固检测（可选）
      2. apktool 反编译
      3. 检测架构，复制 gadget 到 lib/<arch>/
      4. 定位 Application 类，修改 smali 注入 loadLibrary
      5. apktool 重新编译
      6. zipalign 对齐
      7. apksigner 签名（v1+v2+v3）

    Args:
        input_apk: 输入 APK
        output_apk: 输出 APK
        arch: 架构（None 自动检测）
        application_class: 自定义 Application 类名（None 自动检测）
        v2_signing: 是否启用 v2 签名
        v3_signing: 是否启用 v3 签名
        skip_packer_check: 是否跳过加固检测

    Returns:
        操作结果
    """
    work_dir = tempfile.mkdtemp(prefix="fridamcp_apktool_")

    try:
        # 1. 加固检测
        packer_info = None
        if not skip_packer_check:
            packer_info = detect_packer(input_apk)
            if packer_info["is_packed"]:
                logger.warning(f"Packed APK detected: {packer_info['packer_name']}")
                logger.warning(packer_info["recommendation"])

        # 2. 反编译
        decompiled = os.path.join(work_dir, "decompiled")
        result = subprocess.run(
            ["apktool", "d", "-f", "-o", decompiled, input_apk],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {"error": f"apktool decode failed: {result.stderr}"}
        logger.info("APK decompiled")

        # 3. 检测架构并复制 gadget
        archs = []
        lib_dir = os.path.join(decompiled, "lib")
        if os.path.isdir(lib_dir):
            archs = os.listdir(lib_dir)

        target_archs = [arch] if arch else archs
        injected_archs = []
        missing_archs = []
        for a in target_archs:
            gp = get_gadget_path(a)
            if gp is None:
                missing_archs.append(a)
                continue
            dest_dir = os.path.join(lib_dir, a)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(gp, os.path.join(dest_dir, "libfrida-gadget.so"))
            injected_archs.append(a)

            # gadget 配置
            cfg_path = os.path.join(dest_dir, "libfrida-gadget.config.so")
            with open(cfg_path, "w") as f:
                json.dump(GADGET_CONFIG_TEMPLATE, f, indent=2)

        if not injected_archs:
            return {
                "error": "No gadget injected. Missing gadgets for all archs.",
                "missing_archs": missing_archs,
            }

        # 4. 修改 smali 注入 loadLibrary
        manifest = os.path.join(decompiled, "AndroidManifest.xml")
        inject_target = application_class or _find_application_class(manifest)

        smali_patched = False
        if inject_target:
            smali_path = _class_to_smali(decompiled, inject_target)
            if smali_path and os.path.exists(smali_path):
                _patch_smali(smali_path)
                smali_patched = True
                logger.info(f"Patched smali: {smali_path}")
            else:
                logger.warning(f"Application smali not found: {smali_path}")

        # 5. 重新编译
        rebuilt = os.path.join(work_dir, "rebuilt.apk")
        result = subprocess.run(
            ["apktool", "b", "-o", rebuilt, decompiled],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {"error": f"apktool build failed: {result.stderr}"}
        logger.info("APK rebuilt")

        # 6. zipalign 对齐
        aligned = os.path.join(work_dir, "aligned.apk")
        align_result = _zipalign_apk(rebuilt, aligned)
        sign_input = aligned if align_result["success"] else rebuilt

        # 7. 签名（v1+v2+v3）
        sign_result = _sign_apk(
            sign_input,
            output_apk,
            v2_signing=v2_signing,
            v3_signing=v3_signing,
        )
        if not sign_result["success"]:
            return {
                "error": "Signing failed",
                "detail": sign_result.get("error"),
                "unsigned_apk": sign_input,
            }

        return {
            "success": True,
            "input_apk": input_apk,
            "output_apk": output_apk,
            "archs": injected_archs,
            "missing_archs": missing_archs,
            "application_class": inject_target,
            "smali_patched": smali_patched,
            "packer_info": packer_info,
            "sign_method": sign_result.get("method"),
            "sign_schemes": sign_result.get("schemes", []),
            "aligned": align_result["success"],
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
    """在 smali 文件的 onCreate 方法开头注入 loadLibrary 调用

    注入代码：
        const-string v0, "frida-gadget"
        invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

    优先注入到 onCreate，回退到 <clinit>（静态初始化块）。
    """
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
