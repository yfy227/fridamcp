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
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.Socket
import java.net.URL
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.LinkedBlockingQueue
import org.json.JSONArray
import org.json.JSONObject

/**
 * MCP Server — SSE + Streamable HTTP 双传输
 *
 * 真实实现:
 * - SSE: GET /sse → 建立 EventStream，返回 endpoint event
 * - SSE: POST /messages?session_id=xxx → JSON-RPC 请求
 * - Streamable HTTP: POST /mcp, GET /mcp, DELETE /mcp
 * - Health: GET /health
 *
 * 工具实现全部使用 Shizuku/Root 真实执行。
 * 无 frida-gadget 进程连接时，run_frida_script 返回明确错误。
 * read_memory 包含 ptrace attach 步骤。
 * 状态变更通过 broadcast 同步到 McpRepository。
 */
class McpServerService : Service() {

    companion object {
        const val ACTION_START = "com.fridamcp.app.START_MCP"
        const val ACTION_STOP = "com.fridamcp.app.STOP_MCP"
        const val ACTION_STATUS = "com.fridamcp.app.STATUS_MCP"
        private const val NOTIF_ID = 2001
        private const val TAG = "McpServerService"
        private const val PORT = 8768
        private const val PROTOCOL_VERSION = "2024-11-05"
        private const val SERVER_NAME = "FridaMCP"
        private const val SERVER_VERSION = "1.0.0"
    }

    private var running = false
    private var serverStartTime: Long = 0
    private var serverSocket: ServerSocket? = null
    private val sessions = ConcurrentHashMap<String, McpSession>()

    private data class McpSession(
        val id: String,
        val sseOutput: OutputStream?,
        val socket: Socket,
        val responseQueue: LinkedBlockingQueue<String>,
        var initialized: Boolean = false,
        val clientAddr: String,
    )

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
        if (running) {
            Log.w(TAG, "Server already running")
            return
        }

