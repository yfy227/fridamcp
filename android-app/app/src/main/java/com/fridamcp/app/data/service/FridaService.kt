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
 * Foreground service that manages the Frida engine lifecycle on-device.
 *
 * In production, this loads libfrida-core.so via JNA and provides:
 * - Local device enumeration
 * - Process attachment / spawning
 * - Script injection and message routing
 * - Session lifecycle management
 *
 * Currently a skeleton — real Frida bindings will be added in Phase 2.
 */
class FridaService : Service() {

    companion object {
        const val ACTION_START = "com.fridamcp.app.START_FRIDA"
        const val ACTION_STOP = "com.fridamcp.app.STOP_FRIDA"
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
            ACTION_STOP -> {
                stopFrida()
                stopSelf()
            }
        }
        return START_STICKY
    }

    private fun startFrida() {
        val notification = NotificationCompat.Builder(this, FridaMCPApplication.CHANNEL_FRIDA)
            .setContentTitle(getString(R.string.frida_running))
            .setContentText("Frida 引擎已加载")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }

        // TODO: Load frida-core via JNA
        // System.loadLibrary("frida-core")
        // frida = FridaLocalDevice()
        Log.i(TAG, "Frida engine started (skeleton)")
    }

    private fun stopFrida() {
        Log.i(TAG, "Frida engine stopped")
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
