package com.yfy227.fridamcp.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.yfy227.fridamcp.vm.AppViewModel
import org.json.JSONObject

@Composable
fun DashboardScreen(vm: AppViewModel) {
    val status by vm.statusJson.collectAsState()
    val sessions by vm.sessions.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("📊 仪表盘", style = MaterialTheme.typography.titleLarge)

        status?.let { StatusCard(it) } ?: Text("加载中…")

        sessions?.let {
            Text("活跃会话: ${it.length()}", style = MaterialTheme.typography.titleMedium)
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(it.length()) { i ->
                    val s = it.optJSONObject(i) ?: return@items
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surface
                        )
                    ) {
                        Column(Modifier.padding(12.dp)) {
                            Text(
                                s.optString("id"),
                                fontFamily = FontFamily.Monospace,
                                style = MaterialTheme.typography.bodySmall
                            )
                            Text(
                                "pid=${s.opt("pid")} ${s.optString("name")} " +
                                    "[${s.optString("state")}]",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusCard(s: JSONObject) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val device = s.optJSONObject("device") ?: JSONObject()
            val dev = device.optJSONObject("device") ?: device
            KeyValue("MCP 服务器", s.optString("mcp"))
            KeyValue("设备", "${dev.opt("name", "未连接")} (${dev.opt("type", "-")})")
            KeyValue("设备状态", if (device.optBoolean("connected", false)) "已连接" else "断开")
            KeyValue("会话", "${s.optJSONObject("sessions")?.opt("total_sessions") ?: 0}")
        }
    }
}

@Composable
private fun KeyValue(k: String, v: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(k, style = MaterialTheme.typography.bodyMedium)
        Text(v, style = MaterialTheme.typography.bodyMedium)
    }
}
