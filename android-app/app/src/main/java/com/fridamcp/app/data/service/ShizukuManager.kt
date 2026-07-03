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
 * Shizuku 检测通过 PackageManager 检查安装 + ContentProvider 探测运行状态。
 * Shizuku 执行通过反射调用 rikka.shizuku.api.Shizuku.newProcess()（运行时可用）。
 * Root 模式：su -c 执行。
 *
 * 三种模式：
 * - NONE: 无特殊权限，只能 execDirect
 * - SHIZUKU: Shizuku 已授权，通过反射调用 newProcess 获得ADB权限
 * - ROOT: su -c 执行
 */
object ShizukuManager {

    private const val TAG = "ShizukuManager"
    private const val SHIZUKU_PACKAGE = "moe.shizuku.privileged.api"
    private const val SHIZUKU_CLASS = "rikka.shizuku.api.Shizuku"

    enum class PermissionMode {
        NONE, SHIZUKU, ROOT
    }

    @Volatile
    var currentMode: PermissionMode = PermissionMode.NONE
        private set

    fun init(context: Context) {
        currentMode = when {
            isRootAvailable() -> PermissionMode.ROOT
            isShizukuAuthorized() -> PermissionMode.SHIZUKU
            else -> PermissionMode.NONE
        }
        Log.i(TAG, "Permission mode: $currentMode")
    }

    fun refresh() {
        currentMode = when {
            isRootAvailable() -> PermissionMode.ROOT
            isShizukuAuthorized() -> PermissionMode.SHIZUKU
            else -> PermissionMode.NONE
        }
    }

    fun isRootAvailable(): Boolean {
        val paths = listOf("/sbin/su","/system/bin/su","/system/xbin/su","/data/local/xbin/su","/data/local/bin/su","/system/sd/xbin/su","/system/bin/failsafe/su","/su/bin/su")
        return paths.any { File(it).exists() }
    }

    fun isShizukuInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo(SHIZUKU_PACKAGE, 0) != null
        } catch (e: Exception) { false }
    }

    fun isShizukuAuthorized(): Boolean {
        return try {
            val cls = Class.forName(SHIZUKU_CLASS)
            val ping = cls.getMethod("pingBinder").invoke(null) as? Boolean ?: false
            if (!ping) return false
            val checkMethod = cls.getMethod("checkSelfPermission")
            val result = checkMethod.invoke(null) as Int
            result == PackageManager.PERMISSION_GRANTED
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

    private fun execShizuku(command: String): String {
        return try {
            // 通过反射调用 Shizuku.newProcess()
            val cls = Class.forName(SHIZUKU_CLASS)
            val newProcessMethod = cls.getMethod("newProcess",
                Array<String>::class.java, String::class.java, String::class.java)
            val process = newProcessMethod.invoke(null, arrayOf("sh", "-c", command), null, null) as Process
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            process.waitFor()
            output + if (error.isNotBlank()) "\n$error" else ""
        } catch (e: Exception) {
            // Fallback to direct
            execDirect(command)
        }
    }

    private fun execRoot(command: String): String {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("su", "-c", command))
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            val code = process.waitFor()
            output + if (error.isNotBlank() && code != 0) "\n$error" else ""
        } catch (e: Exception) {
            execShizuku(command)
        }
    }

    fun requestShizukuPermission(context: Context) {
        try {
            val cls = Class.forName(SHIZUKU_CLASS)
            val requestMethod = cls.getMethod("requestPermission", Int::class.javaPrimitiveType)
            requestMethod.invoke(null, 0)
        } catch (e: Exception) {
            // Shizuku not running — open settings
            openShizukuSettings(context)
        }
    }

    fun openShizukuSettings(context: Context) {
        try {
            context.startActivity(getShizukuSettingsIntent())
        } catch (e: Exception) {
            Log.e(TAG, "Shizuku not installed", e)
        }
    }

    fun getShizukuSettingsIntent(): Intent {
        return Intent(Intent.ACTION_MAIN).apply {
            component = ComponentName(SHIZUKU_PACKAGE, "$SHIZUKU_PACKAGE.MainActivity")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    }
}
