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
import org.mockito.kotlin.any
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.doThrow
import org.mockito.kotlin.mock
import org.mockito.kotlin.stubbing
import java.io.IOException

/**
 * ViewModel 状态流转测试（纯 JVM + coroutines-test）。
 *
 * 注：org.json 在本地 JVM 单测里可用（Android Gradle 的 jar）。
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

    private fun mockRest(status: JSONObject? = null): RestClient = mock {
        if (status != null) {
            stubbing(it) { onBlocking { getStatus() } doReturn status }
        }
    }

    @Test
    fun `connect success sets connected and loads status`() {
        val status = JSONObject(
            """{"version":"3.0.0","mcp":"port 8768",
                "device":{"connected":false},"sessions":{"total_sessions":0}}"""
        )
        val rest = mock {
            stubbing(it) {
                onBlocking { getStatus() } doReturn status
                onBlocking { getSessions() } doReturn JSONArray("[]")
                onBlocking { getProcesses() } doReturn JSONArray("[]")
                onBlocking { getApplications() } doReturn JSONArray("[]")
            }
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
        val rest = mock {
            stubbing(it) {
                onBlocking { getStatus() } doThrow IOException("Connection refused")
            }
        }
        val vm = AppViewModel(restClient = rest)
        vm.connect("http://x:8770") {}

        assertFalse(vm.connected.value)
        assertTrue(vm.lastError.value!!.contains("Connection refused"))
    }

    @Test
    fun `default rest client points to localhost`() {
        val vm = AppViewModel()
        assertEquals("http://127.0.0.1:8770", vm.rest.getBaseUrl())
        assertEquals(vm.rest.getBaseUrl(), vm.baseUrl.value)
    }
}
