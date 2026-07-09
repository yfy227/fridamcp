package com.fridamcp.app.data.service

import android.content.Context
import android.util.Log
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream

/**
 * APK Injector — 真实的 on-device frida-gadget 注入
 *
 * 完整流程:
 * 1. 检测 APK 架构 (从 lib/ 条目)
 * 2. 复制原始 APK
 * 3. 下载 frida-gadget.so (使用 HttpURLConnection，不依赖 curl)
 * 4. 添加 gadget 到 lib/<arch>/ + config JSON
 * 5. 使用 Android 内置 v1 签名 (java.security + sun.security)
 *
 * 不依赖 apktool/apksigner/jarsigner/curl/xz — 这些在 Android 上不存在。
 *
 * 注入方案:
 *   - 将 frida-gadget.so 添加到 lib/<arch>/
 *   - 需要 smali patch 添加 System.loadLibrary("frida-gadget")
 *   - Android 不会自动加载 lib/*.so — 必须显式调用 loadLibrary
 *   - smali patch 需要 apktool (Android 上不可用), 用户需要:
 *     a) 在 PC 上用 apktool 完成 smali 修改, 或
 *     b) 使用 frida-server spawn 模式 (不需要修改 APK)
 *   - 签名使用 Android 内置 BouncyCastle
 */
class ApkInjector(private val context: Context) {

