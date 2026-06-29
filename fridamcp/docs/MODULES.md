# FridaMCP 模块文档

本文档详细描述所有 MCP 模块及其工具。

## 模块概览

FridaMCP 提供 8 个功能模块，共 40+ 个工具，覆盖 Android 动态分析的主要场景。

| 模块 | 工具数 | 主要功能 |
|------|--------|----------|
| Process | 11 | 进程/应用/会话管理 |
| Hook | 5 | Java/Native Hook |
| Memory | 5 | 内存读写搜索 |
| Network | 4 | 网络捕获/SSL |
| Filesystem | 6 | 设备文件操作 |
| UI Automation | 7 | UI 自动化 |
| Crypto | 3 | 加密分析 |
| Log | 6 | 日志捕获 |

---

## 1. Process 模块 (`process.py`)

进程、应用和会话管理。

### `list_devices()`
列出所有可用的 Frida 设备。

**返回**: 设备列表
```json
[
  {"id": "emulator-5554", "name": "Android Emulator", "type": "usb"},
  {"id": "local", "name": "Local OS", "type": "local"}
]
```

### `select_device(device_id?, device_type?)`
选择 Frida 设备。

**参数**:
- `device_id` (可选): 设备 ID
- `device_type` (可选): 设备类型 usb/remote/local

### `get_device_info()`
获取当前设备详细信息。

**返回**:
```json
{
  "id": "emulator-5554",
  "name": "Android Emulator",
  "type": "usb",
  "os": {"id": "android", "version": "13"},
  "arch": "x86_64",
  "frida_version": "16.5.9"
}
```

### `list_processes()`
列出设备上所有运行中的进程。

**返回**: 进程列表
```json
[{"pid": 1234, "name": "com.example.app"}]
```

### `list_applications()`
列出设备上所有已安装应用。

**返回**: 应用列表
```json
[{"identifier": "com.example.app", "name": "Example App", "pid": 0}]
```

### `spawn_app(package, paused=true)`
启动应用。

**参数**:
- `package`: 应用包名
- `paused`: 是否暂停启动（默认 true，便于 Hook）

**返回**: `{"pid": 1234, "package": "com.example.app"}`

### `attach_process(target)`
附加到进程。

**参数**:
- `target`: 进程 PID (int) 或应用包名 (str)

**返回**: `{"session_id": "sess_xxx", "pid": 1234, "name": "com.example.app"}`

### `resume_process(pid)`
恢复暂停的进程。

### `kill_process(pid)`
杀死进程。

### `list_sessions()`
列出所有活跃会话。

### `close_session(session_id)`
关闭会话。

---

## 2. Hook 模块 (`hook.py`)

Java 方法和 Native 函数 Hook。

### `hook_method(session_id, class_name, method_name, print_args=true, print_return=true, print_stack=false)`
Hook Java 方法。

**参数**:
- `session_id`: 会话 ID
- `class_name`: 完整类名，如 `com.example.app.LoginActivity`
- `method_name`: 方法名
- `print_args`: 打印参数（默认 true）
- `print_return`: 打印返回值（默认 true）
- `print_stack`: 打印调用栈（默认 false）

**返回**: `{"hook_id": "hook_xxx", "script_id": "..."}`

**示例**:
```
hook_method("sess_abc", "com.example.app.LoginActivity", "checkPassword")
```

### `hook_native(session_id, module_name, function_name, print_args=true)`
Hook Native 函数。

**参数**:
- `session_id`: 会话 ID
- `module_name`: 模块名，如 `libnative.so`
- `function_name`: 函数名
- `print_args`: 打印参数

### `list_hooks(session_id)`
列出会话中的所有 Hook。

### `unhook(session_id, hook_id?)`
移除 Hook。不指定 hook_id 则移除所有。

### `get_hook_messages(session_id, hook_id?, clear=false)`
获取 Hook 捕获的消息。

---

## 3. Memory 模块 (`memory.py`)

内存读写和搜索。

### `read_memory(session_id, address, size)`
读取内存。

**参数**:
- `session_id`: 会话 ID
- `address`: 内存地址（十六进制字符串，如 `0x7f8a6b5c0000`）
- `size`: 读取字节数

**返回**: `{"address": "0x...", "size": 64, "hex": "48656c6c6f..."} `

### `write_memory(session_id, address, hex_data)`
写入内存。

**参数**:
- `hex_data`: 十六进制数据字符串

### `search_memory(session_id, pattern, max_results=100)`
搜索内存。

**参数**:
- `pattern`: 搜索模式，支持十六进制（`48 65 6c 6c 6f`）或 ASCII 字符串

**返回**:
```json
{
  "results": ["0x7f8a6b5c0000", "0x7f8a6b5c1000"],
  "truncated": false
}
```

### `list_modules(session_id)`
列出已加载模块。

### `list_exports(session_id, module_name)`
列出模块导出函数。

---

## 4. Network 模块 (`network.py`)

网络流量捕获。

### `start_capture(session_id, capture_ssl=true, capture_socket=true)`
开始网络捕获。

