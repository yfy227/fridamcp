# FridaMCP QEMU Bridge

> 在无 Docker/KVM 的环境下，通过 QEMU user mode 运行 Android arm64 二进制，提供 MCP 服务。

## 工作原理

```
AI 工具 ──(MCP SSE/HTTP)──> Python MCP Server (x86_64)
                                    │
                                    ▼
                            qemu-aarch64-static
                                    │
                                    ▼
                            Android rootfs (arm64)
                            /home/z/my-project/redroid-rootfs
```

Python MCP 服务器运行在 x86_64 上，通过 `qemu-aarch64-static` 用户模式模拟器执行 Android rootfs 中的 arm64 二进制文件。不需要 Docker、KVM 或 root 权限。

## 前置条件

1. `qemu-aarch64-static` — 下载静态编译的 QEMU user mode 二进制
2. Android rootfs — 从 redroid Docker 镜像提取或从 redroid-rootfs 目录获取
3. Python 3 — 运行 MCP 服务器

## 安装

```bash
# 1. 下载 qemu-aarch64-static
curl -fsSL "https://github.com/multiarch/qemu-user-static/releases/download/v7.2.0-1/qemu-aarch64-static" -o /home/z/bin/qemu-aarch64-static
chmod +x /home/z/bin/qemu-aarch64-static

# 2. 确保 Android rootfs 在 /home/z/my-project/redroid-rootfs

# 3. 启动 MCP 服务器
python3 fridamcp-qemu-server.py
```

## MCP 工具

| 工具 | 功能 | 实现方式 |
|------|------|---------|
| `ping` | 健康检查 | 直接返回 "pong" |
| `server_info` | 服务器状态 | 返回端口、rootfs 路径、会话数 |
| `get_device_info` | 设备信息 | `getprop` + QEMU 环境信息 |
| `list_apps` | 列出应用 | `pm list packages` |
| `list_files` | 列出目录 | `ls -la` |
| `read_file` | 读取文件 | `cat` |
| `exec_shell` | 执行命令 | `sh -c` |
| `get_logcat` | 获取日志 | `logcat -d -t N` |
| `check_injection` | 检测注入 | `pm path` + APK 扫描 |

## 连接

在 AI 工具中配置 MCP 端点：

```
SSE:  http://127.0.0.1:8768/sse
POST: http://127.0.0.1:8768/mcp
```

## 测试

```bash
# 运行全功能测试套件 (35 项测试)
python3 test_mcp_server.py
```

## 限制

- QEMU user mode 无法运行需要 binder/ashmem 的服务（如 PackageManager、ActivityManager）
- `pm list packages` 和 `logcat` 需要完整 Android 运行时，在 user mode 下可能返回空
- 文件操作限于 rootfs 目录内
- 无法安装 APK（需要 PackageInstaller 服务）
