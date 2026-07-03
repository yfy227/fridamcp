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
import java.net.ServerSocket
import java.net.Socket
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.LinkedBlockingQueue
import org.json.JSONArray
import org.json.JSONObject

/**
 * MCP Server — proper implementation of MCP SSE + Streamable HTTP transport.
 *
 * ============== SSE Transport (legacy, widely supported) ===============
 *
 *   GET  /sse
 *     → Opens SSE stream
 *     → Sends: event: endpoint\ndata: /messages?session_id=xxx\n\n
 *     → Keeps open, delivers JSON-RPC responses as: event: message\ndata: {...}\n\n
 *
 *   POST /messages?session_id=xxx
 *     → Accepts JSON-RPC request in body
 *     → Returns HTTP 202 Accepted (NOT the JSON-RPC response!)
 *     → JSON-RPC response is sent back through the SSE stream
 *
 * =========== Streamable HTTP Transport (newer spec) ===================
 *
 *   POST /mcp
 *     → Accept: application/json, text/event-stream
 *     → Content-Type: application/json
 *     → Returns either:
 *       - 200 OK with Content-Type: application/json (simple response)
 *       - 200 OK with Content-Type: text/event-stream (streaming response)
 *     → mcp-session-id header for session management
 *
 *   GET  /mcp
 *     → Opens SSE stream for server-to-client notifications
 *
 *   DELETE /mcp
 *     → Terminates session
 *
 * =======================================================================
 */
class McpServerService : Service() {

    companion object {
        const val ACTION_START = "com.fridamcp.app.START_MCP"
        const val ACTION_STOP = "com.fridamcp.app.STOP_MCP"
        private const val NOTIF_ID = 2001
        private const val TAG = "McpServerService"
        private const val PORT = 8768

        // MCP Protocol Version
        private const val PROTOCOL_VERSION = "2024-11-05"

        // Server info
        private const val SERVER_NAME = "FridaMCP"
        private const val SERVER_VERSION = "1.0.0"
    }

    private var serverSocket: ServerSocket? = null
    private var running = false

    /** Session management: session_id → SSE response queue */
    private val sessions = ConcurrentHashMap<String, McpSession>()

