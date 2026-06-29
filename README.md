# FridaMCP - AI-Powered Frida MCP Server for Android

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-green.svg)](https://modelcontextprotocol.io/)
[![Frida](https://img.shields.io/badge/Frida-16+-orange.svg)](https://frida.re/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 在 Android 设备上运行 Frida，并通过 MCP (Model Context Protocol) 服务让 AI 更加便捷地使用 Frida 进行动态分析、Hook、内存检查、网络监控等操作。

## 项目简介

**FridaMCP** 是一个将 Frida 动态插桩工具与 MCP 协议结合的项目，专为 AI 辅助的 Android 应用安全分析而设计。它包含三个核心组件：

1. **Android 端 Frida 运行器** —— 在 Android 设备上启动 `frida-server`，提供 Frida 运行环境。
2. **APK 注入器** —— 将 `frida-gadget` 自动注入到目标 APK 中，使目标应用启动时自动加载 Frida，无需 root 也能使用。
3. **MCP 服务器** —— 监听端口 `8768`，向 AI 客户端暴露一系列 Frida 操作工具，让 AI 可以直接调用 Frida 进行安全分析。

## 工作流程

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  AI Client  │◄───►│  MCP Server      │◄───►│  Android Device │
│ (Claude等)  │ MCP │  (Port 8768)     │ USB │  + Frida Server │
└─────────────┘     └──────────────────┘     └─────────────────┘
                            │                          │
                            │                          ▼
                    ┌───────────────┐          ┌────────────────┐
                    │  MCP Modules  │          │  Target App    │
                    │  (8 modules)  │          │  (Injected)    │
                    └───────────────┘          └────────────────┘
```

1. 在 Android 设备上启动 `frida-server`（root 设备）或使用 APK 注入器注入 `frida-gadget`（非 root 设备）。
2. 启动 MCP 服务器，监听 `8768` 端口。
3. AI 客户端通过 MCP 协议连接服务器，调用各种 Frida 工具。
4. AI 可以列出进程、Hook 方法、读取内存、监控网络、自动化 UI 等。

## 核心特性

- **9 个 MCP 模块**：进程管理、Hook 管理、内存检查、网络监控、文件系统、UI 自动化、加密分析、日志捕获、**自定义脚本执行**
- **直接运行 Frida JS 脚本**：AI 可通过 `run_script` 工具直接编写并执行任意 Frida JavaScript，不再局限于预置模板
- **APK 注入器**：自动将 `frida-gadget` 注入 APK，支持非 root 设备
- **多设备支持**：支持 USB 设备、远程设备、模拟器
- **脚本管理**：内置常用 Frida 脚本模板，支持自定义脚本、RPC 调用、文件加载
- **实时日志**：捕获 Frida 脚本输出和应用日志
- **AI 友好**：所有工具都设计为 AI 易于调用，参数清晰，返回结构化数据

## 快速开始

### 环境要求

- Python 3.9+
- Android 设备（root 或非 root 均可）
- USB 数据线（或通过网络连接）
- `adb` 工具

### 安装

```bash
# 克隆仓库
git clone https://github.com/yfy227/fridamcp.git
cd fridamcp

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Frida CLI
pip install frida-tools
```

### Android 端准备

#### 方式一：Root 设备（推荐）

```bash
# 进入 android 目录
cd android

# 安装 frida-server 到设备
bash install_frida.sh

# 启动 frida-server
bash start_frida.sh
```

#### 方式二：非 Root 设备（使用 APK 注入器）

```bash
# 进入 injector 目录
cd injector

# 注入 frida-gadget 到目标 APK
python inject_apk.py --input target.apk --output target_injected.apk

# 安装注入后的 APK
adb install target_injected.apk

# 启动应用，frida-gadget 会自动加载
adb shell am start -n com.target.app/.MainActivity
```

### 启动 MCP 服务器

```bash
# 启动 MCP 服务器（监听 8768 端口）
python -m fridamcp.server

# 或使用脚本
bash scripts/run.sh
```

### 配置 AI 客户端

在 AI 客户端（如 Claude Desktop）的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "fridamcp": {
      "url": "http://localhost:8768/mcp"
    }
  }
}
```

## MCP 模块

| 模块 | 说明 | 主要工具 |
|------|------|----------|
| **process** | 进程管理 | `list_processes`, `spawn_app`, `attach_process`, `kill_process`, `resume_process` |
| **hook** | Hook 管理 | `hook_method`, `hook_native`, `unhook`, `list_hooks`, `trace_method` |
| **memory** | 内存检查 | `read_memory`, `write_memory`, `search_memory`, `list_modules`, `list_exports` |
| **network** | 网络监控 | `start_capture`, `stop_capture`, `get_capture`, `hook_ssl` |
| **filesystem** | 文件系统 | `list_files`, `read_file`, `pull_file`, `push_file` |
| **ui_automation** | UI 自动化 | `tap`, `input_text`, `screenshot`, `list_ui` |
| **crypto** | 加密分析 | `hook_crypto`, `dump_keys`, `hook_ssl_keys` |
| **log** | 日志捕获 | `start_log`, `get_logs`, `clear_all_logs` |
| **script** | **自定义脚本执行** | `run_script`, `call_script_rpc`, `unload_script`, `list_scripts`, `load_script_file`, `get_script_messages` |

详细文档请参考 [docs/MODULES.md](docs/MODULES.md)。

## 项目结构

```
fridamcp/
├── fridamcp/                  # MCP 服务器主包
│   ├── __init__.py
│   ├── server.py              # MCP 服务器入口 (端口 8768)
│   ├── config.py              # 配置管理
│   ├── core/                  # 核心封装
│   │   ├── frida_client.py    # Frida 客户端封装
│   │   ├── device_manager.py  # 设备管理
│   │   └── session_manager.py # 会话管理
│   ├── modules/               # MCP 模块
│   │   ├── process.py         # 进程管理
│   │   ├── hook.py            # Hook 管理
│   │   ├── memory.py          # 内存检查
│   │   ├── network.py         # 网络监控
│   │   ├── filesystem.py      # 文件系统
│   │   ├── ui_automation.py   # UI 自动化
│   │   ├── crypto.py          # 加密分析
│   │   ├── log.py             # 日志捕获
│   │   └── script.py          # 自定义脚本执行（核心）
│   └── utils/                 # 工具
│       ├── apk_injector.py    # APK 注入逻辑
│       └── logger.py          # 日志工具
├── injector/                  # APK 注入器
│   ├── inject_apk.py          # 注入脚本
│   ├── frida_gadget/          # frida-gadget 二进制
│   └── templates/             # 配置模板
├── android/                   # Android 端
│   ├── install_frida.sh       # 安装 frida-server
│   ├── start_frida.sh         # 启动 frida-server
│   └── frida_server/          # frida-server 二进制
├── scripts/                   # 脚本
│   ├── setup.sh               # 环境配置
│   └── run.sh                 # 启动服务器
├── docs/                      # 文档
│   ├── ARCHITECTURE.md        # 架构设计
│   ├── USAGE.md               # 使用指南
│   └── MODULES.md             # 模块文档
├── tests/                     # 测试
├── requirements.txt           # Python 依赖
├── setup.py                   # 安装配置
└── README.md                  # 项目说明
```

## 使用示例

### 示例 1：Hook Java 方法

让 AI 帮你 Hook 某个 Java 方法：

```
AI: 请帮我 Hook com.example.app.LoginActivity 的 checkPassword 方法，
    打印参数和返回值。

FridaMCP: 
1. [process] attach_process("com.example.app")
2. [hook] hook_method("com.example.app.LoginActivity", "checkPassword", 
                      "{ print args, retval }")
3. [log] get_logs() → 返回 Hook 到的调用记录
```

### 示例 2：监控网络请求

```
AI: 请监控应用的所有 HTTPS 请求，持续 30 秒。

FridaMCP:
1. [process] attach_process("com.example.app")
2. [network] start_capture()
3. 等待 30 秒
4. [network] get_capture() → 返回所有捕获的请求
5. [network] stop_capture()
```

### 示例 3：内存搜索

```
AI: 在应用内存中搜索字符串 "password"。

FridaMCP:
1. [process] attach_process("com.example.app")
2. [memory] search_memory("password") → 返回所有匹配地址
3. [memory] read_memory(address, 64) → 读取上下文
```

### 示例 4：直接运行 Frida JS 脚本（核心功能）

```
AI: 请帮我 Hook 所有 SharedPreferences 的 putString 调用，打印键值。

FridaMCP:
1. [process] attach_process("com.example.app")
2. [script] run_script(session_id, '''
   Java.perform(function() {
       var SharedPreferencesEditor = Java.use("android.app.SharedPreferencesImpl$EditorImpl");
       SharedPreferencesEditor.putString.implementation = function(key, value) {
           send({ type: "putString", key: key, value: value });
           return this.putString(key, value);
       };
       send({ type: "hook_ready" });
   });
   ''')
3. [script] get_script_messages(session_id) → 返回 Hook 捕获的数据
4. [script] unload_script(session_id, script_id) → 卸载脚本
```

### 示例 5：使用 RPC 导出执行复杂操作

```
AI: 编写一个脚本，导出 decrypt 函数让我调用。

FridaMCP:
1. [process] attach_process("com.example.app")
2. [script] run_script(session_id, '''
   rpc.exports = {
       decrypt: function(encrypted) {
           var result = null;
           Java.perform(function() {
               var Crypto = Java.use("com.example.app.Crypto");
               result = Crypto.decrypt(encrypted);
           });
           return result;
       }
   };
   ''')
3. [script] call_script_rpc(session_id, script_id, "decrypt", ["base64data..."])
   → 返回解密结果
```

## 配置

配置文件位于 `fridamcp/config.py`，主要配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MCP_PORT` | `8768` | MCP 服务器监听端口 |
| `MCP_HOST` | `0.0.0.0` | MCP 服务器监听地址 |
| `FRIDA_DEVICE_ID` | `None` | Frida 设备 ID（None 表示自动选择） |
| `FRIDA_DEVICE_TYPE` | `usb` | 设备类型（usb/remote/local） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `SCRIPT_TIMEOUT` | `30` | 脚本执行超时（秒） |

## 安全提示

- 本工具仅用于合法的安全研究和应用测试
- 请勿用于非法用途
- 使用前请确保已获得目标应用的所有者授权
- 注入 APK 后请勿分发，仅供个人测试使用

## 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 贡献

欢迎提交 Issue 和 Pull Request。

## 致谢

- [Frida](https://frida.re/) - 世界级的动态插桩工具
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
- 所有为 Android 安全研究做出贡献的开源项目
