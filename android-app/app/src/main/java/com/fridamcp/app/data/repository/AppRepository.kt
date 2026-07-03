package com.fridamcp.app.data.repository

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable
import com.fridamcp.app.data.model.*
import com.fridamcp.app.data.service.InjectionDetector
import com.fridamcp.app.ui.theme.AppIconColors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class AppRepository(val context: Context) {

    private val _apps = MutableStateFlow<List<AppInfo>>(emptyList())
    val apps: StateFlow<List<AppInfo>> = _apps.asStateFlow()

    private val _scanning = MutableStateFlow(false)
    val scanning: StateFlow<Boolean> = _scanning.asStateFlow()

    private val detector = InjectionDetector(context)
    private var colorIndex = 0

    /** Load real installed apps from PackageManager */
    fun loadInstalledApps() {
        _scanning.value = true
        try {
            val pm = context.packageManager
            val packages = pm.getInstalledApplications(0)
            val appList = packages.mapIndexed { index, appInfo ->
                val pkgInfo = try {
                    pm.getPackageInfo(appInfo.packageName, 0)
                } catch (e: Exception) {
                    null
                }

                val isSystem = (appInfo.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0

                // Detect injection status
                val detectionResult = try {
                    detector.detectStatic(appInfo.packageName)
                } catch (e: Exception) {
                    InjectionDetector.DetectionResult(false, DetectionMethod.NONE, "检测失败: ${e.message}")
                }

                val injectionStatus = if (detectionResult.detected) {
                    InjectionStatus.INJECTED
                } else {
                    InjectionStatus.NOT_INJECTED
                }

                val color = AppIconColors[colorIndex % AppIconColors.size].value.toLong()
                colorIndex++

                AppInfo(
                    id = "app-$index",
                    packageName = appInfo.packageName,
                    appName = pm.getApplicationLabel(appInfo).toString(),
                    version = pkgInfo?.versionName ?: "unknown",
                    versionCode = pkgInfo?.let { if (it.versionCode > 0) it.versionCode else 1 } ?: 1,
                    iconColor = color,
                    iconText = pm.getApplicationLabel(appInfo).toString().firstOrNull()?.toString() ?: "?",
                    isSystem = isSystem,
                    installTime = pkgInfo?.firstInstallTime ?: System.currentTimeMillis(),
                    updateTime = pkgInfo?.lastUpdateTime ?: System.currentTimeMillis(),
                    injectionStatus = injectionStatus,
                    gadgetVersion = detectionResult.gadgetVersion,
                    gadgetArch = detectionResult.gadgetArch,
                    injectedAt = if (detectionResult.detected) pkgInfo?.firstInstallTime else null,
                    mcpStatus = if (detectionResult.detected) MCPServiceStatus.OFFLINE else null,
                    lastScanTime = System.currentTimeMillis(),
                    detectionMethod = detectionResult.method,
                )
            }.sortedWith(compareBy<AppInfo> { it.injectionStatus != InjectionStatus.INJECTED }
                .thenBy { it.appName.lowercase() })

            _apps.value = appList
        } catch (e: Exception) {
            // If anything fails, leave empty list
        } finally {
            _scanning.value = false
        }
    }

    /** Scan a single app for injection */
    fun scanApp(packageName: String) {
        val apps = _apps.value.toMutableList()
        val index = apps.indexOfFirst { it.packageName == packageName }
        if (index < 0) return

        val app = apps[index]
        val result = detector.fullScan(app)
        apps[index] = app.copy(
            injectionStatus = if (result.detected) {
                if (result.method == DetectionMethod.RUNTIME || result.method == DetectionMethod.PROCESS) {
                    InjectionStatus.RUNNING
                } else {
                    InjectionStatus.INJECTED
                }
            } else {
                InjectionStatus.NOT_INJECTED
            },
            detectionMethod = result.method,
            lastScanTime = System.currentTimeMillis(),
            gadgetArch = result.gadgetArch,
            gadgetVersion = result.gadgetVersion,
        )
        _apps.value = apps
    }

    /** Update app status (e.g., after launch or MCP toggle) */
    fun updateAppStatus(packageName: String, status: InjectionStatus, mcpStatus: MCPServiceStatus? = null) {
        _apps.value = _apps.value.map { app ->
            if (app.packageName == packageName) {
                app.copy(
                    injectionStatus = status,
                    mcpStatus = mcpStatus ?: app.mcpStatus,
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
