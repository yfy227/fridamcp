package com.fridamcp.app.data.repository

import android.content.Context
import com.fridamcp.app.data.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class McpRepository(private val context: Context) {

    private val _serverStatus = MutableStateFlow(mockMCPServer)
    val serverStatus: StateFlow<MCPServerStatus> = _serverStatus.asStateFlow()

    private val _sessions = MutableStateFlow<List<MCPSession>>(emptyList())
    val sessions: StateFlow<List<MCPSession>> = _sessions.asStateFlow()

    private val _modules = MutableStateFlow(mockModules)
    val modules: StateFlow<List<MCPModule>> = _modules.asStateFlow()

    private val _logs = MutableStateFlow(mockLogs)
    val logs: StateFlow<List<LogEntry>> = _logs.asStateFlow()

    private val _tasks = MutableStateFlow(mockInjectionTasks)
    val tasks: StateFlow<List<InjectionTask>> = _tasks.asStateFlow()

    init {
        updateDynamicSessions()
    }

    /** Generate dynamic sessions from running apps with MCP online */
    fun updateDynamicSessions(runningApps: List<AppInfo> = emptyList()) {
        val sessions = runningApps
            .filter { it.injectionStatus == InjectionStatus.RUNNING && it.mcpStatus == MCPServiceStatus.ONLINE }
            .mapIndexed { i, app ->
                MCPSession(
                    id = "sess-${app.id}",
                    pid = app.pid ?: 0,
                    appName = app.appName,
                    packageName = app.packageName,
                    state = "attached",
                    createdAt = app.injectedAt ?: System.currentTimeMillis(),
                    scriptCount = 1 + i,
                    hookCount = (1..8).random(),
                    messageCount = (0..120).random(),
                )
            }
        _sessions.value = sessions
    }

    fun toggleServer() {
        val current = _serverStatus.value
        _serverStatus.value = current.copy(
            running = !current.running,
            startTime = if (!current.running) System.currentTimeMillis() else null,
            activeSessions = if (!current.running) current.activeSessions else 0,
        )
    }

    fun toggleModule(moduleName: String) {
        _modules.value = _modules.value.map { m ->
            if (m.name == moduleName) m.copy(enabled = !m.enabled) else m
        }
    }

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
        _logs.value = listOf(entry) + _logs.value
    }
}
