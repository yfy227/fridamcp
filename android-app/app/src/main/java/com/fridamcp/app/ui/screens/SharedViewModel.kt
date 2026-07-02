package com.fridamcp.app.ui.screens

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.fridamcp.app.FridaMCPApplication
import com.fridamcp.app.data.model.AppInfo
import com.fridamcp.app.data.model.InjectionTask
import com.fridamcp.app.data.model.InjectionTaskStatus
import com.fridamcp.app.data.model.LogEntry
import com.fridamcp.app.data.model.MCPModule
import com.fridamcp.app.data.model.MCPServerStatus
import com.fridamcp.app.data.model.MCPSession
import com.fridamcp.app.data.model.DeviceInfo
import com.fridamcp.app.data.repository.AppRepository
import com.fridamcp.app.data.repository.DeviceRepository
import com.fridamcp.app.data.repository.McpRepository
import kotlinx.coroutines.flow.StateFlow

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

    val injectedCount: StateFlow<Int> = kotlinx.coroutines.flow.MutableStateFlow(0)

    init {
        refreshInjectedCount()
    }

    fun refreshInjectedCount() {
        (injectedCount as kotlinx.coroutines.flow.MutableStateFlow).value =
            apps.value.count { it.injectionStatus.name in listOf("INJECTED", "RUNNING") }
    }

    fun scanApps() {
        appRepository.scanApps()
        refreshInjectedCount()
    }

    fun launchApp(appId: String) {
        appRepository.launchApp(appId)
        refreshInjectedCount()
        val app = apps.value.find { it.id == appId }
        app?.let {
            mcpRepository.updateDynamicSessions(apps.value.filter { a ->
                a.injectionStatus.name == "RUNNING" && a.mcpStatus?.name == "ONLINE"
            })
        }
    }

    fun toggleMCP(appId: String) {
        appRepository.toggleMCP(appId)
        mcpRepository.updateDynamicSessions(apps.value.filter {
            it.injectionStatus.name == "RUNNING" && it.mcpStatus?.name == "ONLINE"
        })
    }

    fun rescanApp(appId: String) {
        appRepository.rescanApp(appId)
    }

    fun removeInjection(appId: String) {
        appRepository.removeInjection(appId)
        refreshInjectedCount()
    }

    fun toggleMCPServer() {
        mcpRepository.toggleServer()
    }

    fun toggleModule(name: String) {
        mcpRepository.toggleModule(name)
    }

    fun createInjectionTask(
        apkPath: String,
        appName: String,
        packageName: String,
        arch: String,
        useApktool: Boolean,
    ): InjectionTask {
        val task = mcpRepository.createInjectionTask(apkPath, appName, packageName, arch, useApktool)
        // Simulate injection progress
        mcpRepository.updateTask(task.id, 100, InjectionTaskStatus.DONE, outputApk = "${apkPath.removeSuffix(".apk")}_injected.apk")
        appRepository.addInjectedApp(task.copy(outputApk = "${apkPath.removeSuffix(".apk")}_injected.apk"))
        refreshInjectedCount()
        mcpRepository.addLog(
            level = com.fridamcp.app.data.model.LogLevel.INFO,
            source = "ApkInjector",
            message = "注入完成: $appName ($packageName) [$arch]",
        )
        return task
    }
}

class SharedViewModelFactory(
    private val app: FridaMCPApplication,
) : ViewModelProvider.Factory() {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return SharedViewModel(
            app.appRepository,
            app.deviceRepository,
            app.mcpRepository,
        ) as T
    }
}
