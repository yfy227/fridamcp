package com.fridamcp.app.data.service

import android.content.Context
import android.util.Log
import com.fridamcp.app.data.model.InjectionTaskStatus
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream

/**
 * APK Injector — real on-device frida-gadget injection.
 *
 * 完整流程:
 * 1. 检测 APK 架构从 lib/ 条目
 * 2. 复制原始 APK
 * 3. 添加 frida-gadget.so 到 lib/<arch>/
 * 4. 添加 libfrida-gadget.config.so (gadget config JSON)
 * 5. 使用 v2 签名 (通过 Shizuku/Root 调用 apksigner)
 *
 * smali 修改 (System.loadLibrary) 通过 Shizuku/Root 调用 apktool 实现。
 * 如果 apktool 不可用，使用 zip 注入 + 签名 (gadget 会通过 init array 自动加载)。
 */
class ApkInjector(private val context: Context) {

    private val pm = context.packageManager

    /**
     * 注入 frida-gadget 到 APK
     *
     * @param apkPath 源 APK 路径
     * @param arch 目标架构 (arm64-v8a, armeabi-v7a, x86_64)
     * @return Result.Success(outputPath) or Result.Error(message)
     */
    fun inject(apkPath: String, arch: String = "arm64-v8a"): Result {
        val sourceApk = File(apkPath)
        if (!sourceApk.exists()) {
            return Result.Error("APK not found: $apkPath")
        }

        val outputApk = File(apkPath.removeSuffix(".apk") + "_injected.apk")
        val tempApk = File(context.cacheDir, "inject_temp_${System.currentTimeMillis()}.apk")

        try {
            // Step 1: Copy original APK
            FileInputStream(sourceApk).use { input ->
                FileOutputStream(tempApk).use { output -> input.copyTo(output) }
            }

            // Step 2: Open original APK for reading
            ZipFile(sourceApk).use { sourceZip ->
                FileOutputStream(outputApk).use { fos ->
                    ZipOutputStream(fos).use { zos ->
                        val existingEntries = mutableSetOf<String>()

                        // Step 3: Copy all entries except existing signature
                        val entries = sourceZip.entries()
                        while (entries.hasMoreElements()) {
                            val entry = entries.nextElement()
                            existingEntries.add(entry.name)

                            // Skip existing signature files
                            if (entry.name.startsWith("META-INF/") &&
                                (entry.name.endsWith(".SF") || entry.name.endsWith(".RSA") ||
                                 entry.name.endsWith(".DSA") || entry.name.endsWith(".MF"))) {
                                continue
                            }

                            zos.putNextEntry(ZipEntry(entry.name))
                            if (!entry.isDirectory) {
                                sourceZip.getInputStream(entry).use { it.copyTo(zos) }
                            }
                            zos.closeEntry()
                        }

                        // Step 4: Add frida-gadget.so
                        val gadgetData = getGadgetFromAssets(arch)
                        val gadgetPath = "lib/$arch/libfrida-gadget.so"
                        if (gadgetPath !in existingEntries) {
                            zos.putNextEntry(ZipEntry(gadgetPath))
                            if (gadgetData != null && gadgetData.size > 100) {
                                // Real gadget binary
                                zos.write(gadgetData)
                                Log.i("ApkInjector", "Injected real frida-gadget.so (${gadgetData.size} bytes) for $arch")
                            } else {
                                // Download gadget from GitHub releases
                                val downloaded = downloadGadget(arch)
                                if (downloaded != null) {
                                    zos.write(downloaded)
                                    Log.i("ApkInjector", "Downloaded and injected frida-gadget.so (${downloaded.size} bytes) for $arch")
                                } else {
                                    return Result.Error(
                                        "frida-gadget.so not found!\n" +
                                        "Place it in assets/gadgets/$arch/libfrida-gadget.so\n" +
                                        "Or download from https://github.com/frida/frida/releases"
                                    )
                                }
                            }
                            zos.closeEntry()
                        }

                        // Step 5: Add gadget config (listen mode)
                        val configPath = "lib/$arch/libfrida-gadget.config.so"
                        if (configPath !in existingEntries) {
                            zos.putNextEntry(ZipEntry(configPath))
                            zos.write(GADGET_CONFIG.toByteArray())
                            zos.closeEntry()
                        }
                    }
                }
            }

            // Step 6: Sign the APK (v1+v2) using apksigner via Shizuku/Root
            val signResult = signApk(outputApk.absolutePath)
            if (!signResult) {
                Log.w("ApkInjector", "APK signing failed — APK may not install on non-rooted devices")
            }

            // Step 7: Try smali modification via apktool (optional, for auto-load on app start)
            trySmaliModification(apkPath, outputApk.absolutePath, arch)

            // Clean up temp
            tempApk.delete()

            return Result.Success(outputApk.absolutePath)
        } catch (e: Exception) {
            Log.e("ApkInjector", "Injection failed", e)
            tempApk.delete()
            return Result.Error("注入失败: ${e.message}")
        }
    }

    /**
     * Download frida-gadget.so from GitHub releases
     */
    private fun downloadGadget(arch: String): ByteArray? {
        return try {
            val gadgetArch = when (arch) {
                "arm64-v8a" -> "arm64"
                "armeabi-v7a" -> "arm"
                "x86_64" -> "x86_64"
                "x86" -> "x86"
                else -> return null
            }
            // Try to download via Shizuku/Root (curl/wget)
            val url = "https://github.com/frida/frida/releases/download/17.2.1/frida-gadget-17.2.1-android-$gadgetArch.so.xz"
            val cmd = "curl -sL '$url' | xz -d > /data/local/tmp/frida-gadget-$gadgetArch.so 2>&1 && cat /data/local/tmp/frida-gadget-$gadgetArch.so | base64"
            val result = ShizukuManager.execShell(cmd)
            if (result.isNotBlank() && !result.startsWith("Error")) {
                val data = android.util.Base64.decode(result.trim(), android.util.Base64.DEFAULT)
                if (data.size > 1000) {
                    return data
                }
            }
            null
        } catch (e: Exception) {
            Log.w("ApkInjector", "Failed to download gadget: ${e.message}")
            null
        }
    }

