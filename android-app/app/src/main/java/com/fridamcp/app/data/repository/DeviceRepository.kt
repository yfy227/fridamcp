package com.fridamcp.app.data.repository

import android.content.Context
import android.os.Build
import com.fridamcp.app.data.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.File

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

    /** Detect real device info — called at app startup */
    fun detectDevice() {
        val rooted = checkRoot()
        val fridaRunning = checkFridaServer()
        val fridaVersion = if (fridaRunning) getFridaVersion() else null

        _deviceInfo.value = DeviceInfo(
            id = "local",
            name = "${Build.MANUFACTURER} ${Build.MODEL}",
            type = "local",
            status = DeviceStatus.CONNECTED,
            androidVersion = Build.VERSION.RELEASE,
            apiLevel = Build.VERSION.SDK_INT,
            arch = Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown",
            isRooted = rooted,
            fridaServerVersion = fridaVersion,
            fridaServerRunning = fridaRunning,
        )
    }

    private fun checkRoot(): Boolean {
        val paths = listOf(
            "/system/app/Superuser.apk", "/sbin/su", "/system/bin/su",
            "/system/xbin/su", "/data/local/xbin/su", "/data/local/bin/su",
            "/system/sd/xbin/su", "/system/bin/failsafe/su", "/data/semc/su",
            "/su/bin/su", "/magisk/.core/bin/su"
        )
        return paths.any { File(it).exists() }
    }

    /** Check if frida-server is running by scanning /proc */
    private fun checkFridaServer(): Boolean {
        return try {
            val procDir = File("/proc")
            val processDirs = procDir.listFiles { f: File -> f.name.matches(Regex("\\d+")) } ?: emptyArray()
            for (procDir in processDirs) {
                try {
                    val cmdline = File(procDir, "cmdline").readText().trimEnd('\u0000')
                    if (cmdline.contains("frida-server") || cmdline.contains("frida_server")) {
                        return true
                    }
                } catch (e: Exception) { continue }
            }
            false
        } catch (e: Exception) {
            false
        }
    }

    /** Try to get frida-server version */
    private fun getFridaVersion(): String? {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("frida-server", "--version"))
            val output = process.inputStream.bufferedReader().readText().trim()
            process.waitFor()
            if (output.isNotEmpty()) output else null
        } catch (e: Exception) {
            "unknown"
        }
    }
}
