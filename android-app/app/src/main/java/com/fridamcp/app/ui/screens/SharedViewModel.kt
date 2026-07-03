package com.fridamcp.app.ui.screens

import android.content.Intent
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
import com.fridamcp.app.data.service.ShizukuManager
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

    init {
        // Load real data at startup — device detection is fast (no I/O)
        deviceRepository.refresh()
        // App loading scans all APKs — defer to background thread to avoid ANR
        Thread {
            appRepository.loadInstalledApps()
            refreshInjectedCount()
        }.start()
        mcpRepository.addLog(LogLevel.INFO, "System", "FridaMCP 已启动 — 设备: ${deviceRepository.deviceInfo.value.name}")
    }

    fun refreshInjectedCount() {
        _injectedCount.value = apps.value.count {
            it.injectionStatus == InjectionStatus.INJECTED || it.injectionStatus == InjectionStatus.RUNNING
        }
    }

    fun scanAllApps() {
        mcpRepository.addLog(LogLevel.INFO, "Scanner", "开始扫描 ${apps.value.size} 个应用...")
        Thread {
            appRepository.loadInstalledApps()
            refreshInjectedCount()
            val injected = _injectedCount.value
            mcpRepository.addLog(LogLevel.INFO, "Scanner", "扫描完成 — 发现 $injected 个已注入应用")
        }.start()
    }

    fun scanApp(packageName: String) {
        Thread {
            appRepository.scanApp(packageName)
            refreshInjectedCount()
            mcpRepository.addLog(LogLevel.INFO, "Scanner", "已重新扫描: $packageName")
        }.start()
    }

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

    /** Toggle floating window overlay */
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
            return
        }
        val intent = Intent(ctx, FloatingWindowService::class.java)
        intent.action = FloatingWindowService.ACTION_SHOW
        ctx.startService(intent)
        _floatingWindowEnabled.value = true
        mcpRepository.addLog(LogLevel.INFO, "FloatingWindow", "悬浮窗已显示")
    }

    fun hideFloatingWindow() {
        val ctx = appRepository.context
        ctx.stopService(Intent(ctx, FloatingWindowService::class.java))
        _floatingWindowEnabled.value = false
        mcpRepository.addLog(LogLevel.INFO, "FloatingWindow", "悬浮窗已隐藏")
    }

    // === Shizuku / Root ===
    val permissionMode: String get() = ShizukuManager.currentMode.toString()
    val shizukuAuthorized: Boolean get() = ShizukuManager.shizukuPermissionGranted
    val shizukuBinderAlive: Boolean get() = ShizukuManager.shizukuBinderAlive
    val rootAvailable: Boolean get() = ShizukuManager.rootGranted
    val fridaServerRunning: Boolean get() = ShizukuManager.isFridaServerRunning()
    val fridaVersion: String? get() = ShizukuManager.getFridaVersion()

    private val _permissionRequestResult = MutableStateFlow<String?>(null)
    val permissionRequestResult: StateFlow<String?> = _permissionRequestResult.asStateFlow()

    fun requestShizuku() {
        val ctx = appRepository.context
        mcpRepository.addLog(LogLevel.INFO, "Shizuku", "正在请求 Shizuku 授权...")

        // 设置回调
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

        // 也刷新一次状态
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

    fun startFridaServer() {
        ShizukuManager.refresh()
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.ROOT) {
            val started = ShizukuManager.startFridaServer()
            if (started) {
                mcpRepository.addLog(LogLevel.INFO, "FridaServer", "frida-server 已启动")
            } else {
                mcpRepository.addLog(LogLevel.ERROR, "FridaServer", "frida-server 启动失败 — 请检查是否已下载")
            }
        } else {
            mcpRepository.addLog(LogLevel.WARNING, "FridaServer", "需要 Root 权限才能启动 frida-server")
        }
        deviceRepository.refresh()
    }

    fun stopFridaServer() {
        ShizukuManager.refresh()
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.ROOT) {
            val stopped = ShizukuManager.stopFridaServer()
            mcpRepository.addLog(
                LogLevel.INFO,
                "FridaServer",
                if (stopped) "frida-server 已停止" else "frida-server 停止失败"
            )
        } else {
            mcpRepository.addLog(LogLevel.WARNING, "FridaServer", "需要 Root 权限才能停止 frida-server")
        }
        deviceRepository.refresh()
    }

    fun openShizukuSettings() {
        try {
            appRepository.context.startActivity(com.fridamcp.app.data.service.ShizukuManager.getShizukuSettingsIntent())
        } catch (e: Exception) {
            mcpRepository.addLog(LogLevel.ERROR, "Shizuku", "打开设置失败: ${e.message} — 请先安装 Shizuku")
        }
    }

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

    fun toggleAppMCP(app: AppInfo) {
        when (app.mcpStatus) {
            MCPServiceStatus.ONLINE -> {
                appRepository.updateAppStatus(app.packageName, app.injectionStatus, MCPServiceStatus.OFFLINE)
                mcpRepository.removeSession(app.packageName)
                mcpRepository.addLog(LogLevel.INFO, "McpServer", "已断开 MCP 会话: ${app.packageName}")
            }
            else -> {
                // Launch the app first if not running
                try {
                    val launchIntent = appRepository.context.packageManager.getLaunchIntentForPackage(app.packageName)
                    if (launchIntent != null) {
                        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        appRepository.context.startActivity(launchIntent)
                        mcpRepository.addLog(LogLevel.INFO, "ProcessManager", "已启动: ${app.packageName}")
                    }
                } catch (e: Exception) {
                    mcpRepository.addLog(LogLevel.WARNING, "ProcessManager", "启动失败: ${e.message}")
                }
                appRepository.updateAppStatus(app.packageName, InjectionStatus.RUNNING, MCPServiceStatus.ONLINE)
                mcpRepository.addSession(app.packageName, app.appName)
                mcpRepository.addLog(LogLevel.INFO, "McpServer", "已创建 MCP 会话: ${app.packageName}")
            }
        }
    }

    fun removeInjection(app: AppInfo) {
        appRepository.updateAppStatus(app.packageName, InjectionStatus.NOT_INJECTED, null)
        refreshInjectedCount()
        try {
            val intent = Intent(Intent.ACTION_DELETE)
            intent.data = android.net.Uri.parse("package:${app.packageName}")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            appRepository.context.startActivity(intent)
            mcpRepository.addLog(LogLevel.WARNING, "Injector", "正在卸载已注入应用: ${app.packageName}")
        } catch (e: Exception) {
            mcpRepository.addLog(LogLevel.WARNING, "Injector", "已移除标记: ${app.packageName} (需手动卸载)")
        }
    }

    fun startInjection(
        apkPath: String,
        appName: String,
        packageName: String,
        arch: String,
        useApktool: Boolean,
    ): InjectionTask {
        mcpRepository.addLog(LogLevel.INFO, "ApkInjector", "开始注入: $appName ($packageName) [$arch]")
        val task = mcpRepository.createInjectionTask(apkPath, appName, packageName, arch, useApktool)

        // Run injection in background
        Thread {
            try {
                val injector = com.fridamcp.app.data.service.ApkInjector(appRepository.context)

                // Step 1: Detect arch (from parameter or auto)
                mcpRepository.updateTask(task.id, 10, InjectionTaskStatus.INJECTING)
                mcpRepository.addLog(LogLevel.DEBUG, "ApkInjector", "目标架构: $arch")

                // Step 2: Inject gadget
                mcpRepository.updateTask(task.id, 30, InjectionTaskStatus.INJECTING)
                mcpRepository.addLog(LogLevel.DEBUG, "ApkInjector", "注入 frida-gadget...")

                val result = injector.inject(apkPath, arch)

                when (result) {
                    is com.fridamcp.app.data.service.ApkInjector.Result.Success -> {
                        mcpRepository.updateTask(task.id, 100, InjectionTaskStatus.DONE, outputApk = result.outputPath)
                        appRepository.addInjectedApp(task.copy(outputApk = result.outputPath))
                        refreshInjectedCount()
                        mcpRepository.addLog(LogLevel.INFO, "ApkInjector", "注入完成: $appName → ${result.outputPath}")
                    }
                    is com.fridamcp.app.data.service.ApkInjector.Result.Error -> {
                        mcpRepository.updateTask(task.id, 0, InjectionTaskStatus.ERROR)
                        mcpRepository.addLog(LogLevel.ERROR, "ApkInjector", "注入失败: ${result.message}")
                    }
                }
            } catch (e: Exception) {
                mcpRepository.updateTask(task.id, 0, InjectionTaskStatus.ERROR)
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
