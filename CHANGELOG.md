# Changelog

All notable changes to FridaMCP are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-07-01

### Fixed — APK 注入器破损修复（关键）

- **重新打包保留原始压缩方式**: `.so` 文件用 `ZIP_STORED` 而非 `ZIP_DEFLATED`，满足 Android mmap 优化要求
- **注入前剥离原签名**: 自动移除 `META-INF/*.SF|*.RSA|*.MF`，避免 `apksigner` 签名冲突
- **smali 寄存器分配修复**: 自动将 `.locals 0` 扩容为 `.locals 1`，防止 `INSTALL_FAILED_DEXOPT`
- **smali 注入点修复**: 跳过 `.annotation`/`.param` 块，在第一条实际指令处插入
- **simple 模式真正注入**: `inject_gadget` 不再只加 `.so`，而是调用 `apktool` 修改 smali
- **APK 完整性验证**: 注入后用 `aapt dump badging` 验证 APK 可正常解析

### Added

- `_repack_apk_safe()` — 安全重新打包，保留压缩方式和条目顺序
- `_is_signature_file()` — 签名文件检测
- `_inject_into_method()` — 安全 smali 注入（寄存器扩容 + annotation 跳过）
- `_verify_apk_integrity()` — APK 完整性验证
- 26 个新测试用例覆盖注入器修复

### Changed

- 版本号统一为 `2.2.0`（`__init__.py` / `setup.py` / `pyproject.toml` / `server.py` 全部一致）
- `server_info` 和 `health_check` 工具返回真实版本号

---

## [2.1.0] - 2026-06-30

### Added — 可验证性体系

- **模拟设备模式** (`--mock`): 无需真实 Android 设备即可完整测试
  - `MockDevice` / `MockSession` / `MockScript` / `MockProcess` 四个类
  - 7 个模拟进程（systemui/settings/targetapp/wechat/chrome 等）
  - 通过 `FRIDAMCP_MOCK_DEVICE=1` 或 `--mock` 启用
- **自测命令** (`--self-test`): 12 项检查，验证导入/工具注册/模拟工作流/沙箱/配置
- **工具列表命令** (`--list-tools`): 列出所有 71 个已注册 MCP 工具
- **单元测试套件** (88 个测试): 覆盖沙箱/会话/配置/模拟设备/注入器/MCP 集成
- **GitHub Actions CI**: Python 3.9-3.12 矩阵测试 + 自测 + 传输启动验证
- **Makefile**: `make test` / `make self-test` / `make run-mock` 等快捷命令

### Fixed

- 移除 `list_sessions` / `close_session` 重复注册（server.py 和 process.py）
- 修复 `mock_device.py` 导入路径错误
- 修复 `MockSession.detach()` 不触发 detach handler

---

## [2.0.0] - 2026-06-30

### Added — 架构增强

- **Session 生命周期管理**: 显式状态机（CREATED→ATTACHED→IDLE→DETACHED/EXPIRED）
  - 会话复用（同一 PID 默认复用现有会话）
  - 空闲超时回收（默认 600 秒）
  - 并发锁（每会话独立 RLock）
  - 保活线程（周期性清理超时/已分离会话）
  - 引用计数（多调用者复用）
- **Hook 沙箱隔离** (`hook_sandbox.py`): AI 生成的脚本经 try-catch 包装，异常通过 `send()` 回传
  - 静态校验（括号匹配、危险 API 检测）
  - 加载失败重试
  - 错误聚合供 AI 调试
- **SSL Pinning Bypass**: 多层绕过（Java/OkHttp2/OkHttp3/Conscrypt/Native BoringSSL）
- **Native 加密 Hook**: BoringSSL EVP 系列（`EVP_EncryptInit_ex` / `EVP_DigestInit_ex` / `HMAC_Init_ex`）
- **SSL 密钥导出**: `SSL_CTX_set_keylog_callback` 输出 SSLKEYLOGFILE 格式
- **APK 注入器增强**: v1/v2/v3 签名、zipalign、加固检测、多 ABI
- **多传输模式**: stdio（默认）/ SSE / HTTP
- **容器化部署**: Dockerfile + docker-compose
- **PyInstaller 打包**: `fridamcp.spec` + `build.sh`

### Changed

- 默认传输从 SSE 改为 stdio（Claude Desktop/Cursor 本地标准方式）
- `setup.py` 版本升级到 2.0.0

---

## [1.1.0] - 2026-06-29

### Added

- `script` 模块：AI 可直接运行任意 Frida JS 脚本
- `run_script` / `call_script_rpc` / `load_script_file` 工具
- 设备重连机制
- 优雅关闭

### Fixed

- 修复目录结构、死锁、重复注册等缺陷

---

## [1.0.0] - 2026-06-28

### Added

- 初始发布
- 9 个 MCP 模块：process / hook / memory / network / filesystem / ui_automation / crypto / log / script
- APK 注入器
- Android 端 frida-server 安装脚本
- MCP 服务器（SSE/HTTP 传输）

---

[2.2.0]: https://github.com/yfy227/fridamcp/releases/tag/v2.2.0
[2.1.0]: https://github.com/yfy227/fridamcp/releases/tag/v2.1.0
[2.0.0]: https://github.com/yfy227/fridamcp/releases/tag/v2.0.0
[1.1.0]: https://github.com/yfy227/fridamcp/releases/tag/v1.1.0
[1.0.0]: https://github.com/yfy227/fridamcp/releases/tag/v1.0.0
