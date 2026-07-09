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
 * 完整实现：
 * 1. Shizuku binder 存活监听 (OnBinderReceivedListener / OnBinderDeadListener)
 * 2. Shizuku 权限请求回调 (OnRequestPermissionResultListener)
 * 3. Root 检测：su 二进制 + 实际执行测试
 * 4. 命令执行：ROOT > SHIZUKU > DIRECT 三级降级
 * 5. frida-server 启动/停止 (需要 Root)
 */
object ShizukuManager {

    private const val TAG = "ShizukuManager"
    private const val SHIZUKU_PACKAGE = "moe.shizuku.privileged.api"
    private const val SHIZUKU_CLASS = "rikka.shizuku.api.Shizuku"
    private const val SHIZUKU_LISTENER_CLASS = "rikka.shizuku.api.Shizuku\$OnRequestPermissionResultListener"
    private const val SHIZUKU_BINDER_RECEIVED_CLASS = "rikka.shizuku.api.Shizuku\$OnBinderReceivedListener"
    private const val SHIZUKU_BINDER_DEAD_CLASS = "rikka.shizuku.api.Shizuku\$OnBinderDeadListener"
    private const val SHIZUKU_SERVER_NAME = "rikka.shizuku.shared.ShizukuProvider"
    private const val REQUEST_CODE = 0

    enum class PermissionMode {
        NONE, SHIZUKU, ROOT
    }

    @Volatile
    var currentMode: PermissionMode = PermissionMode.NONE
        private set

    @Volatile
    var shizukuBinderAlive: Boolean = false
        private set

    @Volatile
    var shizukuPermissionGranted: Boolean = false
        private set

    @Volatile
    var rootGranted: Boolean = false
        private set

    /** 权限状态变化回调 */
    var onPermissionChanged: ((PermissionMode) -> Unit)? = null

    /** Shizuku 权限请求结果回调 */
    var onShizukuPermissionResult: ((granted: Boolean) -> Unit)? = null

    /** Shizuku binder 状态变化回调 */
    var onBinderStateChanged: ((alive: Boolean) -> Unit)? = null

    // ============================================================
    // 初始化
    // ============================================================

    fun init(context: Context) {
        // 注册 Shizuku binder 监听 (通过反射)
        registerBinderListeners()

        // 检测 Root
        rootGranted = checkRootGranted()
        Log.i(TAG, "Root granted: $rootGranted")

        // 检测 Shizuku
        shizukuBinderAlive = isShizukuBinderAlive()
        shizukuPermissionGranted = isShizukuAuthorized()
        Log.i(TAG, "Shizuku binder alive: $shizukuBinderAlive, permission: $shizukuPermissionGranted")

        // 确定当前权限模式
        updateMode()
    }

    fun refresh() {
        rootGranted = checkRootGranted()
        shizukuBinderAlive = isShizukuBinderAlive()
        shizukuPermissionGranted = isShizukuAuthorized()
        updateMode()
    }

    private fun updateMode() {
        val newMode = when {
            rootGranted -> PermissionMode.ROOT
            shizukuPermissionGranted -> PermissionMode.SHIZUKU
            else -> PermissionMode.NONE
        }
        if (newMode != currentMode) {
            Log.i(TAG, "Permission mode changed: $currentMode → $newMode")
            currentMode = newMode
            onPermissionChanged?.invoke(newMode)
        }
    }

    // ============================================================
    // Root 检测 — 不只检查 su 是否存在，还实际测试执行
    // ============================================================

    /** 检查 su 二进制是否存在 */
    fun isRootAvailable(): Boolean {
        val paths = listOf(
            "/sbin/su", "/system/bin/su", "/system/xbin/su",
            "/data/local/xbin/su", "/data/local/bin/su",
            "/system/sd/xbin/su", "/system/bin/failsafe/su", "/su/bin/su"
        )
        return paths.any { File(it).exists() }
    }

