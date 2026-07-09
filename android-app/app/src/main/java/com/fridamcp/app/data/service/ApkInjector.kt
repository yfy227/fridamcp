package com.fridamcp.app.data.service

import android.content.Context
import android.util.Log
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.Signature
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream

/**
 * APK Injector — on-device frida-gadget 注入
 *
 * 注入流程:
 * 1. 检测 APK 架构 (从 lib/ 条目)
 * 2. 复制原始 APK
 * 3. 获取 frida-gadget.so (assets 或下载)
 * 4. 添加 gadget 到 lib/<arch>/ + config JSON
 * 5. 签名 APK (v1 JAR 签名, 使用 BouncyCastle 或 shell jarsigner)
 *
 * 注意: Android 不会自动加载 lib/\*.so — 需要 smali patch 添加
 * System.loadLibrary("frida-gadget")。smali patch 需要 apktool (Android 上不可用)。
 * 推荐使用 frida-server spawn 模式替代 APK 注入。
 */
class ApkInjector(private val context: Context) {

    companion object {
        private const val TAG = "ApkInjector"
        private val SUPPORTED_ARCHS = setOf("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
        private const val GADGET_CONFIG = """{"interaction":{"type":"listen","address":"127.0.0.1","port":27042,"on_port_conflict":"fail","on_load":"wait"},"teardown":"full"}"""
        private val GADGET_URL_TEMPLATE = "https://github.com/frida/frida/releases/download/%s/frida-gadget-%s-android-%s.so.xz"
    }

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

            // Step 3: 获取 frida-gadget.so
            var gadgetData: ByteArray? = getGadgetFromAssets(detectedArch)
            if (gadgetData == null) {
                Log.i(TAG, "Gadget not in assets, downloading...")
                gadgetData = downloadGadget(detectedArch)
            }
            if (gadgetData == null || gadgetData.size < 1000) {
                return Result.Error(
                    "无法获取 frida-gadget.so\n" +
                    "请手动下载 frida-gadget-${detectedArch}.so\n" +
                    "放到 app/src/main/assets/gadgets/$detectedArch/libfrida-gadget.so\n" +
                    "下载: https://github.com/frida/frida/releases"
                )
            }
            Log.i(TAG, "Gadget size: ${gadgetData.size} bytes")

            // Step 4: 复制 APK 并注入 gadget
            copyAndInject(sourceApk, outputApk, detectedArch, gadgetData)

            // Step 5: 签名 APK
            val signSuccess = signApk(outputApk)
            if (!signSuccess) {
                Log.w(TAG, "APK signing failed — APK needs manual signing before install")
            }

            return Result.Success(outputApk.absolutePath)
        } catch (e: Exception) {
            Log.e(TAG, "Injection failed", e)
            return Result.Error("注入失败: ${e.message}")
        }
    }

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
                archs.firstOrNull { it == "arm64-v8a" }
                    ?: archs.firstOrNull { it == "x86_64" }
                    ?: archs.firstOrNull()
            }
        } catch (e: Exception) {
            Log.e(TAG, "detectArch failed", e)
            null
        }
    }

    private fun copyAndInject(sourceApk: File, outputApk: File, arch: String, gadgetData: ByteArray) {
        val configData = GADGET_CONFIG.toByteArray()

        ZipFile(sourceApk).use { zip ->
            ZipOutputStream(FileOutputStream(outputApk)).use { zos ->
                val existingEntries = mutableSetOf<String>()
                val entries = zip.entries()
                while (entries.hasMoreElements()) {
                    val entry = entries.nextElement()
                    existingEntries.add(entry.name)

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
                }

                // 添加 gadget config
                val configPath = "lib/$arch/libfrida-gadget.config.so"
                if (configPath !in existingEntries) {
                    zos.putNextEntry(ZipEntry(configPath))
                    zos.write(configData)
                    zos.closeEntry()
                    Log.i(TAG, "Added: $configPath")
                }

                // 其他架构也添加
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
     * 签名 APK — 通过 Shizuku/Root 使用 jarsigner
     * 
     * Android 上没有 keytool/jarsigner/apksigner (这些是 JDK 工具)
     * 但某些 Magisk 模块或 termux 可能安装了它们
     * 
     * 如果没有, APK 需要在 PC 上用 apksigner 签名:
     *   apksigner sign --ks debug.keystore --ks-pass pass:android app.apk
     */
    private fun signApk(apkFile: File): Boolean {
        return signApkViaShell(apkFile)
    }

        private fun signApkViaShell(apkFile: File): Boolean {
        return try {
            val apkPath = apkFile.absolutePath
            val result = ShizukuManager.execShell(
                "KS=/data/local/tmp/fridamcp.keystore\n" +
                "if [ ! -f \$KS ]; then\n" +
                "  keytool -genkey -v -keystore \$KS -alias fridamcp -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android -dname 'CN=FridaMCP' 2>/dev/null\n" +
                "fi\n" +
                "if [ -f \$KS ]; then\n" +
                "  jarsigner -sigalg SHA256withRSA -digestalg SHA-256 -keystore \$KS -storepass android -keypass android '$apkPath' fridamcp 2>&1 | tail -3\n" +
                "  echo SHELL_SIGN_OK\n" +
                "else\n" +
                "  echo SHELL_SIGN_FAIL\n" +
                "fi"
            )
            if (result.contains("SHELL_SIGN_OK")) {
                Log.i(TAG, "APK signed via shell jarsigner")
                true
            } else {
                Log.w(TAG, "Shell signing failed: $result")
                false
            }
        } catch (e: Exception) {
            Log.w(TAG, "Shell signing error: ${e.message}")
            false
        }
    }

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
     * 下载 frida-gadget.so — 使用 HttpURLConnection
     * 解压 XZ: 先用 toybox xz (Android 6+), 再用 python3 lzma
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

            if (compressedData.size < 1000) return null

            // 解压 XZ — 使用 toybox (Android 6+ 内置) 或 python3
            val tmpXz = File(context.cacheDir, "gadget_${arch}.so.xz")
            val tmpSo = File(context.cacheDir, "gadget_${arch}.so")
            tmpXz.writeBytes(compressedData)

            // 方法1: toybox xz
            ShizukuManager.execShell("xz -d -c '${tmpXz.absolutePath}' > '${tmpSo.absolutePath}' 2>&1")

            if (!tmpSo.exists() || tmpSo.length() < 10000) {
                // 方法2: python3 lzma
                ShizukuManager.execShell(
                    "python3 -c \"import lzma; open('${tmpSo.absolutePath}','wb').write(lzma.decompress(open('${tmpXz.absolutePath}','rb').read()))\" 2>&1"
                )
            }

            tmpXz.delete()
            if (tmpSo.exists() && tmpSo.length() > 10000) {
                val data = tmpSo.readBytes()
                tmpSo.delete()
                return data
            }

            Log.e(TAG, "XZ decompress failed — no xz or python3 available")
            null
        } catch (e: Exception) {
            Log.e(TAG, "downloadGadget failed: ${e.message}")
            null
        }
    }

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
