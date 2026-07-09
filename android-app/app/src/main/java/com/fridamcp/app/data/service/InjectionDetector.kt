package com.fridamcp.app.data.service

import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import com.fridamcp.app.data.model.AppInfo
import com.fridamcp.app.data.model.DetectionMethod
import com.fridamcp.app.data.model.InjectionStatus
import java.io.File
import java.util.zip.ZipFile

/**
 * Three-layer injection detector — matches the design doc.
 *
 * Layer 1: Static — check APK for libfrida-gadget.so
 * Layer 2: Runtime — check /proc/[pid]/maps for frida-gadget
 * Layer 3: Process — check running processes for "gadget" / "frida"
 */
class InjectionDetector(private val context: Context) {

    private val pm = context.packageManager

    /** Layer 1: Static detection — scan APK for frida-gadget */
    fun detectStatic(packageName: String): DetectionResult {
        try {
            val appInfo = pm.getApplicationInfo(packageName, 0)
            val apkPath = appInfo.sourceDir
            ZipFile(apkPath).use { zip ->
                val gadgetEntry = zip.entries().asSequence()
                    .firstOrNull { it.name.contains("frida-gadget") || it.name.contains("libgadget") }
                if (gadgetEntry != null) {
                    val arch = gadgetEntry.name.substringAfter("lib/")
                        .substringBefore("/")
                    return DetectionResult(
                        detected = true,
                        method = DetectionMethod.STATIC,
                        details = "在 APK 中发现 ${gadgetEntry.name} ($arch)",
                        gadgetArch = arch,
                        gadgetVersion = extractGadgetVersion(zip, gadgetEntry.name),
                    )
                }
            }
        } catch (e: Exception) {
            return DetectionResult(
                detected = false,
                method = DetectionMethod.NONE,
                details = "静态检测失败: ${e.message}",
            )
        }
        return DetectionResult(
            detected = false,
            method = DetectionMethod.NONE,
            details = "未在 APK 中找到 frida-gadget",
        )
    }

    /** Layer 2: Runtime detection — check /proc/[pid]/maps */
    fun detectRuntime(pid: Int): DetectionResult {
        try {
            val mapsFile = File("/proc/$pid/maps")
            if (!mapsFile.exists()) {
                return DetectionResult(
                    detected = false,
                    method = DetectionMethod.NONE,
                    details = "进程 $pid 不存在",
                )
            }
            val maps = mapsFile.readText()
            if (maps.contains("frida-gadget") || maps.contains("libgadget")) {
                return DetectionResult(
                    detected = true,
                    method = DetectionMethod.RUNTIME,
                    details = "在进程 $pid 的内存映射中发现 frida-gadget",
                )
            }
        } catch (e: Exception) {
            return DetectionResult(
                detected = false,
                method = DetectionMethod.NONE,
                details = "运行时检测失败: ${e.message}",
            )
        }
        return DetectionResult(
            detected = false,
            method = DetectionMethod.NONE,
            details = "进程 $pid 未加载 frida-gadget",
        )
    }

    /** Layer 3: Process detection — scan all processes */
    fun detectProcess(packageName: String): DetectionResult {
        try {
            // Android 10+ 限制 /proc 访问, 先尝试 Shizuku/Root
            val pidResult = com.fridamcp.app.data.service.ShizukuManager.execShell("pidof $packageName 2>/dev/null")
            val pid = pidResult.trim().split("\n")[0].trim().toIntOrNull()

            if (pid != null && pid > 0) {
                // 找到进程 — 检查 /proc/PID/maps
                val result = detectRuntime(pid)
                if (result.detected) return result

                // maps 不可读时, 通过 Shizuku 读
                val mapsResult = com.fridamcp.app.data.service.ShizukuManager.execShell(
                    "cat /proc/$pid/maps 2>/dev/null | grep -i -e frida -e gadget"
                )
                if (mapsResult.isNotBlank() && !mapsResult.contains("Error")) {
                    return DetectionResult(
                        detected = true,
                        method = DetectionMethod.RUNTIME,
                        details = "在进程 $pid 的内存映射中发现 frida-gadget (via Shizuku/Root)",
                    )
                }
            }

            // 降级: 直接读 /proc (Android 9 或以下)
            val procRoot = File("/proc")
            val processDirs = procRoot.listFiles { f: File -> f.name.matches(Regex("\\d+")) } ?: emptyArray()

            for (procDir in processDirs) {
                try {
                    val cmdline = File(procDir, "cmdline").readText().trimEnd('\u0000')
                    if (cmdline == packageName) {
                        val foundPid = procDir.name.toInt()
                        val result = detectRuntime(foundPid)
                        if (result.detected) return result
                    }
                } catch (e: Exception) { continue }
            }
        } catch (e: Exception) {
            return DetectionResult(
                detected = false,
                method = DetectionMethod.NONE,
                details = "进程检测失败: ${e.message}",
            )
        }
        return DetectionResult(
            detected = false,
            method = DetectionMethod.NONE,
            details = "未找到运行中的 $packageName 进程",
        )
    }

    /** Full three-layer scan */
    fun fullScan(app: AppInfo): DetectionResult {
        // Layer 1: Static
        val static = detectStatic(app.packageName)
        if (static.detected) {
            // Layer 2/3: Check if running
            val runtime = detectProcess(app.packageName)
            if (runtime.detected) return runtime
            return static
        }
        return static
    }

    private fun extractGadgetVersion(zip: ZipFile, entryName: String): String? {
        // Parse version from filename: libfrida-gadget-16.5.1-android-arm64.so
        val match = Regex("""frida-gadget-(\d+\.\d+\.\d+)""").find(entryName)
        return match?.groupValues?.getOrNull(1)
    }

    data class DetectionResult(
        val detected: Boolean,
        val method: DetectionMethod,
        val details: String,
        val gadgetArch: String? = null,
        val gadgetVersion: String? = null,
    )
}