    /** 实际测试 root 是否可用 — 执行 su -c id 并检查 uid=0 */
    fun checkRootGranted(): Boolean {
        if (!isRootAvailable()) return false
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("su", "-c", "id"))
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            val code = process.waitFor()
            Log.d(TAG, "su id output: $output, error: $error, code: $code")
            output.contains("uid=0") || (code == 0 && error.isBlank())
        } catch (e: Exception) {
            Log.w(TAG, "Root check failed: ${e.message}")
            false
        }
    }

    // ============================================================
    // Shizuku 检测
    // ============================================================

    fun isShizukuInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo(SHIZUKU_PACKAGE, 0) != null
        } catch (e: Exception) { false }
    }

    /** 检查 Shizuku binder 是否存活 */
    fun isShizukuBinderAlive(): Boolean {
        return try {
            val cls = Class.forName(SHIZUKU_CLASS)
            val ping = cls.getMethod("pingBinder").invoke(null) as? Boolean ?: false
            ping
        } catch (e: Exception) {
            false
        }
    }

    /** 检查 Shizuku 权限是否已授权 */
    fun isShizukuAuthorized(): Boolean {
        if (!isShizukuBinderAlive()) return false
        return try {
            val cls = Class.forName(SHIZUKU_CLASS)
            val checkMethod = cls.getMethod("checkSelfPermission")
            val result = checkMethod.invoke(null) as Int
            result == PackageManager.PERMISSION_GRANTED
        } catch (e: Exception) {
            false
        }
    }

    // ============================================================
    // Shizuku Binder 监听 — 通过反射注册监听器
    // ============================================================

    private fun registerBinderListeners() {
        try {
            val cls = Class.forName(SHIZUKU_CLASS)

            // 注册 OnBinderReceivedListener
            val binderReceivedInterface = Class.forName(SHIZUKU_BINDER_RECEIVED_CLASS)
            val binderReceivedProxy = java.lang.reflect.Proxy.newProxyInstance(
                ShizukuManager::class.java.classLoader,
                arrayOf(binderReceivedInterface)
            ) { _, method, _ ->
                if (method.name == "onBinderReceived") {
                    Log.i(TAG, "Shizuku binder received")
                    shizukuBinderAlive = true
                    shizukuPermissionGranted = isShizukuAuthorized()
                    updateMode()
                    onBinderStateChanged?.invoke(true)
                }
                null
            }
            val addBinderReceived = cls.getMethod("addBinderReceivedListener", binderReceivedInterface)
            addBinderReceived.invoke(null, binderReceivedProxy)

            // 注册 OnBinderDeadListener
            val binderDeadInterface = Class.forName(SHIZUKU_BINDER_DEAD_CLASS)
            val binderDeadProxy = java.lang.reflect.Proxy.newProxyInstance(
                ShizukuManager::class.java.classLoader,
                arrayOf(binderDeadInterface)
            ) { _, method, _ ->
                if (method.name == "onBinderDead") {
                    Log.i(TAG, "Shizuku binder dead")
                    shizukuBinderAlive = false
                    shizukuPermissionGranted = false
                    updateMode()
                    onBinderStateChanged?.invoke(false)
                }
                null
            }
            val addBinderDead = cls.getMethod("addBinderDeadListener", binderDeadInterface)
            addBinderDead.invoke(null, binderDeadProxy)

            Log.i(TAG, "Shizuku binder listeners registered")
        } catch (e: Exception) {
            Log.w(TAG, "Failed to register Shizuku binder listeners: ${e.message}")
        }
    }

    // ============================================================
    // Shizuku 权限请求 — 带回调
    // ============================================================

    fun requestShizukuPermission(context: Context) {
        if (!isShizukuBinderAlive()) {
            Log.w(TAG, "Shizuku binder not alive, opening settings")
            openShizukuSettings(context)
            onShizukuPermissionResult?.invoke(false)
            return
        }

        if (isShizukuAuthorized()) {
            Log.i(TAG, "Shizuku permission already granted")
            shizukuPermissionGranted = true
            updateMode()
            onShizukuPermissionResult?.invoke(true)
            return
        }

        try {
            val cls = Class.forName(SHIZUKU_CLASS)

            // 注册权限请求结果监听器
            val listenerInterface = Class.forName(SHIZUKU_LISTENER_CLASS)
            val listenerProxy = java.lang.reflect.Proxy.newProxyInstance(
                ShizukuManager::class.java.classLoader,
                arrayOf(listenerInterface)
            ) { _, method, args ->
                if (method.name == "onRequestPermissionResult") {
                    val requestCode = args?.getOrNull(0) as? Int ?: 0
                    val grantResult = args?.getOrNull(1) as? Int ?: -1
                    val granted = grantResult == PackageManager.PERMISSION_GRANTED
                    Log.i(TAG, "Shizuku permission result: requestCode=$requestCode, granted=$granted")
                    shizukuPermissionGranted = granted
                    updateMode()
                    onShizukuPermissionResult?.invoke(granted)
                }
                null
            }

            // 调用 addRequestPermissionResultListener
            val addListenerMethod = cls.getMethod("addRequestPermissionResultListener", listenerInterface)
            addListenerMethod.invoke(null, listenerProxy)

            // 调用 requestPermission
            val requestMethod = cls.getMethod("requestPermission", Int::class.javaPrimitiveType)
            requestMethod.invoke(null, REQUEST_CODE)

            Log.i(TAG, "Shizuku permission request sent (requestCode=$REQUEST_CODE)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to request Shizuku permission: ${e.message}")
            openShizukuSettings(context)
            onShizukuPermissionResult?.invoke(false)
        }
    }

    fun openShizukuSettings(context: Context) {
        try {
            context.startActivity(getShizukuSettingsIntent())
        } catch (e: Exception) {
            Log.e(TAG, "Shizuku not installed", e)
            // 尝试打开 Shizuku 的 Google Play 页面
            try {
                val playIntent = Intent(Intent.ACTION_VIEW,
                    android.net.Uri.parse("market://details?id=$SHIZUKU_PACKAGE"))
                playIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(playIntent)
            } catch (e2: Exception) {
                Log.e(TAG, "Cannot open Play Store either", e2)
            }
        }
    }

    fun getShizukuSettingsIntent(): Intent {
        return Intent(Intent.ACTION_MAIN).apply {
            component = ComponentName(SHIZUKU_PACKAGE, "$SHIZUKU_PACKAGE.MainActivity")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    }

    // ============================================================
    // 命令执行 — 三级降级: ROOT > SHIZUKU > DIRECT
    // ============================================================

    /** 执行 shell 命令 — 根据权限模式选择执行方式 */
    fun execShell(command: String): String {
        return when (currentMode) {
            PermissionMode.ROOT -> execRoot(command)
            PermissionMode.SHIZUKU -> execShizuku(command)
            PermissionMode.NONE -> execDirect(command)
        }
    }

    /** 直接执行 (应用进程权限) */
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
            val cls = Class.forName(SHIZUKU_CLASS)
            val newProcessMethod = cls.getMethod("newProcess",
                Array<String>::class.java, String::class.java, String::class.java)
            val process = newProcessMethod.invoke(null, arrayOf("sh", "-c", command), null, null) as Process
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            process.waitFor()
            output + if (error.isNotBlank()) "\n$error" else ""
        } catch (e: Exception) {
            Log.w(TAG, "Shizuku exec failed, falling back to direct: ${e.message}")
            execDirect(command)
        }
    }

    /** 通过 Root 执行 (su -c) */
    private fun execRoot(command: String): String {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("su", "-c", command))
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            val code = process.waitFor()
            if (code != 0 && error.isNotBlank()) {
                // Root 执行失败，降级到 Shizuku
                Log.w(TAG, "Root exec failed (code=$code), falling back to Shizuku")
                execShizuku(command)
            } else {
                output + if (error.isNotBlank()) "\n$error" else ""
            }
        } catch (e: Exception) {
            Log.w(TAG, "Root exec failed, falling back to Shizuku: ${e.message}")
            execShizuku(command)
        }
    }

    // ============================================================
    // frida-server 管理 (需要 Root 或 Shizuku)
    // ============================================================

    /** 启动 frida-server — Root 或 Shizuku (ADB) 模式均可 */
    fun startFridaServer(): Boolean {
        if (currentMode == PermissionMode.NONE) {
            Log.w(TAG, "Cannot start frida-server: no root or shizuku")
            return false
        }

        if (isFridaServerRunning()) {
            Log.i(TAG, "frida-server already running")
            return true
        }

        val fridaPaths = listOf(
            "/data/local/tmp/frida-server",
            "/data/local/tmp/frida-server-arm64",
            "/data/local/tmp/frida-server-arm",
            "/system/bin/frida-server",
            "/system/xbin/frida-server"
        )

        for (path in fridaPaths) {
            val result = execShell("test -x $path && echo EXISTS || echo MISSING")
            if (result.contains("EXISTS")) {
                Log.i(TAG, "Starting frida-server from $path (mode: $currentMode)")
                execShell("$path -D &")
                Thread.sleep(1000)
                if (isFridaServerRunning()) {
                    Log.i(TAG, "frida-server started successfully")
                    return true
                }
            }
        }

        Log.e(TAG, "frida-server binary not found in any path")
        return false
    }

    /** 停止 frida-server — Root 或 Shizuku 均可 */
    fun stopFridaServer(): Boolean {
        if (currentMode == PermissionMode.NONE) return false
        execShell("pkill -f frida-server 2>/dev/null; pkill -f frida_server 2>/dev/null")
        Thread.sleep(500)
        return !isFridaServerRunning()
    }

    /** 检查 frida-server 是否在运行 */
    fun isFridaServerRunning(): Boolean {
        return try {
            val procDir = File("/proc")
            val processDirs = procDir.listFiles { f: File -> f.name.matches(Regex("\\d+")) } ?: emptyArray()
            for (procDir in processDirs) {
                try {
                    val cmdline = File(procDir, "cmdline").readText().trimEnd('\u0000')
                    if (cmdline.contains("frida-server") || cmdline.contains("frida_server")) return true
                } catch (e: Exception) { continue }
            }
            false
        } catch (e: Exception) { false }
    }

    /** 获取 frida-server 版本 */
    fun getFridaVersion(): String? {
        return try {
            val result = execShell("frida-server --version 2>/dev/null || frida --version 2>/dev/null")
            result.trim().ifBlank { null }
        } catch (e: Exception) { null }
    }

    // ============================================================
    // 工具方法
    // ============================================================

    /** 获取权限状态的详细描述 */
    fun getPermissionStatusText(): String {
        return buildString {
            appendLine("=== 权限状态 ===")
            appendLine("当前模式: $currentMode")
            appendLine("Root 可用: ${isRootAvailable()} (su 二进制)")
            appendLine("Root 已授权: $rootGranted (实际执行测试)")
            appendLine("Shizuku 已安装: ${SHIZUKU_PACKAGE}")
            appendLine("Shizuku Binder 存活: $shizukuBinderAlive")
            appendLine("Shizuku 权限已授权: $shizukuPermissionGranted")
            appendLine("frida-server 运行中: ${isFridaServerRunning()}")
            appendLine("frida 版本: ${getFridaVersion() ?: "未检测到"}")
        }
    }
}
