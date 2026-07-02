package com.fridamcp.app.data.service

import android.content.Context
import com.fridamcp.app.data.model.InjectionTask
import com.fridamcp.app.data.model.InjectionTaskStatus
import java.io.File
import java.util.zip.ZipFile

/**
 * APK Injector — on-device frida-gadget injection.
 *
 * Replaces the Python inject_apk.py with native Android implementation.
 * Steps:
 * 1. Detect APK architecture (arm64-v8a, armeabi-v7a, x86_64)
 * 2. Copy frida-gadget.so into APK's lib/ directory
 * 3. Add gadget config JSON
 * 4. (Optional) Use apktool to modify smali for System.loadLibrary("frida-gadget")
 * 5. Re-sign APK with debug key
 */
class ApkInjector(private val context: Context) {

    /** Detect target APK architecture */
    fun detectArch(apkPath: String): String? {
        try {
            ZipFile(apkPath).use { zip ->
                val archs = mutableSetOf<String>()
                zip.entries().asSequence().forEach { entry ->
                    if (entry.name.startsWith("lib/")) {
                        val arch = entry.name.removePrefix("lib/").substringBefore("/")
                        if (arch in SUPPORTED_ARCHS) archs.add(arch)
                    }
                }
                // Prefer arm64-v8a
                return archs.firstOrNull { it == "arm64-v8a" }
                    ?: archs.firstOrNull { it == "armeabi-v7a" }
                    ?: archs.firstOrNull()
            }
        } catch (e: Exception) {
            return null
        }
    }

    /**
     * Inject frida-gadget into APK.
     * Returns the output APK path on success.
     */
    fun inject(
        apkPath: String,
        outputPath: String,
        arch: String,
        useApktool: Boolean = false,
        onProgress: (Int, InjectionTaskStatus) -> Unit,
   ): Result {
        try {
            val inputFile = File(apkPath)
            if (!inputFile.exists()) {
                return Result.Error("APK 文件不存在: $apkPath")
            }

            val outputFile = File(outputPath)
            outputFile.parentFile?.mkdirs()

            // Step 1: Copy APK
            onProgress(10, InjectionTaskStatus.INJECTING)
            inputFile.copyTo(outputFile, overwrite = true)

            // Step 2: Add frida-gadget.so
            onProgress(30, InjectionTaskStatus.INJECTING)
            val gadgetSo = getGadgetSo(arch)
            if (gadgetSo == null) {
                return Result.Error("找不到 $arch 架构的 frida-gadget.so")
            }
            addFileToZip(outputFile, "lib/$arch/libfrida-gadget.so", gadgetSo)

            // Step 3: Add gadget config
            onProgress(50, InjectionTaskStatus.INJECTING)
            val config = GADGET_CONFIG.toByteArray()
            addFileToZip(outputFile, "lib/$arch/libfrida-gadget.config.so", config)

            // Step 4: (Optional) Smali modification
            if (useApktool) {
                onProgress(70, InjectionTaskStatus.INJECTING)
                // TODO: Integrate apktool on-device
                // This requires bundling apktool jar + running via dalvikvm
            }

            // Step 5: Sign APK
            onProgress(85, InjectionTaskStatus.SIGNING)
            signApk(outputFile)

            onProgress(100, InjectionTaskStatus.DONE)
            return Result.Success(outputPath)

        } catch (e: Exception) {
            onProgress(0, InjectionTaskStatus.ERROR)
            return Result.Error(e.message ?: "未知错误")
        }
    }

    /** Get bundled frida-gadget.so for architecture */
    private fun getGadgetSo(arch: String): ByteArray? {
        // TODO: Bundle gadget .so files in assets/
        // For now, return null
        return null
    }

    /** Add a file to a ZIP (APK) */
    private fun addFileToZip(zipFile: File, entryName: String, data: ByteArray) {
        // TODO: Implement ZIP manipulation
        // This requires creating a temp ZIP with the new entry and replacing the original
    }

    /** Sign APK with debug key */
    private fun signApk(apkFile: File) {
        // TODO: Use apksigner library or bundle signer
    }

    companion object {
        private val SUPPORTED_ARCHS = setOf("arm64-v8a", "armeabi-v7a", "x86", "x86_64")

        private const val GADGET_CONFIG = """{
  "interaction": {
    "type": "listen",
    "address": "127.0.0.1",
    "port": 27042,
    "on_port_conflict": "fail",
    "on_load": "wait"
  },
  "teardown": "full"
}"""
    }

    sealed class Result {
        data class Success(val outputPath: String) : Result()
        data class Error(val message: String) : Result()
    }
}
