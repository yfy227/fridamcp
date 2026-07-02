# FridaMCP 快速上手

> 5 分钟内让 AI 帮你分析 Android 应用。

## 一、安装

### 1. 克隆仓库

```bash
git clone https://github.com/yfy227/fridamcp.git
cd fridamcp/fridamcp
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

> **提示**：建议使用 Python 3.9+ 的虚拟环境：
> ```bash
> python3 -m venv venv
> source venv/bin/activate
> pip install -r requirements.txt
> ```

### 3. 验证安装

```bash
python -m fridamcp --help
```

看到帮助信息说明安装成功。

---

## 二、两种使用方式

FridaMCP 支持两种设备模式，根据你的设备情况选择：

### 方式 A：有 Root 的 Android 设备（推荐）

适合：有 root 权限的真机或模拟器

```bash
# 1. 确认设备已连接
adb devices

# 2. 在设备上安装 frida-server
./android/install_frida.sh

# 3. 启动 frida-server
./android/start_frida.sh

# 4. 验证 frida 能看到设备
frida-ps -U
```

### 方式 B：无 Root 设备（APK 注入）

适合：没有 root 权限的普通手机

```bash
# 1. 下载 frida-gadget
#    访问 https://github.com/frida/frida/releases
#    下载对应架构的 frida-gadget-XX.X.X-android-arm64.so
#    重命名为 libfrida-gadget-arm64-v8a.so
#    放到 injector/frida_gadget/ 目录

# 2. 注入目标 APK
python injector/inject_apk.py 目标应用.apk 输出.apk --use-apktool

# 3. 安装注入后的 APK
adb install 输出.apk
```

### 方式 C：本地测试（无 Android 设备）

适合：先体验功能，没有设备也能跑

```bash
# 使用 local 设备模式，分析本机进程
export FRIDA_DEVICE_TYPE=local
python -m fridamcp --transport sse --port 8768 --device-type local
```

---

## 三、启动 MCP 服务器

```bash
# SSE 模式（推荐，支持远程连接）
python -m fridamcp --transport sse --host 0.0.0.0 --port 8768

# stdio 模式（用于 IDE 集成）
python -m fridamcp --transport stdio

# HTTP 模式
python -m fridamcp --transport http --host 0.0.0.0 --port 8768
```

看到以下输出说明启动成功：

```
============================================================
FridaMCP - AI-Powered Frida MCP Server for Android
============================================================
Host: 0.0.0.0
Port: 8768
Transport: sse
Device type: usb
============================================================
INFO:     Uvicorn running on http://0.0.0.0:8768
```

---

## 四、连接 AI 客户端

### Claude Desktop

编辑配置文件（macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "fridamcp": {
      "command": "python",
      "args": ["-m", "fridamcp", "--transport", "stdio", "--device-type", "usb"],
      "cwd": "/path/to/fridamcp/fridamcp"
    }
  }
}
```

### Cursor / VS Code

在 MCP 设置中添加 SSE 服务器地址：

```
http://localhost:8768/sse
```

### 任何支持 MCP 的客户端

SSE 连接地址：`http://<服务器IP>:8768/sse`

---

## 五、开始使用

连接成功后，直接用自然语言告诉 AI 你想做什么：

```
帮我列出设备上的所有进程

帮我附加到 com.example.app 进程

Hook 这个应用的 LoginActivity.checkPassword 方法

在内存中搜索 "password" 字符串

截取当前屏幕
```

AI 会自动调用对应的 MCP 工具完成操作。

---

## 六、验证是否工作

启动服务器后，用浏览器访问：

```
http://localhost:8768/sse
```

如果看到 `event: endpoint` 开头的响应，说明服务器正常工作。

---

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| `device not found` | 确认设备已连接：`adb devices`，或改用 `--device-type local` |
| `port 8768 already in use` | 换个端口：`--port 8769` |
| `frida-server not running` | 在设备上启动：`./android/start_frida.sh` |
| AI 客户端连不上 | 检查防火墙，确认 SSE 地址正确 |

更多问题请查阅 [FAQ](docs/FAQ.md)。
