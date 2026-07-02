# FridaMCP 常见问题

## 安装相关

### Q: pip install 报错怎么办？

**A:** 常见原因和解决方案：

```bash
# 1. 升级 pip
pip install --upgrade pip

# 2. 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. frida 编译失败？尝试预编译版本
pip install frida --only-binary :all:
```

### Q: Python 版本不够怎么办？

**A:** FridaMCP 需要 Python 3.9+。推荐使用 pyenv 管理多版本：

```bash
curl https://pyenv.run | bash
pyenv install 3.12
pyenv local 3.12
```

### Q: 安装后 `python -m fridamcp` 报 ModuleNotFoundError？

**A:** 确保在正确的目录下运行，或安装为包：

```bash
cd fridamcp/fridamcp
pip install -e .  # 以开发模式安装
python -m fridamcp --help
```

---

## 设备连接相关

### Q: 提示 "device not found"？

**A:** 这是 USB 设备未连接导致的。三种解决方式：

```bash
# 方式 1：确认设备已连接并开启 USB 调试
adb devices
# 应显示类似：List of devices attached
#             XXXXXX    device

# 方式 2：使用模拟器（本地模式）
python -m fridamcp --device-type local

# 方式 3：使用远程设备
python -m fridamcp --device-type remote
```

### Q: frida-ps -U 提示 "unable to connect to remote frida-server"？

**A:** frida-server 未启动或版本不匹配：

```bash
# 1. 检查 frida-server 是否在运行
adb shell "ps | grep frida"

# 2. 启动 frida-server
adb shell "su -c '/data/local/tmp/frida-server &'"

# 3. 检查版本是否匹配
frida --version          # 本机版本
adb shell "/data/local/tmp/frida-server --version"  # 设备版本
# 两个版本必须一致！
```

### Q: 设备已连接但 list_processes 返回空？

**A:** 可能是设备未正确选择。先调用 select_device：

```
AI: 请先选择 USB 设备
→ 调用 select_device(device_type="usb")

AI: 现在列出进程
→ 调用 list_processes()
```

### Q: 如何使用非 Root 设备？

**A:** 使用 APK 注入方式：

```bash
# 1. 下载 frida-gadget
#    https://github.com/frida/frida/releases
#    选择 frida-gadget-XX.X.X-android-arm64.so.xz
#    解压后重命名为 libfrida-gadget-arm64-v8a.so

# 2. 放到指定目录
mkdir -p injector/frida_gadget
cp libfrida-gadget-arm64-v8a.so injector/frida_gadget/

# 3. 注入 APK
python injector/inject_apk.py target.apk output.apk --use-apktool

# 4. 安装
adb install output.apk

# 5. 启动应用后，frida-gadget 会自动加载
#    通过 frida -U Gadget 连接
```

---

## MCP 服务器相关

### Q: 服务器启动后立即退出？

**A:** 查看错误日志：

```bash
# 开启 DEBUG 日志
FRIDAMCP_LOG_LEVEL=DEBUG python -m fridamcp --transport sse

# 常见原因：
# 1. 端口被占用 → 换端口 --port 8769
# 2. 依赖未安装 → pip install -r requirements.txt
# 3. frida 版本不兼容 → pip install frida>=16.0.0
```

### Q: SSE 模式启动报 TypeError: run_sse_async() got an unexpected keyword argument 'host'？

**A:** 这是旧版本的问题，已在最新代码中修复。请更新代码：

```bash
git pull origin main
```

### Q: AI 客户端连接不上 MCP 服务器？

**A:** 排查步骤：

```bash
# 1. 确认服务器在运行
curl http://localhost:8768/sse
# 应返回 event: endpoint 开头的响应

# 2. 检查防火墙
sudo ufw allow 8768

# 3. 确认地址正确
# SSE 地址: http://localhost:8768/sse
# HTTP 地址: http://localhost:8768/mcp

# 4. 远程连接时用服务器 IP
# SSE 地址: http://192.168.1.100:8768/sse
```

### Q: Claude Desktop 配置后不生效？

**A:** 检查配置文件：

```json
{
  "mcpServers": {
    "fridamcp": {
      "command": "python",
      "args": ["-m", "fridamcp", "--transport", "stdio"],
      "cwd": "/绝对路径/fridamcp/fridamcp",
      "env": {
        "FRIDA_DEVICE_TYPE": "usb"
      }
    }
  }
}
```

