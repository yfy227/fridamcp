#!/bin/bash
# FridaMCP 桌面独立应用打包脚本
#
# 用法: ./build_desktop.sh
# 产物: dist/FridaMCP (Linux/macOS) 或 dist/FridaMCP.exe (Windows)
#
# 依赖: 打包机需要已安装 fridamcp 运行依赖（pip install -r requirements.txt）
#       脚本会自动补装 pyinstaller 与 pywebview。

set -euo pipefail
cd "$(dirname "$0")"

echo "=========================================="
echo "FridaMCP 桌面应用打包"
echo "=========================================="

# 1. 打包工具（缺失时自动安装）
if ! python3 -c "import PyInstaller" 2>/dev/null && ! python -c "import PyInstaller" 2>/dev/null; then
    echo "[*] 安装 pyinstaller..."
    pip install pyinstaller
fi
python3 -c "import webview" 2>/dev/null || pip install pywebview

# 2. Windows 图标（.ico）
if [ ! -f static/icon.ico ]; then
    echo "[*] 生成 Windows 图标..."
    python3 - <<'EOF'
from PIL import Image
img = Image.open("static/icon-512.png")
img.save("static/icon.ico", sizes=[(256, 256), (128, 128), (64, 64),
                                   (48, 48), (32, 32), (16, 16)])
print("static/icon.ico OK")
EOF
fi

# 3. 打包
echo "[*] PyInstaller 打包中（约 2-5 分钟）..."
pyinstaller --clean -y fridamcp_desktop.spec

# 4. 结果
echo ""
echo "=========================================="
if [ -f dist/FridaMCP ] || [ -f dist/FridaMCP.exe ]; then
    echo "✅ 打包完成"
    ls -lh dist/ | grep -i fridamcp || true
    echo ""
    echo "使用: 双击运行 dist/FridaMCP —— 无终端、无浏览器地址栏，"
    echo "      GUI 与 MCP 服务器已全部内嵌，关闭窗口即退出。"
else
    echo "❌ 打包失败，请检查上方日志"
    exit 1
fi
