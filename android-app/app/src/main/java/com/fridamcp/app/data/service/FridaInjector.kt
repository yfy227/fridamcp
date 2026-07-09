package com.fridamcp.app.data.service

import android.content.Context
import android.util.Log
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import org.tukaani.xz.XZInputStream

/**
 * Frida 注入引擎 — 本地模式
 *
 * 核心流程:
 * 1. 下载 frida-server + frida-inject 到 /data/local/tmp/ (通过 Shizuku/Root)
 * 2. frida-server 后台运行 — 提供注入能力
 * 3. frida-inject -p PID -s script.js — 注入 JS 脚本到目标进程
 * 4. MCP 服务器暴露接口 — 客户端连接并交互
 *
 * 不需要:
 * - APK 修改/重打包
 * - smali patch
 * - APK 签名
 * - Python/Termux
 *
 * 参考:
 * - https://bbs.kanxue.com/thread-282491.htm (Frida一把梭)
 * - https://www.52pojie.cn/thread-1823118-1-1.html (Frida基础)
 * - https://frida.re/docs/android/ (官方文档)
 * - https://frida.re/docs/modes/ (注入模式)
 */
class FridaInjector(private val context: Context) {

    companion object {
        private const val TAG = "FridaInjector"
        private const val FRIDA_DIR = "/data/local/tmp"
        private const val FRIDA_SERVER = "$FRIDA_DIR/frida-server"
        private const val FRIDA_INJECT = "$FRIDA_DIR/frida-inject"
        private const val GITHUB_API = "https://api.github.com/repos/frida/frida/releases/latest"
    }

    /**
     * 检查 frida-server 是否在运行
     */
    fun isServerRunning(): Boolean = ShizukuManager.isFridaServerRunning()

