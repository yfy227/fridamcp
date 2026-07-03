package com.fridamcp.app.data.service

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import java.io.File

/**
 * 权限管理器 — Shizuku (ADB 级别) + Root 模式
 *
 * Shizuku 提供 ADB 级别权限（无需 root）：
 * - am force-stop, pm install, input, screencap, dumpsys
 * 通过 rikka.shizuku.api.Shizuku.newProcess() 执行命令
 *
 * Root 模式：su -c 执行，权限更高
 * - 读写 /proc/pid/mem, kill -9, 任意文件
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
    fun init(context: Context) {
        currentMode = when {
            isRootAvailable() -> PermissionMode.ROOT
            isShizukuAuthorized() -> PermissionMode.SHIZUKU
            else -> PermissionMode.NONE
        }
        Log.i(TAG, "Permission mode: $currentMode")
    }

    /** 刷新权限状态 */
    fun refresh() {
        currentMode = when {
            isRootAvailable() -> PermissionMode.ROOT
            isShizukuAuthorized() -> PermissionMode.SHIZUKU
            else -> PermissionMode.NONE
        }
        Log.i(TAG, "Permission mode refreshed: $currentMode")
    }

    /** 检测 Root */
    fun isRootAvailable(): Boolean {
        val paths = listOf("/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su")
        return paths.any { File(it).exists() }
    }

    /** 检测 Shizuku 是否已安装 */
    fun isShizukuInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo(SHIZUKU_PACKAGE, 0)
            true
        } catch (e: PackageManager.NameNotFoundException) {
            false
        }
    }

    /** 检测 Shizuku 是否已授权 */
    fun isShizukuAuthorized(): Boolean {
        return try {
            rikka.shizuku.api.Shizuku.pingBinder() &&
                rikka.shizuku.api.Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
        } catch (e: Exception) {
            false
        }
    }

    /** 执行 shell 命令 — 根据权限模式选择执行方式 */
    fun execShell(command: String): String {
        return when (currentMode) {
            PermissionMode.ROOT -> execRoot(command)
            PermissionMode.SHIZUKU -> execShizuku(command)
            PermissionMode.NONE -> execDirect(command)
        }
    }

    /** 直接执行 (无特殊权限 — 只有应用自身权限) */
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
        return try {
            val process = rikka.shizuku.api.Shizuku.newProcess(arrayOf("sh", "-c", command), null, null)
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            process.waitFor()
            output + if (error.isNotBlank()) "\n$error" else ""
        } catch (e: Exception) {
            // Fallback to direct
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
            output + if (error.isNotBlank() && code != 0) "\n$error" else ""
        } catch (e: Exception) {
            execDirect(command)
        }
    }

    /** 请求 Shizuku 权限 */
    fun requestShizukuPermission(context: Context) {
        try {
            if (rikka.shizuku.api.Shizuku.shouldShowRequestPermissionRationale()) {
                // Previously denied — open Shizuku settings
                openShizukuSettings(context)
            } else {
                rikka.shizuku.api.Shizuku.requestPermission(0)
            }
        } catch (e: Exception) {
            // Shizuku not running — open settings
            openShizukuSettings(context)
        }
    }

    /** 打开 Shizuku 设置 */
    fun openShizukuSettings(context: Context) {
        try {
            val intent = getShizukuSettingsIntent()
            context.startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Shizuku not installed", e)
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
