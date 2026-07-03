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
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import org.json.JSONArray
import org.json.JSONObject

/**
 * Real MCP Server — listens on 127.0.0.1:8768
 *
 * Endpoints:
 *  GET  /          — health check, returns server info JSON
 *  GET  /sse       — SSE stream for MCP events
 *  POST /mcp       — JSON-RPC 2.0 handler (initialize, tools/list, tools/call)
 *  GET  /tools     — list all registered tools as JSON
 */
class McpServerService : Service() {

    companion object {
        const val ACTION_START = "com.fridamcp.app.START_MCP"
        const val ACTION_STOP = "com.fridamcp.app.STOP_MCP"
        const val MCP_HOST = "127.0.0.1"
        const val MCP_PORT = 8768
        private const val NOTIF_ID = 2002
        private const val TAG = "McpServerService"
    }

    private var serverSocket: ServerSocket? = null
    @Volatile private var running = false
    @Volatile private var clientCount = 0

    // Registered MCP tools
    private val mcpTools: List<ToolDef> = listOf(
        ToolDef("list_devices", "列出所有可用设备", emptyList()),
        ToolDef("select_device", "选择目标设备", listOf("device_id", "device_type")),
        ToolDef("get_system_status", "获取系统状态", emptyList()),
        ToolDef("list_processes", "列出运行中的进程", emptyList()),
        ToolDef("list_apps", "列出已安装应用", listOf("include_system")),
        ToolDef("launch_app", "启动应用", listOf("package_name")),
        ToolDef("kill_process", "杀死进程", listOf("pid")),
        ToolDef("attach_process", "附加到进程", listOf("package_name")),
        ToolDef("list_sessions", "列出会话", emptyList()),
        ToolDef("close_session", "关闭会话", listOf("session_id")),
        ToolDef("hook_java_method", "Hook Java 方法", listOf("session_id", "class_name", "method_name")),
        ToolDef("hook_native", "Hook Native 函数", listOf("session_id", "module", "function")),
        ToolDef("list_hooks", "列出活跃 Hook", listOf("session_id")),
        ToolDef("remove_hook", "移除 Hook", listOf("session_id", "hook_id")),
        ToolDef("read_memory", "读取内存", listOf("session_id", "address", "size")),
        ToolDef("write_memory", "写入内存", listOf("session_id", "address", "data")),
        ToolDef("search_memory", "搜索内存", listOf("session_id", "pattern")),
        ToolDef("list_modules", "列出内存模块", listOf("session_id")),
        ToolDef("list_exports", "列出导出函数", listOf("session_id", "module")),
        ToolDef("start_capture", "开始网络捕获", listOf("session_id", "capture_ssl")),
        ToolDef("stop_capture", "停止网络捕获", listOf("session_id")),
        ToolDef("get_capture", "获取捕获数据", listOf("session_id")),
        ToolDef("hook_ssl", "Hook SSL/TLS", listOf("session_id")),
        ToolDef("list_files", "列出文件", listOf("path")),
        ToolDef("read_file", "读取设备文件", listOf("path")),
        ToolDef("push_file", "推送文件到设备", listOf("local_path", "remote_path")),
        ToolDef("pull_file", "拉取文件", listOf("remote_path", "local_path")),
        ToolDef("click", "点击坐标", listOf("x", "y")),
        ToolDef("input_text", "输入文本", listOf("text")),
        ToolDef("screenshot", "截图", emptyList()),
        ToolDef("get_current_activity", "获取当前 Activity", emptyList()),
        ToolDef("hook_crypto", "Hook 加密 API", listOf("session_id")),
        ToolDef("dump_ssl_keys", "导出 SSL 密钥", listOf("session_id")),
        ToolDef("start_logcat", "开始 logcat", listOf("package")),
        ToolDef("stop_logcat", "停止 logcat", listOf("session_id")),
        ToolDef("get_logs", "获取日志", listOf("session_id")),
        ToolDef("get_server_logs", "获取服务器日志", emptyList()),
        ToolDef("clear_all_logs", "清空日志", emptyList()),
        ToolDef("execute_script", "执行 Frida 脚本", listOf("session_id", "source")),
        ToolDef("call_script_function", "调用脚本函数", listOf("session_id", "script_id", "function_name")),
        ToolDef("unload_script", "卸载脚本", listOf("session_id", "script_id")),
    )

