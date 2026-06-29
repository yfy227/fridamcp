# Android 端 Frida 运行环境

在 Android 设备上安装和运行 `frida-server`，提供 Frida 运行环境。

## 前置要求

- Android 设备已开启 USB 调试
- 设备已 root（frida-server 需要 root 权限）
- PC 已安装 adb 和 frida-tools

## 快速安装

在 PC 上运行：

```bash
# 自动检测架构并安装最新版本
./android/install_frida.sh

# 指定版本和架构
./android/install_frida.sh 16.5.9 arm64
```

安装脚本会自动：
1. 检测设备架构
2. 下载对应版本的 frida-server
3. 推送到设备 `/data/local/tmp/frida/`
4. 设置可执行权限
5. 启动 frida-server

## 手动安装

如果自动安装失败，可以手动操作：

### 1. 下载 frida-server

从 [Frida Releases](https://github.com/frida/frida/releases) 下载对应版本：

```bash
# 检测设备架构
adb shell getprop ro.product.cpu.abi
# 输出例如: arm64-v8a

# 下载对应的 frida-server
wget https://github.com/frida/frida/releases/download/16.5.9/frida-server-16.5.9-android-arm64.xz
xz -d frida-server-16.5.9-android-arm64.xz
```

### 2. 推送到设备

```bash
adb shell "su -c 'mkdir -p /data/local/tmp/frida'"
adb push frida-server-16.5.9-android-arm64 /data/local/tmp/frida/frida-server
adb shell "su -c 'chmod 755 /data/local/tmp/frida/frida-server'"
```

### 3. 启动 frida-server

```bash
# 推送启动脚本
adb push android/start_frida.sh /data/local/tmp/
adb shell "su -c 'chmod 755 /data/local/tmp/start_frida.sh'"

# 启动
adb shell "su -c 'sh /data/local/tmp/start_frida.sh'"
```

## 管理命令

### 启动

```bash
adb shell "su -c 'sh /data/local/tmp/start_frida.sh'"
```

### 停止

```bash
adb shell "su -c 'sh /data/local/tmp/start_frida.sh --stop'"
```

### 查看状态

```bash
adb shell "su -c 'sh /data/local/tmp/start_frida.sh --status'"
```

### 查看日志

```bash
adb shell "su -c 'cat /data/local/tmp/frida-server.log'"
```

### 指定监听地址和端口

```bash
adb shell "su -c 'sh /data/local/tmp/start_frida.sh --host 0.0.0.0 --port 27042'"
```

## 验证

在 PC 上验证 frida-server 是否正常工作：

```bash
# 列出设备上的进程
frida-ps -U

# 列出设备上的应用
frida-ps -Ua

# 附加到某个进程
frida -U -n com.android.chrome
```

## 无 Root 方案

如果设备没有 root，可以使用 frida-gadget 注入方式：

1. 使用 APK 注入器将 frida-gadget 注入到目标 APK
2. 安装注入后的 APK
3. 启动应用，gadget 自动加载

详见 [injector/README.md](../injector/README.md)

## 常见问题

### Q: frida-server 启动后立即退出？

A: 可能原因：
- 架构不匹配，检查 `uname -m` 输出
- SELinux 限制，尝试：`adb shell "su -c 'setenforce 0'"`
- 端口被占用，更换端口：`--port 27043`

### Q: frida-ps -U 报错 "unable to connect to remote frida-server"？

A: 检查：
- frida-server 是否在运行：`adb shell "su -c 'ps | grep frida'"`
- adb 连接是否正常：`adb devices`
- frida 版本是否与 frida-server 匹配：`frida --version`

### Q: 如何让 frida-server 开机自启？

A: 使用 Magisk 模块或 init.d 脚本，例如：

```bash
# 创建 Magisk 模块
mkdir -p /data/adb/modules/frida-server
cat > /data/adb/modules/frida-server/service.sh << 'EOF'
#!/system/bin/sh
nohup /data/local/tmp/frida/frida-server -l 127.0.0.1:27042 &
EOF
chmod 755 /data/adb/modules/frida-server/service.sh
```

## 安全提示

- frida-server 监听端口后，任何能访问该端口的程序都可以控制设备
- 不要将 frida-server 监听到 0.0.0.0（除非在受控网络环境）
- 测试完成后及时停止 frida-server
