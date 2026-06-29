# APK 注入器

将 `frida-gadget` 注入到目标 APK 中，使应用启动时自动加载 Frida，**无需 root**。

## 工作原理

1. 解压目标 APK
2. 将 `frida-gadget.so` 复制到 APK 的 `lib/<arch>/` 目录
3. 修改 smali 代码，在 Application 类的 `onCreate` 中添加 `System.loadLibrary("frida-gadget")`
4. 重新打包并签名 APK
5. 安装后启动应用，frida-gadget 自动加载并监听端口

## 前置准备

### 1. 下载 frida-gadget

从 [Frida Releases](https://github.com/frida/frida/releases) 下载对应架构的 gadget：

```bash
# 创建 gadget 目录
mkdir -p frida_gadget

# 下载 frida-gadget (以 arm64 为例)
wget https://github.com/frida/frida/releases/download/16.5.9/frida-gadget-16.5.9-android-arm64.so.xz
xz -d frida-gadget-16.5.9-android-arm64.so.xz
mv frida-gadget-16.5.9-android-arm64.so frida_gadget/libfrida-gadget-arm64-v8a.so

# 下载 armeabi-v7a 版本
wget https://github.com/frida/frida/releases/download/16.5.9/frida-gadget-16.5.9-android-arm.so.xz
xz -d frida-gadget-16.5.9-android-arm.so.xz
mv frida-gadget-16.5.9-android-arm.so frida_gadget/libfrida-gadget-armeabi-v7a.so
```

### 2. 安装依赖工具

```bash
# apktool (推荐，用于完整注入)
# 参考: https://ibotpeaches.github.io/Apktool/install/

# Android SDK build-tools (提供 apksigner)
# 参考: https://developer.android.com/studio/releases/build-tools

# Java (keytool, jarsigner)
sudo apt install default-jdk
```

## 使用方法

### 简单模式（仅复制 gadget，不修改 smali）

```bash
python injector/inject_apk.py app.apk app_injected.apk
```

> 注意：简单模式只复制 gadget 到 APK，不会自动加载。需要配合其他方式触发。

### 完整模式（推荐，使用 apktool）

```bash
python injector/inject_apk.py app.apk app_injected.apk --use-apktool
```

完整模式会：
- 反编译 APK
- 修改 Application 类的 smali 代码
- 添加 `System.loadLibrary("frida-gadget")`
- 重新编译并签名

### 指定架构

```bash
python injector/inject_apk.py app.apk app_injected.apk --use-apktool --arch arm64-v8a
```

### 自定义 gadget 配置

```bash
python injector/inject_apk.py app.apk app_injected.apk \
    --use-apktool \
    --gadget-host 0.0.0.0 \
    --gadget-port 27042
```

### 自定义 Application 类

```bash
python injector/inject_apk.py app.apk app_injected.apk \
    --use-apktool \
    --application-class com.example.app.MyApplication
```

## gadget 配置

gadget 配置文件 `libfrida-gadget.config.so`（与 .so 同目录）：

```json
{
    "interaction": {
        "type": "listen",
        "address": "127.0.0.1",
        "port": 27042,
        "on_port_conflict": "fail",
        "on_load": "wait"
    },
    "teardown": "full"
}
```

### 配置选项

| 选项 | 说明 |
|------|------|
| `type: listen` | gadget 监听端口，等待 frida 连接 |
| `type: connect` | gadget 主动连接到指定 frida 服务 |
| `type: script` | 启动时自动加载指定脚本 |
| `on_load: wait` | 应用启动时等待 frida 连接（推荐） |
| `on_load: resume` | 应用启动后自动继续 |

## 注入后使用

### 1. 安装注入后的 APK

```bash
adb install app_injected.apk
```

### 2. 启动应用

```bash
adb shell am start -n com.example.app/.MainActivity
```

应用启动时会暂停，等待 frida 连接。

### 3. 使用 frida 连接

```bash
# 列出 gadget
frida-ls-devices

# 连接到 gadget
frida -U Gadget

# 加载脚本
frida -U Gadget -l script.js
```

### 4. 通过 FridaMCP 进行 AI 辅助分析

启动 FridaMCP 服务器后，AI 可以通过 MCP 协议连接到 gadget：

```
AI: 请附加到 Gadget 进程并 Hook 登录方法

FridaMCP:
1. [process] attach_process("Gadget")
2. [hook] hook_method("com.example.app.LoginActivity", "login", ...)
3. [log] get_frida_messages() → 返回 Hook 结果
```

## 常见问题

### Q: 注入后应用闪退？

A: 可能原因：
- gadget 架构不匹配，检查 `--arch` 参数
- 签名问题，尝试重新签名
- 应用有完整性校验，需要先绕过

### Q: frida 连接不上 gadget？

A: 检查：
- gadget 配置中的端口是否被占用
- adb forward 是否设置：`adb forward tcp:27042 tcp:27042`
- 应用是否真的启动了（gadget 在 `on_load: wait` 模式下会暂停应用）

### Q: 如何同时支持多架构？

A: 下载所有架构的 gadget，放入 `frida_gadget/` 目录，注入器会自动处理。
