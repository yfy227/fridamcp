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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.yfy227.fridamcp.vm.AppViewModel
import org.json.JSONArray
import org.json.JSONObject

private data class ProcRow(val pid: Int, val name: String, val extra: String = "")

@Composable
fun ProcessesScreen(vm: AppViewModel) {
    var tab by remember { mutableIntStateOf(0) }
    var search by remember { mutableStateOf("") }
    val processes by vm.processes.collectAsState()
    val applications by vm.applications.collectAsState()
    val busy by vm.busy.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("📱 设备 & 进程", style = MaterialTheme.typography.titleLarge)

        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 },
                text = { Text("进程 (${processes?.length() ?: 0})") })
            Tab(selected = tab == 1, onClick = { tab = 1 },
                text = { Text("应用 (${applications?.length() ?: 0})") })
        }

        OutlinedTextField(
            value = search,
            onValueChange = { search = it },
            label = { Text(if (tab == 0) "搜索进程名/PID" else "搜索包名/应用名") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        if (tab == 0) {
            ProcessList(processes, search, busy) { vm.attachProcess(it) }
        } else {
            AppList(applications, search, busy) { vm.spawnApp(it, true) }
        }
    }
}

@Composable
private fun ProcessList(
    data: JSONArray?,
    search: String,
    busy: Boolean,
    onAttach: (Int) -> Unit
) {
    val rows = remember(data, search) {
        val list = mutableListOf<ProcRow>()
        data?.let { arr ->
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                val name = o.optString("name")
                val pid = o.optInt("pid")
                if (search.isBlank() || name.contains(search, true) ||
                    pid.toString().contains(search)
                ) {
                    list.add(ProcRow(pid, name))
                }
            }
        }
        list
    }

    LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items(rows, key = { it.pid }) { row ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(row.name, style = MaterialTheme.typography.bodyMedium,
                             maxLines = 1)
                        Text("pid ${row.pid}",
                             style = MaterialTheme.typography.bodySmall)
                    }
                    TextButton(onClick = { onAttach(row.pid) }, enabled = !busy) {
                        Text("附加")
                    }
                }
            }
        }
    }
}

@Composable
private fun AppList(
    data: JSONArray?,
    search: String,
    busy: Boolean,
    onSpawn: (String) -> Unit
) {
    val rows = remember(data, search) {
        val list = mutableListOf<ProcRow>()
        data?.let { arr ->
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                val pkg = o.optString("identifier")
                val name = o.optString("name")
                val pid = o.optInt("pid", 0)
                if (search.isBlank() || pkg.contains(search, true) ||
                    name.contains(search, true)
                ) {
                    list.add(ProcRow(pid, name, pkg))
                }
            }
        }
        list
    }

    LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items(rows, key = { it.extra }) { row ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(row.name, style = MaterialTheme.typography.bodyMedium,
                             maxLines = 1)
                        Text(
                            row.extra + if (row.pid > 0) " · 运行中 pid ${row.pid}" else "",
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 1
                        )
                    }
                    TextButton(onClick = { onSpawn(row.extra) }, enabled = !busy) {
                        Text(if (row.pid > 0) "重启" else "启动")
                    }
                }
            }
        }
    }
}
