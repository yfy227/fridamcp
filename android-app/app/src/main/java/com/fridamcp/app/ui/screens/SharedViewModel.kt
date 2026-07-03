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
        // Load real data at startup
        deviceRepository.detectDevice()
        appRepository.loadInstalledApps()
        refreshInjectedCount()
        mcpRepository.addLog(LogLevel.INFO, "System", "FridaMCP 已启动 — 设备: ${deviceRepository.deviceInfo.value.name}")
    }

    fun refreshInjectedCount() {
        _injectedCount.value = apps.value.count {
            it.injectionStatus == InjectionStatus.INJECTED || it.injectionStatus == InjectionStatus.RUNNING
        }
    }

    fun scanAllApps() {
        mcpRepository.addLog(LogLevel.INFO, "Scanner", "开始扫描 ${apps.value.size} 个应用...")
        appRepository.loadInstalledApps()
        refreshInjectedCount()
        val injected = _injectedCount.value
        mcpRepository.addLog(LogLevel.INFO, "Scanner", "扫描完成 — 发现 $injected 个已注入应用")
    }

    fun scanApp(packageName: String) {
        appRepository.scanApp(packageName)
        refreshInjectedCount()
        mcpRepository.addLog(LogLevel.INFO, "Scanner", "已重新扫描: $packageName")
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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ctx.startForegroundService(intent)
        } else {
            ctx.startService(intent)
        }
        _floatingWindowEnabled.value = true
        mcpRepository.addLog(LogLevel.INFO, "FloatingWindow", "悬浮窗已显示")
    }

    fun hideFloatingWindow() {
        val ctx = appRepository.context
        val intent = Intent(ctx, FloatingWindowService::class.java)
        intent.action = FloatingWindowService.ACTION_HIDE
        ctx.startService(intent)
        ctx.stopService(Intent(ctx, FloatingWindowService::class.java))
        _floatingWindowEnabled.value = false
        mcpRepository.addLog(LogLevel.INFO, "FloatingWindow", "悬浮窗已隐藏")
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
                mcpRepository.addLog(LogLevel.INFO, "McpServer", "已断开 MCP 会话: ${app.packageName}")
            }
            else -> {
                appRepository.updateAppStatus(app.packageName, InjectionStatus.RUNNING, MCPServiceStatus.ONLINE)
                mcpRepository.addLog(LogLevel.INFO, "McpServer", "已创建 MCP 会话: ${app.packageName}")
            }
        }
    }

    fun removeInjection(app: AppInfo) {
        appRepository.updateAppStatus(app.packageName, InjectionStatus.NOT_INJECTED, null)
        refreshInjectedCount()
        mcpRepository.addLog(LogLevel.WARNING, "Injector", "已移除注入标记: ${app.packageName} (需卸载重装)")
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
        // Simulate injection progress
        mcpRepository.updateTask(task.id, 100, InjectionTaskStatus.DONE, outputApk = "${apkPath.removeSuffix(".apk")}_injected.apk")
        appRepository.addInjectedApp(task.copy(outputApk = "${apkPath.removeSuffix(".apk")}_injected.apk"))
        refreshInjectedCount()
        mcpRepository.addLog(LogLevel.INFO, "ApkInjector", "注入完成: $appName ($packageName) [$arch]")
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
