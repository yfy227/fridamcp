package com.fridamcp.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fridamcp.app.data.model.AppInfo
import com.fridamcp.app.data.model.InjectionStatus
import com.fridamcp.app.data.model.MCPServiceStatus
import com.fridamcp.app.ui.components.AppIcon
import com.fridamcp.app.ui.components.StatusBadge
import com.fridamcp.app.ui.components.badgeColor
import com.fridamcp.app.ui.theme.Background
import com.fridamcp.app.ui.theme.CardElevated
import com.fridamcp.app.ui.theme.Foreground
import com.fridamcp.app.ui.theme.MutedForeground
import com.fridamcp.app.ui.theme.Primary

@Composable
fun AppsScreen(
    viewModel: SharedViewModel,
    modifier: Modifier = Modifier,
) {
    val apps by viewModel.apps.collectAsState()
    val scanning by viewModel.scanning.collectAsState()

    var searchQuery by remember { mutableStateOf("") }
    var filterInjected by remember { mutableStateOf(false) }
    var selectedApp by remember { mutableStateOf<AppInfo?>(null) }

    val filteredApps = apps.filter { app ->
        val matchesSearch = searchQuery.isBlank() ||
            app.appName.contains(searchQuery, ignoreCase = true) ||
            app.packageName.contains(searchQuery, ignoreCase = true)
        val matchesFilter = !filterInjected ||
            app.injectionStatus == InjectionStatus.INJECTED ||
            app.injectionStatus == InjectionStatus.RUNNING
        matchesSearch && matchesFilter
    }

    val injectedCount = apps.count { it.injectionStatus == InjectionStatus.INJECTED || it.injectionStatus == InjectionStatus.RUNNING }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Background),
    ) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text("应用列表", style = MaterialTheme.typography.headlineLarge, color = Foreground, fontWeight = FontWeight.Bold)
                Text("$injectedCount 个已注入 / ${apps.size} 个应用", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
            IconButton(onClick = { viewModel.scanAllApps() }) {
                Icon(
                    imageVector = Icons.Default.Refresh,
                    contentDescription = "扫描",
                    tint = Primary,
                    modifier = Modifier.size(24.dp),
                )
            }
        }

        // Search bar
        OutlinedTextField(
            value = searchQuery,
            onValueChange = { searchQuery = it },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            placeholder = { Text("搜索应用名称或包名") },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = MutedForeground) },
            trailingIcon = {
                if (searchQuery.isNotEmpty()) {
                    IconButton(onClick = { searchQuery = "" }) {
                        Icon(Icons.Default.Close, contentDescription = "清除", tint = MutedForeground)
                    }
                }
            },
            shape = RoundedCornerShape(12.dp),
            singleLine = true,
        )

        // Filter chip
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
        ) {
            FilterChip(
                label = "仅显示已注入",
                selected = filterInjected,
                onClick = { filterInjected = !filterInjected },
            )
        }

        // App list
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(filteredApps) { app ->
                AppListItem(
                    app = app,
                    onClick = { selectedApp = app },
                )
            }
            item { Spacer(modifier = Modifier.height(80.dp)) }
        }
    }

    // App detail dialog
    selectedApp?.let { app ->
        AppDetailDialog(
            app = app,
            onDismiss = { selectedApp = null },
            onLaunch = {
                viewModel.launchApp(app.packageName)
                selectedApp = null
            },
            onToggleMCP = {
                viewModel.toggleAppMCP(app)
                selectedApp = null
            },
            onRescan = {
                viewModel.scanApp(app.packageName)
                selectedApp = null
            },
            onRemoveInjection = {
                viewModel.removeInjection(app)
                selectedApp = null
            },
        )
    }
}

@Composable
private fun AppListItem(
    app: AppInfo,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
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
            AppIcon(text = app.iconText, color = app.iconColor, size = 44)

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = app.appName,
                    style = MaterialTheme.typography.titleMedium,
                    color = Foreground,
                )
                Text(
                    text = app.packageName,
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground,
                )
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.padding(top = 4.dp),
                ) {
                    StatusBadge(text = app.injectionStatus.label, color = app.injectionStatus.badgeColor())
                    app.mcpStatus?.let {
                        StatusBadge(text = it.label, color = it.badgeColor())
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val bg = if (selected) Primary.copy(alpha = 0.15f) else CardElevated
    val fg = if (selected) Primary else MutedForeground
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(bg)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        Text(text = label, style = MaterialTheme.typography.labelLarge, color = fg)
    }
}

@Composable
private fun AppDetailDialog(
    app: AppInfo,
    onDismiss: () -> Unit,
    onLaunch: () -> Unit,
    onToggleMCP: () -> Unit,
    onRescan: () -> Unit,
    onRemoveInjection: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                AppIcon(text = app.iconText, color = app.iconColor, size = 40)
                Column {
                    Text(app.appName, style = MaterialTheme.typography.titleLarge, color = Foreground)
                    Text(app.packageName, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                }
            }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                DetailRow("版本", "${app.version} (${app.versionCode})")
                DetailRow("注入状态", app.injectionStatus.label)
                app.gadgetVersion?.let { DetailRow("Gadget 版本", it) }
                app.gadgetArch?.let { DetailRow("Gadget 架构", it) }
                app.injectedAt?.let { DetailRow("注入时间", java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.getDefault()).format(java.util.Date(it))) }
                app.pid?.let { DetailRow("PID", it.toString()) }
                app.mcpStatus?.let { DetailRow("MCP 状态", it.label) }
                DetailRow("检测方式", app.detectionMethod.label)
            }
        },
        confirmButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onRescan) { Text("重新检测", color = Primary) }
                if (app.injectionStatus == InjectionStatus.INJECTED || app.injectionStatus == InjectionStatus.RUNNING) {
                    TextButton(onClick = onLaunch) { Text("启动", color = Primary) }
                    TextButton(onClick = onToggleMCP) {
                        Text(
                            if (app.mcpStatus == MCPServiceStatus.ONLINE) "停止 MCP" else "启动 MCP",
                            color = Primary,
                        )
                    }
                    TextButton(onClick = onRemoveInjection) { Text("移除注入", color = com.fridamcp.app.ui.theme.Error) }
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("关闭", color = MutedForeground) }
        },
    )
}

@Composable
private fun DetailRow(key: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(key, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = Foreground)
    }
}
