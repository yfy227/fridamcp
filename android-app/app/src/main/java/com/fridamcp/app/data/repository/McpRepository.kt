package com.fridamcp.app.data.repository

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import com.fridamcp.app.data.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class McpRepository(private val context: Context) {

    companion object {
        const val ACTION_SERVER_STATUS = "com.fridamcp.app.SERVER_STATUS"
        const val EXTRA_RUNNING = "running"
        const val EXTRA_SESSIONS = "sessions"
        const val EXTRA_TOOLS = "tools"
        const val EXTRA_CLIENTS = "clients"
    }

    private val _serverStatus = MutableStateFlow(
        MCPServerStatus(
            running = false,
            host = "127.0.0.1",
            port = 8768,
            transport = "sse",
            startTime = 0,
            activeSessions = 0,
            totalTools = 0, // 从服务实际获取
            connectedClients = 0,
        )
    )
    val serverStatus: StateFlow<MCPServerStatus> = _serverStatus.asStateFlow()

    private val _sessions = MutableStateFlow<List<MCPSession>>(emptyList())
    val sessions: StateFlow<List<MCPSession>> = _sessions.asStateFlow()

    /**
     * 真实模块定义 — 与 McpServerService.getToolsList() 一一对应
     * toolCount 从实际代码中统计，不是虚构数字
     */
    private val _modules = MutableStateFlow(
        listOf(
            MCPModule("system", "系统管理", "设备信息、系统状态、ping", 3, "Info", true),
            MCPModule("process", "进程管理", "进程列表、应用启动/杀死、注入检测", 5, "Apps", true),
            MCPModule("filesystem", "文件系统", "文件列表、读取、应用信息", 3, "File", true),
            MCPModule("ui_automation", "UI 自动化", "点击、滑动、输入、按键、截图", 5, "UI", true),
            MCPModule("log", "日志捕获", "logcat 获取/清除", 2, "Log", true),
            MCPModule("memory", "内存检查", "模块列表、内存读取", 2, "Memory", true),
            MCPModule("injection", "APK 注入", "frida-gadget APK 注入", 1, "Inject", true),
            MCPModule("session", "会话管理", "MCP 会话列表/关闭", 2, "Session", true),
            MCPModule("shell", "Shell 执行", "通过 Shizuku/Root 执行命令", 1, "Terminal", true),
            MCPModule("frida", "Frida 脚本", "在目标进程执行 JS", 1, "Code", true),
        )
    )
    val modules: StateFlow<List<MCPModule>> = _modules.asStateFlow()

    private val _logs = MutableStateFlow<List<LogEntry>>(emptyList())
    val logs: StateFlow<List<LogEntry>> = _logs.asStateFlow()

    private val _tasks = MutableStateFlow<List<InjectionTask>>(emptyList())
    val tasks: StateFlow<List<InjectionTask>> = _tasks.asStateFlow()

    init {
        val prefs = context.getSharedPreferences("fridamcp_modules", Context.MODE_PRIVATE)
        _modules.value = _modules.value.map { module ->
            module.copy(enabled = prefs.getBoolean(module.name, module.enabled))
        }
    }

/**
     * 启动 MCP 服务器 — 先启动服务，由服务回调确认状态
     * 不在这里假设成功
     */
    fun startServer() {
        addLog(LogLevel.INFO, "McpServer", "正在启动 MCP 服务器...")

        try {
            val intent = Intent(context, com.fridamcp.app.data.service.McpServerService::class.java)
            intent.action = com.fridamcp.app.data.service.McpServerService.ACTION_START
            context.startForegroundService(intent)
            // 状态由 McpServerService 通过 broadcast 更新
        } catch (e: Exception) {
            addLog(LogLevel.ERROR, "McpServer", "启动 MCP 服务失败: ${e.message}")
            _serverStatus.value = _serverStatus.value.copy(running = false)
        }
    }

    /** 停止 MCP 服务器 */
    fun stopServer() {
        addLog(LogLevel.INFO, "McpServer", "正在停止 MCP 服务器...")

        try {
            val intent = Intent(context, com.fridamcp.app.data.service.McpServerService::class.java)
            intent.action = com.fridamcp.app.data.service.McpServerService.ACTION_STOP
            context.startForegroundService(intent)
        } catch (e: Exception) {
            addLog(LogLevel.ERROR, "McpServer", "停止 MCP 服务失败: ${e.message}")
        }

        // 立即更新 UI — 服务即将停止
        _serverStatus.value = _serverStatus.value.copy(
            running = false,
            activeSessions = 0,
            connectedClients = 0,
        )
        _sessions.value = emptyList()
    }

    /**
     * 由 McpServerService 调用 — 更新真实状态
     */
    fun onServerStatusUpdate(running: Boolean, sessions: Int, tools: Int, clients: Int) {
        _serverStatus.value = _serverStatus.value.copy(
            running = running,
            activeSessions = sessions,
            totalTools = tools,
            connectedClients = clients,
            startTime = if (running && _serverStatus.value.startTime == 0L) System.currentTimeMillis() else if (!running) 0L else _serverStatus.value.startTime,
        )
    }

    /** 切换模块 — 写入 SharedPreferences + 广播通知服务刷新 */
    fun toggleModule(name: String) {
        _modules.value = _modules.value.map { m ->
            if (m.name == name) m.copy(enabled = !m.enabled) else m
        }
        val enabled = _modules.value.find { it.name == name }?.enabled ?: true
        // 持久化到 SharedPreferences — McpServerService 读取此配置
        val prefs = context.getSharedPreferences("fridamcp_modules", Context.MODE_PRIVATE)
        prefs.edit().putBoolean(name, enabled).apply()
        // 广播通知服务立即刷新
        val intent = Intent("com.fridamcp.app.MODULE_TOGGLED")
        intent.setPackage(context.packageName)
        context.sendBroadcast(intent)
        addLog(LogLevel.INFO, "Module", "模块 $name 已 ${if (enabled) "启用" else "禁用"}")
    }

    /**
     * 添加真实会话 — 由 McpServerService 调用
     * 不再由 UI 层假创建
     */
    fun onSessionAdded(sessionId: String, clientAddr: String) {
        val session = MCPSession(
            id = sessionId,
            clientAddr = clientAddr,
            state = "connected",
            createdAt = System.currentTimeMillis(),
        )
        _sessions.value = _sessions.value + session
        _serverStatus.value = _serverStatus.value.copy(
            activeSessions = _sessions.value.size,
        )
        addLog(LogLevel.INFO, "McpServer", "客户端已连接: $clientAddr (会话: $sessionId)")
    }

    fun onSessionRemoved(sessionId: String) {
        _sessions.value = _sessions.value.filter { it.id != sessionId }
        _serverStatus.value = _serverStatus.value.copy(
            activeSessions = _sessions.value.size,
        )
        addLog(LogLevel.INFO, "McpServer", "会话已断开: $sessionId")
    }

    /** 创建注入任务 */
    fun createInjectionTask(
        apkPath: String,
        appName: String,
        packageName: String,
        arch: String,
    ): InjectionTask {
        val task = InjectionTask(
            id = "task-${System.currentTimeMillis()}",
            apkPath = apkPath,
            appName = appName,
            packageName = packageName,
            status = InjectionTaskStatus.PENDING,
            progress = 0,
            arch = arch,
            createdAt = System.currentTimeMillis(),
        )
        _tasks.value = listOf(task) + _tasks.value
        return task
    }

    fun updateTask(taskId: String, progress: Int, status: InjectionTaskStatus, outputApk: String? = null, error: String? = null) {
        _tasks.value = _tasks.value.map { t ->
            if (t.id == taskId) t.copy(
                progress = progress,
                status = status,
                outputApk = outputApk ?: t.outputApk,
                error = error ?: t.error,
            )
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
