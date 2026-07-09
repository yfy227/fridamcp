package com.fridamcp.app.data.model

import kotlinx.serialization.Serializable

/** Injection status of an app */
enum class InjectionStatus {
    INJECTED, NOT_INJECTED, RUNNING, ERROR;

    val label: String get() = when (this) {
        INJECTED -> "已注入"
        NOT_INJECTED -> "未注入"
        RUNNING -> "运行中"
        ERROR -> "异常"
    }
}

/** MCP service status */
enum class MCPServiceStatus {
    ONLINE, OFFLINE, STARTING, ERROR;

    val label: String get() = when (this) {
        ONLINE -> "在线"
        OFFLINE -> "离线"
        STARTING -> "启动中"
        ERROR -> "异常"
    }
}

/** Device connection status */
enum class DeviceStatus {
    CONNECTED, DISCONNECTED, UNAUTHORIZED, OFFLINE;

    val label: String get() = when (this) {
        CONNECTED -> "已连接"
        DISCONNECTED -> "未连接"
        UNAUTHORIZED -> "未授权"
        OFFLINE -> "离线"
    }
}

/** Detection method */
enum class DetectionMethod {
    STATIC, RUNTIME, PROCESS, NONE;

    val label: String get() = when (this) {
        STATIC -> "静态检测"
        RUNTIME -> "运行时检测"
        PROCESS -> "进程检测"
        NONE -> "未检测"
    }
}

/** App info - represents an installed Android application */
@Serializable
data class AppInfo(
    val id: String,
    val packageName: String,
    val appName: String,
    val version: String,
    val versionCode: Long,
    val iconColor: Long,
    val iconText: String,
    val isSystem: Boolean,
    val installTime: Long,
    val updateTime: Long,
    val injectionStatus: InjectionStatus = InjectionStatus.NOT_INJECTED,
    val gadgetVersion: String? = null,
    val gadgetArch: String? = null,
    val injectedAt: Long? = null,
    val pid: Int? = null,
    val mcpPort: Int? = null,
    val mcpStatus: MCPServiceStatus? = null,
    val lastScanTime: Long? = null,
    val detectionMethod: DetectionMethod = DetectionMethod.NONE,
)

/** Frida device info */
@Serializable
data class DeviceInfo(
    val id: String,
    val name: String,
    val type: String, // "local", "remote", "usb"
    val status: DeviceStatus,
    val androidVersion: String,
    val apiLevel: Int,
    val arch: String,
    val isRooted: Boolean,
    val fridaServerVersion: String? = null,
    val fridaServerRunning: Boolean = false,
)

/** MCP server status */
@Serializable
data class MCPServerStatus(
    val running: Boolean,
    val host: String,
    val port: Int,
    val transport: String, // "stdio", "sse", "http"
    val startTime: Long? = null,
    val activeSessions: Int,
    val totalTools: Int,
    val connectedClients: Int,
)

/** MCP session info */
@Serializable
data class MCPSession(
    val id: String,
    val pid: Int,
    val appName: String,
    val packageName: String,
    val state: String, // "created", "attached", "detached", "error"
    val createdAt: Long,
    val scriptCount: Int,
    val hookCount: Int,
    val messageCount: Int,
)

/** Injection task */
@Serializable
data class InjectionTask(
    val id: String,
    val apkPath: String,
    val appName: String,
    val packageName: String,
    val status: InjectionTaskStatus,
    val progress: Int,
    val arch: String,
    val outputApk: String? = null,
    val error: String? = null,
    val createdAt: Long,
)

enum class InjectionTaskStatus {
    PENDING, INJECTING, SIGNING, DONE, ERROR;

    val label: String get() = when (this) {
        PENDING -> "等待中"
        INJECTING -> "注入中"
        SIGNING -> "签名中"
        DONE -> "已完成"
        ERROR -> "失败"
    }
}

/** MCP module info */
@Serializable
data class MCPModule(
    val name: String,
    val displayName: String,
    val description: String,
    val toolCount: Int,
    val iconName: String,
    val enabled: Boolean,
)

/** Log entry */
@Serializable
data class LogEntry(
    val id: String,
    val timestamp: Long,
    val level: LogLevel,
    val source: String,
    val message: String,
)

enum class LogLevel {
    INFO, WARNING, ERROR, DEBUG;

    val label: String get() = when (this) {
        INFO -> "INFO"
        WARNING -> "WARN"
        ERROR -> "ERROR"
        DEBUG -> "DEBUG"
    }
}

/** Scan result */
@Serializable
data class ScanResult(
    val appId: String,
    val packageName: String,
    val detected: Boolean,
    val method: DetectionMethod,
    val details: String,
    val timestamp: Long,
)

/** Navigation tabs */
enum class TabId(val route: String) {
    DASHBOARD("dashboard"),
    APPS("apps"),
    INJECT("inject"),
    MCP("mcp"),
    SETTINGS("settings");
}