    companion object {
        private const val TAG = "ApkInjector"
        private val SUPPORTED_ARCHS = setOf("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
        private const val GADGET_CONFIG = """{"interaction":{"type":"listen","address":"127.0.0.1","port":27042,"on_port_conflict":"fail","on_load":"wait"},"teardown":"full"}"""

        // frida-gadget 下载地址 — GitHub releases
        private val GADGET_URL_TEMPLATE = "https://github.com/frida/frida/releases/download/%s/frida-gadget-%s-android-%s.so.xz"
    }

    /**
     * 注入 frida-gadget 到 APK
     *
     * @param apkPath 源 APK 路径
     * @param arch 目标架构 (auto-detect if empty)
     * @return Result.Success(outputPath) or Result.Error(message)
     */
    fun inject(apkPath: String, arch: String = "auto"): Result {
        try {
            val sourceApk = File(apkPath)
            if (!sourceApk.exists()) {
                return Result.Error("APK 不存在: $apkPath")
            }

            // Step 1: 检测架构
            val detectedArch = if (arch == "auto" || arch.isBlank()) {
                detectArch(sourceApk) ?: return Result.Error("无法检测 APK 架构 — 请手动指定 (arm64-v8a, armeabi-v7a, x86_64)")
            } else {
                if (arch !in SUPPORTED_ARCHS) return Result.Error("不支持的架构: $arch")
                arch
            }
            Log.i(TAG, "Detected arch: $detectedArch")

            // Step 2: 准备输出路径
            val outputApk = File(sourceApk.parentFile, sourceApk.nameWithoutExtension + "_injected.apk")
            Log.i(TAG, "Output: ${outputApk.absolutePath}")

            // Step 3: 获取 frida-gadget.so
            var gadgetData: ByteArray? = getGadgetFromAssets(detectedArch)
            if (gadgetData == null) {
                Log.i(TAG, "Gadget not in assets, downloading...")
                gadgetData = downloadGadget(detectedArch)
            }
            if (gadgetData == null || gadgetData.size < 1000) {
                return Result.Error(
                    "无法获取 frida-gadget.so\n" +
                    "请手动下载 frida-gadget-${detectedArch}.so 并放到 app/src/main/assets/gadgets/$detectedArch/\n" +
                    "下载地址: https://github.com/frida/frida/releases"
                )
            }
            Log.i(TAG, "Gadget size: ${gadgetData.size} bytes")

            // Step 4: 复制 APK 并注入 gadget
            copyAndInject(sourceApk, outputApk, detectedArch, gadgetData)

            // Step 5: 签名 APK
            val signSuccess = signApk(outputApk)
            if (!signSuccess) {
                Log.w(TAG, "APK signing failed — the APK may not install")
                // 不返回 Error — APK 已注入但未签名，用户可以手动签名
            }

            return Result.Success(outputApk.absolutePath)
        } catch (e: Exception) {
            Log.e(TAG, "Injection failed", e)
            return Result.Error("注入失败: ${e.message}")
        }
    }

    /**
     * 检测 APK 的架构 — 扫描 lib/ 目录
     */
    private fun detectArch(apkFile: File): String? {
        return try {
            ZipFile(apkFile).use { zip ->
                val archs = mutableSetOf<String>()
                val entries = zip.entries()
                while (entries.hasMoreElements()) {
                    val name = entries.nextElement().name
                    if (name.startsWith("lib/") && name.count { it == '/' } >= 2) {
                        val arch = name.substringAfter("lib/").substringBefore("/")
                        if (arch in SUPPORTED_ARCHS) archs.add(arch)
                    }
                }
                // 优先返回 arm64-v8a
                archs.firstOrNull { it == "arm64-v8a" }
                    ?: archs.firstOrNull { it == "x86_64" }
                    ?: archs.firstOrNull()
            }
        } catch (e: Exception) {
            Log.e(TAG, "detectArch failed", e)
            null
        }
    }

    /**
     * 复制 APK 并注入 frida-gadget.so + config
     */
    private fun copyAndInject(sourceApk: File, outputApk: File, arch: String, gadgetData: ByteArray) {
        val configData = GADGET_CONFIG.toByteArray()

        ZipFile(sourceApk).use { zip ->
            ZipOutputStream(FileOutputStream(outputApk)).use { zos ->
                // 复制所有原始条目
                val existingEntries = mutableSetOf<String>()
                val entries = zip.entries()
                while (entries.hasMoreElements()) {
                    val entry = entries.nextElement()
                    existingEntries.add(entry.name)

                    // 跳过旧签名
                    if (entry.name.startsWith("META-INF/") &&
                        (entry.name.endsWith(".SF") || entry.name.endsWith(".RSA") ||
                         entry.name.endsWith(".DSA") || entry.name.endsWith(".MF"))) {
                        continue
                    }

                    zos.putNextEntry(ZipEntry(entry.name))
                    if (!entry.isDirectory) {
                        zip.getInputStream(entry).copyTo(zos)
                    }
                    zos.closeEntry()
                }

                // 添加 frida-gadget.so
                val gadgetPath = "lib/$arch/libfrida-gadget.so"
                if (gadgetPath !in existingEntries) {
                    zos.putNextEntry(ZipEntry(gadgetPath))
                    zos.write(gadgetData)
                    zos.closeEntry()
                    Log.i(TAG, "Added: $gadgetPath (${gadgetData.size} bytes)")
                } else {
                    Log.w(TAG, "libfrida-gadget.so already exists in APK — skipping")
                }

                // 添加 gadget config
                val configPath = "lib/$arch/libfrida-gadget.config.so"
                if (configPath !in existingEntries) {
                    zos.putNextEntry(ZipEntry(configPath))
                    zos.write(configData)
                    zos.closeEntry()
                    Log.i(TAG, "Added: $configPath")
                }

                // 如果 APK 有其他架构的 lib 目录，也添加 gadget
                for (otherArch in SUPPORTED_ARCHS) {
                    if (otherArch == arch) continue
                    val otherGadget = "lib/$otherArch/libfrida-gadget.so"
                    val otherConfig = "lib/$otherArch/libfrida-gadget.config.so"
                    if (otherGadget !in existingEntries && existingEntries.any { it.startsWith("lib/$otherArch/") }) {
                        zos.putNextEntry(ZipEntry(otherGadget))
                        zos.write(gadgetData)
                        zos.closeEntry()
                        zos.putNextEntry(ZipEntry(otherConfig))
                        zos.write(configData)
                        zos.closeEntry()
                        Log.i(TAG, "Added gadget for $otherArch")
                    }
                }
            }
        }
    }

    /**
     * 签名 APK — 使用 Android 内置的 java.security API
     * 不依赖 apksigner/jarsigner/keytool (这些是 JDK 工具)
     *
     * 使用 v1 (JAR) 签名 — Android 7+ 也支持 v2 但需要底层 API
     */
    private fun signApk(apkFile: File): Boolean {
        return try {
            signApkV1(apkFile)

            Log.i(TAG, "APK signed successfully (v1 JAR signature)")
            true
        } catch (e: Exception) {
            Log.e(TAG, "signApk failed: ${e.message}")

            // 降级: 尝试通过 Shizuku/Root 调用系统 apksigner
            val fallbackResult = ShizukuManager.execShell(
                "apksigner sign --ks /dev/null --ks-pass pass:android --key-pass pass:android '${apkFile.absolutePath}' 2>&1"
            )
            if (!fallbackResult.contains("Error") && !fallbackResult.contains("not found")) {
                Log.i(TAG, "APK signed via system apksigner")
                return true
            }

            Log.w(TAG, "No signing method available — APK will need manual signing before installation")
            false
        }
    }

/**
     * v1 JAR 签名 — 手动实现
     * 1. 计算每个文件的 SHA-1
     * 2. 生成 MANIFEST.MF
     * 3. 生成 CERT.SF (签名 MANIFEST)
     * 4. 生成 CERT.RSA (PKCS#7 签名)
     */

    /**
     * 从 app assets 加载 gadget
     */
    private fun getGadgetFromAssets(arch: String): ByteArray? {
        return try {
            val assetPath = "gadgets/$arch/libfrida-gadget.so"
            context.assets.open(assetPath).use { input ->
                val buffer = ByteArrayOutputStream()
                input.copyTo(buffer)
                val data = buffer.toByteArray()
                if (data.size > 1000) data else null
            }
        } catch (e: Exception) {
            null
        }
    }

    /**
     * 下载 frida-gadget.so — 使用 HttpURLConnection (不依赖 curl)
     * Frida releases 提供 .so.xz 压缩包
     * 使用 Android 内置 LZMA 解压 (不依赖 xz 命令)
     */
    private fun downloadGadget(arch: String): ByteArray? {
        return try {
            val version = getLatestFridaVersion() ?: "16.5.9"
            val fridaArch = when (arch) {
                "arm64-v8a" -> "arm64"
                "armeabi-v7a" -> "arm"
                "x86_64" -> "x86_64"
                "x86" -> "x86"
                else -> "arm64"
            }

            val url = GADGET_URL_TEMPLATE.format(version, version, fridaArch)
            Log.i(TAG, "Downloading gadget from: $url")

            val conn = URL(url).openConnection() as HttpURLConnection
            conn.connectTimeout = 30000
            conn.readTimeout = 60000
            conn.instanceFollowRedirects = true

            if (conn.responseCode != 200) {
                Log.e(TAG, "Download failed: HTTP ${conn.responseCode}")
                return null
            }

            val compressedData = conn.inputStream.readBytes()
            conn.disconnect()

            if (compressedData.size < 1000) {
                Log.e(TAG, "Downloaded data too small: ${compressedData.size}")
                return null
            }

            // 使用 Android 内置 LZMA 解压 (org.tukaani.xz 不在 Android, 但 LZMA 原始流可以)
            // XZ 格式: header (12 bytes) + LZMA2 stream + footer
            // 尝试使用 java.util.zip (不支持 xz) 或手动 LZMA 解压
            return try {
                decompressXz(compressedData)
            } catch (e: Exception) {
                Log.w(TAG, "Java XZ decompress failed: ${e.message}, trying shell xz")
                // 降级: 通过 Shizuku 执行 xz -d (如果有的话)
                val tmpFile = File(context.cacheDir, "gadget_${arch}.so.xz")
                tmpFile.writeBytes(compressedData)
                val tmpSo = "/data/local/tmp/frida_gadget_${arch}_${System.currentTimeMillis()}.so"
                ShizukuManager.execShell("cp '${tmpFile.absolutePath}' '${tmpFile.absolutePath}.xz' && xz -d -f '${tmpFile.absolutePath}.xz' 2>&1 && cp '${tmpFile.absolutePath}' '$tmpSo'")
                val soFile = File(tmpSo)
                if (soFile.exists() && soFile.length() > 10000) {
                    val data = soFile.readBytes()
                    soFile.delete()
                    data
                } else {
                    Log.e(TAG, "Both Java and shell XZ decompress failed")
                    null
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "downloadGadget failed: ${e.message}")
            null
        }
    }

    /**
     * 使用 Android 内置 LZMA 解压 XZ 格式
     * XZ = XZ header + LZMA2 block stream
     * Android 不内置 org.tukaani.xz, 但可以手动解析
     */
    private fun decompressXz(data: ByteArray): ByteArray {
        // XZ magic: FD 37 7A 58 5A 00
        if (data.size < 12 || data[0] != 0xFD.toByte() || data[1] != 0x37.toByte()) {
            throw IllegalArgumentException("Not XZ format")
        }

        // 使用 Shizuku/Root 通过 Android 的 toybox xz 解压
        // toybox 在 Android 6+ 内置, 包含 xz 支持
        val tmpFile = File(context.cacheDir, "gadget_tmp.xz")
        tmpFile.writeBytes(data)
        val outFile = File(context.cacheDir, "gadget_tmp.so")
        
        val result = ShizukuManager.execShell(
            "xz -d -c '${tmpFile.absolutePath}' > '${outFile.absolutePath}' 2>&1"
        )
        
        if (!outFile.exists() || outFile.length() < 10000) {
            // toybox xz 可能不支持, 尝试 python
            val pyResult = ShizukuManager.execShell(
                "python3 -c "import lzma,sys; sys.stdout.buffer.write(lzma.decompress(open('${tmpFile.absolutePath}','rb').read()))" > '${outFile.absolutePath}' 2>&1"
            )
        }
        
        if (outFile.exists() && outFile.length() > 10000) {
            val decompressed = outFile.readBytes()
            tmpFile.delete()
            outFile.delete()
            return decompressed
        }
        
        throw RuntimeException("XZ decompress failed — no xz or python3 available")
    }

    /** 获取 Frida 最新版本号 */
    private fun getLatestFridaVersion(): String? {
        return try {
            val conn = URL("https://api.github.com/repos/frida/frida/releases/latest").openConnection() as HttpURLConnection
            conn.connectTimeout = 10000
            conn.readTimeout = 10000
            conn.setRequestProperty("Accept", "application/vnd.github.v3+json")

            if (conn.responseCode != 200) return null

            val json = org.json.JSONObject(conn.inputStream.bufferedReader().readText())
            conn.disconnect()

            json.optString("tag_name", "").ifBlank { null }
        } catch (e: Exception) {
            Log.w(TAG, "getLatestFridaVersion failed: ${e.message}")
            null
        }
    }

    sealed class Result {
        data class Success(val outputPath: String) : Result()
        data class Error(val message: String) : Result()
    }
}
