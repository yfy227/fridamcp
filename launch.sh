#!/bin/bash
# FridaMCP GUI 一键启动脚本
# 用法: ./launch.sh [选项]
#   --mcp          同时启动 MCP 服务器
#   --port 8080    指定 GUI 端口
#   --device usb   指定设备类型
#   --no-browser   不自动打开浏览器（Termux/无头环境）
#
# 移动端: 启动后用手机浏览器访问 http://<本机IP>:<端口>，
#         并"添加到主屏幕"获得 App 式全屏体验

cd "$(dirname "$0")"

echo "=========================================="
echo "FridaMCP GUI 启动中..."
echo "=========================================="

python3 app.py "$@"
