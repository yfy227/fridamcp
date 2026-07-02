package com.fridamcp.app.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val FridaColorScheme = darkColorScheme(
    primary = Primary,
    onPrimary = Background,
    primaryContainer = PrimaryContainer,
    onPrimaryContainer = Primary,
    secondary = CardElevated,
    onSecondary = Foreground,
    tertiary = PrimaryDim,
    onTertiary = Foreground,
    background = Background,
    onBackground = Foreground,
    surface = Card,
    onSurface = Foreground,
    surfaceVariant = CardElevated,
    onSurfaceVariant = MutedForeground,
    outline = Border,
    outlineVariant = Border,
    error = Error,
    onError = Foreground,
)

@Composable
fun FridaMCPTheme(
    content: @Composable () -> Unit
) {
    // Always dark theme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = Background.toArgb()
            window.navigationBarColor = Background.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = FridaColorScheme,
        typography = FridaTypography,
        content = content
    )
}
