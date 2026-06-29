#!/bin/bash
# FridaMCP - 启动脚本
# 启动 MCP 服务器，监听端口 8768

set -e

# 默认配置
HOST="${FRIDAMCP_HOST:-0.0.0.0}"
PORT="${FRIDAMCP_PORT:-8768}"
TRANSPORT="${FRIDAMCP_TRANSPORT:-sse}"
DEVICE_TYPE="${FRIDA_DEVICE_TYPE:-usb}"

# 解析参数
while [ $# -gt 0 ]; do
    case "$1" in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --transport|-t)
            TRANSPORT="$2"
            shift 2
            ;;
        --device-type)
            DEVICE_TYPE="$2"
            shift 2
            ;;
        --stdio)
            TRANSPORT="stdio"
            shift
            ;;
        --help|-h)
            echo "FridaMCP Server Launcher"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --host HOST          Listen host (default: $HOST)"
            echo "  --port PORT          Listen port (default: $PORT)"
            echo "  --transport TYPE     Transport: sse|http|stdio (default: $TRANSPORT)"
            echo "  --device-type TYPE   Frida device: usb|remote|local (default: $DEVICE_TYPE)"
            echo "  --stdio              Use stdio transport (for IDE integration)"
            echo "  --help               Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "FridaMCP Server"
echo "=========================================="
echo "Host:       $HOST"
echo "Port:       $PORT"
echo "Transport:  $TRANSPORT"
echo "Device:     $DEVICE_TYPE"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 启动服务器
export FRIDAMCP_HOST="$HOST"
export FRIDAMCP_PORT="$PORT"
export FRIDA_DEVICE_TYPE="$DEVICE_TYPE"

python -m fridamcp.server \
    --host "$HOST" \
    --port "$PORT" \
    --transport "$TRANSPORT" \
    --device-type "$DEVICE_TYPE"
