# FridaMCP Android App

> Android 原生版 FridaMCP —— 把 Frida + MCP 服务器装进口袋，手机即是完整的动态分析平台。

## 项目简介

将 FridaMCP 从 PC 端 Python 服务 + Web UI 原型，彻底迁移为 Android 原生应用。手机既是控制器也是目标设备，无需 PC。

### 与原项目的区别

| 特性 | 原项目 (Python + Next.js) | 本项目 (Android Native) |
|------|--------------------------|------------------------|
| 运行平台 | PC (Linux/Mac/Win) | Android 手机 |
| Frida 连接 | USB/ADB 远程 | 本地直接调用 |
| MCP 服务器 | Python FastMCP | Kotlin HTTP Server |
| UI | Next.js Web (mock) | Jetpack Compose (原生) |
| APK 注入 | Python apktool | On-device 原生实现 |
| 需要 PC | ✅ | ❌ |

## 技术栈

- **语言**: Kotlin 2.0
- **UI**: Jetpack Compose + Material 3
- **架构**: MVVM + Repository
- **Frida**: frida-core via JNA
- **MCP**: 内嵌 HTTP/SSE Server (port 8768)
- **构建**: Gradle 8.9 + AGP 8.5
- **最低 SDK**: Android 8.0 (API 26)

## 目录结构

```
android-app/
├── build.gradle.kts              # 项目级构建
├── settings.gradle.kts
├── gradle.properties
├── gradlew
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── app/
│   ├── build.gradle.kts          # App 模块构建
│   ├── proguard-rules.pro
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/fridamcp/app/
│       │   ├── FridaMCPApplication.kt
│       │   ├── MainActivity.kt
│       │   ├── data/
│       │   │   ├── model/
│       │   │   │   ├── Models.kt        # 所有数据模型
│       │   │   │   └── MockData.kt      # 开发用模拟数据
│       │   │   ├── repository/
│       │   │   │   ├── AppRepository.kt
│       │   │   │   ├── DeviceRepository.kt
│       │   │   │   └── McpRepository.kt
│       │   │   └── service/
│       │   │       ├── FridaService.kt       # Frida 引擎前台服务
│       │   │       ├── McpServerService.kt   # MCP 服务器前台服务
│       │   │       ├── InjectionDetector.kt  # 三层注入检测
│       │   │       └── ApkInjector.kt        # APK 注入器
│       │   └── ui/
│       │       ├── theme/
│       │       │   ├── Color.kt
│       │       │   ├── Theme.kt
│       │       │   └── Type.kt
│       │       ├── navigation/
│       │       │   └── NavGraph.kt
│       │       ├── components/
│       │       │   ├── AppCard.kt
│       │       │   ├── AppIcon.kt
│       │       │   ├── BottomNav.kt
│       │       │   └── StatusBadge.kt
│       │       └── screens/
│       │           ├── SharedViewModel.kt
│       │           ├── DashboardScreen.kt   # 仪表盘
│       │           ├── AppsScreen.kt        # 应用列表
│       │           ├── InjectScreen.kt      # APK 注入
│       │           ├── McpScreen.kt         # MCP 管理
│       │           └── SettingsScreen.kt    # 设置
│       └── res/
│           ├── values/
│           │   ├── strings.xml
│           │   ├── colors.xml
│           │   └── themes.xml
│           ├── drawable/
│           │   └── ic_launcher_foreground.xml
│           └── mipmap-anydpi-v26/
│               ├── ic_launcher.xml
│               └── ic_launcher_round.xml
└── README.md
```

## 5 个核心界面

### 1. 仪表盘 (Dashboard)
- 设备状态卡片（型号、Android 版本、架构、Root 状态、Frida 版本）
- MCP 服务器状态卡片（运行状态、端口、会话数、连接客户端）
- 注入概览（已注入/运行中/总计）
- 最近日志列表

### 2. 应用 (Apps)
- 设备已安装应用列表
- 搜索 + 过滤（全部/已注入/运行中）
- 注入状态自动检测（三层检测：静态 / 运行时 / 进程）
- 点击应用打开详情面板
- 一键启动应用 / 启停 MCP / 重新检测 / 移除注入

### 3. 注入 (Inject)
- APK 注入工作流
- 输入 APK 路径、应用名、包名
- 架构选择（arm64-v8a / armeabi-v7a / x86_64）
- apktool 模式开关（自动修改 smali）
- 注入任务列表 + 进度

### 4. MCP
- MCP 服务器启停
- SSE/HTTP 连接地址展示
- 活跃会话列表
- 8 个 MCP 模块开关（Process / Hook / Memory / Network / Filesystem / UI / Crypto / Log）

### 5. 设置
- 设备详细信息
- 扫描配置（自动扫描、扫描间隔）
- MCP 配置（端口、传输方式、自动启动）
- 关于信息

## 构建方法

### 本地构建

```bash
cd android-app
./gradlew assembleDebug
# APK 输出: app/build/outputs/apk/debug/app-debug.apk
```

### CI 构建

推送代码到 `main` 分支即可触发 GitHub Actions 自动构建：
- 构建 Debug + Release APK
- 运行单元测试
- APK 作为 Artifact 上传

## 开发路线

### Phase 1 (当前) — UI 骨架 ✅
- [x] Jetpack Compose 5 屏 UI
- [x] 深色主题（Frida 绿色主色调）
- [x] 数据模型 + Mock 数据
- [x] Repository 层 + ViewModel
- [x] CI/CD (GitHub Actions)

### Phase 2 — Frida 引擎集成
- [ ] frida-core native 库打包
- [ ] JNA 绑定实现
- [ ] 本地设备枚举 / 进程附加
- [ ] 脚本注入 + 消息路由
- [ ] 8 个模块的 52 个工具实现

### Phase 3 — MCP 服务器
- [ ] NanoHTTPD/Ktor HTTP 服务器
- [ ] JSON-RPC 请求处理
- [ ] SSE 流式响应
- [ ] MCP 协议兼容

### Phase 4 — APK 注入
- [ ] On-device apktool 集成
- [ ] frida-gadget.so 注入
- [ ] smali 修改自动化
- [ ] APK 签名

### Phase 5 — 高级功能
- [ ] 脚本市场（SSL Pinning 绕过、Root 检测绕过等）
- [ ] 分析报告导出
- [ ] 多设备协同
