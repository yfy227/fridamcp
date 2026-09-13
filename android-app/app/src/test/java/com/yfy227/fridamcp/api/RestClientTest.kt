package com.yfy227.fridamcp.api

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * REST 契约测试：MockWebServer 回放服务端（fridamcp/rest_api.py）
 * 实测响应结构——字段契约与服务器逐一对齐。
 *
 * 响应样例采集自真实运行实例（无设备场景）。
 */
class RestClientTest {

    private lateinit var server: MockWebServer
    private lateinit var client: RestClient

    @Before
    fun setup() {
        server = MockWebServer()
        server.start()
        client = RestClient(server.url("/").toString())
    }

    @After
    fun teardown() {
        server.shutdown()
    }

    private fun enqueue(body: String, code: Int = 200) {
        server.enqueue(
            MockResponse().setResponseCode(code)
                .setHeader("Content-Type", "application/json")
                .setBody(body)
        )
    }

    // ---------- /api/status（真实实测结构） ----------

    @Test
    fun `status parses real contract`() = runBlocking {
        enqueue(
            """
            {"version":"3.0.0","mcp":"port 8768",
             "device":{"connected":false,"device_type":null,
                       "reconnect_count":0,"heartbeat_active":false},
             "sessions":{"total_sessions":0,"active_sessions":0,
                         "detached_sessions":0,"max_sessions":10}}
            """.trimIndent()
        )
        val s = client.getStatus()
        assertEquals("3.0.0", s.getString("version"))
        assertEquals("port 8768", s.getString("mcp"))
        // DashboardScreen 读取路径
        assertEquals(false, s.getJSONObject("device").getBoolean("connected"))
        assertEquals(0, s.getJSONObject("sessions").getInt("total_sessions"))
    }

    // ---------- 无设备 503 错误契约 ----------

    @Test
    fun `processes 503 surfaces error detail`() = runBlocking {
        enqueue(
            """{"error":"Failed to connect to device after 1 attempts: no matching device found"}""",
            code = 503
        )
        val e = runCatching { client.getProcesses() }.exceptionOrNull()
        assertTrue("应抛 ApiException", e is RestClient.ApiException)
        val api = e as RestClient.ApiException
        assertEquals(503, api.code)
        assertTrue(api.message!!.contains("no matching device"))
    }

    // ---------- /api/processes（正常结构） ----------

    @Test
    fun `processes parses pid and name`() = runBlocking {
        enqueue("""[{"pid":1,"name":"init"},{"pid":42,"name":"com.example.app"}]""")
        val list = client.getProcesses()
        assertEquals(2, list.length())
        assertEquals("init", list.getJSONObject(0).getString("name"))
        assertEquals(42, list.getJSONObject(1).getInt("pid"))
    }

    // ---------- /api/applications ----------

    @Test
    fun `applications parses identifier name pid`() = runBlocking {
        enqueue(
            """[{"identifier":"com.yfy227.fridamcp","name":"FridaMCP","pid":0}]"""
        )
        val list = client.getApplications()
        assertEquals("com.yfy227.fridamcp", list.getJSONObject(0).getString("identifier"))
        assertEquals("FridaMCP", list.getJSONObject(0).getString("name"))
        assertEquals(0, list.getJSONObject(0).getInt("pid"))
    }

    // ---------- /api/sessions（SessionScreen 解析路径） ----------

    @Test
    fun `sessions parses id pid name state`() = runBlocking {
        enqueue(
            """[{"id":"sess_ab12","pid":100,"name":"com.example.app","state":"attached",
                "created_at":1.0}]"""
        )
        val list = client.getSessions()
        assertEquals("sess_ab12", list.getJSONObject(0).getString("id"))
        assertEquals(100, list.getJSONObject(0).getInt("pid"))
        assertEquals("attached", list.getJSONObject(0).getString("state"))
    }

    // ---------- /api/messages（Hook 消息结构） ----------

    @Test
    fun `messages parses nested message payload`() = runBlocking {
        enqueue(
            """[{"message":{"type":"ssl_write","data":"GET /api HTTP/1.1","size":14}}]"""
        )
        val list = client.getMessages("sess_x")
        val m = list.getJSONObject(0).getJSONObject("message")
        assertEquals("ssl_write", m.getString("type"))
        assertEquals(14, m.getInt("size"))
        // 请求参数校验
        val req = server.takeRequest()
        assertTrue(req.path!!.contains("session_id=sess_x"))
    }

    // ---------- POST 请求体契约 ----------

    @Test
    fun `spawn sends package and paused`() = runBlocking {
        enqueue("""{"session_id":"s1","pid":123}""")
        val r = client.spawn("com.example.app", paused = true)
        assertEquals("s1", r.getString("session_id"))
        val body = JSONObject(server.takeRequest().body.readUtf8())
        assertEquals("com.example.app", body.getString("package"))
        assertEquals(true, body.getBoolean("paused"))
    }

    @Test
    fun `hook java sends class and method`() = runBlocking {
        enqueue("""{"hook_id":"hook_1","script_id":"scr_1","class_name":"a.B"}""")
        val r = client.hookJava("s1", "com.example.Login", "check")
        assertEquals("hook_1", r.getString("hook_id"))
        val body = JSONObject(server.takeRequest().body.readUtf8())
        assertEquals("com.example.Login", body.getString("class_name"))
        assertEquals("check", body.getString("method_name"))
        assertEquals("s1", body.getString("session_id"))
    }

    @Test
    fun `hook error result is surfaced not swallowed`() = runBlocking {
        // impl 层异常时返回 {"error": ...}（HTTP 200 契约）
        enqueue("""{"error":"Session not found: sX"}""")
        val r = client.hookJava("sX", "a.B", "m")
        assertEquals("Session not found: sX", r.getString("error"))
    }

    // ---------- attach（pid 或 name 二选一契约） ----------

    @Test
    fun `attach by name sends name field`() = runBlocking {
        enqueue("""{"session_id":"s1","pid":50,"name":"com.x"}""")
        client.attachByName("com.x")
        val body = JSONObject(server.takeRequest().body.readUtf8())
        assertEquals("com.x", body.getString("name"))
    }

    @Test
    fun `base url trailing slash trimmed`() {
        val c = RestClient("http://10.0.2.2:8770/")
        assertEquals("http://10.0.2.2:8770", c.getBaseUrl())
    }
}