    /**
     * Sign APK using apksigner (via Shizuku/Root)
     * Creates a debug keystore if needed
     */
    private fun signApk(apkPath: String): Boolean {
        return try {
            // Create debug keystore if not exists
            val keystorePath = "/data/local/tmp/debug.keystore"
            ShizukuManager.execShell(
                "keytool -genkey -v -keystore $keystorePath -storepass android -alias androiddebugkey " +
                "-keypass android -keyalg RSA -keysize 2048 -validity 10000 " +
                "-dname 'CN=Android,O=Android,C=US' 2>/dev/null || true"
            )

            // Sign with apksigner (v1+v2)
            val result = ShizukuManager.execShell(
                "apksigner sign --ks $keystorePath --ks-pass pass:android " +
                "--key-pass pass:android --v1-signing-enabled true --v2-signing-enabled true " +
                "'$apkPath' 2>&1"
            )
            val success = !result.contains("ERROR", ignoreCase = true) && !result.contains("failed", ignoreCase = true)
            if (success) {
                Log.i("ApkInjector", "APK signed successfully")
            } else {
                // Fallback: try jarsigner
                val jarResult = ShizukuManager.execShell(
                    "jarsigner -keystore $keystorePath -storepass android -keypass android " +
                    "'$apkPath' androiddebugkey 2>&1"
                )
                Log.i("ApkInjector", "jarsigner result: $jarResult")
                !jarResult.contains("error", ignoreCase = true)
            }
            success
        } catch (e: Exception) {
            Log.e("ApkInjector", "Signing failed: ${e.message}")
            false
        }
    }

    /**
     * Attempt smali modification via apktool — adds System.loadLibrary("frida-gadget")
     * to the Application class's <clinit> or onCreate
     */
    private fun trySmaliModification(originalApk: String, injectedApk: String, arch: String) {
        try {
            val tmpDir = "/data/local/tmp/apktool_work_${System.currentTimeMillis()}"
            // Decompile
            val decompile = ShizukuManager.execShell("apktool d -f -o '$tmpDir' '$injectedApk' 2>&1")
            if (decompile.contains("Exception", ignoreCase = true) || !File("$tmpDir/AndroidManifest.xml").exists()) {
                Log.w("ApkInjector", "apktool decompile failed, skipping smali modification")
                ShizukuManager.execShell("rm -rf '$tmpDir'")
                return
            }

            // Find Application class or default Application
            val smaliDir = File("$tmpDir/smali")
            if (!smaliDir.exists()) {
                // Try smali_classes2 etc
                val altDir = File("$tmpDir").listFiles()?.firstOrNull { it.name.startsWith("smali") }
                if (altDir == null) {
                    Log.w("ApkInjector", "No smali directory found")
                    ShizukuManager.execShell("rm -rf '$tmpDir'")
                    return
                }
            }

            // Find the Application class (from AndroidManifest)
            val manifestContent = ShizukuManager.execShell("cat '$tmpDir/AndroidManifest.xml'")
            val appClassMatch = Regex("""android:name="([^"]+)"""").find(manifestContent)
            val appClass = appClassMatch?.groupValues?.getOrNull(1) ?: "android.app.Application"

            // Modify the Application class to load frida-gadget
            val smaliPath = appClass.replace(".", "/") + ".smali"
            val smaliFile = File("$tmpDir/smali/$smaliPath")
            if (smaliFile.exists()) {
                val content = smaliFile.readText()
                // Add loadLibrary to <clinit> or onCreate
                if (!content.contains("frida-gadget")) {
                    val modified = content.replace(
                        ".method public onCreate()V",
                        ".method public onCreate()V\n" +
                        "    const-string v0, \"frida-gadget\"\n" +
                        "    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n"
                    )
                    smaliFile.writeText(modified)
                    Log.i("ApkInjector", "Smali modified: added loadLibrary(\"frida-gadget\")")

                    // Recompile
                    val recompile = ShizukuManager.execShell("apktool b -o '$injectedApk' '$tmpDir' 2>&1")
                    if (recompile.contains("built", ignoreCase = true)) {
                        Log.i("ApkInjector", "APK recompiled with smali modification")
                        // Re-sign
                        signApk(injectedApk)
                    }
                }
            }

            ShizukuManager.execShell("rm -rf '$tmpDir'")
        } catch (e: Exception) {
            Log.w("ApkInjector", "Smali modification skipped: ${e.message}")
        }
    }

    /**
     * Try to load frida-gadget.so from app assets.
     * Expected path: assets/gadgets/<arch>/libfrida-gadget.so
     */
    private fun getGadgetFromAssets(arch: String): ByteArray? {
        return try {
            val assetPath = "gadgets/$arch/libfrida-gadget.so"
            context.assets.open(assetPath).use { input ->
                val buffer = ByteArrayOutputStream()
                input.copyTo(buffer)
                buffer.toByteArray()
            }
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        private val SUPPORTED_ARCHS = setOf("arm64-v8a", "armeabi-v7a", "x86", "x86_64")

        private const val GADGET_CONFIG = """{"interaction":{"type":"listen","address":"127.0.0.1","port":27042,"on_port_conflict":"fail","on_load":"wait"},"teardown":"full"}"""
    }

    sealed class Result {
        data class Success(val outputPath: String) : Result()
        data class Error(val message: String) : Result()
    }
}
