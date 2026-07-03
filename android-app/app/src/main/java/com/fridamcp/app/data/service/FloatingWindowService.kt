package com.fridamcp.app.data.service

import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import androidx.compose.runtime.MutableFloatState
import com.fridamcp.app.R

/**
 * Floating window service — shows a draggable overlay with MCP server status.
 *
 * Requires SYSTEM_ALERT_WINDOW permission (Settings.canDrawOverlays).
 * Shows:
 *  - FridaMCP status (running/stopped)
 *  - Server address (127.0.0.1:8768)
 *  - Quick toggle button
 */
class FloatingWindowService : Service() {

    companion object {
        const val ACTION_SHOW = "com.fridamcp.app.SHOW_FLOATING"
        const val ACTION_HIDE = "com.fridamcp.app.HIDE_FLOATING"
        private const val TAG = "FloatingWindow"
    }

    private var windowManager: WindowManager? = null
    private var floatingView: View? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_SHOW -> showFloating()
            ACTION_HIDE -> hideFloating()
        }
        return START_STICKY
    }

    private fun showFloating() {
        if (floatingView != null) return

        // Check overlay permission
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Log.e(TAG, "No overlay permission")
            return
        }

        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else
            @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        params.x = 20
        params.y = 200

        // Create floating view programmatically
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xE614161C.toInt())
            setPadding(24, 16, 24, 16)
        }
        val layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        )
        layoutParams.setMargins(0, 4, 0, 4)

        val titleText = TextView(this).apply {
            text = "🔧 FridaMCP"
            setTextColor(0xFF20C020.toInt())
            textSize = 13f
            setPadding(0, 0, 0, 4)
        }
        container.addView(titleText, layoutParams)

        val statusText = TextView(this).apply {
            text = "状态: 运行中"
            setTextColor(0xFF22C55E.toInt())
            textSize = 11f
            id = STATUS_TEXT_ID
        }
        container.addView(statusText, layoutParams)

        val addrText = TextView(this).apply {
            text = "127.0.0.1:8768"
            setTextColor(0xFFA0A4AB.toInt())
            textSize = 11f
        }
        container.addView(addrText, layoutParams)

        val endpointText = TextView(this).apply {
            text = "/sse · /mcp"
            setTextColor(0xFF6B7280.toInt())
            textSize = 10f
        }
        container.addView(endpointText, layoutParams)

        // Make it draggable
        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f

        container.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = initialX + (event.rawX - initialTouchX).toInt()
                    params.y = initialY + (event.rawY - initialTouchY).toInt()
                    windowManager?.updateViewLayout(container, params)
                    true
                }
                else -> false
            }
        }

        floatingView = container
        try {
            windowManager?.addView(container, params)
            Log.i(TAG, "Floating window shown")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to show floating window", e)
        }
    }

    private fun hideFloating() {
        floatingView?.let {
            try {
                windowManager?.removeView(it)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to remove floating window", e)
            }
        }
        floatingView = null
    }

    companion object {
        const val STATUS_TEXT_ID = 10001
    }

    override fun onDestroy() {
        hideFloating()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
