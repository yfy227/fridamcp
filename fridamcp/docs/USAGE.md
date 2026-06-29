# FridaMCP 使用指南

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/yfy227/fridamcp.git
cd fridamcp

# 安装依赖
pip install -r requirements.txt

# 运行设置脚本
./scripts/setup.sh
```

### 2. 准备 Android 设备

**方式 A: Root 设备 (推荐)**

```bash
# 安装 frida-server 到设备
./android/install_frida.sh

# 验证
frida-ps -U
```

**方式 B: 无 Root 设备**

```bash
# 注入 frida-gadget 到目标 APK
python injector/inject_apk.py target.apk target_injected.apk --use-apktool

# 安装注入后的 APK
adb install target_injected.apk
```

### 3. 启动 MCP 服务器

```bash
# 默认配置 (端口 8768, SSE 传输)
./scripts/run.sh

# 自定义配置
./scripts/run.sh --host 0.0.0.0 --port 8768 --transport sse

# stdio 模式 (用于 IDE 集成)
./scripts/run.sh --stdio
```

### 4. 连接 AI 客户端

#### Claude Desktop

在 `claude_desktop_config.json` 中添加：

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

#### 其他 MCP 客户端

连接到 `http://<server-ip>:8768/mcp` (SSE) 或 `http://<server-ip>:8768` (HTTP)

## 常用场景

### 场景 1: 分析应用登录流程

```
用户: 帮我分析 com.example.app 的登录流程

AI:
1. [process] list_applications() → 找到 com.example.app
2. [process] spawn_app("com.example.app") → 启动应用，返回 pid
3. [process] attach_process(pid) → 创建会话 session_id
4. [hook] hook_method(session_id, "com.example.app.LoginActivity", "login")
5. [process] resume_process(pid) → 恢复执行
6. [ui_automation] tap(500, 800) → 点击登录按钮
7. [ui_automation] input_text("username")
8. [ui_automation] input_text("password")
9. [ui_automation] tap(500, 900) → 提交
10. [log] get_frida_messages(session_id) → 获取 Hook 到的调用
11. [hook] unhook(session_id, hook_id) → 清理
12. [process] close_session(session_id)
```

### 场景 2: 监控网络请求

```
用户: 监控应用的所有 HTTPS 请求

AI:
1. [process] attach_process("com.example.app")
2. [network] start_capture(session_id, capture_ssl=True)
3. [ui_automation] tap(...) → 触发网络请求
4. [network] get_capture(session_id) → 返回捕获的请求
5. [network] stop_capture(session_id)
```

### 场景 3: 内存搜索

```
用户: 在内存中搜索 "secret_key" 字符串

AI:
1. [process] attach_process("com.example.app")
2. [memory] search_memory(session_id, "secret_key") → 返回匹配地址
3. [memory] read_memory(session_id, address, 64) → 读取上下文
4. [memory] list_modules(session_id) → 查看模块
```

### 场景 4: 加密分析

```
用户: 分析应用使用的加密算法

AI:
1. [process] attach_process("com.example.app")
2. [crypto] hook_crypto(session_id) → Hook 所有加密 API
3. [ui_automation] tap(...) → 触发加密操作
4. [crypto] get_crypto_operations(session_id) → 返回加密记录
5. 分析: 应用使用 AES/CBC/PKCS5Padding，密钥为...
```

### 场景 5: UI 自动化测试

```
用户: 自动化测试应用的注册流程

AI:
1. [process] spawn_app("com.example.app")
2. [ui_automation] screenshot() → 查看当前界面
3. [ui_automation] list_ui() → 获取 UI 元素
4. [ui_automation] tap(注册按钮坐标)
5. [ui_automation] input_text("test@example.com")
6. [ui_automation] input_text("password123")
7. [ui_automation] tap(提交按钮)
8. [ui_automation] screenshot() → 验证结果
```

## 工具列表

