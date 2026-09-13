package com.yfy227.fridamcp.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val DarkColors = darkColorScheme(
    primary = Primary,
    onPrimary = OnPrimary,
    secondary = Secondary,
    background = Background,
    surface = Surface,
    onSurface = OnSurface,
    error = Error,
)

@Composable
fun FridaMCPTheme(content: @Composable () -> Unit) {
    // 安全工具风格：始终深色（无视系统主题，保证可读性）
    MaterialTheme(
        colorScheme = DarkColors,
        content = content
    )
}
