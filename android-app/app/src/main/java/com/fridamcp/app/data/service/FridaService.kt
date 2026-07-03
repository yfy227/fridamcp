package com.fridamcp.app.data.service

import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.fridamcp.app.FridaMCPApplication
import com.fridamcp.app.R
import java.io.File

/**
 * Frida 引擎前台服务
 *
 * 管理 frida-server 生命周期：
 * 1. 检测 frida-server 是否已运行（遍历 /proc/[pid]/cmdline）
 * 2. 如果有 root，可以启动/停止 frida-server
 * 3. 检测 frida-gadget 进程
 * 4. 提供状态查询
 */
class FridaService : Service() {

    companion object {
        const val ACTION_START = "com.fridamcp.app.START_FRIDA"
        const val ACTION_STOP = "com.fridamcp.app.STOP_FRIDA"
        const val ACTION_CHECK = "com.fridamcp.app.CHECK_FRIDA"
        private const val NOTIF_ID = 2001
        private const val TAG = "FridaService"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "FridaService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startFrida()
            ACTION_STOP -> { stopFrida(); stopSelf() }
            ACTION_CHECK -> checkFrida()
        }
        return START_STICKY
    }

    private fun startFrida() {
        val notification = NotificationCompat.Builder(this, FridaMCPApplication.CHANNEL_FRIDA)
            .setContentTitle(getString(R.string.frida_running))
            .setContentText("Frida 引擎运行中")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }

        if (isFridaServerRunning()) {
            Log.i(TAG, "frida-server already running")
            return
        }

        val mode = ShizukuManager.currentMode
        if (mode == ShizukuManager.PermissionMode.ROOT) {
            val paths = listOf("/data/local/tmp/frida-server", "/system/bin/frida-server", "/system/xbin/frida-server", "/sbin/frida-server")
            var started = false
            for (path in paths) {
                if (File(path).exists()) {
                    Log.i(TAG, "Starting frida-server from: $path")
                    Runtime.getRuntime().exec(arrayOf("su", "-c", "$path -D &"))
                    started = true
                    break
                }
            }
            if (!started) Log.w(TAG, "frida-server binary not found on device")
        } else {
            Log.w(TAG, "Cannot start frida-server without root — mode: $mode")
        }
        Log.i(TAG, "Frida engine service started")
    }

    private fun stopFrida() {
        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.ROOT) {
            try {
                Runtime.getRuntime().exec(arrayOf("su", "-c", "pkill -f frida-server"))
                Log.i(TAG, "frida-server stopped")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to stop frida-server", e)
            }
        }
        Log.i(TAG, "Frida engine stopped")
    }

    private fun checkFrida() {
        Log.i(TAG, "frida-server running: ${isFridaServerRunning()}")
    }

    private fun isFridaServerRunning(): Boolean {
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

    override fun onBind(intent: Intent?): IBinder? = null
}
