#!/bin/bash
# FridaMCP - 环境设置脚本
# 安装所有依赖

set -e

echo "=========================================="
echo "FridaMCP Environment Setup"
echo "=========================================="

# 检查 Python 版本
echo ""
echo "[1/4] Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found. Please install Python 3.9+."
    exit 1
fi

VERSION=$($PYTHON --version 2>&1 | cut -d' ' -f2)
echo "Python version: $VERSION"

# 安装依赖
echo ""
echo "[2/4] Installing Python dependencies..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
pip install -r requirements.txt
echo "Dependencies installed."

# 检查 adb
echo ""
echo "[3/4] Checking adb..."
if ! command -v adb &> /dev/null; then
    echo "WARNING: adb not found. Install Android Platform Tools for device interaction."
else
    echo "adb found: $(adb --version | head -1)"
fi

# 检查 frida
echo ""
echo "[4/4] Checking frida..."
if ! command -v frida &> /dev/null; then
    echo "WARNING: frida CLI not found. It will be available after pip install."
else
    echo "frida version: $(frida --version)"
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Connect Android device with USB debugging"
echo "  2. Install frida-server on device: ./android/install_frida.sh"
echo "  3. Start MCP server: ./scripts/run.sh"
echo "  4. Connect AI client to MCP port 8768"
echo ""