**参数**:
- `capture_ssl`: 捕获 SSL/TLS 明文
- `capture_socket`: 捕获 socket 操作

**返回**: `{"capture_id": "cap_xxx", "hooks": [...]}`

### `stop_capture(session_id)`
停止捕获。

### `get_capture(session_id, filter_type?)`
获取捕获数据。

**参数**:
- `filter_type`: 可选过滤类型 ssl_write/ssl_read/socket_connect/socket_send/socket_recv

**返回**:
```json
[
  {
    "type": "ssl_write",
    "size": 256,
    "data": "GET /api/login HTTP/1.1\r\nHost: example.com\r\n..."
  }
]
```

### `hook_ssl(session_id)`
Hook SSL（start_capture 的快捷方式）。

---

## 5. Filesystem 模块 (`filesystem.py`)

设备文件操作，通过 adb 实现。

### `list_files(path="/sdcard/", device?)`
列出设备文件。

### `read_file(path, device?)`
读取设备文件内容（文本）。

### `pull_file(remote_path, local_path, device?)`
从设备拉取文件到 PC。

### `push_file(local_path, remote_path, device?)`
从 PC 推送文件到设备。

### `list_app_data(package, device?)`
列出应用数据目录。

### `get_app_info(package, device?)`
获取应用信息（版本、SDK、数据目录等）。

---

## 6. UI Automation 模块 (`ui_automation.py`)

UI 自动化操作，通过 adb input 实现。

### `tap(x, y, device?)`
点击坐标。

### `swipe(x1, y1, x2, y2, duration_ms=300, device?)`
滑动。

### `input_text(text, device?)`
输入文本（不支持中文）。

### `key_event(keycode, device?)`
发送按键事件。

**常用 keycode**:
- 3: HOME
- 4: BACK
- 24/25: 音量增/减
- 66: 回车
- 187: 最近任务

### `screenshot(device?)`
截图，返回 base64 编码的 PNG。

**返回**: `{"image_base64": "...", "saved_to": "/tmp/xxx.png"}`

### `list_ui(device?)`
列出当前界面的 UI 元素。

**返回**: `{"xml": "...", "elements": [...], "count": 42}`

### `get_current_activity(device?)`
获取当前前台 Activity。

---

## 7. Crypto 模块 (`crypto.py`)

加密操作监控。

### `hook_crypto(session_id)`
Hook Java 加密 API。

**Hook 的 API**:
- `javax.crypto.Cipher` (init, doFinal)
- `javax.crypto.Mac` (init, doFinal)
- `java.security.MessageDigest` (update, digest)
- `javax.crypto.KeyGenerator`
- `javax.crypto.SecretKeySpec`

### `get_crypto_operations(session_id, clear=false)`
获取捕获的加密操作。

**返回**:
```json
[
  {
    "type": "cipher_init",
    "algorithm": "AES/CBC/PKCS5Padding",
    "mode": 1,
    "key": "javax.crypto.spec.SecretKeySpec@..."
  },
  {
    "type": "cipher_doFinal",
    "input_hex": "48656c6c6f",
    "output_hex": "7a8b9c..."
  }
]
```

### `hook_ssl_keys(session_id)`
Hook SSL 密钥派生。

---

## 8. Log 模块 (`log.py`)

日志捕获。

### `start_logcat(session_id, package?, device?)`
开始 logcat 捕获。

**参数**:
- `package`: 可选，只捕获指定应用的日志

### `stop_logcat(session_id)`
停止 logcat 捕获。

### `get_logcat(session_id, clear=false, max_entries=100)`
获取 logcat 日志。

### `get_frida_messages(session_id, clear=false, max_entries=100)`
获取 Frida 脚本发送的消息。

### `get_server_logs(clear=false, max_entries=100)`
获取 MCP 服务器自身的日志。

### `clear_all_logs()`
清空所有日志缓冲区。

---

## 工具调用示例

### 完整的登录分析流程

```python
# 1. 启动应用
spawn_app("com.example.app", paused=True)
# → {"pid": 1234}

# 2. 附加进程
attach_process(1234)
# → {"session_id": "sess_abc"}

# 3. Hook 登录方法
hook_method("sess_abc", "com.example.app.LoginActivity", "login")
# → {"hook_id": "hook_xyz"}

# 4. Hook 网络请求
start_capture("sess_abc", capture_ssl=True)
# → {"capture_id": "cap_123"}

# 5. 恢复应用
resume_process(1234)

# 6. UI 操作触发登录
tap(500, 800)  # 点击用户名输入框
input_text("testuser")
tap(500, 900)  # 点击密码输入框
input_text("password123")
tap(500, 1000)  # 点击登录按钮

# 7. 获取 Hook 结果
get_hook_messages("sess_abc")
# → [{"type": "hook_call", "args": ["testuser", "password123"], "retval": true}]

# 8. 获取网络捕获
get_capture("sess_abc")
# → [{"type": "ssl_write", "data": "POST /api/login HTTP/1.1..."}]

# 9. 清理
stop_capture("sess_abc")
close_session("sess_abc")
```
