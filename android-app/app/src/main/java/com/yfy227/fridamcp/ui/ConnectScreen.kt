package com.yfy227.fridamcp.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.yfy227.fridamcp.vm.AppViewModel

@Composable
fun ConnectScreen(vm: AppViewModel) {
    var url by remember { mutableStateOf(vm.baseUrl.value) }
    val busy by vm.busy.collectAsState()
    val error by vm.lastError.collectAsState()
    val connected by vm.connected.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("🔧 FridaMCP", style = MaterialTheme.typography.headlineLarge,
             fontWeight = FontWeight.Bold)
        Text("Android Frida 动态分析平台", style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text("服务器地址") },
            placeholder = { Text("http://192.168.1.100:8770") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "Termux 本机部署: http://127.0.0.1:8770",
            style = MaterialTheme.typography.bodySmall
        )
        Spacer(Modifier.height(24.dp))

        Button(
            onClick = { vm.connect(url) {} },
            enabled = !busy && url.isNotBlank(),
            modifier = Modifier.fillMaxWidth()
        ) {
            if (busy) {
                CircularProgressIndicator(
                    modifier = Modifier.height(20.dp),
                    strokeWidth = 2.dp,
                    color = MaterialTheme.colorScheme.onPrimary
                )
                Spacer(Modifier.height(8.dp))
            }
            Text(if (connected) "重新连接" else "连接")
        }

        error?.let {
            Spacer(Modifier.height(16.dp))
            Text("❌ $it", color = MaterialTheme.colorScheme.error,
                 style = MaterialTheme.typography.bodySmall)
        }
    }
}
