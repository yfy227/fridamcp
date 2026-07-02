package com.fridamcp.app.data.repository

import android.content.Context
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable
import com.fridamcp.app.data.model.*
import com.fridamcp.app.ui.theme.AppIconColors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class AppRepository(private val context: Context) {

    private val _apps = MutableStateFlow<List<AppInfo>>(emptyList())
    val apps: StateFlow<List<AppInfo>> = _apps.asStateFlow()

    private val _scanning = MutableStateFlow(false)
    val scanning: StateFlow<Boolean> = _scanning.asStateFlow()

    init {
        // Start with mock data; real implementation will call loadInstalledApps()
        _apps.value = mockApps
    }

    /** Load installed apps from PackageManager */
    fun loadInstalledApps() {
        val pm = context.packageManager
        val packages = pm.getInstalledApplications(PackageManager.GET_META_DATA)
        val appList = packages.mapIndexed { index, appInfo ->
            val pkgInfo = try {
                pm.getPackageInfo(appInfo.packageName, 0)
            } catch (e: Exception) {
                null
            }
            AppInfo(
                id = "app-$index",
                packageName = appInfo.packageName,
                appName = pm.getApplicationLabel(appInfo).toString(),
                version = pkgInfo?.versionName ?: "unknown",
                versionCode = pkgInfo?.longVersionCode ?: 0,
                iconColor = AppIconColors[index % AppIconColors.size].value.toLong(),
                iconText = (pm.getApplicationLabel(appInfo).toString().firstOrNull() ?: '?').toString(),
                isSystem = (appInfo.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0,
                installTime = pkgInfo?.firstInstallTime ?: 0,
                updateTime = pkgInfo?.lastUpdateTime ?: 0,
                injectionStatus = InjectionStatus.NOT_INJECTED,
                detectionMethod = DetectionMethod.NONE,
            )
        }.sortedBy { it.appName }
        _apps.value = appList
    }

    /** Get app icon */
    fun getAppIcon(packageName: String): Drawable? {
        return try {
            context.packageManager.getApplicationIcon(packageName)
        } catch (e: Exception) {
            null
        }
    }

    /** Scan apps for injection status */
    fun scanApps() {
        _scanning.value = true
        // TODO: Real detection logic via InjectionDetector
        // For now, just update scan times
        _apps.value = _apps.value.map { it.copy(lastScanTime = System.currentTimeMillis()) }
        _scanning.value = false
    }

    /** Launch app */
    fun launchApp(appId: String) {
        _apps.value = _apps.value.map { app ->
            if (app.id == appId) {
                app.copy(
                    injectionStatus = InjectionStatus.RUNNING,
                    pid = (10000..40000).random(),
                    mcpStatus = MCPServiceStatus.ONLINE,
                    lastScanTime = System.currentTimeMillis(),
                    detectionMethod = DetectionMethod.RUNTIME,
                )
            } else app
        }
    }

    /** Toggle MCP service for app */
    fun toggleMCP(appId: String) {
        _apps.value = _apps.value.map { app ->
            if (app.id == appId) {
                val newStatus = if (app.mcpStatus == MCPServiceStatus.ONLINE) MCPServiceStatus.OFFLINE else MCPServiceStatus.ONLINE
                app.copy(mcpStatus = newStatus)
            } else app
        }
    }

    /** Rescan single app */
    fun rescanApp(appId: String) {
        _apps.value = _apps.value.map { app ->
            if (app.id == appId) app.copy(lastScanTime = System.currentTimeMillis()) else app
        }
    }

    /** Remove injection */
    fun removeInjection(appId: String) {
        _apps.value = _apps.value.map { app ->
            if (app.id == appId) {
                app.copy(
                    injectionStatus = InjectionStatus.NOT_INJECTED,
                    gadgetVersion = null,
                    gadgetArch = null,
                    injectedAt = null,
                    pid = null,
                    mcpPort = null,
                    mcpStatus = null,
                    detectionMethod = DetectionMethod.NONE,
                    lastScanTime = System.currentTimeMillis(),
                )
            } else app
        }
    }

    /** Add injected app to list */
    fun addInjectedApp(task: InjectionTask) {
        val newApp = AppInfo(
            id = "app-${System.currentTimeMillis()}",
            packageName = task.packageName,
            appName = task.appName,
            version = "1.0.0",
            versionCode = 10000,
            iconColor = 0xFF6366F1,
            iconText = task.appName.firstOrNull()?.toString() ?: "?",
            isSystem = false,
            installTime = System.currentTimeMillis(),
            updateTime = System.currentTimeMillis(),
            injectionStatus = InjectionStatus.INJECTED,
            gadgetVersion = "16.5.1",
            gadgetArch = task.arch,
            injectedAt = System.currentTimeMillis(),
            mcpStatus = MCPServiceStatus.OFFLINE,
            lastScanTime = System.currentTimeMillis(),
            detectionMethod = DetectionMethod.STATIC,
        )
        _apps.value = listOf(newApp) + _apps.value
    }
}
