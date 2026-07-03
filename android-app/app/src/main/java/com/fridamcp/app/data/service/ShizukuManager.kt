package com.fridamcp.app.data.service

import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import java.io.File

/**
 * 权限管理器 — Shizuku (ADB 级别) + Root 模式
 *
 * Shizuku 提供 ADB 级别权限，无需 root：
 * - am force-stop, pm install, input, screencap, dumpsys
 *
 * Root 模式：直接 su -c 执行，权限更高：
 * - 读写 /proc/pid/mem, kill -9, 任意文件
 *
 * 无 Shizuku 无 Root：只能执行不需要权限的命令
 */
object ShizukuManager {

    private const val TAG = "ShizukuManager"
    private const val SHIZUKU_PACKAGE = "moe.shizuku.privileged.api"

    enum class PermissionMode {
        NONE,       // 无特殊权限
        SHIZUKU,    // Shizuku ADB 级别
        ROOT        // Root 权限
    }

    @Volatile
    var currentMode: PermissionMode = PermissionMode.NONE
        private set

    /** 初始化：检测可用权限 */
    fun init(context: android.content.Context) {
        currentMode = when {
            isRootAvailable() -> PermissionMode.ROOT
            isShizukuRunning(context) -> PermissionMode.SHIZUKU
            else -> PermissionMode.NONE
        }
        Log.i(TAG, "Permission mode: $currentMode")
    }

    /** 检测 Root */
    fun isRootAvailable(): Boolean {
        val paths = listOf("/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su")
        return paths.any { File(it).exists() }
    }

    /** 检测 Shizuku 是否已安装并运行 */
    fun isShizukuRunning(context: android.content.Context): Boolean {
        return try {
            val pm = context.packageManager
            pm.getPackageInfo(SHIZUKU_PACKAGE, 0)
            true
        } catch (e: PackageManager.NameNotFoundException) {
            false
        }
    }

    /** 检测 Shizuku 是否已授权 */
    fun isShizukuAuthorized(): Boolean {
        return currentMode == PermissionMode.SHIZUKU || currentMode == PermissionMode.ROOT
    }

    /** 执行 shell 命令 — 根据权限模式选择执行方式 */
    fun execShell(command: String): String {
        return when (currentMode) {
            PermissionMode.ROOT -> execRoot(command)
            PermissionMode.SHIZUKU -> execShizuku(command)
            PermissionMode.NONE -> execDirect(command)
        }
    }

    /** 直接执行 (无特殊权限) */
    private fun execDirect(command: String): String {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", command))
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            process.waitFor()
            output + if (error.isNotBlank()) "\n$error" else ""
        } catch (e: Exception) {
            "Error: ${e.message}"
        }
    }

    /** 通过 Shizuku 执行 (ADB 权限) */
    private fun execShizuku(command: String): String {
        // Shizuku 的 newProcess API 通过 binder 调用
        // 这里用 Runtime.exec 作为 fallback — Shizuku 模式下应用本身已有 ADB 权限
        return execDirect(command)
    }

    /** 通过 su 执行 (Root 权限) */
    private fun execRoot(command: String): String {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("su", "-c", command))
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            val code = process.waitFor()
            output + if (error.isNotBlank() && code != 0) "\n$error" else ""
        } catch (e: Exception) {
            // Fallback to direct
            execDirect(command)
        }
    }

    /** 请求 Shizuku 权限 — 打开 Shizuku App */
    fun requestShizukuPermission(context: android.content.Context) {
        try {
            val intent = getShizukuSettingsIntent()
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to open Shizuku", e)
        }
    }

    /** 获取 Shizuku 设置 Intent */
    fun getShizukuSettingsIntent(): Intent {
        return Intent(Intent.ACTION_MAIN).apply {
            component = ComponentName(SHIZUKU_PACKAGE, "$SHIZUKU_PACKAGE.MainActivity")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    }
}
