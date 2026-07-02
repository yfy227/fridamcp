# FridaMCP 移动端 APP 设计方案

> 本文档描述 FridaMCP 移动端应用的设计思路、UI 风格、注入检测逻辑和 MCP 服务拉起机制。
> UI 风格参考 [JsHook](https://github.com/0x67666767/JsHook)（Xposed 模块），适配 FridaMCP 的 MCP 协议架构。

## 一、设计背景

### 1.1 原项目现状

FridaMCP 原项目是一个纯 Python 实现的 MCP 服务器，通过 CLI 或 AI 客户端调用。存在以下使用痛点：

- **无图形界面**：所有操作依赖命令行或 AI 对话，门槛高
- **无注入状态检测**：无法直观知道哪些应用已注入 frida-gadget
- **注入流程不完整**：简单模式仅复制 `.so` 文件，未自动修改 smali 调用 `System.loadLibrary`
- **MCP 服务管理不便**：启停服务、查看会话状态均需命令行操作

### 1.2 设计目标

参考 jshook 的设计思路，构建一个移动端 APP，实现：

1. **可视化应用列表**：展示设备上所有应用，标注注入状态
2. **自动检测已注入应用**：安装注入后的 APK 后，APP 自动检测并标识
3. **一键拉起 MCP 服务**：为已注入应用快速启动 MCP 服务
4. **APK 注入工作流**：图形化 APK 注入流程

## 二、UI 风格设计

### 2.1 视觉风格

参考 jshook 的视觉语言：

| 设计要素 | 方案 | 说明 |
|---------|------|------|
| **主题** | 深色模式 | 逆向工具标配，降低视觉疲劳 |
| **主色调** | Frida 绿 `oklch(0.72 0.19 152)` | 呼应 Frida 品牌色 |
| **背景色** | 深蓝灰 `oklch(0.13 0.005 250)` | 比纯黑更柔和 |
| **卡片** | `oklch(0.18 0.006 250)` + 8% 白色边框 | 层次分明 |
| **圆角** | 2xl (16px) 卡片 / xl (12px) 按钮 | 现代感 |
| **字体** | Geist Sans / Geist Mono | 等宽字体用于包名、PID |

### 2.2 布局结构

采用移动端经典的「状态栏 + 内容区 + 底部导航」三段式布局：

```
┌─────────────────────────┐
│      Android 状态栏       │  ← 时间、信号、WiFi、电量
├─────────────────────────┤
│                         │
│      内容区（可滚动）      │  ← 根据当前标签页渲染
│                         │
│                         │
├─────────────────────────┤
│  总览  应用  注入  MCP 设置 │  ← 底部导航栏（5 标签）
└─────────────────────────┘
```

- **最大宽度 480px**：居中显示，适配手机屏幕
- **底部导航固定**：5 个标签页，已注入应用数量以徽章显示在「应用」标签上
- **底部面板（Bottom Sheet）**：应用详情从底部滑出，符合移动端交互习惯

### 2.3 五个核心界面

#### 界面一：总览（Dashboard）

展示全局状态概览：

- **设备状态卡片**：设备名、Android 版本、架构、Root 状态、frida-server 版本与运行状态
- **MCP 服务卡片**：运行状态、端口、传输协议、运行时长、启停按钮
- **注入检测概览**：已注入 / 运行中 / 异常 三个数字统计 + 重新扫描按钮
- **活跃会话列表**：当前 MCP 会话，显示应用名、PID、Hook 数
- **快捷操作**：应用列表、MCP 服务、注入工具入口

#### 界面二：应用列表（Apps）—— 核心界面

参考 jshook 的应用列表设计，这是 APP 的核心功能页：

**应用卡片元素**：
- 左侧：应用图标（彩色圆角方块 + 首字）
- 中间：应用名、包名、版本号
- 右侧：注入状态徽章
- 底部（仅已注入应用）：gadget 版本、架构、PID + 操作按钮

**注入状态徽章**（4 种状态）：

| 状态 | 图标 | 颜色 | 含义 |
|------|------|------|------|
| 运行中 | `CircleDot` | 琥珀色 | 已注入且应用正在运行，gadget 已激活 |
| 已注入 | `CircleCheck` | 绿色（主色） | APK 已注入 frida-gadget，但应用未启动 |
| 未注入 | `CircleDashed` | 灰色 | 未检测到注入 |
| 注入异常 | `CircleAlert` | 红色 | 注入检测出错（架构不匹配等） |

**操作按钮**（仅已注入应用显示）：
- 「启动应用」/「已运行」：拉起目标应用，触发 gadget 加载
- 「拉起 MCP」/「停止 MCP」：为该应用启动/停止 MCP 服务

**交互功能**：
- 搜索框：支持应用名和包名搜索
- 过滤器：全部 / 已注入 / 运行中 / 未注入 / 异常
- 点击卡片：弹出底部详情面板

#### 界面三：应用详情（Bottom Sheet）

从底部滑出的详情面板，展示注入检测的完整信息：

- **应用基本信息**：图标、名称、包名、版本、安装时间
- **注入检测详情**：
  - 检测状态（运行中/已注入/未注入/异常）
  - 检测方法（静态/运行时/进程）及说明文字
  - gadget 版本、架构
  - 注入时间、最后扫描时间
- **MCP 服务信息**：服务状态、端口、连接地址
- **操作按钮**：启动应用、拉起/停止 MCP、重新扫描、移除注入

#### 界面四：注入（Inject）

APK 注入工作流界面：

- **APK 文件选择**：文件路径输入（移动端可对接文件选择器）
- **架构选择**：arm64-v8a（推荐）/ armeabi-v7a / x86 / x86_64
- **注入模式**：apktool 完整模式（推荐，自动修改 smali）/ 简单模式
- **选项开关**：自动安装、注入后自动扫描检测
- **注入任务列表**：历史注入记录，展示状态（等待/注入中/签名中/完成/失败）和进度

#### 界面五：MCP 服务（MCP）

MCP 服务器管理界面：

- **服务器状态卡片**：运行状态指示灯、启停按钮
- **连接信息**：SSE 地址 `http://127.0.0.1:8768/sse`、HTTP 地址 `http://127.0.0.1:8768/mcp`（可复制）
- **运行统计**：运行时长、活跃会话数、工具总数、连接客户端数
- **活跃会话列表**：每个会话显示状态、应用名、包名、PID、Hook 数、消息数、创建时间
- **MCP 模块列表**：8 个模块（process / hook / memory / network / filesystem / ui_automation / crypto / log），每个显示工具数量和启用开关

## 三、注入检测逻辑

### 3.1 设计思路

参考 jshook 的注入检测机制：jshook 作为 Xposed 模块，能在应用列表中标识哪些应用已启用 Hook。FridaMCP 采用类似思路，但检测对象从 Xposed 模块变为 frida-gadget。

### 3.2 三层检测策略

```
应用列表获取
     │
     ▼
┌─────────────────────────────────────┐
│  第一层：运行时检测（runtime）        │  ← 优先级最高
│  检测端口 27042 是否有 gadget 监听    │
│  frida -U Gadget 是否可连接          │
└──────────────┬──────────────────────┘
               │ 未检测到
               ▼
┌─────────────────────────────────────┐
│  第二层：进程检测（process）          │
│  扫描进程内存映射                     │
│  查找 libfrida-gadget.so 已加载      │
└──────────────┬──────────────────────┘
               │ 进程未运行
               ▼
┌─────────────────────────────────────┐
│  第三层：静态检测（static）           │
│  解析 APK 文件                       │
│  检查 lib/<arch>/libfrida-gadget.so  │
└─────────────────────────────────────┘
```

### 3.3 检测方法详解

#### 静态检测（static）

**原理**：解析 APK 文件（本质是 ZIP），检查 `lib/<arch>/` 目录下是否存在 `libfrida-gadget.so`。

**实现**：
```python
import zipfile

def detect_static(apk_path: str, arch: str = "arm64-v8a") -> bool:
    """静态检测 APK 是否已注入 frida-gadget"""
    try:
        with zipfile.ZipFile(apk_path, 'r') as z:
            gadget_path = f"lib/{arch}/libfrida-gadget.so"
            return gadget_path in z.namelist()
    except Exception:
        return False
```

**适用场景**：应用未运行时，判断 APK 是否已被注入。

**局限**：只能判断文件是否存在，无法确认 gadget 是否能正常加载。

#### 运行时检测（runtime）

**原理**：frida-gadget 注入后默认监听 `127.0.0.1:27042`（可配置）。检测该端口是否有服务监听，即可判断应用是否已启动且 gadget 已激活。

**实现**：
```python
import socket
import frida

def detect_runtime(package_name: str) -> dict:
    """运行时检测 gadget 是否已激活"""
    try:
        # 方式1：尝试通过 frida 连接 Gadget
        device = frida.get_usb_device()
        session = device.attach("Gadget")
        session.detach()
        return {"detected": True, "method": "runtime", "detail": "Gadget 可连接"}
    except Exception:
        pass

    # 方式2：检测端口 27042
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", 27042))
        sock.close()
        if result == 0:
            return {"detected": True, "method": "runtime", "detail": "端口 27042 监听中"}
    except Exception:
        pass

    return {"detected": False, "method": "none", "detail": "未检测到运行时 gadget"}
```

**适用场景**：应用已启动，gadget 已加载并监听端口。

#### 进程检测（process）

**原理**：通过 Frida 或 `/proc/<pid>/maps` 扫描进程内存映射，查找已加载的 `libfrida-gadget.so` 共享库。

**实现**：
```python
def detect_process(package_name: str) -> dict:
    """进程检测：扫描内存映射查找 gadget"""
    try:
        device = frida.get_usb_device()
        # 查找目标应用进程
        processes = device.enumerate_processes()
        target = next((p for p in processes if p.name == package_name), None)
        if not target:
            return {"detected": False, "method": "none", "detail": "进程未运行"}

        # 附加进程，扫描已加载模块
        session = device.attach(target.pid)
        script = session.create_script("""
            var modules = Process.enumerateModules();
            var gadget = modules.filter(m => m.name.includes('frida-gadget'));
            send({ found: gadget.length > 0, modules: gadget.map(m => m.name) });
        """)
        result = {}
        script.on('message', lambda msg, _: result.update(msg.get('payload', {})))
        script.load()
        session.detach()

        if result.get('found'):
            return {"detected": True, "method": "process", "detail": f"已加载: {result['modules']}"}
        return {"detected": False, "method": "none", "detail": "进程未加载 gadget"}
    except Exception as e:
        return {"detected": False, "method": "none", "detail": str(e)}
```

**适用场景**：应用运行中但 gadget 未监听端口（如配置为 `connect` 模式而非 `listen`）。

### 3.4 检测流程

APP 启动时的自动检测流程：

```
APP 启动
  │
  ▼
获取已安装应用列表（adb shell pm list packages -3）
  │
  ▼
对每个应用并行执行检测：
  ├─ 1. 运行时检测（端口 27042 / frida -U Gadget）
  ├─ 2. 进程检测（扫描内存映射）
  └─ 3. 静态检测（解析 APK）
  │
  ▼
汇总检测结果，更新应用列表 UI
  │
  ▼
定时轮询（默认 30 秒）重新检测运行中应用
```

### 3.5 状态展示

检测结果映射到 UI 状态：

| 检测结果 | UI 状态 | 徽章颜色 |
|---------|---------|---------|
| 运行时检测命中 | 运行中（running） | 琥珀色 |
| 静态检测命中，运行时未命中 | 已注入（injected） | 绿色 |
| 静态检测命中但架构不匹配 | 注入异常（error） | 红色 |
| 所有检测均未命中 | 未注入（not_injected） | 灰色 |

## 四、MCP 服务拉起机制

### 4.1 设计思路

原项目中 MCP 服务器是全局单例，监听 8768 端口。移动端 APP 设计为「按应用拉起」模式：用户在应用列表中点击「拉起 MCP」，APP 为该应用创建 MCP 会话。

### 4.2 拉起流程

```
用户点击「拉起 MCP」
  │
  ▼
检查应用注入状态
  ├─ 未注入 → 提示「请先注入 frida-gadget」
  └─ 已注入/运行中 → 继续
  │
  ▼
检查应用是否运行
  ├─ 未运行 → 自动启动应用（am start）
  └─ 运行中 → 继续
  │
  ▼
等待 gadget 激活（端口 27042 可连接）
  │
  ▼
调用 MCP 工具 attach_process(package_name)
  │
  ▼
创建 Frida 会话，返回 session_id
  │
  ▼
更新应用 UI 状态：mcpStatus = online
显示会话信息（session_id、PID、Hook 数）
```

### 4.3 实现接口

APP 与 FridaMCP 后端通过 MCP 协议交互，核心工具调用：

| 操作 | MCP 工具 | 参数 |
|------|---------|------|
| 拉起 MCP 服务 | `attach_process` | `package_name` |
| 获取会话状态 | `list_sessions` | — |
| 获取系统状态 | `get_system_status` | — |
| 启动网络捕获 | `start_capture` | `session_id`, `capture_ssl` |
| 安装 Hook | `hook_java_method` | `session_id`, `class_name`, `method_name` |
| 关闭会话 | `close_session` | `session_id` |

### 4.4 会话管理

- 每个已注入应用对应一个 MCP 会话
- 会话状态：created → attached → detached
- APP 实时展示会话列表，包括 Hook 数、消息数、运行时长
- 支持手动关闭会话，释放资源

## 五、技术实现

### 5.1 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 框架 | Next.js 16 (App Router) | React 服务端渲染框架 |
| 语言 | TypeScript | 类型安全 |
| 样式 | Tailwind CSS 4 | 原子化 CSS |
| 图标 | lucide-react | 轻量图标库 |
| 主题 | CSS 变量 + dark 模式 | Frida 绿色主色调 |

### 5.2 状态管理

采用 React `useState` + props 传递的轻量方案，核心状态集中在主页面 `page.tsx`：

```typescript
// 核心状态
const [activeTab, setActiveTab] = useState<TabId>("dashboard");
const [apps, setApps] = useState<AppInfo[]>(mockApps);        // 应用列表
const [scanning, setScanning] = useState(false);               // 扫描状态
const [selectedApp, setSelectedApp] = useState<AppInfo | null>(null);
const [mcpServer, setMcpServer] = useState<MCPServerStatus>(mockMCPServer);
const [tasks, setTasks] = useState<InjectionTask[]>(mockInjectionTasks);
```

### 5.3 类型定义

核心类型定义在 `src/lib/types.ts`，包括：

- `AppInfo`：应用信息（含注入状态、gadget 版本、MCP 状态）
- `DeviceInfo`：设备信息
- `MCPServerStatus`：MCP 服务器状态
- `MCPSession`：MCP 会话
- `MCPModule`：MCP 模块
- `InjectionTask`：注入任务
- `InjectionStatus`：注入状态枚举

### 5.4 与后端集成

当前版本使用 `src/lib/mock-data.ts` 中的模拟数据。与 FridaMCP 后端集成时，需替换为真实 API 调用：

```typescript
// 示例：获取应用列表（替换 mockApps）
async function fetchApps(): Promise<AppInfo[]> {
  // 1. 通过 adb 获取已安装应用列表
  const packages = await adb.listPackages();

  // 2. 对每个应用执行注入检测
  const apps = await Promise.all(packages.map(async (pkg) => {
    const detection = await detectInjection(pkg);
    return { ...pkg, ...detection };
  }));

  return apps;
}

// 示例：拉起 MCP 服务
async function launchMCP(app: AppInfo): Promise<void> {
  // 1. 确保应用运行
  if (app.injectionStatus !== 'running') {
    await adb.launchApp(app.packageName);
  }

  // 2. 调用 MCP attach_process
  const session = await mcp.callTool('attach_process', {
    package_name: app.packageName
  });

  // 3. 更新 UI
  updateAppStatus(app.id, { mcpStatus: 'online', sessionId: session.id });
}
```

## 六、后续规划

### 阶段一：Android 原生化

将 Next.js UI 原型转换为 Android 原生应用（Kotlin + Jetpack Compose），集成真实 Frida API：

- 使用 Frida 的 Java 绑定直接调用
- 通过 ADB 或 root 权限获取应用列表
- 实现真实的 APK 注入工具链

### 阶段二：完整注入工具链

- 自动化 smali 修改（`System.loadLibrary("frida-gadget")`）
- APK 签名（内置测试密钥或支持自定义密钥）
- 注入后自动验证 gadget 可加载

### 阶段三：高级功能

- **脚本市场**：内置常用 Frida 脚本（SSL Pinning 绕过、Root 检测绕过等）
- **分析报告导出**：将 Hook 日志、网络捕获导出为报告
- **多设备协同**：支持同时连接多台设备进行对比分析
