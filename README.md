# FridaMCP - AI-Powered Frida MCP Server for Android

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-green.svg)](https://modelcontextprotocol.io/)
[![Frida](https://img.shields.io/badge/Frida-16+-orange.svg)](https://frida.re/)
[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 在 Android 设备上运行 Frida，并通过 MCP (Model Context Protocol) 服务让 AI 更加便捷地使用 Frida 进行动态分析、Hook、内存检查、网络监控等操作。

## 项目简介

**FridaMCP** 是一个将 Frida 动态插桩工具与 MCP 协议结合的项目，专为 AI 辅助的 Android 应用安全分析而设计。它包含三个核心组件：

1. **Android 端 Frida 运行器** —— 在 Android 设备上启动 `frida-server`，提供 Frida 运行环境。
2. **APK 注入器** —— 将 `frida-gadget` 自动注入到目标 APK 中，使目标应用启动时自动加载 Frida，无需 root 也能使用。支持 v1/v2/v3 签名方案、多 ABI 自动检测、加固 APK 检测。
3. **MCP 服务器** —— 通过 stdio（本地，默认）或 HTTP/SSE（远程）向 AI 客户端暴露一系列 Frida 操作工具，让 AI 可以直接调用 Frida 进行安全分析。

## 工作流程

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  AI Client  │◄───►│  MCP Server      │◄───►│  Android Device │
│ (Claude等)  │ MCP │  (stdio/HTTP/SSE)│ USB │  + Frida Server │
└─────────────┘     └──────────────────┘     └─────────────────┘
                            │                          │
                            │                          ▼
                    ┌───────────────┐          ┌────────────────┐
                    │  MCP Modules  │          │  Target App    │
                    │  (9 modules)  │          │  (Injected)    │
                    └───────────────┘          └────────────────┘
                            │
                    ┌───────────────┐
                    │  Session Mgr  │  ← 生命周期管理
                    │  (复用/超时/锁) │
                    └───────────────┘
```

1. 在 Android 设备上启动 `frida-server`（root 设备）或使用 APK 注入器注入 `frida-gadget`（非 root 设备）。
2. 启动 MCP 服务器（默认 stdio 传输，适合 Claude Desktop；远程使用 HTTP/SSE）。
3. AI 客户端通过 MCP 协议连接服务器，调用各种 Frida 工具。
4. AI 可以列出进程、Hook 方法、读取内存、监控网络、自动化 UI 等。
5. 会话管理器自动管理 Frida 会话的生命周期（复用、超时回收、并发锁）。

## 核心特性

- **9 个 MCP 模块**：进程管理、Hook 管理、内存检查、网络监控、文件系统、UI 自动化、加密分析、日志捕获、**自定义脚本执行**
- **直接运行 Frida JS 脚本**：AI 可通过 `run_script` / `run_hook_script` 工具直接编写并执行任意 Frida JavaScript，不再局限于预置模板
- **Hook 沙箱隔离**：所有 Hook 脚本经过沙箱包装，异常被捕获并通过 `send()` 回传，不会导致目标进程崩溃
- **SSL Pinning Bypass**：多层绕过（Java/OkHttp2/OkHttp3/Conscrypt/Native BoringSSL），支持抓包 HTTPS
- **Native 加密 Hook**：覆盖 BoringSSL EVP 系列（EVP_EncryptInit_ex / EVP_DigestInit_ex / HMAC 等）
- **SSL 密钥导出**：通过 SSL_CTX_set_keylog_callback 导出 SSLKEYLOGFILE 格式密钥，可直接导入 Wireshark
- **APK 注入器**：自动将 `frida-gadget` 注入 APK，支持 v1/v2/v3 签名、多 ABI、加固检测
- **会话生命周期管理**：会话复用、空闲超时回收、并发锁、保活线程
- **多传输模式**：stdio（本地，默认）/ SSE / HTTP（远程）
- **多设备支持**：支持 USB 设备、远程设备、模拟器
- **AI 友好**：所有工具都设计为 AI 易于调用，参数清晰，返回结构化数据
- **容器化部署**：提供 Dockerfile 和 docker-compose，支持一键部署

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

# 方式一：pip 安装（推荐）
pip install -e .

# 方式二：安装依赖
pip install -r requirements.txt
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

# 注入 frida-gadget 到目标 APK（简单模式）
python inject_apk.py target.apk target_injected.apk

# 或使用 apktool 完整模式（推荐，支持 smali 注入）
python inject_apk.py target.apk target_injected.apk --use-apktool

# 检测 APK 是否被加固
python inject_apk.py target.apk --check-packer

# 安装注入后的 APK
adb install target_injected.apk

# 启动应用，frida-gadget 会自动加载
adb shell am start -n com.target.app/.MainActivity
```

### 启动 MCP 服务器

```bash
# 方式一：stdio 传输（默认，适合 Claude Desktop / Cursor 本地使用）
fridamcp -t stdio

# 方式二：HTTP 传输（远程访问）
fridamcp -t http -p 8768

# 方式三：SSE 传输（远程访问）
fridamcp -t sse -p 8768

# 或使用 Python 模块
python -m fridamcp -t stdio
```

**传输模式选择**：
- **stdio**（默认）：本地工具标准方式，延迟最低，适合 Claude Desktop / Cursor 等 AI 客户端
- **SSE**：Server-Sent Events，适合远程调用场景
- **HTTP**：Streamable HTTP，适合远程调用场景

### 配置 AI 客户端

#### Claude Desktop（stdio 模式，推荐）

在 Claude Desktop 配置文件中添加：

```json
{
  "mcpServers": {
    "fridamcp": {
      "command": "fridamcp",
      "args": ["-t", "stdio"]
    }
  }
}
```

#### Claude Desktop（HTTP 模式，远程）

```json
{
  "mcpServers": {
    "fridamcp": {
      "url": "http://localhost:8768/mcp"
    }
  }
}
```

#### Cursor / 其他 AI 客户端

参考对应客户端的 MCP 配置文档，使用 stdio 或 HTTP 模式连接。

## MCP 模块

| 模块 | 说明 | 主要工具 |
|------|------|----------|
| **process** | 进程管理 | `list_processes`, `spawn_app`, `attach_process`, `kill_process`, `resume_process` |
| **hook** | Hook 管理（沙箱保护） | `hook_method`, `hook_native`, `trace_method`, `run_hook_script`, `validate_hook_script`, `get_sandbox_errors`, `unhook`, `list_hooks` |
| **memory** | 内存检查 | `read_memory`, `write_memory`, `search_memory`, `list_modules`, `list_exports` |
| **network** | 网络监控 + SSL Bypass | `start_capture`, `stop_capture`, `get_capture`, `hook_ssl`, `bypass_ssl_pinning`, `get_pinning_bypass_status` |
| **filesystem** | 文件系统 | `list_files`, `read_file`, `pull_file`, `push_file` |
| **ui_automation** | UI 自动化 | `tap`, `input_text`, `screenshot`, `list_ui` |
| **crypto** | 加密分析（Java + Native） | `hook_crypto`, `hook_native_crypto`, `get_crypto_operations`, `dump_keys`, `hook_ssl_keys`, `get_ssl_keylog` |
| **log** | 日志捕获 | `start_log`, `get_logs`, `clear_all_logs` |
| **script** | 自定义脚本执行 | `run_script`, `call_script_rpc`, `unload_script`, `list_scripts`, `load_script_file`, `get_script_messages` |
| **session** | 会话生命周期管理 | `list_sessions`, `get_session_info`, `close_session`, `cleanup_sessions`, `session_manager_status` |

详细文档请参考 [docs/MODULES.md](docs/MODULES.md)。

## 项目结构

```
fridamcp/
├── fridamcp/                  # MCP 服务器主包
│   ├── __init__.py
│   ├── __main__.py            # Python -m 入口
│   ├── server.py              # MCP 服务器入口（stdio/HTTP/SSE）
│   ├── config.py              # 配置管理（含会话/传输配置）
│   ├── core/                  # 核心封装
│   │   ├── frida_client.py    # Frida 客户端封装
│   │   ├── device_manager.py  # 设备管理
│   │   └── session_manager.py # 会话管理（生命周期/复用/超时/锁）
│   ├── modules/               # MCP 模块
│   │   ├── process.py         # 进程管理
│   │   ├── hook.py            # Hook 管理（沙箱保护）
│   │   ├── memory.py          # 内存检查
│   │   ├── network.py         # 网络监控 + SSL Pinning Bypass
│   │   ├── filesystem.py      # 文件系统
│   │   ├── ui_automation.py   # UI 自动化
│   │   ├── crypto.py          # 加密分析（Java + Native BoringSSL）
│   │   ├── log.py             # 日志捕获
│   │   └── script.py          # 自定义脚本执行
│   └── utils/                 # 工具
│       ├── apk_injector.py    # APK 注入（v2/v3 签名/多 ABI/加固检测）
│       ├── hook_sandbox.py    # Hook 沙箱（异常隔离）
│       └── logger.py          # 日志工具
├── injector/                  # APK 注入器
│   ├── inject_apk.py          # 注入 CLI
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
├── Dockerfile                 # 容器化部署
├── docker-compose.yml         # Docker Compose
├── fridamcp.spec              # PyInstaller 打包配置
├── build.sh                   # 构建脚本
├── requirements.txt           # Python 依赖
├── setup.py                   # 安装配置
└── README.md                  # 项目说明
```

## 架构设计

### Session 生命周期管理

FridaMCP 2.0 引入了显式的 Session 生命周期管理，解决多 AI 并发调用、会话泄漏等问题。

**生命周期状态**：
```
CREATED → ATTACHED → IDLE → DETACHED
                ↓                  ↑
              EXPIRED ──────────────┘
                (超时回收)
```

**核心机制**：
- **会话复用**：同一 PID 默认复用现有活动会话，避免重复 attach 开销
- **空闲超时**：会话空闲超过 `SESSION_IDLE_TIMEOUT`（默认 600 秒）自动分离回收
- **并发锁**：每个会话持有独立 RLock，防止多 AI 并发调用同一会话产生竞态
- **保活线程**：后台线程周期性检查会话状态、清理超时/已分离会话
- **引用计数**：支持多调用者复用同一会话，引用计数降为 0 才真正分离

**相关工具**：`list_sessions` / `get_session_info` / `close_session` / `session_manager_status`

### Hook 沙箱隔离

AI 生成的 Frida hook 脚本质量不稳定，直接加载可能导致目标进程崩溃。FridaMCP 2.0 引入沙箱包装层：

**沙箱策略**：
1. **脚本包装**：将 AI 原始脚本包裹在 try-catch 中，所有顶层异常被捕获并通过 `send()` 回传
2. **语法预检**：加载前对脚本做轻量级静态检查（括号匹配、危险 API 检测）
3. **加载重试**：脚本加载失败时自动卸载残留并重试一次
4. **错误聚合**：收集脚本运行时错误，供 AI 调试迭代

**相关工具**：`run_hook_script` / `validate_hook_script` / `get_sandbox_errors`

### SSL Pinning Bypass

覆盖 Android 应用证书校验的多个层级：

| 层级 | Hook 目标 | 说明 |
|------|-----------|------|
| Java | `SSLContext.init` | 替换为信任所有证书的 TrustManager |
| Java | `HostnameVerifier` | 信任所有主机名 |
| OkHttp3 | `CertificatePinner.check` / `check$okhttp` | OkHttp3 证书校验 |
| OkHttp2 | `com.squareup.okhttp.CertificatePinner` | OkHttp2 证书校验 |
| Conscrypt | `TrustManagerImpl.checkTrustedRecursive` / `verifyChain` | Android 8+ 默认 Provider |
| Native | `SSL_CTX_set_verify` / `SSL_get_verify_result` | BoringSSL/OpenSSL |
| Native | `SSL_CTX_set_custom_verify` / `SSL_set_verify` | BoringSSL 特有 |

**相关工具**：`bypass_ssl_pinning` / `get_pinning_bypass_status`

### 加密 Hook 覆盖

| 层级 | Hook 目标 | 说明 |
|------|-----------|------|
| Java | `javax.crypto.Cipher` | AES/DES/RSA/SM4 等 |
| Java | `javax.crypto.spec.SecretKeySpec` | 对称密钥构造 |
| Java | `javax.crypto.Mac` | HMAC |
| Java | `java.security.MessageDigest` | MD5/SHA1/SHA256/SM3 |
| Native | `EVP_EncryptInit_ex` / `EVP_DecryptInit_ex` | BoringSSL 对称加密 |
| Native | `EVP_DigestInit_ex` / `EVP_DigestFinal_ex` | BoringSSL 哈希 |
| Native | `HMAC_Init_ex` | BoringSSL HMAC |
| Native | `RSA_generate_key_ex` | RSA 密钥生成 |
| SSL | `SSL_CTX_set_keylog_callback` | SSLKEYLOGFILE 格式密钥导出 |

**相关工具**：`hook_crypto` / `hook_native_crypto` / `get_crypto_operations` / `hook_ssl_keys` / `get_ssl_keylog`

### APK 注入器增强

| 特性 | 说明 |
|------|------|
| v1/v2/v3 签名 | 使用 `apksigner` 显式启用所有签名方案 |
| zipalign 对齐 | 签名前自动对齐，满足 Android 11+ 要求 |
| 多 ABI 检测 | 自动检测 APK 包含的所有 ABI，分别注入对应 gadget |
| 加固检测 | 检测梆梆/爱加密/360/腾讯/娜迦等常见加固，给出注入建议 |
| smali 注入 | apktool 模式下在 Application.onCreate 插入 loadLibrary |
| 注入点选择 | 优先 Application.onCreate，回退 MainActivity.onCreate |

**相关 CLI**：`fridamcp-inject` / `python injector/inject_apk.py`

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
| `MCP_TRANSPORT` | `stdio` | MCP 传输模式（stdio/sse/http） |
| `MCP_PORT` | `8768` | MCP 服务器监听端口（HTTP/SSE 模式） |
| `MCP_HOST` | `0.0.0.0` | MCP 服务器监听地址 |
| `FRIDA_DEVICE_ID` | `None` | Frida 设备 ID（None 表示自动选择） |
| `FRIDA_DEVICE_TYPE` | `usb` | 设备类型（usb/remote/local） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `SCRIPT_TIMEOUT` | `30` | 脚本执行超时（秒） |
| `SESSION_IDLE_TIMEOUT` | `600` | 会话空闲超时（秒，0 表示永不超时） |
| `SESSION_LOCK_TIMEOUT` | `30` | 会话操作锁获取超时（秒） |
| `SESSION_KEEPALIVE_INTERVAL` | `30` | 会话保活检查间隔（秒） |
| `MAX_SESSIONS` | `10` | 最大并发会话数 |

所有配置项均可通过环境变量覆盖，前缀为 `FRIDAMCP_`。

## 打包与部署

### 方式一：pip 安装

```bash
pip install -e .
# 使用
fridamcp -t stdio
fridamcp-inject target.apk --use-apktool
```

### 方式二：PyInstaller 打包为独立可执行文件

```bash
# 安装打包依赖
pip install pyinstaller

# 打包
./build.sh
# 或
pyinstaller fridamcp.spec --noconfirm

# 运行
./dist/fridamcp/fridamcp -t stdio
```

### 方式三：Docker 容器化部署

```bash
# 构建镜像
docker build -t fridamcp .

# 运行（stdio 模式，本地使用）
docker run -i --rm fridamcp

# 运行（HTTP 模式，远程访问）
docker run -p 8768:8768 --rm fridamcp -t http -p 8768 --host 0.0.0.0

# 使用 docker-compose
docker compose up -d
```

Docker 镜像包含：
- Python 3.11 + FridaMCP
- adb（Android 设备通信）
- OpenJDK 17（APK 签名）
- zipalign + apksigner（APK 对齐与签名）

## 验证与测试

FridaMCP 2.1 引入了完整的可验证性体系，无需真实 Android 设备即可验证所有功能。

### 自测命令

```bash
# 运行自测（验证导入、工具注册、模拟工作流、沙箱、配置）
python -m fridamcp --self-test
```

自测覆盖：
1. 所有模块可正常导入
2. MCP 服务器可创建
3. 所有工具已注册（无重复）
4. 模拟模式下完整工作流：`list_devices → list_processes → attach → hook → list_hooks → close`
5. Hook 沙箱可正常包装脚本
6. 配置项可正常读取

### 列出所有工具

```bash
python -m fridamcp --list-tools
```

### 模拟模式（无需 Android 设备）

```bash
# stdio 模式（模拟设备）
python -m fridamcp --mock -t stdio

# HTTP 模式（模拟设备）
python -m fridamcp --mock -t http -p 18768
```

模拟模式提供虚拟 Android 设备，包含 7 个常见进程，可用于：
- AI 客户端功能演示
- CI/CD 自动化测试
- 开发调试

### 单元测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio

# 运行全部测试（88 个测试用例）
pytest tests/ -v

# 或使用 Makefile
make test
```

测试覆盖：
| 测试文件 | 覆盖内容 | 测试数 |
|----------|----------|--------|
| `test_hook_sandbox.py` | 脚本校验、沙箱包装、错误提取 | ~20 |
| `test_session_manager.py` | 会话生命周期、引用计数、状态查询 | ~10 |
| `test_config.py` | 配置读取、环境变量、更新方法 | ~10 |
| `test_mock_device.py` | 模拟设备/会话/脚本 | ~20 |
| `test_apk_injector.py` | 加固检测、架构检测、配置模板 | ~10 |
| `test_mcp_integration.py` | 完整 MCP 工具调用链路 | ~18 |

### CI/CD

项目包含 GitHub Actions 配置（`.github/workflows/ci.yml`），在每次 push/PR 时自动运行：
- Python 3.9 / 3.10 / 3.11 / 3.12 矩阵测试
- 自测命令
- 单元测试
- stdio / HTTP 传输启动验证
- 语法检查

### Makefile 快捷命令

```bash
make install      # 安装
make dev          # 安装开发依赖
make test         # 运行测试
make self-test    # 运行自测
make list-tools   # 列出工具
make run-stdio    # stdio 模式启动
make run-http     # HTTP 模式启动
make run-mock     # 模拟模式启动
make build        # PyInstaller 打包
make docker       # 构建 Docker 镜像
make clean        # 清理构建产物
```

## 已知局限性

### SSL Pinning Bypass
- **加固应用**（梆梆/爱加密/360/腾讯/娜迦）可能自定义校验逻辑，需要先脱壳或定位自定义校验函数
- **厂商魔改 BoringSSL**（腾讯 X5 / 阿里 SSL）函数名可能不同，需要额外 hook
- **Flutter / React Native** 应用静态链接 BoringSSL，需通过内存特征扫描定位 SSL 函数

### 加密 Hook
- 厂商魔改 BoringSSL 函数名可能不同
- Flutter 静态链接 BoringSSL 需内存扫描定位
- 国密 SM2/SM3/SM4 可能使用第三方库（如 BC、GMSecurity），需额外 hook

### APK 注入
- **签名校验应用**（银行/支付类）可能检测到签名变化后拒绝运行
- **加固 APK** 的 Application 类被壳接管，gadget 注入点可能无效，需先脱壳
- **v2/v3 签名** 注入后原签名作废，使用 debug keystore 重签名

### APK 注入器修复（v2.2）
v2.2 修复了导致注入后 APK 破损/无法安装的关键问题：
- **重新打包保留原始压缩方式**：.so 文件用 STORED（Android mmap 优化要求）
- **注入前剥离原签名**：自动移除 META-INF/*.SF|*.RSA|*.MF，避免签名冲突
- **smali 寄存器分配修复**：自动扩容 .locals，防止 INSTALL_FAILED_DEXOPT
- **smali 注入点修复**：跳过 .annotation/.param 块，插入到正确位置
- **simple 模式真正注入**：不再只加 .so，而是调用 apktool 修改 smali
- **APK 完整性验证**：注入后用 aapt 验证 APK 可正常解析

### Session 管理
- 会话超时回收是尽力而为，极端情况下可能有延迟
- 并发锁防止竞态但不防止死锁，AI 应避免长时间持有会话

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
