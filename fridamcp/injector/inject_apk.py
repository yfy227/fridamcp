#!/usr/bin/env python3
"""
FridaMCP APK 注入器

将 frida-gadget 注入到目标 APK 中，使应用启动时自动加载 Frida。
支持非 root 设备。

用法:
    python inject_apk.py <input.apk> [output.apk] [--arch arm64-v8a] [--use-apktool]
"""

import sys
import os
import argparse
import json

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fridamcp.utils.apk_injector import (
    inject_gadget,
    inject_with_apktool,
    detect_apk_arch,
    GADGET_CONFIG_TEMPLATE,
)
from fridamcp.utils.logger import setup_logging, logger


def main():
    parser = argparse.ArgumentParser(
        description="FridaMCP APK Injector - 将 frida-gadget 注入到 APK"
    )
    parser.add_argument(
        "input_apk",
        help="输入 APK 文件路径",
    )
    parser.add_argument(
        "output_apk",
        nargs="?",
        help="输出 APK 文件路径（默认: <input>_injected.apk）",
    )
    parser.add_argument(
        "--arch", "-a",
        help="指定架构 (arm64-v8a, armeabi-v7a, x86, x86_64)",
    )
    parser.add_argument(
        "--use-apktool",
        action="store_true",
        help="使用 apktool 进行完整注入（推荐，需要安装 apktool）",
    )
    parser.add_argument(
        "--no-sign",
        action="store_true",
        help="不签名 APK",
    )
    parser.add_argument(
        "--application-class",
        help="自定义 Application 类名（仅 apktool 模式）",
    )
    parser.add_argument(
        "--gadget-port",
        type=int,
        default=27042,
        help="gadget 监听端口（默认 27042）",
    )
    parser.add_argument(
        "--gadget-host",
        default="127.0.0.1",
        help="gadget 监听地址（默认 127.0.0.1）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出",
    )

    args = parser.parse_args()

    # 初始化日志
    setup_logging()

    # 设置输出路径
    output_apk = args.output_apk
    if not output_apk:
        base, ext = os.path.splitext(args.input_apk)
        output_apk = f"{base}_injected{ext}"

    # 检测 APK 架构
    archs = detect_apk_arch(args.input_apk)
    logger.info(f"Detected architectures: {archs}")

    # 自定义 gadget 配置
    gadget_config = dict(GADGET_CONFIG_TEMPLATE)
    gadget_config["interaction"]["address"] = args.gadget_host
    gadget_config["interaction"]["port"] = args.gadget_port

    logger.info("=" * 60)
    logger.info("FridaMCP APK Injector")
    logger.info("=" * 60)
    logger.info(f"Input:  {args.input_apk}")
    logger.info(f"Output: {output_apk}")
    logger.info(f"Arch:   {args.arch or 'auto'}")
    logger.info(f"Mode:   {'apktool' if args.use_apktool else 'simple'}")
    logger.info(f"Sign:   {not args.no_sign}")
    logger.info("=" * 60)

    # 执行注入
    if args.use_apktool:
        result = inject_with_apktool(
            args.input_apk,
            output_apk,
            arch=args.arch,
            application_class=args.application_class,
        )
    else:
        result = inject_gadget(
            args.input_apk,
            output_apk,
            arch=args.arch,
            gadget_config=gadget_config,
            sign=not args.no_sign,
        )

    # 输出结果
    print("\n" + "=" * 60)
    if result.get("success"):
        logger.info("✓ Injection succeeded!")
        print(f"\nOutput APK: {result.get('output_apk', output_apk)}")
        print(f"Architectures: {result.get('archs', [])}")
        if result.get("application_class"):
            print(f"Application class: {result['application_class']}")
        if result.get("sign_method"):
            print(f"Sign method: {result['sign_method']}")
        print("\n下一步:")
        print(f"  1. 安装注入后的 APK: adb install {output_apk}")
        print("  2. 启动应用（frida-gadget 会自动加载）")
        print("  3. 使用 frida 连接: frida -U Gadget")
        print("  4. 或通过 FridaMCP 服务器进行 AI 辅助分析")
    else:
        logger.error("✗ Injection failed!")
        print(f"\nError: {result.get('error', 'Unknown error')}")
        if result.get("detail"):
            print(f"Detail: {result['detail']}")
        if result.get("note"):
            print(f"\nNote: {result['note']}")
        sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    main()
