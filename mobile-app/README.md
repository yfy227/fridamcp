# FridaMCP Mobile App

FridaMCP 移动端应用 —— 将 Frida 动态插桩与 MCP 协议结合的移动端 UI，参考 [JsHook](https://github.com/0x67666767/JsHook) 的 UI 风格与注入检测逻辑设计。

## 项目简介

本目录包含 FridaMCP 的移动端 APP UI 实现，基于 Next.js 16 + TypeScript + Tailwind CSS 4 构建，采用移动端优先的设计风格。APP 提供了应用注入管理、注入状态自动检测、MCP 服务拉起等核心功能的可视化操作界面。

### 核心特性

- **jshook 风格 UI**：深色主题、卡片式布局、底部导航栏，符合 Android 逆向工具的视觉习惯
- **注入状态自动检测**：三层检测策略（静态 / 运行时 / 进程），实时展示已注入应用
- **一键拉起 MCP 服务**：在应用列表中直接为已注入应用启动/停止 MCP 服务
- **APK 注入工作流**：可视化 APK 注入流程，支持架构选择、apktool 模式、自动签名
- **MCP 服务管理**：服务器启停、SSE/HTTP 连接地址、会话管理、8 个模块开关

## 目录结构

```
mobile-app/
├── README.md                          # 本文件
├── package.json                       # 依赖配置
├── src/
│   ├── app/
│   │   ├── layout.tsx                 # 根布局（深色主题）
│   │   ├── page.tsx                   # 主页面（状态管理 + 路由）
│   │   └── globals.css                # 全局样式（Frida 主题色 + 移动端适配）
│   ├── components/
│   │   └── mobile/
│   │       ├── status-bar.tsx         # 模拟 Android 状态栏
│   │       ├── bottom-nav.tsx         # 底部导航栏（5 个标签）
│   │       ├── dashboard-screen.tsx   # 总览页：设备/MCP/注入概览
│   │       ├── apps-screen.tsx        # 应用列表页：注入状态展示
│   │       ├── app-detail-sheet.tsx   # 应用详情底部面板：检测详情
│   │       ├── inject-screen.tsx      # 注入页：APK 注入工作流
│   │       ├── mcp-screen.tsx         # MCP 页：服务管理
│   │       └── settings-screen.tsx    # 设置页
│   └── lib/
│       ├── types.ts                   # TypeScript 类型定义
│       └── mock-data.ts               # 模拟数据（设备/应用/会话/模块）
```

## 界面说明

### 1. 总览（Dashboard）

展示设备连接状态、MCP 服务器运行状态、注入检测概览（已注入/运行中/异常数量）、活跃会话列表，以及快捷操作入口。

### 2. 应用列表（Apps）

核心界面，参考 jshook 的应用列表设计：

- 每个应用卡片显示图标、名称、包名、版本
- **注入状态徽章**：运行中（琥珀色）/ 已注入（绿色）/ 未注入（灰色）/ 注入异常（红色）
- 已注入应用显示 gadget 版本、架构、PID 等信息
- 已注入应用提供「启动应用」和「拉起 MCP」两个操作按钮
- 支持搜索（应用名/包名）和状态过滤
- 点击应用卡片弹出详情面板，展示检测方法和详细信息

### 3. 注入（Inject）

APK 注入工作流界面：

- APK 文件选择
- 架构选择（arm64-v8a / armeabi-v7a / x86 / x86_64）
- 注入模式（apktool 完整模式 / 简单模式）
- 选项：自动安装、注入后自动扫描检测
- 注入任务列表，展示历史注入记录和进度

### 4. MCP 服务（MCP）

MCP 服务器管理界面：

- 服务器启停控制
- SSE / HTTP 连接地址（可复制）
- 运行时长、活跃会话、工具总数、连接客户端数
- 活跃会话列表（PID、应用名、Hook 数、消息数）
- 8 个 MCP 模块开关（process / hook / memory / network / filesystem / ui_automation / crypto / log）

### 5. 设置（Settings）

设备信息、自动扫描配置（间隔可调）、通知开关、调试模式等。

## 注入检测逻辑

参考 jshook 的注入检测思路，采用三层检测策略：

| 检测方法 | 原理 | 适用场景 |
|---------|------|---------|
| **静态检测（static）** | 解析 APK 文件，检查 `lib/<arch>/libfrida-gadget.so` 是否存在 | 应用未运行时 |
| **运行时检测（runtime）** | 检测端口 27042 是否有 frida-gadget 监听 | 应用已启动 |
| **进程检测（process）** | 扫描进程内存映射，确认 gadget 模块已加载 | 应用运行中 |

检测流程：
1. APP 启动时自动扫描所有已安装应用
2. 对每个应用依次尝试静态 → 运行时 → 进程检测
3. 检测结果写入应用状态，更新列表 UI
4. 支持手动重新扫描单个应用

## 技术栈

- **框架**：Next.js 16 (App Router)
- **语言**：TypeScript
- **样式**：Tailwind CSS 4
- **图标**：lucide-react
- **主题**：深色模式（Frida 绿色主色调 `oklch(0.72 0.19 152)`）

## 本地运行

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 浏览器访问 http://localhost:3000
# 建议使用 Chrome DevTools 移动端模拟（390x844）
```

## 与后端集成

当前版本使用 mock 数据展示 UI 效果。与 FridaMCP 后端集成时，需替换 `src/lib/mock-data.ts` 中的模拟数据为真实 API 调用：

- 设备信息：调用 MCP `list_devices` / `get_device_info` 工具
- 应用列表：通过 `adb shell pm list packages` 获取，结合注入检测结果
- MCP 服务状态：调用 `get_system_status` 工具
- 会话列表：调用 `list_sessions` 工具

## 后续规划

1. **阶段一**：将 UI 原型转换为 Android 原生应用（Kotlin + Jetpack Compose），集成真实 Frida API
2. **阶段二**：实现完整的 APK 注入工具链（自动化 smali 修改 + APK 签名）
3. **阶段三**：增加高级功能（脚本市场、分析报告导出、多设备协同）
