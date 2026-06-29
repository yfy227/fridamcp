#!/usr/bin/env bash
# FridaMCP Build Script
# Builds the standalone executable using PyInstaller
#
# Usage:
#   ./build.sh          # Build for current platform
#   ./build.sh clean    # Clean build artifacts

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Clean mode
if [ "$1" = "clean" ]; then
    info "Cleaning build artifacts..."
    rm -rf build/ dist/ *.egg-info src/*.egg-info
    info "Done."
    exit 0
fi

# Check dependencies
info "Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    error "python3 is not installed."
    exit 1
fi

if ! python3 -c "import PyInstaller" 2>/dev/null; then
    warn "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

if ! python3 -c "import frida" 2>/dev/null; then
    error "frida is not installed. Run: pip install -e ."
    exit 1
fi

if ! python3 -c "import mcp" 2>/dev/null; then
    error "mcp is not installed. Run: pip install -e ."
    exit 1
fi

# Build
info "Building FridaMCP standalone executable..."
info "Platform: $(uname -s) $(uname -m)"
info "Python: $(python3 --version)"

pyinstaller fridamcp.spec --noconfirm

# Verify
if [ -d "dist/fridamcp" ]; then
    info "Build successful!"
    info "Output: dist/fridamcp/fridamcp"
    echo ""
    echo "To run:"
    echo "  ./dist/fridamcp/fridamcp -t stdio      # Local (Claude Desktop)"
    echo "  ./dist/fridamcp/fridamcp -t http -p 8768  # Remote HTTP"
    echo "  ./dist/fridamcp/fridamcp -t sse -p 8768   # Remote SSE"
    echo ""
    echo "To distribute:"
    echo "  tar -czf fridamcp-$(uname -s)-$(uname -m).tar.gz -C dist fridamcp"
else
    error "Build failed!"
    exit 1
fi