    data class ToolDef(val name: String, val description: String, val params: List<String>)

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
            .setContentText("监听 $MCP_HOST:$MCP_PORT · ${mcpTools.size} 个工具")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }

        running = true
        Thread { runServer() }.start()
    }

    private fun runServer() {
        try {
            serverSocket = ServerSocket().apply {
                bind(InetSocketAddress(MCP_HOST, MCP_PORT))
                soTimeout = 0
            }
            Log.i(TAG, "✅ MCP server listening on $MCP_HOST:$MCP_PORT (${mcpTools.size} tools)")

            while (running) {
                try {
                    val client = serverSocket?.accept() ?: break
                    clientCount++
                    Thread { handleClient(client) }.start()
                } catch (e: IOException) {
                    if (running) Log.e(TAG, "Accept error", e)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start MCP server on $MCP_HOST:$MCP_PORT", e)
        }
    }

    private fun handleClient(client: Socket) {
        try {
            client.soTimeout = 30000
            val reader = BufferedReader(InputStreamReader(client.getInputStream(), "UTF-8"))
            val output: OutputStream = client.getOutputStream()

            // Read HTTP request line
            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 3) return
            val method = parts[0]
            val path = parts[1]

            // Read headers
            val headers = mutableMapOf<String, String>()
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isEmpty()) break
                val idx = line.indexOf(":")
                if (idx > 0) {
                    headers[line.substring(0, idx).lowercase()] = line.substring(idx + 1).trim()
                }
            }

            // Read body for POST
            var body = ""
            if (method == "POST") {
                val contentLength = headers["content-length"]?.toIntOrNull() ?: 0
                if (contentLength > 0) {
                    val charArray = CharArray(contentLength)
                    reader.read(charArray, 0, contentLength)
                    body = String(charArray)
                }
            }

            Log.d(TAG, "$method $path")

            when {
                path == "/" || path == "/health" -> {
                    val resp = JSONObject()
                        .put("server", "FridaMCP")
                        .put("version", "1.0.0")
                        .put("status", "running")
                        .put("host", MCP_HOST)
                        .put("port", MCP_PORT)
                        .put("tools", mcpTools.size)
                        .put("clients", clientCount)
                    sendJson(output, 200, resp)
                }

                path == "/sse" -> {
                    sendSseStream(output, client)
                    return // keep connection open
                }

                path == "/tools" -> {
                    val tools = JSONArray()
                    for (t in mcpTools) {
                        val tool = JSONObject()
                            .put("name", t.name)
                            .put("description", t.description)
                        val params = JSONObject()
                        for (p in t.params) params.put(p, "string")
                        tool.put("inputSchema", JSONObject().put("properties", params).put("type", "object"))
                        tools.put(tool)
                    }
                    sendJson(output, 200, JSONObject().put("tools", tools))
                }

                path == "/mcp" && method == "POST" -> {
                    val response = handleJsonRpc(body)
                    sendJson(output, 200, response)
                }

                else -> {
                    sendJson(output, 404, JSONObject().put("error", "Not found: $path"))
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Client handler error", e)
        } finally {
            try { client.close() } catch (e: Exception) {}
        }
    }

    private fun handleJsonRpc(body: String): JSONObject {
        return try {
            val req = JSONObject(body)
            val method = req.optString("method", "")
            val id = req.opt("id")
            val params = req.optJSONObject("params")

            when (method) {
                "initialize" -> JSONObject()
                    .put("jsonrpc", "2.0")
                    .put("id", id ?: JSONObject.NULL)
                    .put("result", JSONObject()
                        .put("protocolVersion", "2024-11-05")
                        .put("serverInfo", JSONObject().put("name", "FridaMCP").put("version", "1.0.0"))
                        .put("capabilities", JSONObject().put("tools", JSONObject()))
                    )

                "tools/list" -> {
                    val tools = JSONArray()
                    for (t in mcpTools) {
                        val tool = JSONObject()
                            .put("name", t.name)
                            .put("description", t.description)
                        val props = JSONObject()
                        for (p in t.params) props.put(p, JSONObject().put("type", "string"))
                        tool.put("inputSchema", JSONObject().put("properties", props).put("type", "object"))
                        tools.put(tool)
                    }
                    JSONObject()
                        .put("jsonrpc", "2.0")
                        .put("id", id ?: JSONObject.NULL)
                        .put("result", JSONObject().put("tools", tools))
                }

                "tools/call" -> {
                    val toolName = params?.optString("name", "") ?: ""
                    val args = params?.optJSONObject("arguments") ?: JSONObject()
                    JSONObject()
                        .put("jsonrpc", "2.0")
                        .put("id", id ?: JSONObject.NULL)
                        .put("result", JSONObject()
                            .put("content", JSONArray().put(JSONObject()
                                .put("type", "text")
                                .put("text", "Tool '$toolName' called with args: $args\n\nNote: Frida engine integration is Phase 2. Tool stub acknowledged.")
                            ))
                        )
                }

                else -> JSONObject()
                    .put("jsonrpc", "2.0")
                    .put("id", id ?: JSONObject.NULL)
                    .put("error", JSONObject()
                        .put("code", -32601)
                        .put("message", "Method not found: $method")
                    )
            }
        } catch (e: Exception) {
            JSONObject()
                .put("jsonrpc", "2.0")
                .put("error", JSONObject().put("code", -32700).put("message", "Parse error: ${e.message}"))
        }
    }

    private fun sendSseStream(output: OutputStream, client: Socket) {
        try {
            val headers = "HTTP/1.1 200 OK\r\n" +
                "Content-Type: text/event-stream\r\n" +
                "Cache-Control: no-cache\r\n" +
                "Connection: keep-alive\r\n" +
                "Access-Control-Allow-Origin: *\r\n" +
                "\r\n"
            output.write(headers.toByteArray())
            output.flush()

            // Send initial event
            val initEvent = "event: endpoint\ndata: /mcp\n\n"
            output.write(initEvent.toByteArray())
            output.flush()

            // Keep alive — send ping every 15s
            while (running && !client.isClosed) {
                Thread.sleep(15000)
                val ping = ": ping\n\n"
                output.write(ping.toByteArray())
                output.flush()
            }
        } catch (e: Exception) {
            Log.d(TAG, "SSE stream ended: ${e.message}")
        }
    }

    private fun sendJson(output: OutputStream, status: Int, json: JSONObject) {
        val body = json.toString()
        val response = "HTTP/1.1 $status OK\r\n" +
            "Content-Type: application/json\r\n" +
            "Content-Length: ${body.toByteArray().size}\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "Connection: close\r\n" +
            "\r\n" +
            body
        output.write(response.toByteArray())
        output.flush()
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
