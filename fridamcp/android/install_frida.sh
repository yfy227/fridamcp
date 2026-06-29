#!/bin/bash
# FridaMCP - frida-server 安装脚本 (在 PC 上运行)
#
# 自动下载并安装 frida-server 到已连接的 Android 设备。
#
# 用法:
#   ./install_frida.sh [version] [arch]
#   ./install_frida.sh 16.5.9 arm64
#   ./install_frida.sh 16.5.9  # 自动检测架构

set -e

FRIDA_VERSION="${1:-16.5.9}"
ARCH="${2:-}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 检查 adb
if ! command -v adb &> /dev/null; then
    error "adb not found. Please install Android Platform Tools."
    exit 1
fi

# 检查设备连接
step "Checking connected devices..."
DEVICES=$(adb devices | grep -v "List of devices" | grep "device" | wc -l)
if [ "$DEVICES" -eq 0 ]; then
    error "No device connected. Please connect a device with USB debugging enabled."
    exit 1
fi
if [ "$DEVICES" -gt 1 ]; then
    warn "Multiple devices connected. Using the first one."
fi
info "Device connected."

# 检测架构
if [ -z "$ARCH" ]; then
    step "Detecting device architecture..."
    DEVICE_ARCH=$(adb shell getprop ro.product.cpu.abi)
    case "$DEVICE_ARCH" in
        arm64-v8a)
            ARCH="arm64"
            ;;
        armeabi-v7a|armeabi)
            ARCH="arm"
            ;;
        x86_64)
            ARCH="x86_64"
            ;;
        x86)
            ARCH="x86"
            ;;
        *)
            error "Unsupported architecture: $DEVICE_ARCH"
            exit 1
            ;;
    esac
    info "Detected: $DEVICE_ARCH -> $ARCH"
fi

# 检查 root
step "Checking root access..."
if ! adb shell "su -c 'id'" 2>/dev/null | grep -q "uid=0"; then
    warn "Root access not available. frida-server requires root."
    warn "You can still use frida-gadget injection (no root needed)."
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 下载 frida-server
DOWNLOAD_URL="https://github.com/frida/frida/releases/download/${FRIDA_VERSION}/frida-server-${FRIDA_VERSION}-android-${ARCH}.xz"
TEMP_FILE="/tmp/frida-server-${FRIDA_VERSION}-android-${ARCH}.xz"
BINARY_FILE="/tmp/frida-server-${FRIDA_VERSION}-android-${ARCH}"

step "Downloading frida-server ${FRIDA_VERSION} (${ARCH})..."
info "URL: $DOWNLOAD_URL"

if [ -f "$TEMP_FILE" ]; then
    warn "Using cached download: $TEMP_FILE"
else
    if command -v wget &> /dev/null; then
        wget -O "$TEMP_FILE" "$DOWNLOAD_URL"
    elif command -v curl &> /dev/null; then
        curl -L -o "$TEMP_FILE" "$DOWNLOAD_URL"
    else
        error "Neither wget nor curl found."
        exit 1
    fi
fi

if [ ! -f "$TEMP_FILE" ]; then
    error "Download failed."
    exit 1
fi
info "Download complete."

# 解压
step "Decompressing..."
if command -v xz &> /dev/null; then
    xz -d -k -f "$TEMP_FILE" -c > "$BINARY_FILE"
elif command -v unxz &> /dev/null; then
    unxz -k -f "$TEMP_FILE"
else
    error "xz not found. Please install xz-utils."
    exit 1
fi
info "Decompressed: $BINARY_FILE"

# 推送到设备
step "Pushing frida-server to device..."
adb shell "su -c 'mkdir -p /data/local/tmp/frida'"
adb push "$BINARY_FILE" /data/local/tmp/frida/frida-server
adb shell "su -c 'chmod 755 /data/local/tmp/frida/frida-server'"
info "Pushed to /data/local/tmp/frida/frida-server"

# 推送启动脚本
step "Pushing start script..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
adb push "$SCRIPT_DIR/start_frida.sh" /data/local/tmp/start_frida.sh
adb shell "su -c 'chmod 755 /data/local/tmp/start_frida.sh'"
info "Start script pushed."

# 启动 frida-server
step "Starting frida-server..."
adb shell "su -c 'sh /data/local/tmp/start_frida.sh --version $FRIDA_VERSION'"

# 验证
step "Verifying..."
sleep 2
if adb shell "su -c 'ps | grep frida-server'" | grep -q frida-server; then
    info "frida-server is running!"
else
    warn "frida-server may not be running. Check log:"
    adb shell "su -c 'cat /data/local/tmp/frida-server.log'"
fi

echo ""
info "========================================"
info "Installation complete!"
info "========================================"
echo ""
echo "Next steps:"
echo "  1. Verify: frida-ps -U"
echo "  2. Start FridaMCP server: python -m fridamcp.server"
echo "  3. Connect AI client to MCP port 8768"
echo ""
echo "To stop frida-server:"
echo "  adb shell \"su -c 'sh /data/local/tmp/start_frida.sh --stop'\""
echo ""
echo "To check status:"
echo "  adb shell \"su -c 'sh /data/local/tmp/start_frida.sh --status'\""
