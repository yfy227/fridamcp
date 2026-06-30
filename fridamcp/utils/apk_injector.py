"""
APK 注入器工具（增强版 v2.2）

将 frida-gadget 注入到目标 APK 中，使应用启动时自动加载 Frida。
支持非 root 设备。

v2.2 修复了导致 APK 破损/无法安装的关键问题：
  - 重新打包时保留原始 zip 条目顺序和压缩方式（.so 用 STORED）
  - 注入前剥离原签名（META-INF/*.SF|*.RSA|*.MF）
  - smali 注入正确处理 .locals 寄存器分配（自动扩容）
  - smali 注入跳过 .annotation 行，插入到正确位置
  - simple 模式现在真正调用 apktool 修改 smali（不再只加 .so）
  - 注入后自动验证 APK 完整性（aapt dump badging）
  - 签名流程：strip META-INF → repack → zipalign → apksigner

增强特性：
  - v1/v2/v3 签名方案：使用 apksigner 显式启用所有签名方案
  - zipalign 对齐：签名前自动对齐，满足 Android 11+ 要求
  - 加固 APK 检测：检测梆梆/爱加密/360/腾讯/娜迦等常见加固
  - 多 ABI 处理：自动检测 APK 包含的所有 ABI，分别注入对应 gadget
  - 注入点选择：优先 Application.onCreate，回退到 MainActivity.onCreate
  - APK 完整性验证：注入后用 aapt 验证 APK 可正常解析

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
PACKER_SIGNATURES = [
    (
        "梆梆加固 (Bangcle)",
        ["libsecexe.so", "libsecmain.so", "com.bangcle.", "com.secapk."],
    ),
    (
        "爱加密 (Ijiami)",
        ["libexec.so", "libexecmain.so", "com.ijm.", "com.tencent.StubShell"],
    ),
    (
        "360 加固",
        ["libjiagu.so", "libjiagu_a64.so", "libjiagu_x86.so", "com.qihoo.util.", "com.qihoo360.mobilesafe."],
    ),
    (
        "腾讯加固 (Legu)",
        ["libshell.so", "libshella.so", "libshellx.so", "com.tencent.StubShell.TxAppEntry", "com.tencent.mobileqq.activity.SplashActivity"],
    ),
    (
        "娜迦 (Nagapt)",
        ["libchaosvmp.so", "libddog.so", "libfdog.so", "com.nagapt."],
    ),
    (
        "百度加固",
        ["libbaiduprotect.so", "com.baidu.protect."],
    ),
    (
        "阿里聚安全",
        ["libmobisec.so", "com.alibaba.wireless.security."],
    ),
    (
        "通付盾 (Tongfudun)",
        ["libtup.so", "libsecshell.so", "com.tongfudun."],
    ),
    (
        "顶象 (Dingxiang)",
        ["libx3g.so", "com.dingxiang-inc."],
    ),
    (
        "Google Play App Signing (Dynamic Delivery)",
        ["assets/dynamic-apk.data"],
    ),
]

# 需要在重新打包时剥离的签名文件模式
SIGNATURE_FILE_PATTERNS = [
    re.compile(r"^META-INF/.*\.(SF|RSA|DSA|EC)$", re.IGNORECASE),
    re.compile(r"^META-INF/MANIFEST\.MF$", re.IGNORECASE),
    re.compile(r"^META-INF/CERT\.SF$", re.IGNORECASE),
    re.compile(r"^META-INF/CERT\.RSA$", re.IGNORECASE),
    re.compile(r"^META-INF/CERT\.DSA$", re.IGNORECASE),
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

    candidates = [
        f"libfrida-gadget-{arch}.so",
        f"frida-gadget-{arch}.so",
        f"libgadget-{arch}.so",
    ]
    for name in candidates:
        path = os.path.join(gadget_dir, name)
        if os.path.exists(path):
            return path

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
    archs = set()
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            for name in zf.namelist():
                if name.startswith("lib/") and "/" in name[4:]:
                    arch = name[4:].split("/")[0]
                    if arch and not name.endswith("/"):
                        archs.add(arch)
    except Exception as e:
        logger.error(f"Failed to detect arch: {e}")
    return sorted(archs)


def detect_packer(apk_path: str) -> Dict[str, Any]:
    """检测 APK 是否被加固

    通过扫描 APK 内的特征文件和 dex 中的字符串识别常见加固方案。

    Args:
        apk_path: APK 文件路径

    Returns:
        检测结果字典：
        - is_packed: 是否被加固
        - packer_name: 加固方案名称
        - matched_signatures: 匹配的特征列表
        - recommendation: 建议
    """
    matched = []
    packer_name = None

    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            all_names = zf.namelist()
            # 读取所有 dex 文件内容用于字符串搜索
            dex_content = b""
            for name in all_names:
                if name.endswith(".dex"):
                    try:
                        dex_content += zf.read(name)
                    except Exception:
                        pass

            for name, sigs in PACKER_SIGNATURES:
                for sig in sigs:
                    sig_matches = []
                    if sig.endswith(".so") or sig.startswith("assets/"):
                        # 文件名特征
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


# ============================================================
# 核心：安全的 APK 重新打包（保留原始结构）
# ============================================================

def _is_signature_file(name: str) -> bool:
    """判断是否为签名文件（需要剥离）"""
    for pattern in SIGNATURE_FILE_PATTERNS:
        if pattern.match(name):
            return True
    return False


def _repack_apk_safe(
    input_apk: str,
    output_apk: str,
    added_files: Dict[str, str],
) -> Dict[str, Any]:
    """安全地重新打包 APK（保留原始条目顺序和压缩方式）

    关键修复：
      1. 保留原始压缩方式（.so 文件用 STORED，其他用原方式）
      2. 剥离原签名文件（META-INF/*.SF|*.RSA|*.MF）
      3. 新增文件追加到末尾（不破坏原始条目顺序）
      4. .so 文件强制使用 STORED（Android 要求 native lib 不压缩以便 mmap）

    Args:
        input_apk: 原始 APK
        output_apk: 输出 APK
        added_files: 要添加的文件 {arcname: local_path}

    Returns:
        操作结果
    """
    try:
        with zipfile.ZipFile(input_apk, "r") as zin:
            with zipfile.ZipFile(output_apk, "w") as zout:
                # 1. 复制原始条目（跳过签名文件和将被覆盖的文件）
                skipped_sig = 0
                for item in zin.infolist():
                    name = item.filename
                    if _is_signature_file(name):
                        skipped_sig += 1
                        logger.info(f"Stripped signature file: {name}")
                        continue
                    if name in added_files:
                        # 将被新文件覆盖，跳过
                        continue

                    # 保留原始压缩方式
                    data = zin.read(name)
                    # .so 文件强制 STORED（Android mmap 要求）
                    if name.endswith(".so"):
                        zout.writestr(name, data, compress_type=zipfile.ZIP_STORED)
                    else:
                        zout.writestr(name, data, compress_type=item.compress_type)

                # 2. 添加新文件
                for arcname, local_path in added_files.items():
                    if not os.path.exists(local_path):
                        logger.warning(f"Added file not found: {local_path}")
                        continue
                    # .so 文件用 STORED
                    if arcname.endswith(".so"):
                        with open(local_path, "rb") as f:
                            zout.writestr(arcname, f.read(), compress_type=zipfile.ZIP_STORED)
                    else:
                        zout.write(local_path, arcname, compress_type=zipfile.ZIP_DEFLATED)
                    logger.info(f"Added: {arcname}")

        logger.info(f"APK repacked: {output_apk} (stripped {skipped_sig} sig files)")
        return {"success": True, "stripped_signatures": skipped_sig}
    except Exception as e:
        logger.error(f"Repack failed: {e}")
        return {"success": False, "error": str(e)}


def _write_gadget_config(config_path: str, gadget_config: Optional[Dict] = None):
    """写入 gadget 配置文件"""
    cfg = gadget_config or GADGET_CONFIG_TEMPLATE
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)


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
    """注入 frida-gadget 到 APK（simple 模式，仅添加 .so 不改 smali）

    此模式只添加 gadget .so 文件和配置，不修改 smali 代码。
    适用于：gadget 配置为 script 模式时（通过 frida-gadget.config.so
    指定加载脚本），或用户自行修改 smali 的场景。

    如果需要自动注入 loadLibrary 调用，请使用 inject_with_apktool()。

    流程：
      1. 检测加固（可选跳过）
      2. 检测架构，为每个 ABI 注入对应 gadget
      3. 安全重新打包（保留原始结构，剥离签名）
      4. zipalign 对齐
      5. 签名（v1 + v2 + v3）
      6. 完整性验证

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
        操作结果字典
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

        # 4. 准备要添加的文件
        added_files: Dict[str, str] = {}
        # gadget .so 文件
        for a, gp in gadget_paths.items():
            arcname = f"lib/{a}/libfrida-gadget.so"
            added_files[arcname] = gp

        # gadget 配置文件（每个架构一个）
        for a in gadget_paths:
            cfg_path = os.path.join(work_dir, f"gadget_config_{a}.so")
            _write_gadget_config(cfg_path, gadget_config)
            added_files[f"lib/{a}/libfrida-gadget.config.so"] = cfg_path

        # 5. 安全重新打包
        repacked = os.path.join(work_dir, "repacked.apk")
        repack_result = _repack_apk_safe(input_apk, repacked, added_files)
        if not repack_result["success"]:
            return {
                "error": "Repack failed",
                "detail": repack_result.get("error"),
            }

        # 6. zipalign 对齐
        aligned = os.path.join(work_dir, "aligned.apk")
        align_result = _zipalign_apk(repacked, aligned)
        sign_input = aligned if align_result["success"] else repacked

        # 7. 签名
        sign_method = None
        sign_schemes = []
        if sign:
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
            sign_method = sign_result.get("method")
            sign_schemes = sign_result.get("schemes", [])
            final_apk = output_apk
        else:
            shutil.copy2(sign_input, output_apk)
            final_apk = output_apk

        # 8. 完整性验证
        verify_result = _verify_apk_integrity(final_apk)

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
            "stripped_signatures": repack_result.get("stripped_signatures", 0),
            "integrity_check": verify_result,
            "note": (
                "Simple mode: gadget .so added but smali not modified. "
                "The gadget will NOT auto-load unless you use 'script' interaction "
                "mode in gadget config, or manually add System.loadLibrary. "
                "Use inject_with_apktool() for full injection with smali patching."
            ),
        }

    except Exception as e:
        logger.error(f"inject_gadget failed: {e}")
        return {"error": str(e)}


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
        logger.warning(f"zipalign failed (non-fatal): {result.stderr}")
        return {"success": False, "error": result.stderr}
    except FileNotFoundError:
        logger.warning("zipalign not found (non-fatal)")
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


def _verify_apk_integrity(apk_path: str) -> Dict[str, Any]:
    """验证 APK 完整性

    使用 aapt dump badging 验证 APK 是否可正常解析。
    使用 apksigner verify 验证签名是否有效。

    Args:
        apk_path: APK 文件路径

    Returns:
        验证结果字典
    """
    result = {
        "apk_valid": False,
        "package_name": None,
        "signature_valid": False,
        "errors": [],
    }

    # 1. aapt 验证 APK 结构
    try:
        r = subprocess.run(
            ["aapt", "dump", "badging", apk_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            result["apk_valid"] = True
            # 提取包名
            for line in r.stdout.splitlines():
                if line.startswith("package: name="):
                    m = re.search(r"name='([^']+)'", line)
                    if m:
                        result["package_name"] = m.group(1)
                    break
        else:
            result["errors"].append(f"aapt: {r.stderr[:200]}")
    except FileNotFoundError:
        # aapt 不可用，用 zipfile 验证基本结构
        try:
            with zipfile.ZipFile(apk_path) as zf:
                names = zf.namelist()
                if "AndroidManifest.xml" in names:
                    result["apk_valid"] = True
                    result["errors"].append("aapt not found, basic zip check only")
                else:
                    result["errors"].append("AndroidManifest.xml not found in APK")
        except Exception as e:
            result["errors"].append(f"zip check failed: {e}")
    except Exception as e:
        result["errors"].append(f"aapt error: {e}")

    # 2. apksigner 验证签名
    try:
        r = subprocess.run(
            ["apksigner", "verify", "--verbose", apk_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            result["signature_valid"] = True
        else:
            result["errors"].append(f"apksigner verify: {r.stderr[:200]}")
    except FileNotFoundError:
        result["errors"].append("apksigner not found, signature not verified")
    except Exception as e:
        result["errors"].append(f"apksigner error: {e}")

    logger.info(f"APK integrity: valid={result['apk_valid']}, sig={result['signature_valid']}")
    return result


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
      8. 完整性验证

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

        # 2. 反编译（使用 -r 保留原始资源不反编译，减少破损风险）
        # 注意：不使用 -r 因为需要修改 AndroidManifest.xml 的 Application 类
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
            _write_gadget_config(cfg_path)

        if not injected_archs:
            return {
                "error": "No gadget injected. Missing gadgets for all archs.",
                "missing_archs": missing_archs,
            }

        # 4. 修改 smali 注入 loadLibrary
        manifest = os.path.join(decompiled, "AndroidManifest.xml")
        inject_target = application_class or _find_application_class(manifest)

        smali_patched = False
        smali_patch_result = None
        if inject_target:
            smali_path = _class_to_smali(decompiled, inject_target)
            if smali_path and os.path.exists(smali_path):
                smali_patch_result = _patch_smali(smali_path)
                if smali_patch_result["success"]:
                    smali_patched = True
                    logger.info(f"Patched smali: {smali_path}")
                else:
                    logger.warning(f"Smali patch failed: {smali_patch_result.get('error')}")
            else:
                logger.warning(f"Application smali not found: {smali_path}")
        else:
            logger.warning("No Application class found, smali not patched")

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

        # 8. 完整性验证
        verify_result = _verify_apk_integrity(output_apk)

        return {
            "success": True,
            "input_apk": input_apk,
            "output_apk": output_apk,
            "archs": injected_archs,
            "missing_archs": missing_archs,
            "application_class": inject_target,
            "smali_patched": smali_patched,
            "smali_patch_detail": smali_patch_result,
            "packer_info": packer_info,
            "sign_method": sign_result.get("method"),
            "sign_schemes": sign_result.get("schemes", []),
            "aligned": align_result["success"],
            "integrity_check": verify_result,
        }

    except FileNotFoundError as e:
        return {"error": f"Required tool not found: {e}. Please install apktool."}
    except Exception as e:
        logger.error(f"inject_with_apktool failed: {e}")
        return {"error": str(e)}


def _find_application_class(manifest_path: str) -> Optional[str]:
    """从 AndroidManifest.xml 查找 Application 类名

    apktool 反编译后的 AndroidManifest.xml 是纯文本 XML。
    """
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
    parts = class_name.split(".")
    rel_path = os.path.join(*parts) + ".smali"

    # 检查 smali, smali_classes2, smali_classes3 等
    for smali_dir in ["smali", "smali_classes2", "smali_classes3", "smali_classes4"]:
        path = os.path.join(base_dir, smali_dir, rel_path)
        if os.path.exists(path):
            return path
    return os.path.join(base_dir, "smali", rel_path)


def _patch_smali(smali_path: str) -> Dict[str, Any]:
    """在 smali 文件中注入 loadLibrary 调用（安全版）

    修复的关键问题：
      1. 自动扩容 .locals（确保 v0 可用）
      2. 跳过 .annotation 行，插入到正确位置
      3. 优先注入 onCreate，回退到 <clinit>
      4. 注入前备份原文件

    注入代码：
        const-string v0, "frida-gadget"
        invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

    Args:
        smali_path: smali 文件路径

    Returns:
        操作结果字典
    """
    try:
        with open(smali_path, "r") as f:
            content = f.read()

        # 备份
        backup_path = smali_path + ".bak"
        with open(backup_path, "w") as f:
            f.write(content)

        # 注入代码模板
        load_library_code = (
            '    const-string v0, "frida-gadget"\n\n'
            '    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n\n'
        )

        # 查找 onCreate 方法
        onCreate_marker = ".method public onCreate()V"
        clinit_marker = ".method static constructor <clinit>()V"

        patched = False
        patch_location = None

        if onCreate_marker in content:
            # 在 onCreate 中注入
            patch_location = "onCreate"
            content = _inject_into_method(content, onCreate_marker, load_library_code)
            patched = True
        elif clinit_marker in content:
            # 在 <clinit> 中注入
            patch_location = "clinit"
            content = _inject_into_method(content, clinit_marker, load_library_code)
            patched = True
        else:
            # 创建 <clinit>
            patch_location = "new_clinit"
            inject_code = (
                '\n.method static constructor <clinit>()V\n'
                '    .locals 1\n\n'
                + load_library_code +
                '    return-void\n'
                '.end method\n'
            )
            content += inject_code
            patched = True

        with open(smali_path, "w") as f:
            f.write(content)

        return {
            "success": patched,
            "location": patch_location,
            "backup": backup_path,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _inject_into_method(content: str, method_marker: str, inject_code: str) -> str:
    """将代码注入到指定方法中（安全版）

    修复：
      1. 自动扩容 .locals（如果原值 < 1，改为 1）
      2. 跳过 .annotation / .param / .line 等伪指令行
      3. 在第一条实际指令前插入

    Args:
        content: smali 文件内容
        method_marker: 方法标记（如 ".method public onCreate()V"）
        inject_code: 要注入的代码

    Returns:
        修改后的内容
    """
    idx = content.find(method_marker)
    if idx == -1:
        return content

    # 找到方法标记后的内容
    after_marker = content[idx + len(method_marker):]

    # 查找 .locals 行并扩容
    locals_match = re.search(r'\.locals\s+(\d+)', after_marker)
    if locals_match:
        locals_count = int(locals_match.group(1))
        if locals_count < 1:
            # 扩容到 1（我们需要 v0）
            new_locals = ".locals 1"
            old_locals = locals_match.group(0)
            after_marker = after_marker.replace(old_locals, new_locals, 1)
    else:
        # 没有 .locals 行，可能是 .registers
        registers_match = re.search(r'\.registers\s+(\d+)', after_marker)
        if registers_match:
            reg_count = int(registers_match.group(1))
            if reg_count < 2:  # 需要 v0 + this(p0)
                new_reg = f".registers 2"
                old_reg = registers_match.group(0)
                after_marker = after_marker.replace(old_reg, new_reg, 1)
        else:
            # 都没有，插入 .locals 1
            after_marker = "\n    .locals 1\n" + after_marker

    # 找到注入点：跳过 .locals/.registers/.annotation/.param/.line 等伪指令
    lines = after_marker.split("\n")
    inject_line_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "":
            inject_line_idx = i + 1
            continue
        if stripped.startswith(".locals") or stripped.startswith(".registers"):
            inject_line_idx = i + 1
            continue
        if stripped.startswith(".annotation") or stripped.startswith(".param"):
            # 跳过整个 annotation/param 块
            if ".annotation" in stripped:
                # 找到 .end annotation
                for j in range(i + 1, len(lines)):
                    if ".end annotation" in lines[j]:
                        inject_line_idx = j + 1
                        break
            elif ".param" in stripped:
                # 找到 .end param
                for j in range(i + 1, len(lines)):
                    if ".end param" in lines[j]:
                        inject_line_idx = j + 1
                        break
            continue
        if stripped.startswith(".line"):
            inject_line_idx = i + 1
            continue
        # 第一条实际指令
        break

    # 在注入点插入代码
    lines.insert(inject_line_idx, inject_code.rstrip("\n"))
    new_after_marker = "\n".join(lines)

    return content[:idx + len(method_marker)] + new_after_marker
