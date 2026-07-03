package com.fridamcp.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fridamcp.app.ui.theme.Background
import com.fridamcp.app.ui.theme.CardElevated
import com.fridamcp.app.ui.theme.Foreground
import com.fridamcp.app.ui.theme.MutedForeground
import com.fridamcp.app.ui.theme.Primary

@Composable
fun SettingsScreen(
    viewModel: SharedViewModel,
    modifier: Modifier = Modifier,
) {
    val device by viewModel.deviceInfo.collectAsState()
    val logs by viewModel.logs.collectAsState()

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(Background),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Spacer(modifier = Modifier.height(32.dp))
            Text("设置", style = MaterialTheme.typography.headlineLarge, color = Foreground, fontWeight = FontWeight.Bold)
        }

        // Device info
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = CardElevated),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Default.Info, contentDescription = null, tint = Primary, modifier = Modifier.size(20.dp))
                        Text("设备信息", style = MaterialTheme.typography.titleLarge, color = Foreground)
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    SettingRow("设备名称", device.name)
                    SettingRow("Android 版本", "${device.androidVersion} (API ${device.apiLevel})")
                    SettingRow("架构", device.arch)
                    SettingRow("Root 状态", if (device.isRooted) "已获取" else "未获取")
                    SettingRow("Frida Server", if (device.fridaServerRunning) "运行中" else "未运行")
                    device.fridaServerVersion?.let { SettingRow("Frida 版本", it) }
                }
            }
        }

        // Shizuku / Root permission
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = CardElevated),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("权限管理", style = MaterialTheme.typography.titleLarge, color = Foreground)
                    Spacer(modifier = Modifier.height(12.dp))
                    SettingRow("当前模式", viewModel.permissionMode)
                    SettingRow("Shizuku Binder", if (viewModel.shizukuBinderAlive) "已连接" else "未连接")
                    SettingRow("Shizuku 授权", if (viewModel.shizukuAuthorized) "已授权" else "未授权")
                    SettingRow("Root (su 二进制)", if (com.fridamcp.app.data.service.ShizukuManager.isRootAvailable()) "存在" else "不存在")
                    SettingRow("Root (已授权)", if (viewModel.rootAvailable) "是" else "否")
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { viewModel.requestShizuku() },
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Primary),
                        ) { Text("授权 Shizuku", style = MaterialTheme.typography.labelLarge) }
                        Button(
                            onClick = { viewModel.openShizukuSettings() },
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = CardElevated),
                        ) { Text("打开 Shizuku", style = MaterialTheme.typography.labelLarge, color = Primary) }
                        Button(
                            onClick = { viewModel.refreshPermission() },
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = CardElevated),
                        ) { Text("刷新", style = MaterialTheme.typography.labelLarge, color = Primary) }
                    }
                    // 权限请求结果
                    viewModel.permissionRequestResult.value?.let { result ->
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            result,
                            style = MaterialTheme.typography.bodySmall,
                            color = if (result.startsWith("✅")) Primary else if (result.startsWith("❌")) Error else MutedForeground,
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "Shizuku 提供 ADB 级别权限（杀进程、截图、UI 自动化）\nRoot 模式可读写内存、执行任意命令",
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground,
                    )
                }
            }
        }

        // Frida Server 控制
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = CardElevated),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Frida Server", style = MaterialTheme.typography.titleLarge, color = Foreground)
                    Spacer(modifier = Modifier.height(12.dp))
                    SettingRow("运行状态", if (viewModel.fridaServerRunning) "✅ 运行中" else "❌ 未运行")
                    viewModel.fridaVersion?.let { SettingRow("版本", it) }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { viewModel.startFridaServer() },
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Primary),
                            enabled = !viewModel.fridaServerRunning,
                        ) { Text("启动", style = MaterialTheme.typography.labelLarge) }
                        Button(
                            onClick = { viewModel.stopFridaServer() },
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = CardElevated),
                            enabled = viewModel.fridaServerRunning,
                        ) { Text("停止", style = MaterialTheme.typography.labelLarge, color = Primary) }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "frida-server 需要 Root 权限\n请先下载对应架构的 frida-server 到 /data/local/tmp/",
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground,
                    )
                }
            }
        }

        // Scan settings
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = CardElevated),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("扫描配置", style = MaterialTheme.typography.titleLarge, color = Foreground)
                    Spacer(modifier = Modifier.height(12.dp))
                    SettingRow("静态检测", "扫描 APK 中的 libfrida-gadget.so")
                    SettingRow("运行时检测", "检查 /proc/[pid]/maps")
                    SettingRow("进程检测", "搜索 gadget 进程")
                    SettingRow("自动扫描", "安装新应用时自动检测")
                }
            }
        }

        // MCP defaults
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = CardElevated),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("MCP 默认配置", style = MaterialTheme.typography.titleLarge, color = Foreground)
                    Spacer(modifier = Modifier.height(12.dp))
                    SettingRow("监听地址", "127.0.0.1")
                    SettingRow("端口", "8768")
                    SettingRow("协议", "SSE / Streamable HTTP")
                    SettingRow("最大会话数", "10")
                    SettingRow("自动重连", "启用 (5 次重试)")
                }
            }
        }

        // About
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = CardElevated),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("关于", style = MaterialTheme.typography.titleLarge, color = Foreground)
                    Spacer(modifier = Modifier.height(12.dp))
                    SettingRow("版本", "1.0.0")
                    SettingRow("构建", "android-native")
                    SettingRow("Frida 兼容", "16+")
                    SettingRow("MCP 协议", "1.0")
                    SettingRow("许可证", "MIT")
                }
            }
        }

        item { Spacer(modifier = Modifier.height(80.dp)) }
    }
}

@Composable
private fun SettingRow(key: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(key, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = Foreground)
    }
}
