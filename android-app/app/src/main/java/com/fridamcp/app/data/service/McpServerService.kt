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
import java.io.IOException
import java.net.InetSocketAddress
import java.net.ServerSocket

/**
 * Foreground service that runs the MCP server on port 8768.
 *
 * Exposes Frida tools via MCP protocol (SSE / Streamable HTTP) so AI clients
 * can connect to the phone directly — no PC required.
 *
 * Architecture:
 * 1. NanoHTTPD-based HTTP server listening on 0.0.0.0:8768
 * 2. SSE endpoint at /mcp for streaming tool results
 * 3. JSON-RPC handler dispatches to FridaService
 *
 * Currently a skeleton — real HTTP server implementation in Phase 2.
 */
class McpServerService : Service() {

    companion object {
        const val ACTION_START = "com.fridamcp.app.START_MCP"
        const val ACTION_STOP = "com.fridamcp.app.STOP_MCP"
        const val MCP_PORT = 8768
        private const val NOTIF_ID = 2002
        private const val TAG = "McpServerService"
    }

    private var serverSocket: ServerSocket? = null
    @Volatile private var running = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startServer()
            ACTION_STOP -> {
                stopServer()
                stopSelf()
            }
        }
        return START_STICKY
    }

    private fun startServer() {
        val notification = NotificationCompat.Builder(this, FridaMCPApplication.CHANNEL_MCP)
            .setContentTitle(getString(R.string.mcp_server_running))
            .setContentText(getString(R.string.mcp_server_running_detail, 0))
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }

        running = true

        // Start HTTP server thread
        Thread {
            try {
                serverSocket = ServerSocket().apply {
                    bind(InetSocketAddress("0.0.0.0", MCP_PORT))
                    soTimeout = 0
                }
                Log.i(TAG, "MCP server listening on port $MCP_PORT")

                while (running) {
                    try {
                        val client = serverSocket?.accept() ?: break
                        // TODO: Handle MCP JSON-RPC request
                        // For now, just close the connection
                        client.close()
                    } catch (e: IOException) {
                        if (running) Log.e(TAG, "Accept error", e)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start MCP server", e)
            }
        }.start()
    }

    private fun stopServer() {
        running = false
        try {
            serverSocket?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Error closing server socket", e)
        }
        serverSocket = null
        Log.i(TAG, "MCP server stopped")
    }

    override fun onDestroy() {
        stopServer()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
