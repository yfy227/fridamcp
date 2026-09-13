#!/bin/bash
# FridaMCP GUI 一键启动脚本
# 用法: ./launch.sh [选项]
#   --mcp        同时启动 MCP 服务器
#   --port 8080  指定 GUI 端口
#   --device usb 指定设备类型

cd "$(dirname "$0")"

echo "=========================================="
echo "FridaMCP GUI 启动中..."
echo "=========================================="

python3 app.py "$@"
