package com.fridamcp.app.ui.components

import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.fridamcp.app.data.model.TabId
import com.fridamcp.app.ui.theme.Background
import com.fridamcp.app.ui.theme.Card
import com.fridamcp.app.ui.theme.Foreground
import com.fridamcp.app.ui.theme.MutedForeground
import com.fridamcp.app.ui.theme.Primary

data class TabItem(
    val tab: TabId,
    val label: String,
    val icon: ImageVector,
    val badge: Int? = null,
)

@Composable
fun BottomNav(
    activeTab: TabId,
    onTabChange: (TabId) -> Unit,
    injectedCount: Int = 0,
) {
    val tabs = listOf(
        TabItem(TabId.DASHBOARD, "仪表盘", Icons.Default.Home),
        TabItem(TabId.APPS, "应用", Icons.Default.Menu, if (injectedCount > 0) injectedCount else null),
        TabItem(TabId.INJECT, "注入", Icons.Default.Build),
        TabItem(TabId.MCP, "MCP", Icons.Default.Email),
        TabItem(TabId.SETTINGS, "设置", Icons.Default.Settings),
    )

    NavigationBar(
        containerColor = Card,
        contentColor = Foreground,
        tonalElevation = 0.dp,
    ) {
        tabs.forEach { item ->
            NavigationBarItem(
                selected = activeTab == item.tab,
                onClick = { onTabChange(item.tab) },
                icon = {
                    Icon(
                        imageVector = item.icon,
                        contentDescription = item.label,
                        modifier = Modifier.size(22.dp),
                    )
                },
                label = {
                    Text(
                        text = item.label,
                        style = MaterialTheme.typography.labelSmall,
                    )
                },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = Primary,
                    selectedTextColor = Primary,
                    unselectedIconColor = MutedForeground,
                    unselectedTextColor = MutedForeground,
                    indicatorColor = Background,
                ),
            )
        }
    }
}
