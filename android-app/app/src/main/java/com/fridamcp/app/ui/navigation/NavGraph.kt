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
    val app = FridaMCPApplication.instance
    val sharedViewModel: SharedViewModel = viewModel(factory = SharedViewModelFactory(app))

    var activeTab by remember { mutableStateOf(TabId.DASHBOARD) }
    val injectedCount by sharedViewModel.injectedCount.collectAsState()

    Scaffold(
        bottomBar = {
            BottomNav(
                activeTab = activeTab,
                onTabChange = { activeTab = it },
                injectedCount = injectedCount,
            )
        }
    ) { innerPadding ->
        when (activeTab) {
            TabId.DASHBOARD -> DashboardScreen(viewModel = sharedViewModel, modifier = Modifier.padding(innerPadding))
            TabId.APPS -> AppsScreen(viewModel = sharedViewModel, modifier = Modifier.padding(innerPadding))
            TabId.INJECT -> InjectScreen(viewModel = sharedViewModel, modifier = Modifier.padding(innerPadding))
            TabId.MCP -> McpScreen(viewModel = sharedViewModel, modifier = Modifier.padding(innerPadding))
            TabId.SETTINGS -> SettingsScreen(viewModel = sharedViewModel, modifier = Modifier.padding(innerPadding))
        }
    }
}
