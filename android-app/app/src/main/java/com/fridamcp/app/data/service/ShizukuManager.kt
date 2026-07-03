package com.fridamcp.app.data.service

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Process
import android.util.Log
import java.io.File

/**
 * Shizuku 权限管理器
 *
 * Shizuku 提供 ADB 级别权限，无需 root 即可执行：
 * - am force-stop (杀进程)
 * - pm install/uninstall
 * - input tap/swipe/text (UI 自动化)
 * - screencap (截图)
 * - dumpsys (获取 Activity 信息)
 * - 读取 /proc/pid/mem (需要 root 模式)
 *
 * Root 模式：如果设备已 root，直接用 su 执行命令，权限更高。
 */
object ShizukuManager {

    private const val TAG = "ShizukuManager"
    private const val SHIZUKU_PACKAGE = "moe.shizuku.privileged.api"

    /** 三种权限模式 */
    enum class PermissionMode {
        NONE,       // 无特殊权限
        SHIZUKU,    // Shizuku (ADB 级别)
        ROOT        // Root
    }

    var currentMode: PermissionMode = PermissionMode.NONE
        private set

    /** 检查 Shizuku 是否已安装 */
    fun isShizukuInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo(SHIZUKU_PACKAGE, 0) != null
        } catch (e: PackageManager.NameNotFoundException) {
            false
        }
    }

    /** 检查 Shizuku 是否已授权 */
    fun isShizukuAuthorized(): Boolean {
        return try {
            if (rikka.shizuku.api.Shizuku.pingBinder()) {
                if (rikka.shizuku.api.Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
                    return true
                }
            }
            false
        } catch (e: Exception) {
            false
        }
    }

    /** 检查设备是否已 root */
    fun isRootAvailable(): Boolean {
        val paths = listOf(
            "/system/bin/su", "/system/xbin/su", "/sbin/su",
            "/data/local/xbin/su", "/data/local/bin/su"
        )
        return paths.any { java.io.File(it).exists() }
    }

    /** 检测当前可用的权限模式 */
    fun detectMode(context: Context): PermissionMode {
        currentMode = when {
            isRootAvailable() -> PermissionMode.ROOT
            isShizukuInstalled(context) && isShizukuAuthorized() -> PermissionMode.SHIZUKU
            else -> PermissionMode.NONE
        }
        Log.i(TAG, "Permission mode: $currentMode")
        return currentMode
    }

    /**
     * 执行 shell 命令，根据权限模式选择执行方式
     * @return 命令输出 (stdout + stderr)
     */
    fun execShell(command: String): String {
        return when (currentMode) {
            PermissionMode.ROOT -> execRoot(command)
            PermissionMode.SHIZUKU -> execShizuku(command)
            PermissionMode.NONE -> execDirect(command)
        }
    }

    /** 直接执行 (只有 app 自身权限) */
    private fun execDirect(command: String): String {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", command))
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            process.waitFor()
            output + error
        } catch (e: Exception) {
            "Error: ${e.message}"
        }
    }

    /** 通过 Shizuku 执行 (ADB 权限) — 使用 newProcess */
    private fun execShizuku(command: String): String {
        return try {
            // Shizuku's newProcess gives us a Process with ADB-level permissions
            val process = rikka.shizuku.api.Shizuku.newProcess(arrayOf("sh", "-c", command), null, null)
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            process.waitFor()
            output + if (error.isNotBlank()) "\n$error" else ""
        } catch (e: Exception) {
            // Fallback to direct execution
            execDirect(command)
        }
    }

    /** 通过 su 执行 (Root 权限) */
    private fun execRoot(command: String): String {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("su", "-c", command))
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            val code = process.waitFor()
            if (code == 0) output else output + error
        } catch (e: Exception) {
            // Fallback to Shizuku or direct
            execShizuku(command)
        }
    }

    /** 请求 Shizuku 权限 */
    fun requestShizukuPermission() {
        try {
            if (rikka.shizuku.api.Shizuku.shouldShowRequestPermissionRationale()) {
                Log.w(TAG, "Shizuku permission previously denied")
            }
            rikka.shizuku.api.Shizuku.requestPermission(0)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to request Shizuku permission", e)
        }
    }

    /** 获取 Shizuku 的 Intent 用于打开设置 */
    fun getShizukuSettingsIntent(): Intent {
        return Intent(Intent.ACTION_MAIN).apply {
            component = ComponentName(SHIZUKU_PACKAGE, "$SHIZUKU_PACKAGE.MainActivity")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    }
}