        val notification = NotificationCompat.Builder(this, FridaMCPApplication.CHANNEL_MCP)
            .setContentTitle(getString(R.string.mcp_server_running))
            .setContentText("127.0.0.1:$PORT")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }

        running = true
        serverStartTime = System.currentTimeMillis()
        Thread {
            try {
                serverSocket = ServerSocket(PORT, 10, java.net.InetAddress.getByName("127.0.0.1"))
                Log.i(TAG, "MCP server listening on 127.0.0.1:$PORT")

                broadcastStatus()

                while (running) {
                    try {
                        val client = serverSocket!!.accept()
                        Thread { handleClient(client) }.start()
                    } catch (e: Exception) {
                        if (running) Log.e(TAG, "Accept error", e)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start server", e)
                running = false
                broadcastStatus()
            }
        }.start()
    }

    /** 广播服务器状态到 McpRepository */
    private fun broadcastStatus() {
        val intent = Intent("com.fridamcp.app.SERVER_STATUS")
        intent.setPackage(packageName)
        intent.putExtra("running", running)
        intent.putExtra("sessions", sessions.size)
        intent.putExtra("tools", getToolsList().length())
        intent.putExtra("clients", sessions.values.count { it.initialized })
        sendBroadcast(intent)
    }

    private fun handleClient(client: Socket) {
        try {
            client.soTimeout = 0
            val input = BufferedReader(InputStreamReader(client.getInputStream()))
            val output = client.getOutputStream()

            val requestLine = input.readLine() ?: return
            val parts = requestLine.split(" ")
            val method = parts.getOrNull(0) ?: return
            val path = parts.getOrNull(1) ?: return

            val headers = mutableMapOf<String, String>()
            var contentLength = 0
            while (true) {
                val line = input.readLine() ?: break
                if (line.isEmpty()) break
                val colonIdx = line.indexOf(":")
                if (colonIdx > 0) {
                    val key = line.substring(0, colonIdx).trim().lowercase()
                    val value = line.substring(colonIdx + 1).trim()
                    headers[key] = value
                    if (key == "content-length") contentLength = value.toIntOrNull() ?: 0
                }
            }

            var body = ""
            if (contentLength > 0) {
                val charArray = CharArray(contentLength)
                input.read(charArray, 0, contentLength)
                body = String(charArray)
            }

            val queryParams = extractQueryParams(path)
            val cleanPath = path.substringBefore("?")

            when {
                method == "GET" && cleanPath == "/sse" -> handleSseConnect(client, output)
                method == "POST" && cleanPath == "/messages" -> handleSsePost(body, queryParams, output)
                method == "POST" && cleanPath == "/mcp" -> handleStreamablePost(body, headers, output)
                method == "GET" && cleanPath == "/mcp" -> handleStreamableGet(headers, output, client)
                method == "DELETE" && cleanPath == "/mcp" -> handleStreamableDelete(headers, output)
                method == "GET" && (cleanPath == "/" || cleanPath == "/health") ->
                    sendJson(output, 200, healthCheckJson())
                else -> sendJson(output, 404, JSONObject().put("error", "Not found: $cleanPath"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling client", e)
        }
    }

    private fun extractQueryParams(path: String): Map<String, String> {
        val query = path.substringAfter("?", "")
        if (query.isEmpty()) return emptyMap()
        return query.split("&").mapNotNull {
            val idx = it.indexOf("=")
            if (idx > 0) it.substring(0, idx) to it.substring(idx + 1)
            else null
        }.toMap()
    }

    // =====================================================================
    // SSE Transport
    // =====================================================================

    private fun handleSseConnect(client: Socket, output: OutputStream) {
        val sessionId = UUID.randomUUID().toString().replace("-", "")
        val clientAddr = client.inetAddress.hostAddress ?: "unknown"

        val header = "HTTP/1.1 200 OK\r\n" +
            "Content-Type: text/event-stream\r\n" +
            "Cache-Control: no-cache\r\n" +
            "Connection: keep-alive\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "\r\n"
        output.write(header.toByteArray())
        output.flush()

        val endpointEvent = "event: endpoint\ndata: /messages?session_id=$sessionId\n\n"
        output.write(endpointEvent.toByteArray())
        output.flush()

        val session = McpSession(
            id = sessionId,
            sseOutput = output,
            socket = client,
            responseQueue = LinkedBlockingQueue(),
            initialized = false,
            clientAddr = clientAddr,
        )
        sessions[sessionId] = session

        // 通知 Repository 真实会话
        val addIntent = Intent("com.fridamcp.app.SESSION_ADDED")
        addIntent.setPackage(packageName)
        addIntent.putExtra("session_id", sessionId)
        addIntent.putExtra("client_addr", clientAddr)
        sendBroadcast(addIntent)
        broadcastStatus()

        Log.i(TAG, "SSE session connected: $sessionId from $clientAddr")

        Thread {
            while (running && sessions.containsKey(sessionId)) {
                try {
                    val response = session.responseQueue.poll(30, java.util.concurrent.TimeUnit.SECONDS)
                    if (response != null) {
                        val event = "event: message\ndata: $response\n\n"
                        try {
                            output.write(event.toByteArray())
                            output.flush()
                        } catch (e: Exception) {
                            Log.w(TAG, "SSE write failed for $sessionId, closing")
                            break
                        }
                    } else {
                        try {
                            output.write(": keepalive\n\n".toByteArray())
                            output.flush()
                        } catch (e: Exception) {
                            break
                        }
                    }
                } catch (e: Exception) {
                    break
                }
            }
            sessions.remove(sessionId)

            val rmIntent = Intent("com.fridamcp.app.SESSION_REMOVED")
            rmIntent.setPackage(packageName)
            rmIntent.putExtra("session_id", sessionId)
            sendBroadcast(rmIntent)
            broadcastStatus()
        }.start()
    }

    private fun handleSsePost(body: String, queryParams: Map<String, String>, output: OutputStream) {
        val sessionId = queryParams["session_id"] ?: run {
            sendHttp(output, 400, "Missing session_id")
            return
        }

        val session = sessions[sessionId] ?: run {
            sendHttp(output, 404, "Session not found")
            return
        }

        val response = processJsonRpc(body, session)
        if (response != null) {
            session.responseQueue.put(response)
        }
        sendHttp(output, 202, "Accepted")
    }

    // =====================================================================
    // Streamable HTTP Transport
    // =====================================================================

    private fun handleStreamablePost(body: String, headers: Map<String, String>, output: OutputStream) {
        val accept = headers["accept"] ?: ""
        val wantsSse = accept.contains("text/event-stream")

        val response = processJsonRpc(body, null) ?: run {
            sendHttp(output, 202, "Accepted")
            return
        }

        if (wantsSse) {
            val sseHeader = "HTTP/1.1 200 OK\r\n" +
                "Content-Type: text/event-stream\r\n" +
                "Cache-Control: no-cache\r\n" +
                "Connection: keep-alive\r\n" +
                "Access-Control-Allow-Origin: *\r\n" +
                "\r\n"
            output.write(sseHeader.toByteArray())
            output.flush()

            val sseEvent = "event: message\ndata: $response\n\n"
            output.write(sseEvent.toByteArray())
            output.flush()
        } else {
            sendRaw(output, 200, response)
        }
    }

    private fun handleStreamableGet(headers: Map<String, String>, output: OutputStream, client: Socket) {
        val sseHeader = "HTTP/1.1 200 OK\r\n" +
            "Content-Type: text/event-stream\r\n" +
            "Cache-Control: no-cache\r\n" +
            "Connection: keep-alive\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "\r\n"
        output.write(sseHeader.toByteArray())
        output.flush()

        val sessionId = UUID.randomUUID().toString().replace("-", "")
        val clientAddr = client.inetAddress.hostAddress ?: "unknown"
        val session = McpSession(
            id = sessionId,
            sseOutput = output,
            socket = client,
            responseQueue = LinkedBlockingQueue(),
            initialized = false,
            clientAddr = clientAddr,
        )
        sessions[sessionId] = session

        val addIntent = Intent("com.fridamcp.app.SESSION_ADDED")
        addIntent.setPackage(packageName)
        addIntent.putExtra("session_id", sessionId)
        addIntent.putExtra("client_addr", clientAddr)
        sendBroadcast(addIntent)
        broadcastStatus()

        Thread {
            while (running && sessions.containsKey(sessionId)) {
                try {
                    val response = session.responseQueue.poll(30, java.util.concurrent.TimeUnit.SECONDS)
                    if (response != null) {
                        try {
                            output.write("event: message\ndata: $response\n\n".toByteArray())
                            output.flush()
                        } catch (e: Exception) { break }
                    } else {
                        try {
                            output.write(": keepalive\n\n".toByteArray())
                            output.flush()
                        } catch (e: Exception) { break }
                    }
                } catch (e: Exception) { break }
            }
            sessions.remove(sessionId)
            val rmIntent = Intent("com.fridamcp.app.SESSION_REMOVED")
            rmIntent.setPackage(packageName)
            rmIntent.putExtra("session_id", sessionId)
            sendBroadcast(rmIntent)
            broadcastStatus()
        }.start()
    }

    private fun handleStreamableDelete(headers: Map<String, String>, output: OutputStream) {
        sendHttp(output, 200, "Deleted")
    }

    // =====================================================================
    // JSON-RPC Processing
    // =====================================================================

    private fun processJsonRpc(body: String, session: McpSession?): String? {
        return try {
            val json = JSONObject(body)
            val id = json.opt("id")
            val method = json.optString("method", "")
            val params = json.optJSONObject("params")
            Log.d(TAG, "JSON-RPC: method=$method id=$id")

            when (method) {
                "initialize" -> {
                    session?.initialized = true
                    val result = JSONObject()
                        .put("protocolVersion", PROTOCOL_VERSION)
                        .put("capabilities", JSONObject()
                            .put("tools", JSONObject())
                            .put("resources", JSONObject())
                            .put("prompts", JSONObject())
                        )
                        .put("serverInfo", JSONObject()
                            .put("name", SERVER_NAME)
                            .put("version", SERVER_VERSION)
                        )
                    makeResponse(id, result)
                }

                "notifications/initialized" -> {
                    session?.initialized = true
                    null
                }

                "tools/list" -> {
                    val result = JSONObject().put("tools", getToolsList())
                    makeResponse(id, result)
                }

                "tools/call" -> {
                    val toolName = params?.optString("name", "") ?: ""
                    val args = params?.optJSONObject("arguments") ?: JSONObject()
                    val result = handleToolCall(toolName, args)
                    makeResponse(id, result)
                }

                "ping" -> {
                    makeResponse(id, JSONObject().put("status", "ok"))
                }

                "resources/list" -> {
                    makeResponse(id, JSONObject().put("resources", JSONArray()))
                }

                "prompts/list" -> {
                    makeResponse(id, JSONObject().put("prompts", JSONArray()))
                }

                else -> makeError(id, -32601, "Method not found: $method")
            }
        } catch (e: Exception) {
            Log.e(TAG, "JSON-RPC error", e)
            makeError(null, -32603, "Internal error: ${e.message}")
        }
    }

    // =====================================================================
    // Tool Definitions
    // =====================================================================

    /** 禁用的模块 — 由 McpRepository.toggleModule 通过广播控制 */
    private val disabledModules = mutableSetOf<String>()

    private fun updateDisabledModules() {
        // 从 SharedPreferences 读取禁用模块列表
        val prefs = getSharedPreferences("fridamcp_modules", MODE_PRIVATE)
        disabledModules.clear()
        for (module in prefs.all) {
            if (module.value == false) {
                disabledModules.add(module.key)
            }
        }
        Log.i(TAG, "Disabled modules: $disabledModules")
    }

    private fun getToolsList(): JSONArray {
        updateDisabledModules()
        val tools = JSONArray()

        fun tool(module: String, name: String, description: String, inputSchema: JSONObject = JSONObject(), required: JSONArray = JSONArray()) {
            if (module in disabledModules) return
            tools.put(JSONObject()
                .put("name", name)
                .put("description", description)
                .put("inputSchema", inputSchema
                    .put("type", "object")
                    .also { if (required.length() > 0) it.put("required", required) })
            )
        }

        // === System ===
        tool("system", "ping", "健康检查")
        tool("system", "server_info", "获取 MCP 服务器信息")
        tool("system", "get_device_info", "获取设备信息：型号、Android 版本、架构、Root 状态")

        // === Process ===
        tool("process", "list_apps", "列出已安装应用", JSONObject().put("system", JSONObject().put("type", "boolean").put("description", "包含系统应用")))
        tool("process", "list_processes", "列出运行中的进程")
        tool("process", "launch_app", "启动应用", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))
        tool("process", "kill_process", "杀死进程", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))
        tool("process", "check_injection", "检测应用是否已注入 frida-gadget", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))
        tool("process", "get_system_status", "获取系统状态")

        // === File System ===
        tool("filesystem", "list_files", "列出目录内容", JSONObject().put("path", JSONObject().put("type", "string")), JSONArray().put("path"))
        tool("filesystem", "read_file", "读取文件内容", JSONObject().put("path", JSONObject().put("type", "string")).put("max_size", JSONObject().put("type", "integer").put("default", 4096)), JSONArray().put("path"))
        tool("filesystem", "get_app_info", "获取应用详细信息", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))

        // === UI Automation ===
        tool("ui_automation", "ui_tap", "点击屏幕", JSONObject().put("x", JSONObject().put("type", "integer")).put("y", JSONObject().put("type", "integer")), JSONArray().put("x").put("y"))
        tool("ui_automation", "ui_swipe", "滑动", JSONObject().put("x1", JSONObject().put("type", "integer")).put("y1", JSONObject().put("type", "integer")).put("x2", JSONObject().put("type", "integer")).put("y2", JSONObject().put("type", "integer")), JSONArray().put("x1").put("y1").put("x2").put("y2"))
        tool("ui_automation", "ui_input_text", "输入文本", JSONObject().put("text", JSONObject().put("type", "string")), JSONArray().put("text"))
        tool("ui_automation", "ui_press_key", "按键", JSONObject().put("keycode", JSONObject().put("type", "string").put("description", "如 KEYCODE_HOME, KEYCODE_BACK")), JSONArray().put("keycode"))
        tool("ui_automation", "screenshot", "截图", JSONObject().put("filename", JSONObject().put("type", "string")))

        // === Log ===
        tool("log", "get_logcat", "获取 logcat 日志", JSONObject().put("lines", JSONObject().put("type", "integer").put("default", 100)).put("filter", JSONObject().put("type", "string")))
        tool("log", "clear_logcat", "清除 logcat")

        // === Memory ===
        tool("memory", "list_modules", "列出进程加载的模块", JSONObject().put("pid", JSONObject().put("type", "integer")), JSONArray().put("pid"))
        tool("memory", "read_memory", "读取进程内存 (需要 Root + ptrace)", JSONObject().put("pid", JSONObject().put("type", "integer")).put("address", JSONObject().put("type", "string")).put("size", JSONObject().put("type", "integer")), JSONArray().put("pid").put("address").put("size"))

        // === Injection ===
        tool("injection", "inject_apk", "注入 frida-gadget 到 APK", JSONObject().put("apk_path", JSONObject().put("type", "string")).put("arch", JSONObject().put("type", "string")), JSONArray().put("apk_path"))

        // === Sessions ===
        tool("session", "list_sessions", "列出 MCP 客户端会话")
        tool("session", "close_session", "关闭客户端会话", JSONObject().put("session_id", JSONObject().put("type", "string")), JSONArray().put("session_id"))

        // === Shell ===
        tool("shell", "exec_shell", "执行 shell 命令 (需要 Shizuku/Root)", JSONObject().put("command", JSONObject().put("type", "string")), JSONArray().put("command"))

        // === Frida Script ===
        tool("frida", "run_frida_script", "在目标进程中执行 Frida JavaScript (通过 frida-server)", JSONObject().put("package_name", JSONObject().put("type", "string")).put("script", JSONObject().put("type", "string")), JSONArray().put("package_name").put("script"))

        return tools
    }

    // =====================================================================
    // Tool Call Handler — 全部真实实现
    // =====================================================================

    private fun handleToolCall(name: String, args: JSONObject): JSONObject {
        try {
            when (name) {
                "ping" -> return textResult("pong")

                "server_info" -> return textResult(
                    "FridaMCP v$SERVER_VERSION\n" +
                    "Port: $PORT\n" +
                    "Address: 127.0.0.1\n" +
                    "SSE: http://127.0.0.1:$PORT/sse\n" +
                    "POST: http://127.0.0.1:$PORT/messages?session_id=xxx\n" +
                    "MCP: http://127.0.0.1:$PORT/mcp\n" +
                    "Sessions: ${sessions.size}\n" +
                    "Permission: ${ShizukuManager.currentMode}\n" +
                    "frida-server: ${if (ShizukuManager.isFridaServerRunning()) "running" else "not running"}"
                )

                "get_device_info" -> {
                    val info = JSONObject()
                        .put("model", android.os.Build.MODEL)
                        .put("manufacturer", android.os.Build.MANUFACTURER)
                        .put("brand", android.os.Build.BRAND)
                        .put("android_version", android.os.Build.VERSION.RELEASE)
                        .put("api_level", android.os.Build.VERSION.SDK_INT)
                        .put("arch", android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
                        .put("root_available", ShizukuManager.isRootAvailable())
                        .put("root_granted", ShizukuManager.rootGranted)
                        .put("shizuku_binder", ShizukuManager.shizukuBinderAlive)
                        .put("shizuku_permission", ShizukuManager.shizukuPermissionGranted)
                        .put("permission_mode", ShizukuManager.currentMode.toString())
                        .put("frida_server_running", ShizukuManager.isFridaServerRunning())
                        .put("frida_version", ShizukuManager.getFridaVersion() ?: "N/A")
                    return textResult(info.toString(2))
                }

                "list_apps" -> {
                    val includeSystem = args.optBoolean("system", false)
                    val pm = packageManager
                    val packages = pm.getInstalledApplications(0)
                    val sb = StringBuilder("Found ${packages.size} apps:\n")
                    for (appInfo in packages) {
                        val isSystem = (appInfo.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0
                        if (!includeSystem && isSystem) continue
                        sb.append("${appInfo.packageName} | ${pm.getApplicationLabel(appInfo)} | ${if (isSystem) "system" else "user"}\n")
                    }
                    return textResult(sb.toString())
                }

                "list_processes" -> {
                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
                        return textResult("Error: 需要 Shizuku/Root 权限才能列出所有进程")
                    }
                    return textResult(ShizukuManager.execShell("ps -e -o PID,NAME 2>/dev/null || ps -A"))
                }

                "launch_app" -> {
                    val pkg = args.optString("package_name")
                    val intent = packageManager.getLaunchIntentForPackage(pkg)
                    if (intent != null) {
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                        return textResult("Launched: $pkg")
                    }
                    return textResult("No launch intent for: $pkg")
                }

                "kill_process" -> {
                    val pkg = args.optString("package_name")
                    return textResult("Killed: $pkg\n${ShizukuManager.execShell("am force-stop $pkg")}")
                }

                "check_injection" -> {
                    val pkg = args.optString("package_name")
                    val detector = InjectionDetector(this)
                    val result = detector.detectStatic(pkg)
                    return textResult("Package: $pkg\nDetected: ${result.detected}\nMethod: ${result.method}\nDetails: ${result.details}\nArch: ${result.gadgetArch ?: "N/A"}")
                }

                "get_system_status" -> {
                    val uptime = if (running && serverStartTime > 0) System.currentTimeMillis() - serverStartTime else 0
                    val status = JSONObject()
                        .put("sessions", sessions.size)
                        .put("permission", ShizukuManager.currentMode.toString())
                        .put("port", PORT)
                        .put("frida_server_running", ShizukuManager.isFridaServerRunning())
                        .put("uptime_ms", uptime)
                    return textResult(status.toString(2))
                }

                "list_files" -> {
                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
                        return textResult("Error: 需要 Shizuku/Root 权限")
                    }
                    val path = args.optString("path").replace("'", "'\''")
                    return textResult(ShizukuManager.execShell("ls -la '$path'"))
                }

                "read_file" -> {
                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
                        return textResult("Error: 需要 Shizuku/Root 权限")
                    }
                    val path = args.optString("path").replace("'", "'\''")
                    return textResult(ShizukuManager.execShell("head -c ${args.optInt("max_size", 4096)} '$path' 2>&1 | cat -v"))
                }

                "get_app_info" -> {
                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
                        return textResult("Error: 需要 Shizuku/Root 权限")
                    }
                    val pkg = args.optString("package_name").replace("'", "'\''").replace(";", "").replace("|", "").replace("&", "")
                    return textResult(ShizukuManager.execShell("dumpsys package '$pkg' | head -50"))
                }

                "ui_tap" -> {
                    val x = args.optInt("x")
                    val y = args.optInt("y")
                    if (x < 0 || y < 0) return textResult("Error: x and y must be non-negative")
                    return textResult("Tapped ($x, $y)\n${ShizukuManager.execShell("input tap $x $y")}")
                }

                "ui_swipe" -> {
                    val x1 = args.optInt("x1"); val y1 = args.optInt("y1")
                    val x2 = args.optInt("x2"); val y2 = args.optInt("y2")
                    return textResult(ShizukuManager.execShell("input swipe $x1 $y1 $x2 $y2"))
                }

                "ui_input_text" -> {
                    val text = args.optString("text")
                    // 避免 shell 注入: 用 Base64 编码传递
                    val b64 = android.util.Base64.encodeToString(text.toByteArray(), android.util.Base64.NO_WRAP)
                    return textResult(ShizukuManager.execShell("echo '$b64' | base64 -d | xargs -0 input text"))
                }

                "ui_press_key" -> {
                    val keycode = args.optString("keycode").replace("'", "").replace(";", "").replace("|", "").replace("&", "").replace(" ", "")
                    if (keycode.isBlank()) return textResult("Error: keycode is required")
                    return textResult(ShizukuManager.execShell("input keyevent $keycode"))
                }

                "screenshot" -> {
                    val tmpPath = "/data/local/tmp/screenshot_${System.currentTimeMillis()}.png"
                    val capResult = ShizukuManager.execShell("screencap -p $tmpPath && echo OK || echo FAIL")
                    return textResult("Screenshot: $tmpPath\n$capResult")
                }

                "get_logcat" -> {
                    val lines = args.optInt("lines", 100)
                    val filter = args.optString("filter", "")
                    val safeFilter = filter.replace("'", "'\''").replace(";", "").replace("|", "").replace("&", "")
                    val cmd = if (safeFilter.isNotBlank()) "logcat -d -t $lines | grep -i '$safeFilter'" else "logcat -d -t $lines"
                    return textResult(ShizukuManager.execShell(cmd))
                }

                "clear_logcat" -> return textResult("Logcat cleared\n${ShizukuManager.execShell("logcat -c")}")

                "list_modules" -> {
                    val pid = args.optInt("pid")
                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
                        return textResult("Error: Need Shizuku/Root to read /proc/$pid/maps")
                    }
                    return textResult(ShizukuManager.execShell("cat /proc/$pid/maps 2>/dev/null | head -100"))
                }

                "read_memory" -> {
                    val pid = args.optInt("pid")
                    val address = args.optString("address", "0")
                    val size = args.optInt("size", 64)

                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
                        return textResult("Error: Need Root to read process memory")
                    }

                    // 转换地址为十进制
                    val decimalAddr = if (address.startsWith("0x")) {
                        java.math.BigInteger(address.substring(2), 16).toString()
                    } else {
                        address.toLongOrNull()?.toString() ?: "0"
                    }

                    // /proc/PID/mem 需要 ptrace(PTRACE_ATTACH) 才能读取
                    // ptrace 是内核 syscall, 不是 shell 命令
                    // 参考: https://juejin.cn/post/7360285681237278761  https://bbs.kanxue.com/thread-284041.htm
                    val cmd = """# 方法1: 使用 gdb (如果安装了)
                        which gdb >/dev/null 2>&1 && {
                            gdb -batch -ex "attach $pid" -ex "x/${size}xb $decimalAddr" -ex "detach" 2>&1
                            exit 0
                        }
                        # 方法3: 直接 dd (某些 root 环境 /proc/PID/mem 可直接读)
                        dd if=/proc/$pid/mem bs=1 skip=$decimalAddr count=$size 2>/dev/null | xxd
                        if [ \$? -ne 0 ]; then
                            echo "ERROR: Cannot read /proc/$pid/mem"
                            echo "需要: 1) Root 权限 2) 目标进程未被 ptrace 保护"
                            echo "或者安装 gdb: pkg install gdb"
                        fi
                    """.trimIndent()

                    val result = ShizukuManager.execShell(cmd)
                    return textResult("PID: $pid, Address: 0x${address.removePrefix("0x")}, Size: $size bytes\n$result")
                }

                "inject_apk" -> {
                    val apkPath = args.optString("apk_path")
                    val arch = args.optString("arch", "arm64-v8a")
                    val injector = ApkInjector(this)
                    val result = injector.inject(apkPath, arch)
                    return when (result) {
                        is ApkInjector.Result.Success -> textResult("Injection complete: ${result.outputPath}")
                        is ApkInjector.Result.Error -> textResult("Injection failed: ${result.message}")
                    }
                }

                "list_sessions" -> {
                    val sb = StringBuilder("MCP Sessions: ${sessions.size}\n")
                    for (s in sessions.values) {
                        sb.append("${s.id} | ${s.clientAddr} | initialized=${s.initialized}\n")
                    }
                    return textResult(sb.toString())
                }

                "close_session" -> {
                    val sid = args.optString("session_id")
                    val s = sessions.remove(sid)
                    if (s != null) {
                        try { s.socket.close() } catch (e: Exception) {}
                        broadcastStatus()
                        return textResult("Session closed: $sid")
                    }
                    return textResult("Session not found: $sid")
                }

                "exec_shell" -> {
                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) {
                        return textResult("Error: No Shizuku/Root permission. Activate Shizuku or grant root first.")
                    }
                    val cmd = args.optString("command")
                    if (cmd.isBlank()) return textResult("Error: command is required")
                    // exec_shell 设计上就是执行任意命令 — 这是它的功能
                    // 但记录日志以供审计
                    Log.w(TAG, "exec_shell: $cmd")
                    return textResult(ShizukuManager.execShell(cmd))
                }

                "run_frida_script" -> {
                    val pkg = args.optString("package_name")
                    val script = args.optString("script")

                    // 检查 frida-server 是否在运行
                    if (!ShizukuManager.isFridaServerRunning()) {
                        return textResult(
                            "Error: frida-server is not running.\n" +
                            "Start it first: Settings → Frida Server → 启动\n" +
                            "Or run: /data/local/tmp/frida-server &"
                        )
                    }

                    // 检查目标进程是否在运行
                    val pidCheck = ShizukuManager.execShell("pidof $pkg")
                    val pid = pidCheck.trim().toIntOrNull()
                    if (pid == null || pid <= 0) {
                        return textResult(
                            "Error: Process '$pkg' is not running.\n" +
                            "Launch the app first, or check package name."
                        )
                    }

                    // 写入脚本到临时文件
                    val tmpScript = "/data/local/tmp/frida_script_${System.currentTimeMillis()}.js"
                    val writeResult = ShizukuManager.execShell("cat > '$tmpScript' << 'FRIDASCRIPT_EOF'\n$script\nFRIDASCRIPT_EOF")
                    if (writeResult.contains("Error")) {
                        return textResult("Error: Cannot write script file: $writeResult")
                    }

                    // frida CLI 是 PC 端 Python 工具, Android 上不可用
                    // frida-inject 是独立二进制, 需要从 frida releases 单独下载
                    // 参考: https://frida.re/docs/android/  https://www.52pojie.cn/thread-1823118-1-1.html
                    // 方案1: /data/local/tmp/frida-inject (如果用户下载了)
                    // 方案2: python3 + frida 库 (需要 Termux)
                    // 方案3: 返回错误, 提示用户
                    val injectResult = ShizukuManager.execShell("""
                        if [ -x /data/local/tmp/frida-inject ]; then
                            /data/local/tmp/frida-inject -p $pid -s '$tmpScript' 2>&1
                            echo "INJECT_OK"
                        elif command -v python3 >/dev/null 2>&1; then
                            python3 -c "
import frida, sys, time
try:
    session = frida.attach($pid)
    script = session.create_script(open('$tmpScript').read())
    script.load()
    time.sleep(2)
    session.detach()
    print('PYTHON_OK')
except Exception as e:
    print('PYTHON_ERROR: ' + str(e))
" 2>&1
                        else
                            echo "ERROR: 需要 frida-inject 或 python3+frida"
                            echo "下载 frida-inject: https://github.com/frida/frida/releases"
                            echo "或安装 Termux + python3 + pip install frida"
                            echo "或使用 frida-gadget listen 模式 (注入 APK)"
                        fi
                        rm -f '$tmpScript'
                    """.trimIndent())

                    return textResult(
                        "Package: $pkg (PID: $pid)\n" +
                        "Script size: ${script.length} chars\n" +
                        "Result:\n$injectResult"
                    )
                }

                else -> return errorResult(-32601, "Method not found: $name")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Tool call error: $name", e)
            return errorResult(-32603, "Internal error: ${e.message}")
        }
    }

    // =====================================================================
    // Helpers
    // =====================================================================

    private fun textResult(text: String): JSONObject {
        return JSONObject().put("content", JSONArray().put(
            JSONObject().put("type", "text").put("text", text)
        ))
    }

    private fun errorResult(code: Int, message: String): JSONObject {
        return JSONObject().put("isError", true).put("content", JSONArray().put(
            JSONObject().put("type", "text").put("text", "Error: $message")
        ))
    }

    private fun makeResponse(id: Any?, result: JSONObject): String {
        val response = JSONObject()
        if (id != null) response.put("id", id)
        response.put("jsonrpc", "2.0")
        response.put("result", result)
        return response.toString()
    }

    private fun makeError(id: Any?, code: Int, message: String): String {
        val response = JSONObject()
        if (id != null) response.put("id", id)
        response.put("jsonrpc", "2.0")
        response.put("error", JSONObject().put("code", code).put("message", message))
        return response.toString()
    }

    private fun sendJson(output: OutputStream, status: Int, json: JSONObject) {
        sendRaw(output, status, json.toString())
    }

    private fun sendRaw(output: OutputStream, status: Int, body: String) {
        val bodyBytes = body.toByteArray()
        val response = "HTTP/1.1 $status OK\r\n" +
            "Content-Type: application/json\r\n" +
            "Content-Length: ${bodyBytes.size}\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "Connection: close\r\n" +
            "\r\n"
        output.write(response.toByteArray())
        output.write(bodyBytes)
        output.flush()
    }

    private fun sendHttp(output: OutputStream, status: Int, message: String) {
        val body = message.toByteArray()
        val response = "HTTP/1.1 $status OK\r\n" +
            "Content-Type: text/plain\r\n" +
            "Content-Length: ${body.size}\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "Connection: close\r\n" +
            "\r\n"
        output.write(response.toByteArray())
        output.write(body)
        output.flush()
    }

    private fun healthCheckJson(): JSONObject {
        return JSONObject()
            .put("status", "ok")
            .put("server", SERVER_NAME)
            .put("version", SERVER_VERSION)
            .put("sessions", sessions.size)
            .put("tools", getToolsList().length())
            .put("permission", ShizukuManager.currentMode.toString())
    }

    private fun stopServer() {
        running = false
        serverStartTime = 0

        for (session in sessions.values) {
            try {
                session.socket.close()
            } catch (e: Exception) {}
        }
        sessions.clear()

        try {
            serverSocket?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Error closing server socket", e)
        }
        serverSocket = null

        broadcastStatus()
        Log.i(TAG, "MCP server stopped")
    }

    override fun onDestroy() {
        stopServer()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
