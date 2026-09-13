package com.yfy227.fridamcp.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yfy227.fridamcp.api.RestClient
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/**
 * 全局状态中心：服务器连接、仪表盘、进程、会话与 Hook 消息。
 */
class AppViewModel(restClient: RestClient = RestClient("http://127.0.0.1:8770")) : ViewModel() {

    // 构造注入（默认真实客户端）——单元测试可传入 mock
    val rest: RestClient = restClient

    // ---------- 连接状态 ----------
    val connected = MutableStateFlow(false)
    val baseUrl = MutableStateFlow(rest.getBaseUrl())
    val lastError = MutableStateFlow<String?>(null)
    val busy = MutableStateFlow(false)

    // ---------- 仪表盘 ----------
    val statusJson = MutableStateFlow<JSONObject?>(null)
    private var pollJob: Job? = null

    // ---------- 进程 / 应用 ----------
    val processes = MutableStateFlow<JSONArray?>(null)
    val applications = MutableStateFlow<JSONArray?>(null)

    // ---------- 会话 / 消息 ----------
    val sessions = MutableStateFlow<JSONArray?>(null)
    val selectedSession = MutableStateFlow<String?>(null)
    val messages = MutableStateFlow<JSONArray?>(null)
    private var messageJob: Job? = null

    val toast = MutableStateFlow<String?>(null)

    // ---------- 连接 ----------

    fun setBaseUrl(url: String) {
        baseUrl.value = url
        rest.setBaseUrl(url)
    }

    fun connect(url: String, onDone: (Boolean) -> Unit) {
        setBaseUrl(url)
        busy.value = true
        viewModelScope.launch {
            try {
                rest.getStatus()
                connected.value = true
                lastError.value = null
                startPolling()
                refreshAll()
                onDone(true)
            } catch (e: Exception) {
                connected.value = false
                lastError.value = e.message
                onDone(false)
            } finally {
                busy.value = false
            }
        }
    }

    // ---------- 数据加载 ----------

    fun refreshAll() {
        viewModelScope.launch { safe { statusJson.value = rest.getStatus() } }
        viewModelScope.launch { safe { processes.value = rest.getProcesses() } }
        viewModelScope.launch { safe { applications.value = rest.getApplications() } }
        viewModelScope.launch { safe { sessions.value = rest.getSessions() } }
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            while (true) {
                delay(5000)
                safe { statusJson.value = rest.getStatus() }
                safe { sessions.value = rest.getSessions() }
            }
        }
    }

    fun selectSession(id: String?) {
        selectedSession.value = id
        messages.value = null
        messageJob?.cancel()
        if (id != null) {
            messageJob = viewModelScope.launch {
                while (true) {
                    delay(2000)
                    safe { messages.value = rest.getMessages(id) }
                }
            }
        }
    }

    // ---------- 操作 ----------

    fun spawnApp(pkg: String, paused: Boolean) {
        busy.value = true
        viewModelScope.launch {
            try {
                val r = rest.spawn(pkg, paused)
                toast.value = "✅ Spawn: pid=${r.opt("pid")} session=${r.opt("session_id")}"
                refreshAll()
            } catch (e: Exception) {
                toast.value = "❌ ${e.message}"
            } finally {
                busy.value = false
            }
        }
    }

    fun attachProcess(pid: Int) {
        busy.value = true
        viewModelScope.launch {
            try {
                val r = rest.attach(pid)
                toast.value = "✅ Attach: ${r.opt("name")} (pid=$pid)"
                refreshAll()
            } catch (e: Exception) {
                toast.value = "❌ ${e.message}"
            } finally {
                busy.value = false
            }
        }
    }

    fun killProcess(pid: Int) {
        viewModelScope.launch {
            try {
                rest.kill(pid)
                toast.value = "☠️ Killed pid=$pid"
                refreshAll()
            } catch (e: Exception) {
                toast.value = "❌ ${e.message}"
            }
        }
    }

    fun hookJava(className: String, methodName: String) {
        val sid = selectedSession.value ?: return
        busy.value = true
        viewModelScope.launch {
            try {
                val r = rest.hookJava(sid, className, methodName)
                toast.value = if (r.has("error")) "❌ ${r.opt("error")}"
                else "✅ Hook ${r.opt("hook_id")}"
            } catch (e: Exception) {
                toast.value = "❌ ${e.message}"
            } finally {
                busy.value = false
            }
        }
    }

    fun hookNative(module: String, func: String?, offset: Long) {
        val sid = selectedSession.value ?: return
        busy.value = true
        viewModelScope.launch {
            try {
                val r = rest.hookNative(sid, module, func, offset)
                toast.value = if (r.has("error")) "❌ ${r.opt("error")}"
                else "✅ Native Hook ${r.opt("hook_id")}"
            } catch (e: Exception) {
                toast.value = "❌ ${e.message}"
            } finally {
                busy.value = false
            }
        }
    }

    fun closeSession(sessionId: String) {
        viewModelScope.launch {
            try {
                rest.closeSession(sessionId)
                toast.value = "✅ Session closed"
                if (selectedSession.value == sessionId) selectSession(null)
                refreshAll()
            } catch (e: Exception) {
                toast.value = "❌ ${e.message}"
            }
        }
    }

    fun consumeToast() {
        toast.value = null
    }

    private inline fun safe(block: () -> Unit) {
        try {
            block()
        } catch (e: Exception) {
            lastError.value = e.message
        }
    }
}