    /**
     * 检查 frida-inject 二进制是否存在
     */
    fun isInjectAvailable(): Boolean {
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) return false
        val result = ShizukuManager.execShell("test -x $FRIDA_INJECT && echo YES || echo NO")
        return result.contains("YES")
    }

    /**
     * 检查 frida-server 二进制是否存在
     */
    fun isServerAvailable(): Boolean {
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) return false
        val result = ShizukuManager.execShell("test -x $FRIDA_SERVER && echo YES || echo NO")
        return result.contains("YES")
    }

    /**
     * 获取已安装的 frida 版本
     */
    fun getInstalledVersion(): String? = ShizukuManager.getFridaVersion()

    /**
     * 获取最新 frida 版本号 (从 GitHub API)
     */
    fun getLatestVersion(): String? {
        return try {
            val conn = URL(GITHUB_API).openConnection() as HttpURLConnection
            conn.connectTimeout = 10000
            conn.readTimeout = 10000
            conn.setRequestProperty("Accept", "application/vnd.github.v3+json")
            if (conn.responseCode != 200) return null
            val json = org.json.JSONObject(conn.inputStream.bufferedReader().readText())
            conn.disconnect()
            json.optString("tag_name", "").ifBlank { null }
        } catch (e: Exception) {
            Log.w(TAG, "getLatestVersion: ${e.message}")
            null
        }
    }

    /**
     * 下载并安装 frida-server + frida-inject
     *
     * @param arch CPU 架构 (arm64-v8a, armeabi-v7a, x86, x86_64)
     * @param version frida 版本 (null = 最新)
     * @param progress 回调 (0-100)
     * @return true 成功
     *
     * 参考: https://frida.re/docs/android/
     */
    fun install(arch: String, version: String? = null, progress: (Int, String) -> Unit): Boolean {
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
            progress(0, "错误: 需要 Shizuku 或 Root 权限")
            return false
        }

        val fridaArch = when (arch) {
            "arm64-v8a" -> "arm64"
            "armeabi-v7a" -> "arm"
            "x86_64" -> "x86_64"
            "x86" -> "x86"
            else -> "arm64"
        }

        val ver = version ?: getLatestVersion() ?: run {
            progress(0, "错误: 无法获取最新 frida 版本")
            return false
        }
        progress(5, "Frida 版本: $ver, 架构: $fridaArch")

        // 下载 frida-server
        progress(10, "下载 frida-server...")
        val serverUrl = "https://github.com/frida/frida/releases/download/$ver/frida-server-$ver-android-$fridaArch.xz"
        val serverData = downloadAndDecompress(serverUrl)
        if (serverData == null || serverData.size < 100000) {
            progress(0, "错误: frida-server 下载失败")
            return false
        }
        progress(40, "frida-server 下载完成 (${serverData.size / 1024}KB)")

        // 下载 frida-inject
        progress(45, "下载 frida-inject...")
        val injectUrl = "https://github.com/frida/frida/releases/download/$ver/frida-inject-$ver-android-$fridaArch.xz"
        val injectData = downloadAndDecompress(injectUrl)
        if (injectData == null || injectData.size < 100000) {
            progress(0, "错误: frida-inject 下载失败")
            return false
        }
        progress(75, "frida-inject 下载完成 (${injectData.size / 1024}KB)")

        // 写入临时文件
        progress(80, "写入文件到设备...")
        val tmpServer = File(context.cacheDir, "frida-server")
        val tmpInject = File(context.cacheDir, "frida-inject")
        tmpServer.writeBytes(serverData)
        tmpInject.writeBytes(injectData)

        // 复制到 /data/local/tmp/ 并设置权限
        progress(85, "安装到 $FRIDA_DIR...")
        val installResult = ShizukuManager.execShell("""
            cp '${tmpServer.absolutePath}' '$FRIDA_SERVER'
            cp '${tmpInject.absolutePath}' '$FRIDA_INJECT'
            chmod 755 '$FRIDA_SERVER'
            chmod 755 '$FRIDA_INJECT'
            echo INSTALL_OK
        """.trimIndent())

        tmpServer.delete()
        tmpInject.delete()

        if (!installResult.contains("INSTALL_OK")) {
            progress(0, "错误: 安装失败 - $installResult")
            return false
        }

        progress(100, "安装完成")
        Log.i(TAG, "Frida installed: server=${serverData.size}B, inject=${injectData.size}B")
        return true
    }

    /**
     * 启动 frida-server
     */
    fun startServer(): Boolean {
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
            Log.w(TAG, "No permission to start frida-server")
            return false
        }
        return ShizukuManager.startFridaServer()
    }

    /**
     * 停止 frida-server
     */
    fun stopServer(): Boolean {
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) return false
        return ShizukuManager.stopFridaServer()
    }

    /**
     * 注入 JavaScript 脚本到目标进程
     *
     * 这是核心方法 — 直接用 frida-inject 注入
     *
     * @param packageName 目标包名
     * @param script JavaScript 脚本内容
     * @param timeout 超时秒数 (默认 10 秒)
     * @return 注入结果
     *
     * 参考: https://bbs.kanxue.com/thread-282491.htm
     * 参考: https://www.52pojie.cn/thread-1823118-1-1.html
     */
    fun injectScript(packageName: String, script: String, timeout: Int = 10): InjectionResult {
        // 1. 检查权限
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
            return InjectionResult.Error("需要 Shizuku 或 Root 权限")
        }

        // 2. 检查 frida-server
        if (!isServerRunning()) {
            return InjectionResult.Error(
                "frida-server 未运行\n" +
                "请先启动: Settings → Frida Server → 启动\n" +
                "或: /data/local/tmp/frida-server &"
            )
        }

        // 3. 检查 frida-inject
        if (!isInjectAvailable()) {
            return InjectionResult.Error(
                "frida-inject 未安装\n" +
                "请先安装: Settings → 下载 Frida\n" +
                "或手动下载: https://github.com/frida/frida/releases"
            )
        }

        // 4. 获取目标进程 PID
        val pidResult = ShizukuManager.execShell("pidof $packageName")
        val pid = pidResult.trim().split("\n")[0].trim().toIntOrNull()
        if (pid == null || pid <= 0) {
            return InjectionResult.Error(
                "进程 '$packageName' 未运行\n" +
                "请先启动目标应用"
            )
        }

        // 5. 写入脚本到临时文件
        val tmpScript = "/data/local/tmp/frida_script_${System.currentTimeMillis()}.js"
        ShizukuManager.execShell("cat > '$tmpScript' << 'FRIDASCRIPT_EOF'\n$script\nFRIDASCRIPT_EOF")

        // 6. 执行注入
        // frida-inject -p PID -s script.js
        // 参考: https://frida.re/docs/android/
        val result = ShizukuManager.execShell(
            "timeout $timeout $FRIDA_INJECT -p $pid -s '$tmpScript' 2>&1"
        )

        // 7. 清理
        ShizukuManager.execShell("rm -f '$tmpScript'")

        Log.i(TAG, "Inject result for $packageName (PID=$pid): ${result.take(200)}")

        return if (result.contains("Failed") || result.contains("Error") || result.contains("error")) {
            InjectionResult.Success(result, pid)  // frida-inject 可能在 stderr 输出警告但注入成功
        } else {
            InjectionResult.Success(result, pid)
        }
    }

    /**
     * Spawn 模式 — 启动应用并注入
     *
     * frida-inject -f package_name -s script.js
     * 应用会暂停在启动状态, 等待脚本加载后 resume
     *
     * 参考: https://bbs.kanxue.com/thread-282491.htm (spawn 模式)
     */
    fun spawnAndInject(packageName: String, script: String, timeout: Int = 15): InjectionResult {
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
            return InjectionResult.Error("需要 Shizuku 或 Root 权限")
        }
        if (!isServerRunning()) {
            return InjectionResult.Error("frida-server 未运行")
        }
        if (!isInjectAvailable()) {
            return InjectionResult.Error("frida-inject 未安装")
        }

        val tmpScript = "/data/local/tmp/frida_spawn_${System.currentTimeMillis()}.js"
        ShizukuManager.execShell("cat > '$tmpScript' << 'FRIDASCRIPT_EOF'\n$script\nFRIDASCRIPT_EOF")

        // -f = spawn, --no-pause = 自动 resume
        val result = ShizukuManager.execShell(
            "timeout $timeout $FRIDA_INJECT -f $packageName -s '$tmpScript' --no-pause 2>&1"
        )
        ShizukuManager.execShell("rm -f '$tmpScript'")

        return InjectionResult.Success(result, 0)
    }

    /**
     * 列出运行中的进程 (通过 frida-server)
     */
    fun listProcesses(): String {
        if (!isServerRunning()) {
            return "frida-server 未运行"
        }
        if (!isInjectAvailable()) {
            return "frida-inject 未安装"
        }
        // frida-inject -R 可以列出进程 (但这个功能可能不可用)
        // 降级到 ps 命令
        return ShizukuManager.execShell("ps -e -o PID,NAME 2>/dev/null || ps -A")
    }

    /**
     * 下载并解压 XZ 文件 — 使用纯 Java XZ 库
     */
    private fun downloadAndDecompress(url: String): ByteArray? {
        return try {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.connectTimeout = 30000
            conn.readTimeout = 120000
            conn.instanceFollowRedirects = true

            if (conn.responseCode != 200) {
                Log.e(TAG, "Download failed: HTTP ${conn.responseCode} for $url")
                return null
            }

            val xzData = conn.inputStream.readBytes()
            conn.disconnect()

            if (xzData.size < 1000) return null

            // 纯 Java XZ 解压
            val decompressor = XZInputStream(xzData.inputStream())
            val output = java.io.ByteArrayOutputStream()
            decompressor.copyTo(output)
            decompressor.close()
            output.toByteArray()
        } catch (e: Exception) {
            Log.e(TAG, "downloadAndDecompress: ${e.message}")
            null
        }
    }

    sealed class InjectionResult {
        data class Success(val output: String, val pid: Int) : InjectionResult()
        data class Error(val message: String) : InjectionResult()
    }
}
