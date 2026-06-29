#!/system/bin/sh
# FridaMCP - Android 端 frida-server 启动脚本
#
# 在 Android 设备上启动 frida-server，提供 Frida 运行环境。
# 需要 root 权限。
#
# 用法:
#   adb push start_frida.sh /data/local/tmp/
#   adb shell "su -c 'sh /data/local/tmp/start_frida.sh'"
#   或
#   adb shell "su -c 'sh /data/local/tmp/start_frida.sh --version 16.5.9'"

set -e

FRIDA_VERSION="${FRIDA_VERSION:-16.5.9}"
FRIDA_HOST="${FRIDA_HOST:-127.0.0.1}"
FRIDA_PORT="${FRIDA_PORT:-27042}"
FRIDA_DIR="/data/local/tmp/frida"
FRIDA_BIN="$FRIDA_DIR/frida-server"
LOG_FILE="/data/local/tmp/frida-server.log"
PID_FILE="/data/local/tmp/frida-server.pid"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() {
    echo "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo "${RED}[ERROR]${NC} $1"
}

# 解析参数
while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            FRIDA_VERSION="$2"
            shift 2
            ;;
        --host)
            FRIDA_HOST="$2"
            shift 2
            ;;
        --port)
            FRIDA_PORT="$2"
            shift 2
            ;;
        --stop)
            if [ -f "$PID_FILE" ]; then
                PID=$(cat "$PID_FILE")
                if kill -0 "$PID" 2>/dev/null; then
                    kill "$PID"
                    info "Frida server stopped (pid=$PID)"
                fi
                rm -f "$PID_FILE"
            else
                warn "Frida server not running"
            fi
            exit 0
            ;;
        --status)
            if [ -f "$PID_FILE" ]; then
                PID=$(cat "$PID_FILE")
                if kill -0 "$PID" 2>/dev/null; then
                    info "Frida server running (pid=$PID)"
                    exit 0
                fi
            fi
            warn "Frida server not running"
            exit 1
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --version VERSION  Frida server version (default: $FRIDA_VERSION)"
            echo "  --host HOST        Listen host (default: $FRIDA_HOST)"
            echo "  --port PORT        Listen port (default: $FRIDA_PORT)"
            echo "  --stop             Stop frida server"
            echo "  --status           Check frida server status"
            echo "  --help             Show this help"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# 检查 root 权限
if [ "$(id -u)" != "0" ]; then
    error "This script requires root. Run with: su -c 'sh $0'"
    exit 1
fi

# 检测架构
ARCH=$(uname -m)
case "$ARCH" in
    aarch64)
        FRIDA_ARCH="arm64"
        ;;
    armv7l|armv8l)
        FRIDA_ARCH="arm"
        ;;
    x86_64)
        FRIDA_ARCH="x86_64"
        ;;
    i686|i386)
        FRIDA_ARCH="x86"
        ;;
    *)
        error "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac
info "Detected architecture: $ARCH -> $FRIDA_ARCH"

# 创建目录
mkdir -p "$FRIDA_DIR"

# 检查 frida-server 是否存在
if [ ! -f "$FRIDA_BIN" ]; then
    error "Frida server not found at $FRIDA_BIN"
    echo ""
    echo "Please install frida-server first:"
    echo "  1. Download from: https://github.com/frida/frida/releases"
    echo "     File: frida-server-${FRIDA_VERSION}-android-${FRIDA_ARCH}.xz"
    echo "  2. Push to device:"
    echo "     adb push frida-server-${FRIDA_VERSION}-android-${FRIDA_ARCH} /data/local/tmp/frida/frida-server"
    echo "  3. Set executable:"
    echo "     adb shell 'su -c \"chmod 755 /data/local/tmp/frida/frida-server\"'"
    echo ""
    echo "Or use the install_frida.sh script."
    exit 1
fi

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        warn "Frida server already running (pid=$PID)"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# 设置可执行权限
chmod 755 "$FRIDA_BIN"

info "Starting frida-server..."
info "  Version: $FRIDA_VERSION"
info "  Binary:  $FRIDA_BIN"
info "  Host:    $FRIDA_HOST"
info "  Port:    $FRIDA_PORT"
info "  Log:     $LOG_FILE"

# 启动 frida-server
nohup "$FRIDA_BIN" \
    -l "$FRIDA_HOST:$FRIDA_PORT" \
    > "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"

# 等待启动
sleep 2

if kill -0 "$PID" 2>/dev/null; then
    info "Frida server started successfully (pid=$PID)"
    info ""
    info "Now you can connect from PC:"
    info "  frida -U -l script.js"
    info "  frida-ps -U"
    info ""
    info "Or via FridaMCP server on port 8768"
else
    error "Frida server failed to start. Check log: $LOG_FILE"
    cat "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
