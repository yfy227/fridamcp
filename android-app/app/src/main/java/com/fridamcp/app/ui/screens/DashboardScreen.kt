package com.fridamcp.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fridamcp.app.data.model.InjectionStatus
import com.fridamcp.app.ui.components.StatusBadge
import com.fridamcp.app.ui.components.badgeColor
import com.fridamcp.app.ui.theme.Background
import com.fridamcp.app.ui.theme.CardElevated
import com.fridamcp.app.ui.theme.Foreground
import com.fridamcp.app.ui.theme.MutedForeground
import com.fridamcp.app.ui.theme.Primary
import com.fridamcp.app.ui.theme.Success

@Composable
fun DashboardScreen(
    viewModel: SharedViewModel,
) {
    val device by viewModel.deviceInfo.collectAsState()
    val mcpServer by viewModel.serverStatus.collectAsState()
    val apps by viewModel.apps.collectAsState()
    val logs by viewModel.logs.collectAsState()

    val injectedCount = apps.count { it.injectionStatus == InjectionStatus.INJECTED || it.injectionStatus == InjectionStatus.RUNNING }
    val runningCount = apps.count { it.injectionStatus == InjectionStatus.RUNNING }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Spacer(modifier = Modifier.height(48.dp))
            // Header
            Text(
                text = "FridaMCP",
                style = MaterialTheme.typography.displayLarge,
                color = Primary,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "AI 驱动的 Frida 动态分析",
                style = MaterialTheme.typography.bodyMedium,
                color = MutedForeground,
            )
        }

        // Device status card
        item {
            StatusCard(
                icon = Icons.Default.Lock,
                title = "设备状态",
                statusText = device.status.label,
                statusColor = Success,
                rows = listOf(
                    "设备" to device.name,
                    "Android" to "${device.androidVersion} (API ${device.apiLevel})",
                    "架构" to device.arch,
                    "Root" to if (device.isRooted) "已获取" else "未获取",
                    "Frida Server" to if (device.fridaServerRunning) "运行中 (${device.fridaServerVersion})" else "未运行",
                ),
            )
        }

        // MCP server status card
        item {
            StatusCard(
                icon = Icons.Default.Email,
                title = "MCP 服务器",
                statusText = if (mcpServer.running) "运行中" else "已停止",
                statusColor = if (mcpServer.running) Success else MutedForeground,
                rows = listOf(
                    "地址" to "${mcpServer.host}:${mcpServer.port}",
                    "协议" to mcpServer.transport.uppercase(),
                    "会话" to "${mcpServer.activeSessions} 个活跃",
                    "工具" to "${mcpServer.totalTools} 个已注册",
                    "客户端" to "${mcpServer.connectedClients} 个已连接",
                ),
            )
        }

        // Injection overview
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                StatCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Default.List,
                    value = "${apps.size}",
                    label = "总应用数",
                )
                StatCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Default.Lock,
                    value = "$injectedCount",
                    label = "已注入",
                    tint = Primary,
                )
                StatCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Default.Star,
                    value = "$runningCount",
                    label = "运行中",
                    tint = Success,
                )
            }
        }

        // Recent logs
        item {
            Text(
                text = "最近日志",
                style = MaterialTheme.typography.titleLarge,
                color = Foreground,
                modifier = Modifier.padding(top = 8.dp),
            )
        }

        items(logs.take(6)) { log ->
            LogRow(log)
        }

        item {
            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

@Composable
private fun StatusCard(
    icon: ImageVector,
    title: String,
    statusText: String,
    statusColor: androidx.compose.ui.graphics.Color,
    rows: List<Pair<String, String>>,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = CardElevated),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(imageVector = icon, contentDescription = null, tint = Primary, modifier = Modifier.size(20.dp))
                Text(text = title, style = MaterialTheme.typography.titleLarge, color = Foreground, modifier = Modifier.weight(1f))
                StatusBadge(text = statusText, color = statusColor)
            }
            Spacer(modifier = Modifier.height(12.dp))
            rows.forEach { (key, value) ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 3.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(text = key, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
                    Text(text = value, style = MaterialTheme.typography.bodyMedium, color = Foreground)
                }
            }
        }
    }
}

@Composable
private fun StatCard(
    icon: ImageVector,
    value: String,
    label: String,
    modifier: Modifier = Modifier,
    tint: androidx.compose.ui.graphics.Color = Foreground,
) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = CardElevated),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Icon(imageVector = icon, contentDescription = null, tint = tint, modifier = Modifier.size(24.dp))
            Text(text = value, style = MaterialTheme.typography.headlineMedium, color = tint, fontWeight = FontWeight.Bold)
            Text(text = label, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
        }
    }
}

@Composable
private fun LogRow(log: com.fridamcp.app.data.model.LogEntry) {
    val levelColor = when (log.level) {
        com.fridamcp.app.data.model.LogLevel.INFO -> Primary
        com.fridamcp.app.data.model.LogLevel.WARNING -> com.fridamcp.app.ui.theme.Warning
        com.fridamcp.app.data.model.LogLevel.ERROR -> com.fridamcp.app.ui.theme.Error
        com.fridamcp.app.data.model.LogLevel.DEBUG -> MutedForeground
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(CardElevated)
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            modifier = Modifier
                .size(4.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(levelColor)
                .align(Alignment.Top),
        )
        Column(modifier = Modifier.weight(1f)) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(text = log.source, style = MaterialTheme.typography.labelSmall, color = levelColor)
                Text(text = formatTime(log.timestamp), style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            }
            Text(text = log.message, style = MaterialTheme.typography.bodySmall, color = Foreground)
        }
    }
}

private fun formatTime(timestamp: Long): String {
    val diff = (System.currentTimeMillis() - timestamp) / 1000
    return when {
        diff < 60 -> "${diff}s ago"
        diff < 3600 -> "${diff / 60}m ago"
        diff < 86400 -> "${diff / 3600}h ago"
        else -> "${diff / 86400}d ago"
    }
}
