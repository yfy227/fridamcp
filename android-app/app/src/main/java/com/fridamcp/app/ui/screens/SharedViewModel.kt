package com.fridamcp.app.ui.screens

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.provider.Settings
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.fridamcp.app.FridaMCPApplication
import com.fridamcp.app.data.model.*
import com.fridamcp.app.data.repository.AppRepository
import com.fridamcp.app.data.repository.DeviceRepository
import com.fridamcp.app.data.repository.McpRepository
import com.fridamcp.app.data.service.FloatingWindowService
import com.fridamcp.app.data.service.InjectionDetector
import com.fridamcp.app.data.service.ShizukuManager
import com.fridamcp.app.data.service.isValidPackageName
import com.fridamcp.app.data.service.requirePackageName
import com.fridamcp.app.data.service.shellQuote
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class SharedViewModel(
    val appRepository: AppRepository,
    val deviceRepository: DeviceRepository,
    val mcpRepository: McpRepository,
) : ViewModel() {

    val apps: StateFlow<List<AppInfo>> = appRepository.apps
    val scanning: StateFlow<Boolean> = appRepository.scanning
    val deviceInfo: StateFlow<DeviceInfo> = deviceRepository.deviceInfo
    val serverStatus: StateFlow<MCPServerStatus> = mcpRepository.serverStatus
    val sessions: StateFlow<List<MCPSession>> = mcpRepository.sessions
    val modules: StateFlow<List<MCPModule>> = mcpRepository.modules
    val logs: StateFlow<List<LogEntry>> = mcpRepository.logs
    val tasks: StateFlow<List<InjectionTask>> = mcpRepository.tasks

    private val _injectedCount = MutableStateFlow(0)
    val injectedCount: StateFlow<Int> = _injectedCount.asStateFlow()

    private val _floatingWindowEnabled = MutableStateFlow(false)
    val floatingWindowEnabled: StateFlow<Boolean> = _floatingWindowEnabled.asStateFlow()

    // === Shizuku / Root ===
    val permissionMode: String get() = ShizukuManager.currentMode.toString()
    val shizukuAuthorized: Boolean get() = ShizukuManager.shizukuPermissionGranted
    val shizukuBinderAlive: Boolean get() = ShizukuManager.shizukuBinderAlive
    val rootAvailable: Boolean get() = ShizukuManager.rootGranted
    val fridaServerRunning: Boolean get() = ShizukuManager.isFridaServerRunning()
    val fridaVersion: String? get() = ShizukuManager.getFridaVersion()

    private val _fridaInstallProgress = MutableStateFlow<Pair<Int, String>?>(null)
    val fridaInstallProgress: StateFlow<Pair<Int, String>?> = _fridaInstallProgress.asStateFlow()

    private val fridaInjector = com.fridamcp.app.data.service.FridaInjector(appRepository.context)
    val fridaServerAvailable: Boolean get() = fridaInjector.isServerAvailable()
    val fridaInjectAvailable: Boolean get() = fridaInjector.isInjectAvailable()
    val fridaLatestVersion: String? get() = fridaInjector.getLatestVersion()

    private val _permissionRequestResult = MutableStateFlow<String?>(null)
    val permissionRequestResult: StateFlow<String?> = _permissionRequestResult.asStateFlow()

    init {
        // 初始化设备检测
        deviceRepository.refresh()

        // 注册广播接收器 — 接收 McpServerService 的状态更新
        registerReceivers()

        // 后台加载已安装应用
        Thread {
            mcpRepository.addLog(LogLevel.INFO, "Scanner", "开始扫描已安装应用...")
            appRepository.loadInstalledApps()
            refreshInjectedCount()
            val injected = _injectedCount.value
            mcpRepository.addLog(LogLevel.INFO, "Scanner", "扫描完成 — 发现 $injected 个已注入应用")
        }.start()
    }

    // =====================================================================
    // 广播接收器 — 接收 McpServerService 的真实状态
    // =====================================================================

    private fun registerReceivers() {
        val filter = IntentFilter().apply {
            addAction("com.fridamcp.app.SERVER_STATUS")
            addAction("com.fridamcp.app.SESSION_ADDED")
            addAction("com.fridamcp.app.SESSION_REMOVED")
            addAction("com.fridamcp.app.MODULE_TOGGLED")
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                appRepository.context.registerReceiver(serverStatusReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
            } else {
                appRepository.context.registerReceiver(serverStatusReceiver, filter)
            }
        } catch (e: Exception) {
            // 忽略重复注册
        }
    }

    private val serverStatusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                "com.fridamcp.app.SERVER_STATUS" -> {
                    val running = intent.getBooleanExtra("running", false)
                    val sessions = intent.getIntExtra("sessions", 0)
                    val tools = intent.getIntExtra("tools", 0)
                    val clients = intent.getIntExtra("clients", 0)
                    mcpRepository.onServerStatusUpdate(running, sessions, tools, clients)
                }
                "com.fridamcp.app.SESSION_ADDED" -> {
                    val sid = intent.getStringExtra("session_id") ?: return
                    val addr = intent.getStringExtra("client_addr") ?: "unknown"
                    mcpRepository.onSessionAdded(sid, addr)
                }
                "com.fridamcp.app.SESSION_REMOVED" -> {
                    val sid = intent.getStringExtra("session_id") ?: return
                    mcpRepository.onSessionRemoved(sid)
                }
            }
        }
    }

    override fun onCleared() {
        try {
            appRepository.context.unregisterReceiver(serverStatusReceiver)
        } catch (e: Exception) {}
        super.onCleared()
    }

    // =====================================================================
    // 扫描
    // =====================================================================

    fun scanApp(packageName: String) {
        Thread {
            appRepository.scanApp(packageName)
            refreshInjectedCount()
            mcpRepository.addLog(LogLevel.INFO, "Scanner", "已重新扫描: $packageName")
        }.start()
    }

    fun scanAllApps() {
        Thread {
            mcpRepository.addLog(LogLevel.INFO, "Scanner", "重新扫描所有应用...")
            appRepository.loadInstalledApps()
            refreshInjectedCount()
            mcpRepository.addLog(LogLevel.INFO, "Scanner", "扫描完成 — ${apps.value.size} 个应用, ${_injectedCount.value} 个已注入")
        }.start()
    }

    // =====================================================================
    // MCP 服务器
    // =====================================================================

    fun toggleMCPServer() {
        if (serverStatus.value.running) {
            mcpRepository.stopServer()
        } else {
            mcpRepository.startServer()
        }
    }

    fun toggleModule(name: String) {
        mcpRepository.toggleModule(name)
    }

    // =====================================================================
    // 悬浮窗
    // =====================================================================

    fun toggleFloatingWindow() {
        if (_floatingWindowEnabled.value) {
            hideFloatingWindow()
        } else {
            showFloatingWindow()
        }
    }

    fun showFloatingWindow() {
        val ctx = appRepository.context
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(ctx)) {
            mcpRepository.addLog(LogLevel.WARNING, "FloatingWindow", "需要悬浮窗权限 — 请在设置中开启")
            // 打开设置页面
            val intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION)
            intent.data = android.net.Uri.parse("package:${ctx.packageName}")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            return
        }
        val intent = Intent(ctx, FloatingWindowService::class.java)
        intent.action = FloatingWindowService.ACTION_SHOW
        ctx.startService(intent)
        _floatingWindowEnabled.value = true
        mcpRepository.addLog(LogLevel.INFO, "FloatingWindow", "悬浮窗已显示")
    }

    fun hideFloatingWindow() {
        val intent = Intent(appRepository.context, FloatingWindowService::class.java)
        intent.action = FloatingWindowService.ACTION_HIDE
        appRepository.context.startService(intent)
        _floatingWindowEnabled.value = false
        mcpRepository.addLog(LogLevel.INFO, "FloatingWindow", "悬浮窗已隐藏")
    }

    // =====================================================================
    // Shizuku / Root 权限
    // =====================================================================

    fun requestShizuku() {
        val ctx = appRepository.context
        mcpRepository.addLog(LogLevel.INFO, "Shizuku", "正在请求 Shizuku 授权...")

        ShizukuManager.onShizukuPermissionResult = { granted: Boolean ->
            ShizukuManager.refresh()
            val mode = ShizukuManager.currentMode
            if (granted) {
                _permissionRequestResult.value = "✅ Shizuku 授权成功 — 模式: $mode"
                mcpRepository.addLog(LogLevel.INFO, "Shizuku", "授权成功 — 模式: $mode")
            } else {
                _permissionRequestResult.value = "❌ Shizuku 授权被拒绝 — 请在 Shizuku 应用中允许"
                mcpRepository.addLog(LogLevel.WARNING, "Shizuku", "授权被拒绝 — 请在 Shizuku 中手动允许")
            }
            deviceRepository.refresh()
        }

        ShizukuManager.requestShizukuPermission(ctx)

        ShizukuManager.refresh()
        if (!ShizukuManager.shizukuBinderAlive) {
            _permissionRequestResult.value = "⚠️ Shizuku 未运行 — 请先启动 Shizuku 服务"
            mcpRepository.addLog(LogLevel.WARNING, "Shizuku", "Binder 未连接 — 请先启动 Shizuku")
        }
    }

    fun refreshPermission() {
        ShizukuManager.refresh()
        deviceRepository.refresh()
        mcpRepository.addLog(LogLevel.INFO, "Permission", ShizukuManager.getPermissionStatusText())
    }

    /**
     * 启动 frida-server — Root 或 Shizuku (ADB) 模式均可
     * (之前只检查 ROOT，遗漏了 Shizuku)
     */
    fun startFridaServer() {
        ShizukuManager.refresh()
        val mode = ShizukuManager.currentMode
        if (mode == ShizukuManager.PermissionMode.NONE) {
            mcpRepository.addLog(LogLevel.WARNING, "FridaServer", "需要 Shizuku 或 Root 权限才能启动 frida-server")
            return
        }

        val started = ShizukuManager.startFridaServer()
        if (started) {
            mcpRepository.addLog(LogLevel.INFO, "FridaServer", "frida-server 已启动 (via $mode)")
        } else {
            mcpRepository.addLog(LogLevel.ERROR, "FridaServer", "frida-server 启动失败 — 请检查是否已下载到 /data/local/tmp/")
        }
        deviceRepository.refresh()
    }

    fun stopFridaServer() {
        ShizukuManager.refresh()
        val mode = ShizukuManager.currentMode
        if (mode == ShizukuManager.PermissionMode.NONE) {
            mcpRepository.addLog(LogLevel.WARNING, "FridaServer", "需要 Shizuku 或 Root 权限才能停止 frida-server")
            return
        }

        val stopped = ShizukuManager.stopFridaServer()
        mcpRepository.addLog(
            LogLevel.INFO,
            "FridaServer",
            if (stopped) "frida-server 已停止" else "frida-server 停止失败"
        )
        deviceRepository.refresh()
    }

    fun openShizukuSettings() {
        try {
            appRepository.context.startActivity(ShizukuManager.getShizukuSettingsIntent())
        } catch (e: Exception) {
            mcpRepository.addLog(LogLevel.ERROR, "Shizuku", "打开设置失败: ${e.message} — 请先安装 Shizuku")
        }
    }

    // =====================================================================
    // 应用管理
    // =====================================================================

    fun launchApp(packageName: String) {
        try {
            val intent = appRepository.context.packageManager.getLaunchIntentForPackage(packageName)
            if (intent != null) {
                intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                appRepository.context.startActivity(intent)
                mcpRepository.addLog(LogLevel.INFO, "ProcessManager", "启动应用: $packageName")
            } else {
                mcpRepository.addLog(LogLevel.WARNING, "ProcessManager", "无法启动 $packageName — 无启动 Activity")
            }
        } catch (e: Exception) {
            mcpRepository.addLog(LogLevel.ERROR, "ProcessManager", "启动失败: ${e.message}")
        }
    }

    /**
     * 切换应用的 MCP 会话 — 真实检测 frida-gadget 是否在运行
     * 不再假设会话创建成功
     */
    fun toggleAppMCP(app: AppInfo) {
        when (app.mcpStatus) {
            MCPServiceStatus.ONLINE -> {
                appRepository.updateAppStatus(app.packageName, app.injectionStatus, MCPServiceStatus.OFFLINE)
                mcpRepository.addLog(LogLevel.INFO, "McpServer", "已断开 MCP 会话: ${app.packageName}")
            }
            else -> {
                // 先检查应用是否在运行
                val safePackage = try { requirePackageName(app.packageName) } catch (e: IllegalArgumentException) {
                    mcpRepository.addLog(LogLevel.ERROR, "McpServer", e.message ?: "包名不合法")
                    return
                }
                var pidResult = ShizukuManager.execShell("pidof ${shellQuote(safePackage)}")
                var pid = pidResult.trim().lines().firstOrNull()?.trim()?.toIntOrNull()

                if (pid == null || pid <= 0) {
                    // 应用未运行 — 启动它
                    val launchIntent = appRepository.context.packageManager.getLaunchIntentForPackage(app.packageName)
                    if (launchIntent != null) {
                        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        appRepository.context.startActivity(launchIntent)
                        mcpRepository.addLog(LogLevel.INFO, "ProcessManager", "已启动: ${app.packageName}")
                        // 等待应用启动后重新读取 PID
                        Thread.sleep(2000)
                        pidResult = ShizukuManager.execShell("pidof ${shellQuote(safePackage)}")
                        pid = pidResult.trim().lines().firstOrNull()?.trim()?.toIntOrNull()
                    } else {
                        mcpRepository.addLog(LogLevel.ERROR, "McpServer", "无法启动 ${app.packageName} — 无启动 Activity")
                        return
                    }
                }

                // 检查 frida-gadget 是否在该进程中运行
                val detector = InjectionDetector(appRepository.context)
                val runtimeResult = detector.detectProcess(app.packageName)

                if (runtimeResult.detected) {
                    // gadget 在运行 — 可以连接
                    appRepository.updateAppStatus(app.packageName, InjectionStatus.RUNNING, MCPServiceStatus.ONLINE, pid = pid)
                    mcpRepository.addLog(LogLevel.INFO, "McpServer", "MCP 会话已建立: ${app.packageName} (gadget 检测到)")
                    mcpRepository.addLog(LogLevel.INFO, "McpServer", "frida-gadget listen on 127.0.0.1:27042")
                } else {
                    // gadget 未检测到
                    appRepository.updateAppStatus(app.packageName, InjectionStatus.INJECTED, MCPServiceStatus.ERROR)
                    mcpRepository.addLog(LogLevel.WARNING, "McpServer", "应用 ${app.packageName} 已注入但未检测到运行中的 frida-gadget")
                    mcpRepository.addLog(LogLevel.WARNING, "McpServer", "请确保: 1) 应用已正确注入 2) gadget config 端口为 27042")
                }
            }
        }
    }

    /**
     * 移除注入标记 — 清除应用注入状态
     * 注意: 这不会卸载应用，只是清除 UI 中的注入标记
     * 如需卸载已注入的应用，请手动卸载
     */
    fun removeInjection(app: AppInfo) {
        appRepository.updateAppStatus(app.packageName, InjectionStatus.NOT_INJECTED, null, clearMcp = true)
        refreshInjectedCount()
        mcpRepository.addLog(LogLevel.INFO, "Injector", "已移除注入标记: ${app.packageName} (如需卸载请手动操作)")
    }

    fun uninstallInjectedApp(app: AppInfo) {
        try {
            val intent = Intent(Intent.ACTION_DELETE)
            intent.data = android.net.Uri.parse("package:${app.packageName}")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            appRepository.context.startActivity(intent)
            mcpRepository.addLog(LogLevel.WARNING, "Injector", "正在卸载: ${app.packageName}")
        } catch (e: Exception) {
            mcpRepository.addLog(LogLevel.ERROR, "Injector", "卸载失败: ${e.message}")
        }
    }

    private fun refreshInjectedCount() {
        _injectedCount.value = apps.value.count {
            it.injectionStatus == InjectionStatus.INJECTED || it.injectionStatus == InjectionStatus.RUNNING
        }
    }

    // =====================================================================
    // Frida 引擎管理 (本地注入模式)
    // 参考: https://bbs.kanxue.com/thread-282491.htm
    // 参考: https://www.52pojie.cn/thread-1823118-1-1.html
    // =====================================================================

    /**
     * 下载并安装 frida-server + frida-inject
     * 流程: 下载 XZ → 纯 Java 解压 → 复制到 /data/local/tmp/ → chmod
     */
    fun installFrida() {
        val arch = android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "arm64-v8a"
        mcpRepository.addLog(LogLevel.INFO, "FridaInstaller", "开始安装 Frida (arch=$arch)")

        Thread {
            val ok = fridaInjector.install(arch) { progress, msg ->
                _fridaInstallProgress.value = progress to msg
                mcpRepository.addLog(LogLevel.DEBUG, "FridaInstaller", "[$progress%] $msg")
            }
            _fridaInstallProgress.value = null

            if (ok) {
                mcpRepository.addLog(LogLevel.INFO, "FridaInstaller", "Frida 安装完成")
            } else {
                mcpRepository.addLog(LogLevel.ERROR, "FridaInstaller", "Frida 安装失败")
            }
            deviceRepository.refresh()
        }.start()
    }

    fun startFridaServerViaInjector() {
        Thread {
            val ok = fridaInjector.startServer()
            mcpRepository.addLog(
                if (ok) LogLevel.INFO else LogLevel.ERROR,
                "FridaServer",
                if (ok) "frida-server 已启动" else "frida-server 启动失败"
            )
            deviceRepository.refresh()
        }.start()
    }

    fun stopFridaServerViaInjector() {
        Thread {
            val ok = fridaInjector.stopServer()
            mcpRepository.addLog(
                LogLevel.INFO,
                "FridaServer",
                "frida-server 已停止"
            )
            deviceRepository.refresh()
        }.start()
    }

    // =====================================================================
    // APK 注入 (可选 — 需要 PC 端 apktool 完成 smali patch)
    // =====================================================================

    fun startInjection(
        apkPath: String,
        appName: String,
        packageName: String,
        arch: String,
    ): InjectionTask {
        if (!apkPath.endsWith(".apk", ignoreCase = true) || !java.io.File(apkPath).exists()) {
            mcpRepository.addLog(LogLevel.ERROR, "ApkInjector", "APK 路径无效: $apkPath")
            return mcpRepository.createInjectionTask(apkPath, appName.ifBlank { "Unknown" }, packageName.ifBlank { "invalid" }, arch).also {
                mcpRepository.updateTask(it.id, 0, InjectionTaskStatus.ERROR, error = "APK 路径无效")
            }
        }
        if (!isValidPackageName(packageName)) {
            mcpRepository.addLog(LogLevel.ERROR, "ApkInjector", "包名格式不合法: $packageName")
            return mcpRepository.createInjectionTask(apkPath, appName.ifBlank { "Unknown" }, packageName.ifBlank { "invalid" }, arch).also {
                mcpRepository.updateTask(it.id, 0, InjectionTaskStatus.ERROR, error = "包名格式不合法")
            }
        }
        mcpRepository.addLog(LogLevel.INFO, "ApkInjector", "开始注入: $appName ($packageName) [$arch]")
        val task = mcpRepository.createInjectionTask(apkPath, appName, packageName, arch)

        Thread {
            try {
                val injector = com.fridamcp.app.data.service.ApkInjector(appRepository.context)

                mcpRepository.updateTask(task.id, 10, InjectionTaskStatus.ANALYZING)
                mcpRepository.addLog(LogLevel.DEBUG, "ApkInjector", "目标架构: $arch")

                mcpRepository.updateTask(task.id, 40, InjectionTaskStatus.INJECTING)
                mcpRepository.addLog(LogLevel.DEBUG, "ApkInjector", "注入 frida-gadget...")

                mcpRepository.updateTask(task.id, 80, InjectionTaskStatus.SIGNING)

                val result = injector.inject(apkPath, arch)

                when (result) {
                    is com.fridamcp.app.data.service.ApkInjector.Result.Success -> {
                        mcpRepository.updateTask(task.id, 92, InjectionTaskStatus.INSTALLING, outputApk = result.outputPath)
                        mcpRepository.updateTask(task.id, 100, InjectionTaskStatus.DONE, outputApk = result.outputPath)
                        appRepository.addInjectedApp(task.copy(outputApk = result.outputPath))
                        refreshInjectedCount()
                        mcpRepository.addLog(LogLevel.INFO, "ApkInjector", "注入完成: $appName → ${result.outputPath}")
                    }
                    is com.fridamcp.app.data.service.ApkInjector.Result.Error -> {
                        mcpRepository.updateTask(task.id, 0, InjectionTaskStatus.ERROR, error = result.message)
                        mcpRepository.addLog(LogLevel.ERROR, "ApkInjector", "注入失败: ${result.message}")
                    }
                }
            } catch (e: Exception) {
                mcpRepository.updateTask(task.id, 0, InjectionTaskStatus.ERROR, error = e.message)
                mcpRepository.addLog(LogLevel.ERROR, "ApkInjector", "注入异常: ${e.message}")
            }
        }.start()

        return task
    }
}

class SharedViewModelFactory(
    private val app: FridaMCPApplication,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return SharedViewModel(
            app.appRepository,
            app.deviceRepository,
            app.mcpRepository,
        ) as T
    }
}
