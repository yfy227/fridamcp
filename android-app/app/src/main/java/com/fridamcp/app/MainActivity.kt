package com.fridamcp.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.fridamcp.app.ui.navigation.FridaMCPNavHost
import com.fridamcp.app.ui.theme.FridaMCPTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            FridaMCPTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    FridaMCPApp()
                }
            }
        }
    }
}

@Composable
fun FridaMCPApp() {
    FridaMCPNavHost()
}
