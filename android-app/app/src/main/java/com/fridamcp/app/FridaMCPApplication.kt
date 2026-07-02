package com.fridamcp.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.fridamcp.app.data.repository.AppRepository
import com.fridamcp.app.data.repository.DeviceRepository
import com.fridamcp.app.data.repository.McpRepository

class FridaMCPApplication : Application() {

    lateinit var appRepository: AppRepository
    lateinit var deviceRepository: DeviceRepository
    lateinit var mcpRepository: McpRepository

    override fun onCreate() {
        super.onCreate()
        instance = this

        appRepository = AppRepository(this)
        deviceRepository = DeviceRepository(this)
        mcpRepository = McpRepository(this)

        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)

            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_MCP,
                    getString(R.string.mcp_server_channel),
                    NotificationManager.IMPORTANCE_LOW
                ).apply { description = "MCP 服务器前台服务通知" }
            )

            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_FRIDA,
                    getString(R.string.frida_channel),
                    NotificationManager.IMPORTANCE_LOW
                ).apply { description = "Frida 引擎前台服务通知" }
            )
        }
    }

    companion object {
        const val CHANNEL_MCP = "mcp_server"
        const val CHANNEL_FRIDA = "frida_engine"

        lateinit var instance: FridaMCPApplication
            private set
    }
}
