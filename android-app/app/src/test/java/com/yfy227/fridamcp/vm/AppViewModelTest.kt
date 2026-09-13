package com.yfy227.fridamcp.vm

import com.yfy227.fridamcp.api.RestClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.doThrow
import org.mockito.kotlin.mock
import java.io.IOException

/**
 * ViewModel 状态流转测试（纯 JVM + coroutines-test + mockito-kotlin）。
 *
 * org.json 使用 Maven 真实实现（见 build.gradle.kts 测试依赖）。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class AppViewModelTest {

    private val dispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `connect success sets connected and loads status`() {
        val status = JSONObject(
            """{"version":"3.0.0","mcp":"port 8768",
                "device":{"connected":false},"sessions":{"total_sessions":0}}"""
        )
        // mockito-kotlin KStubbing 语法：mock<T> { onBlocking ... doReturn ... }
        val rest: RestClient = mock {
            onBlocking { getStatus() } doReturn status
            onBlocking { getSessions() } doReturn JSONArray("[]")
            onBlocking { getProcesses() } doReturn JSONArray("[]")
            onBlocking { getApplications() } doReturn JSONArray("[]")
        }
        val vm = AppViewModel(restClient = rest)
        var navigated = false
        vm.connect("http://x:8770") { navigated = true }

        assertTrue(vm.connected.value)
        assertNotNull(vm.statusJson.value)
        assertEquals("port 8768", vm.statusJson.value!!.getString("mcp"))
        assertTrue(navigated)
    }

    @Test
    fun `connect failure keeps disconnected with error`() {
        // 真实网络层失败路径：MockWebServer 返回 503（比 mock 更真实）
        val server = okhttp3.mockwebserver.MockWebServer()
        server.start()
        server.enqueue(
            okhttp3.mockwebserver.MockResponse()
                .setResponseCode(503)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"error":"no matching device found"}""")
        )
        val serverUrl = server.url("/").toString().trimEnd('/')
        val vm = AppViewModel(
            restClient = RestClient(serverUrl)
        )
        vm.connect(serverUrl) {}

        assertFalse(vm.connected.value)
        assertNotNull(vm.lastError.value)
        assertTrue(vm.lastError.value!!.contains("503"))
        server.shutdown()
    }

    @Test
    fun `default rest client points to localhost`() {
        val vm = AppViewModel()
        assertEquals("http://127.0.0.1:8770", vm.rest.getBaseUrl())
        assertEquals(vm.rest.getBaseUrl(), vm.baseUrl.value)
    }
}
