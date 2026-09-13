package com.yfy227.fridamcp.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * FridaMCP REST API 客户端
 *
 * 服务端见 fridamcp/rest_api.py（默认端口 8770）。
 * 全部为 suspend 函数，IO 在 Dispatchers.IO 执行。
 */
class RestClient(private var baseUrl: String) {

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    fun setBaseUrl(url: String) {
        baseUrl = url.trimEnd('/')
    }

    fun getBaseUrl(): String = baseUrl

    // ---------- 基础请求 ----------

    private suspend fun get(path: String): String = withContext(Dispatchers.IO) {
        val req = Request.Builder().url("$baseUrl$path").get().build()
        client.newCall(req).execute().use { resp ->
            val body = resp.body?.string() ?: ""
            if (!resp.isSuccessful) throw ApiException(resp.code, body)
            body
        }
    }

    private suspend fun post(path: String, json: JSONObject? = null): String =
        withContext(Dispatchers.IO) {
            val body = (json?.toString() ?: "{}").toRequestBody(jsonMedia)
            val req = Request.Builder().url("$baseUrl$path").post(body).build()
            client.newCall(req).execute().use { resp ->
                val s = resp.body?.string() ?: ""
                if (!resp.isSuccessful) throw ApiException(resp.code, s)
                s
            }
        }

    class ApiException(val code: Int, val body: String) :
        Exception("HTTP $code: ${body.take(200)}")

    // ---------- API 封装 ----------

    suspend fun getStatus(): JSONObject = JSONObject(get("/api/status"))

    suspend fun getDevices(): JSONArray = JSONArray(get("/api/devices"))

    suspend fun selectDevice(deviceId: String?, deviceType: String?): JSONObject =
        JSONObject(
            post(
                "/api/device/select",
                JSONObject().apply {
                    putOpt("device_id", deviceId)
                    putOpt("device_type", deviceType)
                }
            )
        )

    suspend fun getProcesses(): JSONArray = JSONArray(get("/api/processes"))

    suspend fun getApplications(): JSONArray = JSONArray(get("/api/applications"))

    suspend fun spawn(packageName: String, paused: Boolean): JSONObject =
        JSONObject(
            post(
                "/api/spawn",
                JSONObject().put("package", packageName).put("paused", paused)
            )
        )

    suspend fun attach(pid: Int): JSONObject =
        JSONObject(post("/api/attach", JSONObject().put("pid", pid)))

    /** 按进程名附加（服务端 AttachReq 支持 pid/name 二选一） */
    suspend fun attachByName(name: String): JSONObject =
        JSONObject(post("/api/attach", JSONObject().put("name", name)))

    suspend fun resume(pid: Int): JSONObject =
        JSONObject(post("/api/resume", JSONObject().put("pid", pid)))

    suspend fun kill(pid: Int): JSONObject =
        JSONObject(post("/api/kill", JSONObject().put("pid", pid)))

    suspend fun getSessions(): JSONArray = JSONArray(get("/api/sessions"))

    suspend fun closeSession(sessionId: String): JSONObject =
        JSONObject(post("/api/session/close", JSONObject().put("session_id", sessionId)))

    suspend fun hookJava(sessionId: String, className: String, methodName: String): JSONObject =
        JSONObject(
            post(
                "/api/hook/java",
                JSONObject()
                    .put("session_id", sessionId)
                    .put("class_name", className)
                    .put("method_name", methodName)
            )
        )

    suspend fun hookNative(
        sessionId: String,
        moduleName: String,
        funcName: String?,
        offset: Long,
    ): JSONObject =
        JSONObject(
            post(
                "/api/hook/native",
                JSONObject()
                    .put("session_id", sessionId)
                    .put("module_name", moduleName)
                    .putOpt("func_name", funcName)
                    .put("offset", offset)
            )
        )

    suspend fun getMessages(sessionId: String, clear: Boolean = false): JSONArray =
        JSONArray(
            get(
                "/api/messages?session_id=$sessionId&clear=${if (clear) "true" else "false"}"
            )
        )

    suspend fun startNetworkCapture(sessionId: String, captureSsl: Boolean): JSONObject =
        JSONObject(
            post(
                "/api/network/start",
                JSONObject().put("session_id", sessionId).put("capture_ssl", captureSsl)
            )
        )

    suspend fun getNetworkCapture(sessionId: String): JSONArray =
        JSONArray(get("/api/network/capture?session_id=$sessionId"))

    suspend fun getServerLogs(maxEntries: Int = 100): JSONArray =
        JSONArray(get("/api/logs/server?max_entries=$maxEntries"))
}
