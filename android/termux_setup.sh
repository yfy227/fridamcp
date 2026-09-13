#!/data/data/com.termux/files/usr/bin/bash
# FridaMCP 手机端一键安装（Termux）
#
# 用法（只需运行这一次）:
#   bash android/termux_setup.sh
#
# 安装完成后日常使用无需终端：
#   - 方式A: 桌面 "FridaMCP" 快捷方式（Termux:Widget，见 termux_widget_start.sh）
#   - 方式B: 开机自动启动（Termux:Boot，见 termux_boot.sh）
#   - 手机浏览器打开 http://127.0.0.1:7860 → “添加到主屏幕” 获得全屏 App

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# 定位项目根（脚本可在任意目录调用）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "FridaMCP 手机端一键安装 (Termux)"
echo "项目: $PROJECT_ROOT"
echo "=========================================="

# ---------- 1. 基础包 ----------
echo "[1/4] 安装基础依赖..."
pkg update -y -o Dpkg::Options::=--force-confnew || warn "pkg update 跳过"
pkg install -y python clang libffi openssl \
    || fail "基础包安装失败（检查网络与 termux-change-mirror）"

# ---------- 2. frida（Termux 优先用发行版包，失败回退 pip 编译） ----------
echo "[2/4] 安装 frida..."
if pkg install -y frida 2>/dev/null; then
    info "frida (termux 包)"
elif pip install frida 2>/dev/null; then
    info "frida (pip)"
else
    warn "frida python 绑定安装失败——尝试社区仓库:"
    warn "  pkg install tur-repo && pkg install python-frida"
    warn "  安装后重新运行本脚本"
    exit 1
fi

# ---------- 3. Python 依赖 ----------
echo "[3/4] 安装 Python 依赖..."
pip install -r requirements.txt || fail "pip 依赖安装失败"

# ---------- 4. 部署免终端入口 ----------
echo "[4/4] 部署桌面快捷方式与自启动..."

# Termux:Widget 快捷方式（桌面长按 → Widgets → Termux shortcut）
mkdir -p ~/.shortcuts
cp android/termux_widget_start.sh ~/.shortcuts/FridaMCP
chmod +x ~/.shortcuts/FridaMCP
info "桌面快捷方式: 长按桌面 → 小部件 → Termux:Shortcut → FridaMCP"

# Termux:Boot 开机自启（安装 Termux:Boot 应用后生效）
mkdir -p ~/.termux/boot
cp android/termux_boot.sh ~/.termux/boot/fridamcp-boot
chmod +x ~/.termux/boot/fridamcp-boot
info "开机自启: 已安装到 ~/.termux/boot/（需 Termux:Boot 应用并打开一次）"

# adb（设备本体调试时可选）
command -v adb >/dev/null || pkg install -y android-tools 2>/dev/null \
    || warn "adb 未安装（本机分析场景通常不需要）"

echo ""
echo "=========================================="
info "安装完成！日常使用方式："
echo "  A. 桌面点击 FridaMCP 快捷方式（首次需安装 Termux:Widget）"
echo "  B. 重启手机后服务自动运行（需安装 Termux:Boot 并打开一次）"
echo "  C. 浏览器访问 http://127.0.0.1:7860 → 添加到主屏幕"
echo ""
echo "  Termux 商店应用: F-Droid 搜索 Termux:Widget / Termux:Boot"
echo "=========================================="
