# FridaMCP - Android Frida 动态分析平台

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![GUI](https://img.shields.io/badge/GUI-Gradio-green.svg)](https://gradio.app/)
[![MCP](https://img.shields.io/badge/MCP-Port_8768-orange.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 在 Android 设备上运行 Frida，通过 **图形界面 APP** 或 **MCP 协议** 让 AI 便捷地进行动态分析、Hook、内存检查、网络监控等操作。

## 快速开始

### 一键启动 GUI

```bash
# 安装依赖
pip install -r requirements.txt

# 启动图形界面（自动打开浏览器）
python app.py

# 同时启动 GUI + MCP 服务器
python app.py --mcp

# 指定端口
python app.py --port 8080
```

或使用启动脚本：

```bash
./launch.sh --mcp
```

打开浏览器访问 `http://localhost:7860` 即可使用图形界面。

### 🖥️ 桌面独立应用（免终端）

**原生窗口形态**——无终端黑窗、无浏览器地址栏，双击即用，
GUI 与 MCP 服务器全部内嵌，关窗即干净退出：

```bash
# 安装原生窗口支持（可选，强烈推荐）
pip install "fridamcp[desktop]"        # = pywebview

# 启动
python desktop_app.py                  # 或 pip install 后: fridamcp-desktop
```

无 pywebview 时自动降级为系统浏览器模式。

**打包为单文件可执行**（Windows .exe / macOS / Linux）：

```bash
./build_desktop.sh                      # 产出 dist/FridaMCP，双击运行
```

### 📱 手机独立应用（Termux，免终端日常使用）

装一次 `bash android/termux_setup.sh`，之后日常使用**零终端操作**：

- **桌面图标启动**：Termux:Widget 提供 "FridaMCP" 桌面快捷方式，点击后台启动 + 弹通知
- **开机自启**：Termux:Boot 自动后台拉起（含健康检查与自动重启）
- **App 式界面**：浏览器打开后"添加到主屏幕"，全屏 PWA 体验
  （Termux 场景直接访问 `http://127.0.0.1:7860`，即本机）

所需 Termux 配套应用（F-Droid 可装）：Termux:Widget、Termux:Boot、（可选）Termux:API。

### 🌐 局域网访问 / PWA

1. 启动 GUI 后，手机（同一局域网）浏览器访问 `http://<主机IP>:7860`
2. 浏览器菜单选择 **"添加到主屏幕" / "安装应用"**（Android Chrome / iOS Safari 均支持）
3. 从主屏幕图标启动即可获得 **全屏独立 App 体验**（无地址栏、独立任务卡片、
   蓝色主题状态栏）

移动端特性：
- 窄屏（≤768px）自动切换单列布局，按钮/输入框为触控优化尺寸
- 输入框 16px 字号，iOS 聚焦不触发页面缩放
- 长输出（hexdump/日志）自动换行，不撑爆窄屏
- 刘海屏安全区（safe-area）适配
- 无头/Termux 环境用 `python app.py --no-browser` 跳过自动开浏览器

### 功能面板

| 面板 | 功能 |
|------|------|
| **仪表盘** | 设备状态、会话概览、MCP 服务器控制、快速操作 |
| **设备管理** | 设备列表、进程列表、应用列表、启动/附加进程 |
| **Hook 管理** | Java 方法 Hook、Native 函数 Hook、方法追踪、消息查看 |
| **内存检查** | 模块列表、内存读取/写入/搜索、导出函数列表 |
| **网络监控** | SSL/Socket 捕获、HTTP 请求监控 |
| **日志查看** | Logcat 捕获、Frida 消息、服务器日志 |
| **APK 注入** | frida-gadget 注入（无需 root） |
| **设置** | 配置管理、设备重连、会话清理 |

## 架构

```
┌──────────────────────────────────────────────────┐
│              浏览器 GUI (端口 7860)                │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│  │仪表盘│ │设备  │ │Hook  │ │内存  │ │网络  │   │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘   │
└──────────────────┬───────────────────────────────┘
                   │ Gradio
┌──────────────────▼───────────────────────────────┐
│              FridaMCP Core                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Device   │ │ Session  │ │ Frida Client     │ │
│  │ Manager  │ │ Manager  │ │ (8 modules)      │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└──────┬───────────────────────────┬───────────────┘
       │ USB                       │ MCP (端口 8768)
       ▼                           ▼
┌──────────────┐          ┌──────────────┐
│ Android 设备  │          │  AI 客户端    │
│ + Frida      │          │ (Claude等)   │
└──────────────┘          └──────────────┘
```

## MCP 服务器

MCP 服务器监听端口 **8768**，提供 52 个工具供 AI 调用：

```bash
# 仅启动 MCP 服务器（无 GUI）
python -m fridamcp.server --transport sse

# 或通过 GUI 同时启动
python app.py --mcp
```

### Claude Desktop 配置

```json
{
  "mcpServers": {
    "fridamcp": {
      "command": "python",
      "args": ["-m", "fridamcp.server", "--stdio"],
      "env": {
        "FRIDA_DEVICE_TYPE": "usb"
      }
    }
  }
}
```

## Android 设备准备

### Root 设备（推荐）

```bash
# 一键安装 frida-server
./android/install_frida.sh

# 验证
frida-ps -U
```

### 无 Root 设备

使用 APK 注入器将 frida-gadget 注入目标 APK：

```bash
python injector/inject_apk.py app.apk app_injected.apk --use-apktool
```

## 项目结构

```
fridamcp/
├── app.py                    # GUI 入口（一键启动）
├── launch.sh                 # 启动脚本
├── fridamcp/                 # 核心包
│   ├── config.py             # 配置管理
│   ├── server.py             # MCP 服务器
│   ├── core/                 # 核心组件
│   │   ├── device_manager.py # 设备管理（自动重连）
│   │   ├── session_manager.py# 会话管理（状态追踪）
│   │   └── frida_client.py   # Frida 客户端封装
│   ├── modules/              # 8 个功能模块（52 个工具）
│   │   ├── process.py        # 进程管理
│   │   ├── hook.py           # Hook 管理
│   │   ├── memory.py         # 内存检查
│   │   ├── network.py        # 网络监控
│   │   ├── filesystem.py     # 文件系统
│   │   ├── ui_automation.py  # UI 自动化
│   │   ├── crypto.py         # 加密分析
│   │   └── log.py            # 日志捕获
│   └── utils/                # 工具
│       ├── logger.py         # 日志系统
│       └── apk_injector.py   # APK 注入器
├── injector/                 # APK 注入工具
├── android/                  # Android 端脚本
├── docs/                     # 文档
└── requirements.txt
```

## 许可证

MIT License
