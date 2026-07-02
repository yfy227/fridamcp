package com.fridamcp.app.data.repository

import android.content.Context
import android.os.Build
import com.fridamcp.app.data.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class DeviceRepository(private val context: Context) {

    private val _deviceInfo = MutableStateFlow(mockDevice)
    val deviceInfo: StateFlow<DeviceInfo> = _deviceInfo.asStateFlow()

    /** Detect real device info */
    fun detectDevice() {
        _deviceInfo.value = DeviceInfo(
            id = "local",
            name = "${Build.MANUFACTURER} ${Build.MODEL}",
            type = "local",
            status = DeviceStatus.CONNECTED,
            androidVersion = Build.VERSION.RELEASE,
            apiLevel = Build.VERSION.SDK_INT,
            arch = Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown",
            isRooted = checkRoot(),
            fridaServerVersion = null,
            fridaServerRunning = false,
        )
    }

    private fun checkRoot(): Boolean {
        val paths = listOf(
            "/system/app/Superuser.apk", "/sbin/su", "/system/bin/su",
            "/system/xbin/su", "/data/local/xbin/su", "/data/local/bin/su",
            "/system/sd/xbin/su", "/system/bin/failsafe/su", "/data/semc/su",
            "/su/bin/su"
        )
        return paths.any { java.io.File(it).exists() }
    }
}
