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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
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
import com.fridamcp.app.data.model.MCPModule
import com.fridamcp.app.ui.theme.Background
import com.fridamcp.app.ui.theme.CardElevated
import com.fridamcp.app.ui.theme.Foreground
import com.fridamcp.app.ui.theme.MutedForeground
import com.fridamcp.app.ui.theme.Primary
import com.fridamcp.app.ui.theme.Success

@Composable
fun McpScreen(
    viewModel: SharedViewModel,
    modifier: Modifier = Modifier,
) {
    val serverStatus by viewModel.serverStatus.collectAsState()
    val sessions by viewModel.sessions.collectAsState()
    val modules by viewModel.modules.collectAsState()

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(Background),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Spacer(modifier = Modifier.height(32.dp))
            Text("MCP 服务器", style = MaterialTheme.typography.headlineLarge, color = Foreground, fontWeight = FontWeight.Bold)
        }

        // Server control card
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = CardElevated),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Icon(Icons.Default.Email, contentDescription = null, tint = if (serverStatus.running) Success else MutedForeground, modifier = Modifier.size(20.dp))
                            Text("MCP 服务器", style = MaterialTheme.typography.titleLarge, color = Foreground)
                        }
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(6.dp))
                                .background(if (serverStatus.running) Success.copy(alpha = 0.15f) else MutedForeground.copy(alpha = 0.15f))
                                .padding(horizontal = 8.dp, vertical = 2.dp),
                        ) {
                            Text(
                                if (serverStatus.running) "运行中" else "已停止",
                                style = MaterialTheme.typography.labelSmall,
                                color = if (serverStatus.running) Success else MutedForeground,
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    InfoRow("地址", "${serverStatus.host}:${serverStatus.port}")
                    InfoRow("协议", serverStatus.transport.uppercase())
                    InfoRow("活跃会话", "${serverStatus.activeSessions}")
                    InfoRow("已注册工具", "${serverStatus.totalTools}")
                    InfoRow("已连接客户端", "${serverStatus.connectedClients}")
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = { viewModel.toggleMCPServer() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(44.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (serverStatus.running) com.fridamcp.app.ui.theme.Error else Primary,
                        ),
                    ) {
                        Icon(
                            if (serverStatus.running) Icons.Default.Stop else Icons.Default.PlayArrow,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(modifier = Modifier.size(8.dp))
                        Text(if (serverStatus.running) "停止服务器" else "启动服务器")
                    }
                }
            }
        }

        // Sessions
        item {
            Text("活跃会话", style = MaterialTheme.typography.titleLarge, color = Foreground, modifier = Modifier.padding(top = 8.dp))
        }

        if (sessions.isEmpty()) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = CardElevated),
                ) {
                    Text(
                        "暂无活跃会话",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MutedForeground,
                        modifier = Modifier.padding(16.dp),
                    )
                }
            }
        } else {
            items(sessions) { session ->
                SessionCard(session)
            }
        }

        // Modules
        item {
            Text("MCP 模块", style = MaterialTheme.typography.titleLarge, color = Foreground, modifier = Modifier.padding(top = 8.dp))
        }

        items(modules) { module ->
            ModuleCard(
                module = module,
                onToggle = { viewModel.toggleModule(module.name) },
            )
        }

        item { Spacer(modifier = Modifier.height(80.dp)) }
    }
}

@Composable
private fun InfoRow(key: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(key, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = Foreground)
    }
}

@Composable
private fun SessionCard(session: com.fridamcp.app.data.model.MCPSession) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = CardElevated),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(session.appName, style = MaterialTheme.typography.titleMedium, color = Foreground)
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(Success),
                )
            }
            Text(session.packageName, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            Spacer(modifier = Modifier.height(4.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("PID: ${session.pid}", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                Text("消息: ${session.messageCount}", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
        }
    }
}

@Composable
private fun ModuleCard(module: MCPModule, onToggle: () -> Unit) {
    val icon = when (module.name) {
        "process" -> Icons.Default.Home
        "hook" -> Icons.Default.Build
        "memory" -> Icons.Default.Info
        "network" -> Icons.Default.Email
        "filesystem" -> Icons.Default.List
        "ui_automation" -> Icons.Default.Search
        "crypto" -> Icons.Default.Lock
        "log" -> Icons.Default.Refresh
        else -> Icons.Default.Star
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = CardElevated),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(Primary.copy(alpha = 0.1f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(icon, contentDescription = null, tint = Primary, modifier = Modifier.size(20.dp))
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(module.displayName, style = MaterialTheme.typography.titleMedium, color = Foreground)
                Text(module.description, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                Text("${module.toolCount} 个工具", style = MaterialTheme.typography.labelSmall, color = Primary)
            }
            Switch(
                checked = module.enabled,
                onCheckedChange = { onToggle() },
            )
        }
    }
}
