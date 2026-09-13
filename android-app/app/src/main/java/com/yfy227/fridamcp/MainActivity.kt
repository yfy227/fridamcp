package com.yfy227.fridamcp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Assignment
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.SettingsRemote
import androidx.compose.material.icons.filled.List
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.yfy227.fridamcp.ui.ConnectScreen
import com.yfy227.fridamcp.ui.DashboardScreen
import com.yfy227.fridamcp.ui.ProcessesScreen
import com.yfy227.fridamcp.ui.SessionsScreen
import com.yfy227.fridamcp.ui.theme.FridaMCPTheme
import com.yfy227.fridamcp.vm.AppViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            FridaMCPTheme {
                App(vm = viewModel())
            }
        }
    }
}

private val TABS = listOf(
    Triple("连接", Icons.Filled.SettingsRemote, "connect"),
    Triple("仪表盘", Icons.Filled.Dashboard, "dashboard"),
    Triple("进程", Icons.Filled.List, "processes"),
    Triple("会话", Icons.Filled.Assignment, "sessions"),
)

@Composable
fun App(vm: AppViewModel) {
    val nav = rememberNavController()
    val snackbar = remember { SnackbarHostState() }
    val toast by vm.toast.collectAsState()

    LaunchedEffect(toast) {
        toast?.let {
            snackbar.showSnackbar(it)
            vm.consumeToast()
        }
    }

    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route ?: "connect"
    val connected by vm.connected.collectAsState()

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar {
                TABS.forEach { (label, icon, route) ->
                    NavigationBarItem(
                        selected = currentRoute == route,
                        onClick = {
                            if (route != "connect" && !connected) {
                                // 未连接时只允许回到连接页
                                nav.navigate("connect") { launchSingleTop = true }
                            } else {
                                nav.navigate(route) { launchSingleTop = true }
                            }
                        },
                        icon = { Icon(icon, contentDescription = label) },
                        label = { Text(label) },
                        enabled = route == "connect" || connected
                    )
                }
            }
        }
    ) { padding ->
        NavHost(
            navController = nav,
            startDestination = "connect",
            modifier = Modifier.padding(padding)
        ) {
            composable("connect") { ConnectScreen(vm) }
            composable("dashboard") { DashboardScreen(vm) }
            composable("processes") { ProcessesScreen(vm) }
            composable("sessions") { SessionsScreen(vm) }
        }
    }
}
