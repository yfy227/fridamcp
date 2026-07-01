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
