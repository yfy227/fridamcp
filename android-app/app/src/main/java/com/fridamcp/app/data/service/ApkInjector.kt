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
 * 完整流程:
 * 1. 检测 APK 架构 (从 lib/ 条目)
 * 2. 获取 frida-gadget.so (assets 或从 GitHub 下载, 用纯 Java XZ 解压)
 * 3. 复制 APK, 添加 gadget 到 lib/<arch>/ + config JSON
 * 4. v1 JAR 签名 (纯 Java: RSA 密钥 + 手动 DER PKCS#7, 不依赖 keytool/jarsigner/apksigner)
 *
 * 限制: 不修改 smali (apktool 在 Android 上不可用)
 * → gadget 不会自动加载, 用户需要:
 *   a) 在 PC 上用 apktool 添加 System.loadLibrary("frida-gadget"), 或
 *   b) 使用 frida-server spawn 模式 (不需要修改 APK)
 * 注入后的 APK 包含 gadget .so 但需要 smali patch 才能生效
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
            if (!sourceApk.exists()) return Result.Error("APK 不存在: $apkPath")

            // Step 1: 架构检测
            val detectedArch = if (arch == "auto" || arch.isBlank()) {
                detectArch(sourceApk) ?: return Result.Error("无法检测 APK 架构")
            } else {
                if (arch !in SUPPORTED_ARCHS) return Result.Error("不支持的架构: $arch")
                arch
            }
            Log.i(TAG, "Arch: $detectedArch")

            // Step 2: 获取 gadget
            var gadgetData: ByteArray? = getGadgetFromAssets(detectedArch)
            if (gadgetData == null) {
                Log.i(TAG, "Downloading gadget...")
                gadgetData = downloadGadget(detectedArch)
            }
            if (gadgetData == null || gadgetData.size < 1000) {
                return Result.Error("无法获取 frida-gadget.so\n请手动放到 assets/gadgets/$detectedArch/libfrida-gadget.so")
            }

            // Step 3: 注入
            val outputApk = File(sourceApk.parentFile, sourceApk.nameWithoutExtension + "_injected.apk")
            copyAndInject(sourceApk, outputApk, detectedArch, gadgetData)

            // Step 4: 签名
            val signOk = signApkV1(outputApk)
            if (!signOk) {
                return Result.Error(
                    "APK 已注入 gadget 但签名失败 — 无法安装\n" +
                    "请在 PC 上签名: apksigner sign --ks debug.keystore --ks-pass pass:android '$outputApk'\n" +
                    "参考: https://juejin.cn/post/6844903557037047815"
                )
            }

            // 重要: 仅注入 .so 不修改 smali, gadget 不会自动加载
            // 用户需要在 PC 上用 apktool 修改 smali:
            //   1. apktool d app.apk
            //   2. 在 Application.onCreate 中添加: const-string v0, "frida-gadget" / invoke-static {v0}, System.loadLibrary
            //   3. apktool b -o app_patched.apk
            // 参考: https://www.52pojie.cn/thread-1181471-1-1.html

            // 检查是否需要 smali patch
            // 参考: https://www.52pojie.cn/thread-1181471-1-1.html
            // 参考: https://bbs.kanxue.com/thread-259158.htm
            // frida-gadget 需要通过 System.loadLibrary("frida-gadget") 加载
            // Android 不会自动加载 lib/*.so — 必须显式调用
            // 由于 Android 上没有 apktool, 无法修改 smali
            // 用户需要在 PC 上完成 smali patch, 或使用 frida-server spawn 模式

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
                    if (name.startsWith("lib/")) {
                        val arch = name.substringAfter("lib/").substringBefore("/")
                        if (arch in SUPPORTED_ARCHS) archs.add(arch)
                    }
                }
                archs.firstOrNull { it == "arm64-v8a" }
                    ?: archs.firstOrNull { it == "x86_64" }
                    ?: archs.firstOrNull()
            }
        } catch (e: Exception) { null }
    }

    private fun copyAndInject(sourceApk: File, outputApk: File, arch: String, gadgetData: ByteArray) {
        val configData = GADGET_CONFIG.toByteArray()
        ZipFile(sourceApk).use { zip ->
            ZipOutputStream(FileOutputStream(outputApk)).use { zos ->
                val existing = mutableSetOf<String>()
                val entries = zip.entries()
                while (entries.hasMoreElements()) {
                    val entry = entries.nextElement()
                    existing.add(entry.name)
                    // 跳过旧签名
                    if (entry.name.startsWith("META-INF/") &&
                        (entry.name.endsWith(".SF") || entry.name.endsWith(".RSA") ||
                         entry.name.endsWith(".DSA") || entry.name.endsWith(".MF"))) continue
                    zos.putNextEntry(ZipEntry(entry.name))
                    if (!entry.isDirectory) zip.getInputStream(entry).copyTo(zos)
                    zos.closeEntry()
                }
                // frida-gadget.so
                val gadget = "lib/$arch/libfrida-gadget.so"
                if (gadget !in existing) {
                    zos.putNextEntry(ZipEntry(gadget)); zos.write(gadgetData); zos.closeEntry()
                }
                // config
                val config = "lib/$arch/libfrida-gadget.config.so"
                if (config !in existing) {
                    zos.putNextEntry(ZipEntry(config)); zos.write(configData); zos.closeEntry()
                }
            }
        }
    }

    // ============================================================
    // 签名 — 纯 Java v1 JAR 签名
    // 不依赖 keytool/jarsigner/apksigner (JDK 工具, Android 不存在)
    // 不依赖 BouncyCastle (Android 内置版本 API 不完整)
    // ============================================================

    private fun signApkV1(apkFile: File): Boolean {
        return try {
            // 1. 生成 RSA 2048 密钥对
            val keyGen = KeyPairGenerator.getInstance("RSA")
            keyGen.initialize(2048)
            val keyPair = keyGen.generateKeyPair()

            // 2. 生成自签名 X.509 证书 (手动 DER 编码)
            val certDer = generateSelfSignedCertDer(keyPair)

            // 3. 读取所有非 META-INF 条目
            val entries = mutableMapOf<String, ByteArray>()
            ZipFile(apkFile).use { zip ->
                val it = zip.entries()
                while (it.hasMoreElements()) {
                    val entry = it.nextElement()
                    if (!entry.isDirectory && !entry.name.startsWith("META-INF/")) {
                        entries[entry.name] = zip.getInputStream(entry).readBytes()
                    }
                }
            }

            // 4. 生成 MANIFEST.MF
            val manifest = StringBuilder()
            manifest.append("Manifest-Version: 1.0\n")
            manifest.append("Created-By: FridaMCP 1.0\n\n")
            for ((name, data) in entries) {
                val sha256 = MessageDigest.getInstance("SHA-256").digest(data)
                val b64 = android.util.Base64.encodeToString(sha256, android.util.Base64.NO_WRAP)
                manifest.append("Name: $name\n")
                manifest.append("SHA-256-Digest: $b64\n\n")
            }
            val manifestBytes = manifest.toString().toByteArray()

            // 5. 生成 CERT.SF
            val certSf = StringBuilder()
            certSf.append("Signature-Version: 1.0\n")
            certSf.append("Created-By: FridaMCP 1.0\n")
            val manifestHash = MessageDigest.getInstance("SHA-256").digest(manifestBytes)
            certSf.append("SHA-256-Digest-Manifest: ${android.util.Base64.encodeToString(manifestHash, android.util.Base64.NO_WRAP)}\n\n")
            for ((name, _) in entries) {
                val entryLine = "Name: $name\n"
                val entryHash = MessageDigest.getInstance("SHA-256").digest(entryLine.toByteArray())
                certSf.append("Name: $name\n")
                certSf.append("SHA-256-Digest: ${android.util.Base64.encodeToString(entryHash, android.util.Base64.NO_WRAP)}\n\n")
            }
            val certSfBytes = certSf.toString().toByteArray()

            // 6. 签名 CERT.SF
            val sig = Signature.getInstance("SHA256withRSA")
            sig.initSign(keyPair.private)
            sig.update(certSfBytes)
            val sigBytes = sig.sign()

            // 7. 构建 PKCS#7 SignedData (手动 DER)
            val pkcs7 = buildPkcs7SignedData(certDer, keyPair, sigBytes)

            // 8. 写回 APK
            val signedApk = File(apkFile.parentFile, apkFile.name + ".signed")
            ZipOutputStream(FileOutputStream(signedApk)).use { zos ->
                ZipFile(apkFile).use { zip ->
                    val it = zip.entries()
                    while (it.hasMoreElements()) {
                        val entry = it.nextElement()
                        if (!entry.name.startsWith("META-INF/")) {
                            zos.putNextEntry(ZipEntry(entry.name))
                            if (!entry.isDirectory) zip.getInputStream(entry).copyTo(zos)
                            zos.closeEntry()
                        }
                    }
                }
                zos.putNextEntry(ZipEntry("META-INF/MANIFEST.MF")); zos.write(manifestBytes); zos.closeEntry()
                zos.putNextEntry(ZipEntry("META-INF/CERT.SF")); zos.write(certSfBytes); zos.closeEntry()
                zos.putNextEntry(ZipEntry("META-INF/CERT.RSA")); zos.write(pkcs7); zos.closeEntry()
            }
            apkFile.delete()
            signedApk.renameTo(apkFile)
            Log.i(TAG, "APK signed (v1 JAR, pure Java)")
            true
        } catch (e: Exception) {
            Log.e(TAG, "signApkV1 failed: ${e.message}")
            false
        }
    }

    /** 生成自签名 X.509 证书 DER — 手动 DER 编码 */
    private fun generateSelfSignedCertDer(keyPair: java.security.KeyPair): ByteArray {
        val notBefore = java.util.Date()
        val notAfter = java.util.Date(notBefore.time + 365L * 24 * 60 * 60 * 1000)
        val serial = java.math.BigInteger.valueOf(System.currentTimeMillis())

        val cnOid = encodeOid(intArrayOf(2, 5, 4, 3))
        val cnValue = encodeUtf8String("FridaMCP")
        val rdn = encodeSequence(encodeSet(encodeSequence(cnOid + cnValue)))
        val nameDer = encodeSequence(rdn)
        val validityDer = encodeSequence(encodeUtcTime(notBefore) + encodeUtcTime(notAfter))
        val sigAlgOid = encodeSequence(encodeOid(intArrayOf(1, 2, 840, 113549, 1, 1, 11)))
        val spki = keyPair.public.encoded

        val tbs = encodeSequence(
            encodeExplicit(0, encodeInteger(2)) +
            encodeInteger(serial.toByteArray()) +
            sigAlgOid + nameDer + validityDer + nameDer + spki
        )

        val sig = Signature.getInstance("SHA256withRSA")
        sig.initSign(keyPair.private)
        sig.update(tbs)
        val sigBytes = sig.sign()

        return encodeSequence(tbs + sigAlgOid + encodeBitString(sigBytes))
    }

    /** 构建 PKCS#7 SignedData DER */
    private fun buildPkcs7SignedData(certDer: ByteArray, keyPair: java.security.KeyPair, signature: ByteArray): ByteArray {
        val serial = java.math.BigInteger.valueOf(System.currentTimeMillis())
        val cnOid = encodeOid(intArrayOf(2, 5, 4, 3))
        val cnValue = encodeUtf8String("FridaMCP")
        val rdn = encodeSequence(encodeSet(encodeSequence(cnOid + cnValue)))
        val issuerDer = encodeSequence(rdn)
        val issuerSerial = encodeSequence(issuerDer + encodeInteger(serial.toByteArray()))
        val sha256Oid = encodeSequence(encodeOid(intArrayOf(2, 16, 840, 1, 101, 3, 4, 2, 1)))
        val rsaOid = encodeSequence(encodeOid(intArrayOf(1, 2, 840, 113549, 1, 1, 1)))
        val signerInfo = encodeSequence(
            encodeInteger(1) + issuerSerial + sha256Oid + rsaOid + encodeOctetString(signature)
        )
        val dataOid = encodeSequence(encodeOid(intArrayOf(1, 2, 840, 113549, 1, 7, 1)))
        val signedData = encodeSequence(
            encodeInteger(1) + encodeSet(ByteArray(0)) + dataOid +
            encodeExplicit(0, certDer) + encodeSet(signerInfo)
        )
        return encodeSequence(
            encodeOid(intArrayOf(1, 2, 840, 113549, 1, 7, 2)) + encodeExplicit(0, signedData)
        )
    }



    // ============================================================
    // Gadget 下载 — 纯 Java HttpURLConnection + XZ 解压
    // ============================================================

    private fun getGadgetFromAssets(arch: String): ByteArray? {
        return try {
            context.assets.open("gadgets/$arch/libfrida-gadget.so").use { input ->
                val buf = ByteArrayOutputStream()
                input.copyTo(buf)
                buf.toByteArray().takeIf { it.size > 1000 }
            }
        } catch (e: Exception) { null }
    }

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
            Log.i(TAG, "Downloading: $url")

            val conn = URL(url).openConnection() as HttpURLConnection
            conn.connectTimeout = 30000
            conn.readTimeout = 60000
            conn.instanceFollowRedirects = true
            if (conn.responseCode != 200) { Log.e(TAG, "HTTP ${conn.responseCode}"); return null }

            val xzData = conn.inputStream.readBytes()
            conn.disconnect()
            if (xzData.size < 1000) return null

            // 纯 Java XZ 解压 — 不依赖 xz 命令或 python3
            val decompressor = org.tukaani.xz.XZInputStream(xzData.inputStream())
            val output = ByteArrayOutputStream()
            decompressor.copyTo(output)
            decompressor.close()
            val soData = output.toByteArray()
            Log.i(TAG, "Decompressed: ${xzData.size} → ${soData.size} bytes")
            soData.takeIf { it.size > 10000 }
        } catch (e: Exception) {
            Log.e(TAG, "downloadGadget: ${e.message}")
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
        } catch (e: Exception) { null }
    }

    // === DER 编码辅助函数 ===

    private fun encodeTagLen(tag: Int, len: Int): ByteArray = when {
        len < 128 -> byteArrayOf(tag.toByte(), len.toByte())
        len < 256 -> byteArrayOf(tag.toByte(), 0x81.toByte(), len.toByte())
        len < 65536 -> byteArrayOf(tag.toByte(), 0x82.toByte(), (len ushr 8).toByte(), len.toByte())
        else -> byteArrayOf(tag.toByte(), 0x83.toByte(), (len ushr 16).toByte(), (len ushr 8).toByte(), len.toByte())
    }
    private fun encodeSequence(body: ByteArray): ByteArray = encodeTagLen(0x30, body.size) + body
    private fun encodeSet(body: ByteArray): ByteArray = encodeTagLen(0x31, body.size) + body
    private fun encodeInteger(v: Int): ByteArray = encodeInteger(java.math.BigInteger.valueOf(v.toLong()).toByteArray())
    private fun encodeInteger(bytes: ByteArray): ByteArray = encodeTagLen(0x02, bytes.size) + bytes
    private fun encodeOctetString(data: ByteArray): ByteArray = encodeTagLen(0x04, data.size) + data
    private fun encodeBitString(data: ByteArray): ByteArray {
        val body = ByteArray(data.size + 1); body[0] = 0; System.arraycopy(data, 0, body, 1, data.size)
        return encodeTagLen(0x03, body.size) + body
    }
    private fun encodeExplicit(tag: Int, data: ByteArray): ByteArray = encodeTagLen(0xA0 or tag, data.size) + data
    private fun encodeUtf8String(s: String): ByteArray { val b = s.toByteArray(Charsets.UTF_8); return encodeTagLen(0x0C, b.size) + b }
    private fun encodeUtcTime(d: java.util.Date): ByteArray {
        val fmt = java.text.SimpleDateFormat("yyMMddHHmmss'Z'", java.util.Locale.US)
        fmt.timeZone = java.util.TimeZone.getTimeZone("UTC")
        val b = fmt.format(d).toByteArray(); return encodeTagLen(0x17, b.size) + b
    }
    private fun encodeOid(oid: IntArray): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        out.write(40 * oid[0] + oid[1])
        for (i in 2 until oid.size) {
            var v = oid[i]
            if (v < 128) { out.write(v) }
            else {
                val stack = mutableListOf<Int>(); stack.add(v and 0x7F); v = v ushr 7
                while (v > 0) { stack.add((v and 0x7F) or 0x80); v = v ushr 7 }
                stack.reverse(); for (b in stack) out.write(b)
            }
        }
        val b = out.toByteArray(); return encodeTagLen(0x06, b.size) + b
    }

    sealed class Result {
        data class Success(val outputPath: String) : Result()
        data class Error(val message: String) : Result()
    }
}


