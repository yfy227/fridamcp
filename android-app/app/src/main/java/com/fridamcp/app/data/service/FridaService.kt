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

/**
 * Frida 引擎前台服务
 *
 * 管理 frida-server 生命周期：
 * 1. 检测 frida-server 是否已运行（遍历 /proc/[pid]/cmdline）
 * 2. 如果有 root，可以启动/停止 frida-server
 * 3. 检测 frida-gadget 进程
 * 4. 提供状态查询
 *
 * 实际功能委托给 ShizukuManager：
 * - startFridaServer(): 查找并启动 frida-server 二进制
 * - stopFridaServer(): pkill frida-server
 * - isFridaServerRunning(): /proc 扫描
 */
class FridaService : Service() {

    companion object {
        const val ACTION_START = "com.fridamcp.app.START_FRIDA"
        const val ACTION_STOP = "com.fridamcp.app.STOP_FRIDA"
        const val ACTION_CHECK = "com.fridamcp.app.CHECK_FRIDA"
        private const val NOTIF_ID = 2002
        private const val TAG = "FridaService"
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startFrida()
            ACTION_STOP -> stopFrida()
            ACTION_CHECK -> checkFrida()
        }
        return START_NOT_STICKY
    }

    private fun startFrida() {
        // 前台通知
        val notification = NotificationCompat.Builder(this, FridaMCPApplication.CHANNEL_MCP)
            .setContentTitle("Frida Engine")
            .setContentText("Starting frida-server...")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }

        // 刷新权限状态
        ShizukuManager.refresh()

        if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
            Log.e(TAG, "No root or shizuku permission — cannot start frida-server")
            stopSelf()
            return
        }

        // 启动 frida-server
        val started = ShizukuManager.startFridaServer()
        if (started) {
            Log.i(TAG, "frida-server started successfully")
            // 更新通知
            val notif = NotificationCompat.Builder(this, FridaMCPApplication.CHANNEL_MCP)
                .setContentTitle("Frida Engine")
                .setContentText("frida-server running")
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setOngoing(true)
                .build()
            startForeground(NOTIF_ID, notif)
        } else {
            Log.e(TAG, "Failed to start frida-server")
            stopSelf()
        }
    }

    private fun stopFrida() {
        ShizukuManager.refresh()
        if (ShizukuManager.currentMode != ShizukuManager.PermissionMode.NONE) {
            val stopped = ShizukuManager.stopFridaServer()
            Log.i(TAG, "frida-server stopped: $stopped (mode: ${ShizukuManager.currentMode})")
        } else {
            Log.w(TAG, "Cannot stop frida-server without Shizuku/Root")
        }
        stopSelf()
    }

    private fun checkFrida() {
        val running = ShizukuManager.isFridaServerRunning()
        val version = ShizukuManager.getFridaVersion()
        Log.i(TAG, "frida-server running: $running, version: $version")
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