    /** Represents a connected SSE client session */
    private data class McpSession(
        val id: String,
        val sseOutput: OutputStream,
        val socket: Socket,
        val responseQueue: LinkedBlockingQueue<String>,
        var initialized: Boolean = false,
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
        Thread {
            try {
                serverSocket = ServerSocket(PORT, 10, java.net.InetAddress.getByName("127.0.0.1"))
                Log.i(TAG, "MCP server listening on 127.0.0.1:$PORT")

                while (running) {
                    try {
                        val client = serverSocket?.accept() ?: break
                        Thread { handleClient(client) }.start()
                    } catch (e: IOException) {
                        if (running) Log.e(TAG, "Accept error", e)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start MCP server", e)
            }
        }.start()
    }

    private fun handleClient(client: Socket) {
        try {
            client.soTimeout = 0 // no timeout for SSE
            val input = BufferedReader(InputStreamReader(client.getInputStream()))
            val output = client.getOutputStream()

            // Parse HTTP request line
            val requestLine = input.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 3) return
            val method = parts[0]
            val path = parts[1]

            // Parse headers
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

            // Read body if present
            var body = ""
            if (contentLength > 0) {
                val buf = CharArray(contentLength)
                input.read(buf, 0, contentLength)
                body = String(buf)
            }

            Log.d(TAG, "$method $path")

            // Route request
            when {
                // ===== SSE Transport: GET /sse =====
                method == "GET" && path == "/sse" -> handleSseConnect(client, output)

                // ===== SSE Transport: POST /messages?session_id=xxx =====
                method == "POST" && path.startsWith("/messages") -> handlePostMessage(path, body, output)

                // ===== Streamable HTTP: POST /mcp =====
                method == "POST" && path == "/mcp" -> handleStreamablePost(body, headers, output)

                // ===== Streamable HTTP: GET /mcp =====
                method == "GET" && path == "/mcp" -> handleStreamableGet(headers, output, client)

                // ===== Streamable HTTP: DELETE /mcp =====
                method == "DELETE" && path == "/mcp" -> handleStreamableDelete(headers, output)

                // ===== Health check =====
                method == "GET" && (path == "/" || path == "/health") ->
                    sendJson(output, 200, healthCheckJson())

                // ===== 404 =====
                else -> sendJson(output, 404, JSONObject().put("error", "Not found: $path"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling client", e)
        }
    }

    // =====================================================================
    // SSE Transport
    // =====================================================================

    private fun handleSseConnect(client: Socket, output: OutputStream) {
        val sessionId = UUID.randomUUID().toString().replace("-", "")

        // Send SSE headers
        val header = "HTTP/1.1 200 OK\r\n" +
            "Content-Type: text/event-stream\r\n" +
            "Cache-Control: no-cache\r\n" +
            "Connection: keep-alive\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "\r\n"
        output.write(header.toByteArray())
        output.flush()

        // Send endpoint event — tell client where to POST messages
        val endpointEvent = "event: endpoint\ndata: /messages?session_id=$sessionId\n\n"
        output.write(endpointEvent.toByteArray())
        output.flush()

        // Create session
        val session = McpSession(
            id = sessionId,
            sseOutput = output,
            socket = client,
            responseQueue = LinkedBlockingQueue(),
        )
        sessions[sessionId] = session

        Log.i(TAG, "SSE session connected: $sessionId")

        // Keep SSE stream open, send queued responses
        try {
            while (running && !client.isClosed) {
                val response = session.responseQueue.poll(15, java.util.concurrent.TimeUnit.SECONDS)
                if (response != null) {
                    val sseEvent = "event: message\ndata: $response\n\n"
                    output.write(sseEvent.toByteArray())
                    output.flush()
                    Log.d(TAG, "SSE sent to $sessionId: ${response.take(200)}")
                } else {
                    // Send keepalive comment
                    output.write(": ping\n\n".toByteArray())
                    output.flush()
                }
            }
        } catch (e: Exception) {
            Log.d(TAG, "SSE stream ended for $sessionId: ${e.message}")
        } finally {
            sessions.remove(sessionId)
            Log.i(TAG, "SSE session disconnected: $sessionId")
        }
    }

    private fun handlePostMessage(path: String, body: String, output: OutputStream) {
        // Extract session_id from query string
        val queryIdx = path.indexOf("?")
        if (queryIdx < 0) {
            sendHttp(output, 400, "Missing session_id")
            return
        }
        val query = path.substring(queryIdx + 1)
        val sessionId = query.split("&")
            .firstOrNull { it.startsWith("session_id=") }
            ?.substring("session_id=".length)

        if (sessionId == null) {
            sendHttp(output, 400, "Missing session_id")
            return
        }

        val session = sessions[sessionId]
        if (session == null) {
            sendHttp(output, 404, "Session not found")
            return
        }

        // Process JSON-RPC and queue response to SSE stream
        val response = processJsonRpc(body, session)
        if (response != null) {
            session.responseQueue.put(response)
        }

        // Return 202 Accepted — response goes through SSE
        sendHttp(output, 202, "Accepted")
    }

    // =====================================================================
    // Streamable HTTP Transport
    // =====================================================================

    private fun handleStreamablePost(
        body: String,
        headers: Map<String, String>,
        output: OutputStream,
    ) {
        val accept = headers["accept"] ?: ""
        val wantsSse = accept.contains("text/event-stream")
        val wantsJson = accept.contains("application/json")

        // Process JSON-RPC
        val response = processJsonRpc(body, null) ?: run {
            sendHttp(output, 202, "Accepted")
            return
        }

        if (wantsSse) {
            // Respond with SSE stream
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
            // Respond with JSON
            val jsonBytes = response.toByteArray()
            val respHeader = "HTTP/1.1 200 OK\r\n" +
                "Content-Type: application/json\r\n" +
                "Content-Length: ${jsonBytes.size}\r\n" +
                "Access-Control-Allow-Origin: *\r\n" +
                "Connection: close\r\n" +
                "\r\n"
            output.write(respHeader.toByteArray())
            output.write(jsonBytes)
            output.flush()
        }
    }

    private fun handleStreamableGet(
        headers: Map<String, String>,
        output: OutputStream,
        client: Socket,
    ) {
        // Open SSE stream for server-to-client notifications
        val header = "HTTP/1.1 200 OK\r\n" +
            "Content-Type: text/event-stream\r\n" +
            "Cache-Control: no-cache\r\n" +
            "Connection: keep-alive\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "\r\n"
        output.write(header.toByteArray())
        output.flush()

        // Keep alive with ping
        try {
            while (running && !client.isClosed) {
                output.write(": ping\n\n".toByteArray())
                output.flush()
                Thread.sleep(15000)
            }
        } catch (e: Exception) {
            Log.d(TAG, "GET SSE stream ended: ${e.message}")
        }
    }

    private fun handleStreamableDelete(headers: Map<String, String>, output: OutputStream) {
        sendJson(output, 200, JSONObject().put("status", "terminated"))
    }

    // =====================================================================
    // JSON-RPC Processing
    // =====================================================================

    private fun processJsonRpc(body: String, session: McpSession?): String? {
        try {
            val json = JSONObject(body)
            val method = json.optString("method", "")
            val id = json.opt("id")
            val params = json.optJSONObject("params")

            Log.i(TAG, "JSON-RPC: method=$method id=$id")

            when (method) {
                "initialize" -> {
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
                    return makeResponse(id, result)
                }

                "notifications/initialized" -> {
                    // Notification — no response
                    session?.initialized = true
                    return null
                }

                "tools/list" -> {
                    val tools = getToolsList()
                    val result = JSONObject().put("tools", tools)
                    return makeResponse(id, result)
                }

                "tools/call" -> {
                    val toolName = params?.optString("name", "") ?: ""
                    val args = params?.optJSONObject("arguments") ?: JSONObject()
                    val result = handleToolCall(toolName, args)
                    return makeResponse(id, result)
                }

                "ping" -> {
                    val result = JSONObject().put("status", "ok")
                    return makeResponse(id, result)
                }

                "resources/list" -> {
                    val result = JSONObject().put("resources", JSONArray())
                    return makeResponse(id, result)
                }

                "prompts/list" -> {
                    val result = JSONObject().put("prompts", JSONArray())
                    return makeResponse(id, result)
                }

                else -> {
                    return makeError(id, -32601, "Method not found: $method")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "JSON-RPC parse error", e)
            return makeError(null, -32700, "Parse error: ${e.message}")
        }
    }

    private fun makeResponse(id: Any?, result: JSONObject): String {
        val resp = JSONObject()
        resp.put("jsonrpc", "2.0")
        if (id != null) resp.put("id", id)
        resp.put("result", result)
        return resp.toString()
    }

    private fun makeError(id: Any?, code: Int, message: String): String {
        val resp = JSONObject()
        resp.put("jsonrpc", "2.0")
        if (id != null) resp.put("id", id)
        resp.put("error", JSONObject()
            .put("code", code)
            .put("message", message)
        )
        return resp.toString()
    }

    // =====================================================================
    // Tool Definitions
    // =====================================================================

    private fun getToolsList(): JSONArray {
        val tools = JSONArray()

        fun tool(name: String, desc: String, props: JSONObject = JSONObject(), required: JSONArray = JSONArray()) {
            tools.put(JSONObject()
                .put("name", name)
                .put("description", desc)
                .put("inputSchema", JSONObject()
                    .put("type", "object")
                    .put("properties", props)
                    .put("required", required)
                )
            )
        }

        // === Process Management ===
        tool("ping", "健康检查")
        tool("server_info", "获取 MCP 服务器信息")
        tool("get_device_info", "获取设备信息：型号、Android 版本、架构、Root 状态")
        tool("list_apps", "列出已安装应用", JSONObject().put("system", JSONObject().put("type", "boolean").put("description", "包含系统应用")))
        tool("list_processes", "列出运行中的进程")
        tool("launch_app", "启动应用", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))
        tool("kill_process", "杀死进程", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))
        tool("check_injection", "检测应用是否已注入 frida-gadget", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))
        tool("get_system_status", "获取系统状态：会话、设备、服务器")

        // === File System ===
        tool("list_files", "列出目录内容", JSONObject().put("path", JSONObject().put("type", "string")), JSONArray().put("path"))
        tool("read_file", "读取文件内容", JSONObject().put("path", JSONObject().put("type", "string")).put("max_size", JSONObject().put("type", "integer").put("default", 4096)), JSONArray().put("path"))
        tool("get_app_info", "获取应用详细信息", JSONObject().put("package_name", JSONObject().put("type", "string")), JSONArray().put("package_name"))

        // === UI Automation ===
        tool("ui_tap", "点击屏幕", JSONObject().put("x", JSONObject().put("type", "integer")).put("y", JSONObject().put("type", "integer")), JSONArray().put("x").put("y"))
        tool("ui_swipe", "滑动", JSONObject().put("x1", JSONObject().put("type", "integer")).put("y1", JSONObject().put("type", "integer")).put("x2", JSONObject().put("type", "integer")).put("y2", JSONObject().put("type", "integer")), JSONArray().put("x1").put("y1").put("x2").put("y2"))
        tool("ui_input_text", "输入文本", JSONObject().put("text", JSONObject().put("type", "string")), JSONArray().put("text"))
        tool("ui_press_key", "按键", JSONObject().put("keycode", JSONObject().put("type", "string").put("description", "如 KEYCODE_HOME, KEYCODE_BACK")), JSONArray().put("keycode"))
        tool("screenshot", "截图", JSONObject().put("package_name", JSONObject().put("type", "string").put("description", "可选：指定应用截图")))
        tool("get_current_activity", "获取当前前台 Activity")

        // === Log ===
        tool("get_logcat", "获取 logcat 日志", JSONObject().put("lines", JSONObject().put("type", "integer").put("default", 100)).put("filter", JSONObject().put("type", "string").put("description", "过滤关键字")))
        tool("clear_logcat", "清空 logcat 缓冲区")

        // === Memory (需要 Root/Shizuku) ===
        tool("list_modules", "列出进程加载的模块", JSONObject().put("pid", JSONObject().put("type", "integer")), JSONArray().put("pid"))
        tool("read_memory", "读取进程内存 (需要 Root)", JSONObject().put("pid", JSONObject().put("type", "integer")).put("address", JSONObject().put("type", "string")).put("size", JSONObject().put("type", "integer")), JSONArray().put("pid").put("address").put("size"))

        // === Injection ===
        tool("inject_apk", "注入 frida-gadget 到 APK", JSONObject().put("apk_path", JSONObject().put("type", "string")).put("arch", JSONObject().put("type", "string")), JSONArray().put("apk_path"))

        // === Sessions ===
        tool("list_sessions", "列出 MCP 会话")
        tool("close_session", "关闭会话", JSONObject().put("session_id", JSONObject().put("type", "string")), JSONArray().put("session_id"))

        // === Shell (通过 Shizuku/Root 执行) ===
        tool("exec_shell", "执行 shell 命令 (需要 Shizuku/Root)", JSONObject().put("command", JSONObject().put("type", "string")), JSONArray().put("command"))

        // === Frida Script (通过 gadget 连接) ===
        tool("run_frida_script", "在目标进程中执行 Frida JavaScript", JSONObject().put("package_name", JSONObject().put("type", "string")).put("script", JSONObject().put("type", "string")), JSONArray().put("package_name").put("script"))

        return tools
    }

    // =====================================================================
    // Tool Call Handler
    // =====================================================================

    private fun handleToolCall(name: String, args: JSONObject): JSONObject {
        try {
            when (name) {
                "ping" -> return textResult("pong")
                "server_info" -> return textResult("FridaMCP v1.0.0\nPort: $PORT\nAddress: 127.0.0.1\nSSE: http://127.0.0.1:$PORT/sse\nPOST: http://127.0.0.1:$PORT/messages?session_id=xxx\nMCP: http://127.0.0.1:$PORT/mcp\nSessions: ${sessions.size}\nPermission: ${ShizukuManager.currentMode}")
                "get_device_info" -> {
                    val info = JSONObject().put("model", android.os.Build.MODEL).put("manufacturer", android.os.Build.MANUFACTURER).put("brand", android.os.Build.BRAND).put("android_version", android.os.Build.VERSION.RELEASE).put("api_level", android.os.Build.VERSION.SDK_INT).put("arch", android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown").put("root", ShizukuManager.isRootAvailable()).put("shizuku", ShizukuManager.isShizukuAuthorized()).put("permission_mode", ShizukuManager.currentMode.toString())
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
                "list_processes" -> return textResult(ShizukuManager.execShell("ps -e -o PID,NAME 2>/dev/null || ps -A"))
                "launch_app" -> {
                    val pkg = args.optString("package_name")
                    val intent = packageManager.getLaunchIntentForPackage(pkg)
                    if (intent != null) { intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); startActivity(intent); return textResult("Launched: $pkg") }
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
                "get_system_status" -> return textResult(JSONObject().put("sessions", sessions.size).put("permission", ShizukuManager.currentMode.toString()).put("port", PORT).toString(2))
                "list_files" -> return textResult(ShizukuManager.execShell("ls -la '${args.optString("path")}'"))
                "read_file" -> return textResult(ShizukuManager.execShell("head -c ${args.optInt("max_size", 4096)} '${args.optString("path")}' 2>&1 | cat -v"))
                "get_app_info" -> return textResult(ShizukuManager.execShell("dumpsys package ${args.optString("package_name")} | head -50"))
                "ui_tap" -> return textResult("Tapped (${args.optInt("x")}, ${args.optInt("y")})\n${ShizukuManager.execShell("input tap ${args.optInt("x")} ${args.optInt("y")}")}")
                "ui_swipe" -> return textResult(ShizukuManager.execShell("input swipe ${args.optInt("x1")} ${args.optInt("y1")} ${args.optInt("x2")} ${args.optInt("y2")}"))
                "ui_input_text" -> return textResult(ShizukuManager.execShell("input text '${args.optString("text")}'"))
                "ui_press_key" -> return textResult(ShizukuManager.execShell("input keyevent ${args.optString("keycode")}"))
                "screenshot" -> {
                    val tmpPath = "/data/local/tmp/screenshot_${System.currentTimeMillis()}.png"
                    return textResult("Screenshot: $tmpPath\n${ShizukuManager.execShell("screencap -p $tmpPath && echo OK || echo FAIL")}")
                }
                "get_current_activity" -> return textResult(ShizukuManager.execShell("dumpsys activity activities | grep mResumedActivity"))
                "get_logcat" -> {
                    val lines = args.optInt("lines", 100)
                    val filter = args.optString("filter", "")
                    val cmd = if (filter.isNotEmpty()) "logcat -d -t $lines | grep '$filter'" else "logcat -d -t $lines"
                    return textResult(ShizukuManager.execShell(cmd))
                }
                "clear_logcat" -> return textResult("Logcat cleared\n${ShizukuManager.execShell("logcat -c")}")
                "list_modules" -> return textResult(ShizukuManager.execShell("cat /proc/${args.optInt("pid")}/maps 2>/dev/null | head -100"))
                "read_memory" -> {
                    val pid = args.optInt("pid"); val address = args.optString("address"); val size = args.optInt("size", 64)
                    return textResult(ShizukuManager.execShell("dd if=/proc/$pid/mem bs=1 skip=\$(printf '%d' 0x$address) count=$size 2>/dev/null | xxd"))
                }
                "inject_apk" -> {
                    val apkPath = args.optString("apk_path"); val arch = args.optString("arch", "arm64-v8a")
                    val injector = ApkInjector(this)
                    val result = injector.inject(apkPath, arch)
                    return when (result) { is ApkInjector.Result.Success -> textResult("Injection complete: ${result.outputPath}"); is ApkInjector.Result.Error -> textResult("Injection failed: ${result.message}") }
                }
                "list_sessions" -> {
                    val sb = StringBuilder("Sessions: ${sessions.size}\n")
                    for (s in sessions.values) sb.append("${s.id} | initialized=${s.initialized}\n")
                    return textResult(sb.toString())
                }
                "close_session" -> {
                    val sid = args.optString("session_id"); val s = sessions.remove(sid)
                    if (s != null) { try { s.socket.close() } catch (e: Exception) {}; return textResult("Session closed: $sid") }
                    return textResult("Session not found: $sid")
                }
                "exec_shell" -> {
                    if (ShizukuManager.currentMode == ShizukuManager.PermissionMode.NONE) return textResult("Error: No Shizuku/Root permission. Activate Shizuku or grant root first.")
                    return textResult(ShizukuManager.execShell(args.optString("command")))
                }
                "run_frida_script" -> {
                    val pkg = args.optString("package_name"); val script = args.optString("script")
                    val tmpScript = "/data/local/tmp/frida_script_${System.currentTimeMillis()}.js"
                    ShizukuManager.execShell("cat > $tmpScript << 'FRIDASCRIPT_EOF'\n$script\nFRIDASCRIPT_EOF")
                    val runResult = ShizukuManager.execShell("frida -U -p \$(pidof $pkg) -l $tmpScript --no-pause 2>&1 | head -50")
                    ShizukuManager.execShell("rm -f $tmpScript")
                    return textResult("Package: $pkg\n$runResult")
                }
                else -> return errorResult(-32601, "Method not found: $name")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Tool call error: $name", e)
            return errorResult(-32603, "Internal error: ${e.message}")
        }
    }

    private fun textResult(text: String): JSONObject {
        return JSONObject().put("content", JSONArray().put(JSONObject().put("type", "text").put("text", text)))
    }

    private fun errorResult(code: Int, message: String): JSONObject {
        return JSONObject().put("content", JSONArray().put(JSONObject().put("type", "text").put("text", "Error: $message"))).put("isError", true)
    }

    // =====================================================================
    // HTTP Helpers
    // =====================================================================

    private fun healthCheckJson(): JSONObject {
        return JSONObject()
            .put("name", SERVER_NAME)
            .put("version", SERVER_VERSION)
            .put("status", "running")
            .put("address", "127.0.0.1:$PORT")
            .put("endpoints", JSONObject()
                .put("sse", "http://127.0.0.1:$PORT/sse")
                .put("messages", "http://127.0.0.1:$PORT/messages?session_id=xxx")
                .put("mcp", "http://127.0.0.1:$PORT/mcp")
                .put("health", "http://127.0.0.1:$PORT/")
            )
            .put("activeSessions", sessions.size)
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

    private fun stopServer() {
        running = false

        // Close all sessions
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
        Log.i(TAG, "MCP server stopped")
    }

    override fun onDestroy() {
        stopServer()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