注意事项：
- `cwd` 必须是**绝对路径**
- `command` 如果是 python3，改为 `"python3"`
- 修改配置后需要**重启 Claude Desktop**
- macOS 配置文件路径：`~/Library/Application Support/Claude/claude_desktop_config.json`

---

## 功能使用相关

### Q: AI 说找不到 execute_script 工具？

**A:** 这是旧版本的问题。execute_script / call_script_function / unload_script 是新增工具，请更新代码：

```bash
git pull origin main
pip install -r requirements.txt
```

### Q: Hook 方法后没有收到消息？

**A:** Hook 消息是异步的，需要主动获取：

```
AI: Hook com.example.LoginActivity 的 checkPassword 方法
→ 返回 hook_id

AI: 获取 Hook 消息
→ 调用 get_hook_messages(session_id, hook_id)
```

如果应用还没触发该方法，消息为空是正常的。操作应用后再次获取。

### Q: 如何执行自定义 Frida 脚本？

**A:** 使用 execute_script 工具：

```
AI: 附加到 com.example.app
→ 调用 attach_process("com.example.app")
→ 返回 session_id

AI: 执行以下脚本：
    rpc.exports = {
        getinfo: function() {
            return {
                platform: Process.platform,
                arch: Process.arch,
                modules: Process.enumerateModules().length
            };
        }
    };
→ 调用 execute_script(session_id, script_code)
→ 返回 script_id

AI: 调用 getinfo 函数
→ 调用 call_script_function(session_id, script_id, "getinfo")
→ 返回 { platform: "linux", arch: "x64", modules: 10 }
```

### Q: 网络捕获没有数据？

**A:** 需要先启动捕获，等待应用发请求，再获取：

```
AI: 1. 附加到应用
    2. 启动网络捕获（包含 SSL）
    3. 等待 30 秒
    4. 获取捕获数据
    5. 停止捕获
```

### Q: 会话太多怎么清理？

**A:** 使用清理工具：

```
AI: 清理所有已分离的会话
→ 调用 cleanup_sessions()

AI: 关闭所有会话
→ 调用 close_all_sessions()
```

---

## 性能相关

### Q: 服务器响应很慢？

**A:** 可能原因：

1. **设备连接不稳定** → 调用 `reconnect_device()` 重连
2. **会话过多** → 调用 `cleanup_sessions()` 清理
3. **脚本消息堆积** → 调用 `get_frida_messages(session_id, clear=true)` 清空
4. **DEBUG 日志过多** → 设置 `FRIDAMCP_LOG_LEVEL=INFO`

### Q: 内存占用越来越高？

**A:** 调整缓冲区大小：

```bash
# 减少日志缓冲区（默认 1000 条）
export FRIDAMCP_LOG_BUFFER_SIZE=200

# 减少网络捕获上限（默认 5000 条）
export FRIDAMCP_NET_CAPTURE_LIMIT=1000
```

---

## 移动端 APP 相关

### Q: 移动端 APP 怎么运行？

**A:** 移动端 APP 是 Next.js Web 应用：

```bash
cd mobile-app
npm install
npm run dev
# 浏览器访问 http://localhost:3000
# 建议使用 Chrome 移动端模拟（F12 → 设备工具栏）
```

### Q: 移动端 APP 能控制真实的 FridaMCP 吗？

**A:** 当前版本使用模拟数据展示 UI 效果。与后端集成需要替换 `src/lib/mock-data.ts` 为真实 API 调用，详见 [移动端设计文档](MOBILE_APP_DESIGN.md) 的"与后端集成"章节。

---

## 其他

### Q: 支持哪些 Android 版本？

**A:** Frida 支持 Android 5.0 (API 21) 及以上版本。不同版本的 Hook 能力：

| Android 版本 | 支持 |
|-------------|------|
| 5.0 - 6.0 | Java Hook 基础 |
| 7.0 - 9.0 | Java + Native Hook |
| 10.0 - 13.0 | 全功能支持 |
| 14.0+ | 需 frida 16.5+ |

### Q: 支持 iOS 吗？

**A:** FridaMCP 当前专注于 Android。Frida 本身支持 iOS，理论上可以扩展，但需要修改设备管理逻辑。

### Q: 如何贡献代码？

**A:** 欢迎提交 PR：

```bash
git checkout -b feature/your-feature
# 修改代码
git commit -m "feat: 添加 XXX 功能"
git push origin feature/your-feature
# 在 GitHub 上创建 Pull Request
```