### Process 模块

| 工具 | 说明 |
|------|------|
| `list_devices` | 列出所有 Frida 设备 |
| `select_device` | 选择设备 |
| `get_device_info` | 获取设备信息 |
| `list_processes` | 列出所有进程 |
| `list_applications` | 列出已安装应用 |
| `spawn_app` | 启动应用 |
| `attach_process` | 附加到进程 |
| `resume_process` | 恢复进程 |
| `kill_process` | 杀死进程 |
| `list_sessions` | 列出会话 |
| `close_session` | 关闭会话 |

### Hook 模块

| 工具 | 说明 |
|------|------|
| `hook_method` | Hook Java 方法 |
| `hook_native` | Hook Native 函数 |
| `list_hooks` | 列出活跃 Hook |
| `unhook` | 移除 Hook |
| `get_hook_messages` | 获取 Hook 消息 |

### Memory 模块

| 工具 | 说明 |
|------|------|
| `read_memory` | 读取内存 |
| `write_memory` | 写入内存 |
| `search_memory` | 搜索内存 |
| `list_modules` | 列出模块 |
| `list_exports` | 列出导出函数 |

### Network 模块

| 工具 | 说明 |
|------|------|
| `start_capture` | 开始捕获 |
| `stop_capture` | 停止捕获 |
| `get_capture` | 获取捕获数据 |
| `hook_ssl` | Hook SSL |

### Filesystem 模块

| 工具 | 说明 |
|------|------|
| `list_files` | 列出文件 |
| `read_file` | 读取文件 |
| `pull_file` | 拉取文件 |
| `push_file` | 推送文件 |
| `list_app_data` | 列出应用数据 |
| `get_app_info` | 获取应用信息 |

### UI Automation 模块

| 工具 | 说明 |
|------|------|
| `tap` | 点击 |
| `swipe` | 滑动 |
| `input_text` | 输入文本 |
| `key_event` | 按键 |
| `screenshot` | 截图 |
| `list_ui` | 列出 UI 元素 |
| `get_current_activity` | 获取当前 Activity |

### Crypto 模块

| 工具 | 说明 |
|------|------|
| `hook_crypto` | Hook 加密 API |
| `get_crypto_operations` | 获取加密操作 |
| `hook_ssl_keys` | Hook SSL 密钥 |

### Log 模块

| 工具 | 说明 |
|------|------|
| `start_logcat` | 开始 logcat 捕获 |
| `stop_logcat` | 停止 logcat |
| `get_logcat` | 获取 logcat |
| `get_frida_messages` | 获取 Frida 消息 |
| `get_server_logs` | 获取服务器日志 |
| `clear_all_logs` | 清空日志 |

## 配置

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FRIDAMCP_HOST` | `0.0.0.0` | 监听地址 |
| `FRIDAMCP_PORT` | `8768` | 监听端口 |
| `FRIDA_DEVICE_TYPE` | `usb` | 设备类型 |
| `FRIDA_DEVICE_ID` | (空) | 设备 ID |
| `FRIDAMCP_LOG_LEVEL` | `INFO` | 日志级别 |

### 配置文件

配置在 `fridamcp/config.py` 中，可通过环境变量覆盖。

## 故障排除

### 服务器无法启动

```bash
# 检查端口是否被占用
lsof -i :8768

# 检查 Python 依赖
pip list | grep -E "mcp|frida"

# 查看详细日志
FRIDAMCP_LOG_LEVEL=DEBUG ./scripts/run.sh
```

### 无法连接设备

```bash
# 检查 adb
adb devices

# 检查 frida-server
adb shell "su -c 'ps | grep frida'"

# 重启 adb
adb kill-server && adb start-server
```

### MCP 客户端连接失败

- 确认服务器正在运行: `curl http://localhost:8768/`
- 检查防火墙设置
- 确认传输协议匹配 (SSE/HTTP/stdio)
