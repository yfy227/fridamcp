#!/data/data/com.termux/files/usr/bin/bash
# FridaMCP 桌面快捷方式（由 termux_setup.sh 部署到 ~/.shortcuts/）
#
# 依赖: Termux:Widget 应用
# 部署后: 桌面长按 → 小部件(W) → Termux:Shortcut → 选择 FridaMCP
#
# 行为: 点击桌面图标 → 后台启动服务 → 自动弹出通知提示访问地址。
#       若已在运行则直接提示。全程无需打开终端。

PROJECT_ROOT="$HOME/fridamcp"
if [ ! -d "$PROJECT_ROOT" ] && [ -d "$HOME/storage/shared/fridamcp" ]; then
    PROJECT_ROOT="$HOME/storage/shared/fridamcp"
fi

URL="http://127.0.0.1:7860"

termux-toast() {
    # 优先用 termux-api（若装了 Termux:API），否则降级 notify
    if command -v termux-toast >/dev/null 2>&1; then
        command termux-toast "$1"
    else
        echo "$1" > "$HOME/.fridamcp_last_msg"
    fi
}

# 已在运行 → 直接提示并打开浏览器
if curl -s -m 3 "$URL" >/dev/null 2>&1; then
    termux-toast "FridaMCP 已在运行"
    command -v termux-open-url >/dev/null 2>&1 && termux-open-url "$URL"
    exit 0
fi

termux-toast "FridaMCP 启动中..."

nohup python "$PROJECT_ROOT/app.py" \
    --no-browser --host 0.0.0.0 --port 7860 --mcp \
    >> "$HOME/fridamcp_widget.log" 2>&1 &

# 等待就绪（最多 40s，首次依赖加载较慢）
for _ in $(seq 1 20); do
    if curl -s -m 3 "$URL" >/dev/null 2>&1; then
        termux-toast "FridaMCP 已就绪 ✅"
        command -v termux-open-url >/dev/null 2>&1 && termux-open-url "$URL"
        exit 0
    fi
    sleep 2
done

termux-toast "FridaMCP 启动失败，查看 fridamcp_widget.log"
