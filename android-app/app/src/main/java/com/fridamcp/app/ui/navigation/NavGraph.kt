package com.fridamcp.app.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.fridamcp.app.FridaMCPApplication
import com.fridamcp.app.data.model.TabId
import com.fridamcp.app.ui.components.BottomNav
import com.fridamcp.app.ui.screens.AppsScreen
import com.fridamcp.app.ui.screens.DashboardScreen
import com.fridamcp.app.ui.screens.InjectScreen
import com.fridamcp.app.ui.screens.McpScreen
import com.fridamcp.app.ui.screens.SettingsScreen
import com.fridamcp.app.ui.screens.SharedViewModel
import com.fridamcp.app.ui.screens.SharedViewModelFactory

@Composable
fun FridaMCPNavHost() {
    val navController = rememberNavController()
    val app = FridaMCPApplication.instance
    val sharedViewModel: SharedViewModel = viewModel(factory = SharedViewModelFactory(app))

    var activeTab by remember { mutableStateOf(TabId.DASHBOARD) }

    Scaffold(
        bottomBar = {
            BottomNav(
                activeTab = activeTab,
                onTabChange = { activeTab = it },
                injectedCount = sharedViewModel.injectedCount.collectAsState().value,
            )
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = TabId.DASHBOARD.route,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(TabId.DASHBOARD.route) {
                DashboardScreen(
                    viewModel = sharedViewModel,
                )
            }
            composable(TabId.APPS.route) {
                AppsScreen(
                    viewModel = sharedViewModel,
                )
            }
            composable(TabId.INJECT.route) {
                InjectScreen(
                    viewModel = sharedViewModel,
                )
            }
            composable(TabId.MCP.route) {
                McpScreen(
                    viewModel = sharedViewModel,
                )
            }
            composable(TabId.SETTINGS.route) {
                SettingsScreen(
                    viewModel = sharedViewModel,
                )
            }
        }
    }
}
