#!/data/data/com.termux/files/usr/bin/bash
# FridaMCP 开机自启脚本（由 termux_setup.sh 部署到 ~/.termux/boot/）
#
# 依赖: Termux:Boot 应用（F-Droid / GitHub 下载，安装后打开一次以授权）
#
# 行为: 开机后台启动 FridaMCP（GUI + MCP），
#       日志写入 ~/fridamcp_boot.log，健康检查失败自动重启一次。

#!/data/data/com.termux/files/usr/bin/bash

PROJECT_ROOT="$HOME/fridamcp"
if [ ! -d "$PROJECT_ROOT" ] && [ -d "$HOME/storage/shared/fridamcp" ]; then
    PROJECT_ROOT="$HOME/storage/shared/fridamcp"
fi

LOG="$HOME/fridamcp_boot.log"

{
    echo "[$(date '+%F %T')] fridamcp boot start"
} >> "$LOG"

# 已在运行则不重复启动
if pgrep -f "python.*app\.py" >/dev/null 2>&1; then
    echo "[$(date '+%F %T')] already running, skip" >> "$LOG"
    exit 0
fi

nohup python "$PROJECT_ROOT/app.py" \
    --no-browser \
    --host 0.0.0.0 \
    --port 7860 \
    --mcp \
    >> "$LOG" 2>&1 &

sleep 15

# 健康检查：失败则重启一次
if ! curl -s -m 5 http://127.0.0.1:7860/ >/dev/null 2>&1; then
    echo "[$(date '+%F %T')] health check failed, retrying" >> "$LOG"
    pkill -f "python.*app\.py" 2>/dev/null || true
    sleep 3
    nohup python "$PROJECT_ROOT/app.py" \
        --no-browser --host 0.0.0.0 --port 7860 --mcp \
        >> "$LOG" 2>&1 &
fi

# 日志防膨胀（>1MB 截断）
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 1048576 ]; then
    tail -c 262144 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
