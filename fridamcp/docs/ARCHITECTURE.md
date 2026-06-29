# FridaMCP 架构设计

## 整体架构

FridaMCP 由三个核心组件构成，协同工作以实现 AI 辅助的 Android 应用动态分析。

```
┌─────────────────────────────────────────────────────────────────┐
│                         AI Client                                │
│              (Claude / GPT / 其他 MCP 客户端)                    │
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP Protocol (SSE/HTTP)
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    FridaMCP Server                               │
│                    (Port 8768)                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    MCP Server Core                       │   │
│  │              (FastMCP / mcp.server.Server)               │   │
│  └────────────────────────────┬─────────────────────────────┘   │
│                               │                                  │
│  ┌────────────────────────────▼─────────────────────────────┐   │
│  │                    Module Layer                          │   │
│  │  ┌────────┐ ┌──────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │   │
│  │  │Process │ │ Hook │ │Memory  │ │Network │ │Filesystem│ │   │
│  │  └────────┘ └──────┘ └────────┘ └────────┘ └──────────┘ │   │
│  │  ┌──────────┐ ┌────────┐ ┌──────┐                        │   │
│  │  │UI Auto   │ │ Crypto │ │ Log  │                        │   │
│  │  └──────────┘ └────────┘ └──────┘                        │   │
│  └────────────────────────────┬─────────────────────────────┘   │
│                               │                                  │
│  ┌────────────────────────────▼─────────────────────────────┐   │
│  │                    Core Layer                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │   │
│  │  │FridaClient   │  │DeviceManager │  │SessionManager│   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │   │
│  └────────────────────────────┬─────────────────────────────┘   │
└───────────────────────────────┼─────────────────────────────────┘
                                │ Frida API (USB/Remote)
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                    Android Device                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              frida-server (root 模式)                    │   │
│  │              或 frida-gadget (注入模式)                  │   │
│  └────────────────────────────┬─────────────────────────────┘   │
│                               │                                  │
│  ┌────────────────────────────▼─────────────────────────────┐   │
│  │                   Target Application                     │   │
│  │              (被分析的应用进程)                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 组件详解

### 1. MCP 服务器 (`fridamcp/server.py`)

- **监听端口**: 8768 (固定)
- **传输协议**: SSE (Server-Sent Events) / Streamable HTTP / stdio
- **实现**: 基于 `mcp` Python SDK 的 FastMCP
- **职责**:
  - 接收 AI 客户端的工具调用请求
  - 路由到对应的 MCP 模块
  - 管理会话生命周期

### 2. 核心层 (`fridamcp/core/`)

#### DeviceManager (`device_manager.py`)
- 管理 Frida 设备连接
- 支持 USB / Remote / Local 三种设备类型
- 单例模式，全局共享设备连接

#### SessionManager (`session_manager.py`)
- 管理 Frida 会话（Session）
- 每个会话对应一个被附加的进程
- 管理会话内的脚本和 Hook
- 维护消息缓冲区

#### FridaClient (`frida_client.py`)
- 高层 API 封装
- 提供进程管理、脚本执行、消息处理等方法
- 供 MCP 模块调用

### 3. 模块层 (`fridamcp/modules/`)

8 个功能模块，每个模块注册一组 MCP 工具：

| 模块 | 文件 | 功能 |
|------|------|------|
| Process | `process.py` | 进程/应用/会话管理 |
| Hook | `hook.py` | Java/Native Hook |
| Memory | `memory.py` | 内存读写搜索 |
| Network | `network.py` | 网络捕获/SSL Hook |
| Filesystem | `filesystem.py` | 设备文件操作 |
| UI Automation | `ui_automation.py` | 点击/输入/截图 |
| Crypto | `crypto.py` | 加密操作监控 |
| Log | `log.py` | 日志捕获 |

### 4. APK 注入器 (`injector/`)

- **目的**: 在无 root 设备上使用 Frida
- **原理**: 将 frida-gadget 注入到目标 APK
- **流程**:
  1. 解压/反编译 APK
  2. 复制 frida-gadget.so 到 lib 目录
  3. 修改 smali 代码添加 loadLibrary
  4. 重新打包并签名
- **两种模式**:
  - 简单模式：仅复制 gadget（zip 操作）
  - 完整模式：使用 apktool 反编译修改（推荐）

### 5. Android 端 (`android/`)

- `install_frida.sh`: 自动下载安装 frida-server
- `start_frida.sh`: 启动/停止/状态管理
- 需要 root 权限

## 数据流

### 典型 Hook 流程

```
1. AI 调用 list_applications() → 获取应用列表
2. AI 调用 spawn_app("com.example.app") → 启动应用
3. AI 调用 attach_process(pid) → 创建会话，返回 session_id
4. AI 调用 hook_method(session_id, class, method) → 注入 Hook 脚本
5. AI 调用 resume_process(pid) → 恢复进程执行
6. 应用运行，触发 Hook → 脚本通过 send() 发送消息
7. AI 调用 get_frida_messages(session_id) → 获取 Hook 结果
8. AI 调用 close_session(session_id) → 清理会话
```

### 网络捕获流程

```
1. AI 调用 attach_process("com.example.app") → 创建会话
2. AI 调用 start_capture(session_id, capture_ssl=True) → 启动捕获
3. 应用发起网络请求 → SSL Hook 捕获明文
4. AI 调用 get_capture(session_id) → 获取捕获数据
5. AI 调用 stop_capture(session_id) → 停止捕获
```

## 设计原则

1. **模块化**: 每个功能独立成模块，便于扩展
2. **单例模式**: 核心组件全局共享，避免重复创建
3. **异步友好**: MCP 协议基于异步，所有操作支持并发
4. **错误隔离**: 单个模块失败不影响其他模块
5. **消息缓冲**: 所有 Hook 消息缓冲在内存，供 AI 按需读取
6. **安全优先**: 不持久化敏感数据，会话关闭即清理

## 扩展指南

### 添加新模块

1. 在 `fridamcp/modules/` 下创建新文件
2. 实现 `register_tools(mcp)` 函数
3. 使用 `@mcp.tool()` 装饰器注册工具
4. 在 `fridamcp/modules/__init__.py` 中导入

```python
# fridamcp/modules/my_module.py
from ..core.frida_client import frida_client
from ..utils.logger import logger


def register_tools(mcp):
    @mcp.tool()
    def my_tool(param: str) -> dict:
        """工具描述"""
        try:
            # 实现
            return {"result": "..."}
        except Exception as e:
            return {"error": str(e)}
```

### 添加新工具到现有模块

在对应模块文件的 `register_tools` 函数内添加新的 `@mcp.tool()` 函数即可。
