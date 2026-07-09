package com.fridamcp.app.data.repository

import android.content.Context
import android.os.Build
import com.fridamcp.app.data.model.*
import com.fridamcp.app.data.service.ShizukuManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class DeviceRepository(private val context: Context) {

    private val _deviceInfo = MutableStateFlow(
        DeviceInfo(
            id = "local",
            name = "检测中...",
            type = "local",
            status = DeviceStatus.CONNECTED,
            androidVersion = Build.VERSION.RELEASE,
            apiLevel = Build.VERSION.SDK_INT,
            arch = Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown",
            isRooted = false,
            fridaServerVersion = null,
            fridaServerRunning = false,
        )
    )
    val deviceInfo: StateFlow<DeviceInfo> = _deviceInfo.asStateFlow()

    fun refresh() {
        // 使用 ShizukuManager 的真实检测
        ShizukuManager.refresh()

        val isRooted = ShizukuManager.rootGranted
        val isShizuku = ShizukuManager.shizukuPermissionGranted
        val fridaRunning = ShizukuManager.isFridaServerRunning()
        val fridaVersion = ShizukuManager.getFridaVersion()

        // 设备名称
        val deviceName = "${Build.MANUFACTURER} ${Build.MODEL}"

        _deviceInfo.value = DeviceInfo(
            id = "local",
            name = deviceName,
            type = "local",
            status = DeviceStatus.CONNECTED,
            androidVersion = Build.VERSION.RELEASE,
            apiLevel = Build.VERSION.SDK_INT,
            arch = Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown",
            isRooted = isRooted, // 只表示真实 Root, 不包含 Shizuku
            fridaServerVersion = fridaVersion,
            fridaServerRunning = fridaRunning,
        )
    }
}
