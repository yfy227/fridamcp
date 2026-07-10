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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Build
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.activity.compose.rememberLauncherForActivityResult
import com.fridamcp.app.data.model.InjectionTaskStatus
import com.fridamcp.app.ui.theme.Background
import com.fridamcp.app.ui.theme.CardElevated
import com.fridamcp.app.ui.theme.Error
import com.fridamcp.app.ui.theme.Foreground
import com.fridamcp.app.ui.theme.MutedForeground
import com.fridamcp.app.ui.theme.Primary
import com.fridamcp.app.ui.theme.Success

@Composable
fun InjectScreen(
    viewModel: SharedViewModel,
    modifier: Modifier = Modifier,
) {
    val tasks by viewModel.tasks.collectAsState()

    var apkPath by remember { mutableStateOf("") }
    var appName by remember { mutableStateOf("") }
    var packageName by remember { mutableStateOf("") }
    var arch by remember { mutableStateOf("arm64-v8a") }

    // File picker launcher
    val ctx = LocalContext.current
    val pickApk = rememberLauncherForActivityResult(
        contract = androidx.activity.result.contract.ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            try {
                val input = ctx.contentResolver.openInputStream(uri)
                if (input != null) {
                    val tempFile = java.io.File(ctx.cacheDir, "temp_${System.currentTimeMillis()}.apk")
                    java.io.FileOutputStream(tempFile).use { out -> input.copyTo(out) }
                    input.close()
                    apkPath = tempFile.absolutePath
                    try {
                        val pm = ctx.packageManager
                        val info = pm.getPackageArchiveInfo(tempFile.absolutePath, 0)
                        if (info != null) {
                            info.applicationInfo.sourceDir = tempFile.absolutePath
                            info.applicationInfo.publicSourceDir = tempFile.absolutePath
                            if (appName.isBlank()) appName = pm.getApplicationLabel(info.applicationInfo).toString()
                            if (packageName.isBlank()) packageName = info.packageName
                        }
                    } catch (e: Exception) { }
                }
            } catch (e: Exception) { }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Background),
    ) {
        // Header
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
        ) {
            Text("APK 注入", style = MaterialTheme.typography.headlineLarge, color = Foreground, fontWeight = FontWeight.Bold)
            Text("将 frida-gadget 注入到 APK 中，无需 root 即可使用 Frida", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Input form
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = CardElevated),
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Text("注入配置", style = MaterialTheme.typography.titleLarge, color = Foreground)

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.Bottom,
                        ) {
                            OutlinedTextField(
                                value = apkPath,
                                onValueChange = { apkPath = it },
                                label = { Text("APK 文件路径") },
                                modifier = Modifier.weight(1f),
                                singleLine = true,
                                shape = RoundedCornerShape(12.dp),
                            )
                            Button(
                                onClick = { pickApk.launch(arrayOf("application/vnd.android.package-archive")) },
                                shape = RoundedCornerShape(12.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = CardElevated),
                            ) {
                                Text("选择", color = Primary, style = MaterialTheme.typography.labelLarge)
                            }
                        }

                        OutlinedTextField(
                            value = appName,
                            onValueChange = { appName = it },
                            label = { Text("应用名称") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            shape = RoundedCornerShape(12.dp),
                        )

                        OutlinedTextField(
                            value = packageName,
                            onValueChange = { packageName = it },
                            label = { Text("包名") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            shape = RoundedCornerShape(12.dp),
                        )

                        // Arch selector
                        Text("目标架构", style = MaterialTheme.typography.labelLarge, color = MutedForeground)
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            listOf("arm64-v8a", "armeabi-v7a", "x86_64").forEach { a ->
                                ArchChip(
                                    label = a,
                                    selected = arch == a,
                                    onClick = { arch = a },
                                )
                            }
                        }

                        // Injection method info
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column {
                                Text("注入模式", style = MaterialTheme.typography.bodyMedium, color = Foreground)
                                Text("ZIP 注入 + 自动签名；Android 端不做 smali patch，需应用显式加载 Gadget 或使用 spawn 模式", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                            }
                        }

                        Button(
                            onClick = {
                                if (apkPath.isNotBlank() && appName.isNotBlank() && packageName.isNotBlank()) {
                                    viewModel.startInjection(apkPath, appName, packageName, arch)
                                }
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(48.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Primary),
                        ) {
                            Icon(Icons.Default.Build, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.size(8.dp))
                            Text("开始注入", style = MaterialTheme.typography.labelLarge)
                        }
                    }
                }
            }

            // Task history
            item {
                Text("注入历史", style = MaterialTheme.typography.titleLarge, color = Foreground, modifier = Modifier.padding(top = 8.dp))
            }

            items(tasks) { task ->
                TaskCard(task)
            }

            item { Spacer(modifier = Modifier.height(80.dp)) }
        }
    }
}

@Composable
private fun ArchChip(label: String, selected: Boolean, onClick: () -> Unit) {
    val bg = if (selected) Primary.copy(alpha = 0.15f) else CardElevated
    val fg = if (selected) Primary else MutedForeground
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(bg)
            .clickable { onClick() }
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = fg)
    }
}

@Composable
private fun TaskCard(task: com.fridamcp.app.data.model.InjectionTask) {
    val statusColor = when (task.status) {
        InjectionTaskStatus.DONE -> Success
        InjectionTaskStatus.ERROR -> Error
        InjectionTaskStatus.ANALYZING, InjectionTaskStatus.INJECTING, InjectionTaskStatus.SIGNING, InjectionTaskStatus.INSTALLING -> Primary
        InjectionTaskStatus.PENDING -> MutedForeground
    }
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
                Text(task.appName, style = MaterialTheme.typography.titleMedium, color = Foreground)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (task.status == InjectionTaskStatus.DONE) {
                        Icon(Icons.Default.CheckCircle, contentDescription = null, tint = statusColor, modifier = Modifier.size(16.dp))
                    }
                    Text(task.status.label, style = MaterialTheme.typography.labelSmall, color = statusColor)
                }
            }
            Text(task.packageName, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            Spacer(modifier = Modifier.height(6.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("架构: ${task.arch}", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
            // Progress bar
            if (task.status != InjectionTaskStatus.DONE && task.status != InjectionTaskStatus.ERROR) {
                Spacer(modifier = Modifier.height(8.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(4.dp)
                        .clip(RoundedCornerShape(2.dp))
                        .background(MutedForeground.copy(alpha = 0.2f)),
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(task.progress / 100f)
                            .height(4.dp)
                            .clip(RoundedCornerShape(2.dp))
                            .background(statusColor),
                    )
                }
            }
            task.outputApk?.let {
                Spacer(modifier = Modifier.height(4.dp))
                Text("输出: $it", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
            task.error?.let {
                Spacer(modifier = Modifier.height(4.dp))
                Text("错误: $it", style = MaterialTheme.typography.bodySmall, color = Error)
            }
        }
    }
}
