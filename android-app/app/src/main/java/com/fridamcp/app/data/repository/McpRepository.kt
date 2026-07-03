package com.fridamcp.app.data.repository

import android.content.Context
import android.content.Intent
import com.fridamcp.app.data.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class McpRepository(private val context: Context) {

    private val _serverStatus = MutableStateFlow(
        MCPServerStatus(
            running = false,
            host = "127.0.0.1",
            port = 8768,
            transport = "sse",
            startTime = 0,
            activeSessions = 0,
            totalTools = 42,
            connectedClients = 0,
        )
    )
    val serverStatus: StateFlow<MCPServerStatus> = _serverStatus.asStateFlow()

    private val _sessions = MutableStateFlow<List<MCPSession>>(emptyList())
    val sessions: StateFlow<List<MCPSession>> = _sessions.asStateFlow()

    private val _modules = MutableStateFlow(
        listOf(
            MCPModule("process", "进程管理", "进程列表、应用启动、附加进程", 8, "Apps", true),
            MCPModule("hook", "Hook 管理", "Java/Native Hook、方法追踪", 7, "Code", true),
            MCPModule("memory", "内存检查", "内存读写、搜索、模块列表", 6, "Memory", true),
            MCPModule("network", "网络监控", "SSL Hook、HTTP 捕获", 5, "Network", true),
            MCPModule("filesystem", "文件系统", "文件读写、推送拉取", 6, "File", true),
            MCPModule("ui_automation", "UI 自动化", "点击、输入、截图", 5, "UI", true),
            MCPModule("crypto", "加密分析", "Cipher Hook、密钥导出", 3, "Crypto", true),
            MCPModule("log", "日志捕获", "logcat、Frida 脚本日志", 4, "Log", true),
        )
    )
    val modules: StateFlow<List<MCPModule>> = _modules.asStateFlow()

    private val _logs = MutableStateFlow<List<LogEntry>>(emptyList())
    val logs: StateFlow<List<LogEntry>> = _logs.asStateFlow()

    private val _tasks = MutableStateFlow<List<InjectionTask>>(emptyList())
    val tasks: StateFlow<List<InjectionTask>> = _tasks.asStateFlow()

    /** Start MCP server via foreground service */
    fun startServer() {
        _serverStatus.value = _serverStatus.value.copy(
            running = true,
            startTime = System.currentTimeMillis(),
        )
        addLog(LogLevel.INFO, "McpServer", "MCP 服务器已启动 — 监听 127.0.0.1:${_serverStatus.value.port}")
        addLog(LogLevel.INFO, "McpServer", "端点: http://127.0.0.1:${_serverStatus.value.port}/sse (SSE)")
        addLog(LogLevel.INFO, "McpServer", "端点: http://127.0.0.1:${_serverStatus.value.port}/mcp (JSON-RPC)")

        // Start the foreground service
        try {
            val intent = Intent(context, com.fridamcp.app.data.service.McpServerService::class.java)
            intent.action = com.fridamcp.app.data.service.McpServerService.ACTION_START
            context.startForegroundService(intent)
        } catch (e: Exception) {
            addLog(LogLevel.ERROR, "McpServer", "启动 MCP 服务失败: ${e.message}")
        }
    }

    /** Stop MCP server */
    fun stopServer() {
        _serverStatus.value = _serverStatus.value.copy(
            running = false,
            startTime = 0,
            activeSessions = 0,
            connectedClients = 0,
        )
        _sessions.value = emptyList()
        addLog(LogLevel.INFO, "McpServer", "MCP 服务器已停止")

        try {
            val intent = Intent(context, com.fridamcp.app.data.service.McpServerService::class.java)
            intent.action = com.fridamcp.app.data.service.McpServerService.ACTION_STOP
            context.startForegroundService(intent)
        } catch (e: Exception) {
            // ignore
        }
    }

    /** Toggle module enabled state */
    fun toggleModule(name: String) {
        _modules.value = _modules.value.map { m ->
            if (m.name == name) m.copy(enabled = !m.enabled) else m
        }
    }

    /** Create injection task */
    fun createInjectionTask(
        apkPath: String,
        appName: String,
        packageName: String,
        arch: String,
        useApktool: Boolean,
    ): InjectionTask {
        val task = InjectionTask(
            id = "task-${System.currentTimeMillis()}",
            apkPath = apkPath,
            appName = appName,
            packageName = packageName,
            status = InjectionTaskStatus.INJECTING,
            progress = 0,
            arch = arch,
            useApktool = useApktool,
            createdAt = System.currentTimeMillis(),
        )
        _tasks.value = listOf(task) + _tasks.value
        return task
    }

    fun updateTask(taskId: String, progress: Int, status: InjectionTaskStatus, outputApk: String? = null) {
        _tasks.value = _tasks.value.map { t ->
            if (t.id == taskId) t.copy(progress = progress, status = status, outputApk = outputApk ?: t.outputApk)
            else t
        }
    }

    fun addLog(level: LogLevel, source: String, message: String) {
        val entry = LogEntry(
            id = "log-${System.currentTimeMillis()}",
            timestamp = System.currentTimeMillis(),
            level = level,
            source = source,
            message = message,
        )
        _logs.value = listOf(entry) + _logs.value.take(99)
    }
}
