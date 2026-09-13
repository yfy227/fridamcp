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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.yfy227.fridamcp.vm.AppViewModel
import org.json.JSONArray

@Composable
fun SessionsScreen(vm: AppViewModel) {
    val sessions by vm.sessions.collectAsState()
    val selected by vm.selectedSession.collectAsState()
    val messages by vm.messages.collectAsState()
    val busy by vm.busy.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("🔗 会话 & Hook", style = MaterialTheme.typography.titleLarge)

        if (selected == null) {
            Text("选择一个会话:", style = MaterialTheme.typography.titleSmall)
            LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(sessions?.length() ?: 0) { i ->
                    val s = sessions?.optJSONObject(i) ?: return@items
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surface
                        )
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(s.optString("name"),
                                     style = MaterialTheme.typography.bodyMedium)
                                Text(
                                    "${s.optString("id")} · pid ${s.opt("pid")}",
                                    fontFamily = FontFamily.Monospace,
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                            TextButton(onClick = { vm.selectSession(s.optString("id")) }) {
                                Text("选择")
                            }
                        }
                    }
                }
            }
        } else {
            SessionDetail(vm, selected!!, messages, busy)
        }
    }
}

@Composable
private fun SessionDetail(
    vm: AppViewModel,
    sessionId: String,
    messages: JSONArray?,
    busy: Boolean
) {
    var tab by remember { mutableIntStateOf(0) }
    var className by remember { mutableStateOf("") }
    var methodName by remember { mutableStateOf("") }
    var moduleName by remember { mutableStateOf("") }
    var funcName by remember { mutableStateOf("") }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primary
            )
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("会话 $sessionId", fontFamily = FontFamily.Monospace,
                     style = MaterialTheme.typography.bodySmall)
                Row {
                    TextButton(onClick = { vm.refreshAll() }) { Text("刷新") }
                    TextButton(onClick = { vm.closeSession(sessionId) }) { Text("关闭") }
                }
            }
        }

        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Hook") })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("消息") })
        }

        if (tab == 0) {
            HookPanel(
                className, { className = it },
                methodName, { methodName = it },
                moduleName, { moduleName = it },
                funcName, { funcName = it },
                busy,
                onJava = { vm.hookJava(className, methodName) },
                onNative = { vm.hookNative(moduleName, funcName, 0L) }
            )
        } else {
            MessageList(messages)
        }
    }
}

@Composable
private fun HookPanel(
    className: String, onClass: (String) -> Unit,
    methodName: String, onMethod: (String) -> Unit,
    moduleName: String, onModule: (String) -> Unit,
    funcName: String, onFunc: (String) -> Unit,
    busy: Boolean,
    onJava: () -> Unit,
    onNative: () -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Java Hook", style = MaterialTheme.typography.titleSmall)
        OutlinedTextField(
            value = className, onValueChange = onClass,
            label = { Text("类名 (com.example.App)") },
            singleLine = true, modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = methodName, onValueChange = onMethod,
            label = { Text("方法名") },
            singleLine = true, modifier = Modifier.fillMaxWidth()
        )
        Button(
            onClick = onJava,
            enabled = !busy && className.isNotBlank() && methodName.isNotBlank(),
            modifier = Modifier.fillMaxWidth()
        ) { Text("安装 Java Hook") }
        Spacer(Modifier.height(8.dp))

        Text("Native Hook", style = MaterialTheme.typography.titleSmall)
        OutlinedTextField(
            value = moduleName, onValueChange = onModule,
            label = { Text("模块名 (libnative.so)") },
            singleLine = true, modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = funcName, onValueChange = onFunc,
            label = { Text("函数名（可选，留空用 offset）") },
            singleLine = true, modifier = Modifier.fillMaxWidth()
        )
        Button(
            onClick = onNative,
            enabled = !busy && moduleName.isNotBlank(),
            modifier = Modifier.fillMaxWidth()
        ) { Text("安装 Native Hook") }
    }
}

@Composable
private fun MessageList(messages: JSONArray?) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        items(messages?.length() ?: 0) { i ->
            val m = messages?.optJSONObject(i)?.optJSONObject("message")
                ?: return@items
            val type = m.optString("type", "?")
            val payload = m.optString("data")
                .ifEmpty { m.optString("message") }
                .ifEmpty { m.toString() }
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            ) {
                Column(Modifier.padding(8.dp)) {
                    Text(type, color = MaterialTheme.colorScheme.primary,
                         style = MaterialTheme.typography.labelSmall)
                    Text(
                        payload.take(300),
                        fontFamily = FontFamily.Monospace,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 4
                    )
                }
            }
        }
    }
}
