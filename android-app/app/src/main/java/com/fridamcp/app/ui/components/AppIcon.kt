package com.fridamcp.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.fridamcp.app.ui.theme.Card

@Composable
fun AppIcon(
    text: String,
    color: Long,
    modifier: Modifier = Modifier,
    size: Int = 48,
) {
    Box(
        modifier = modifier
            .size(size.dp)
            .clip(androidx.compose.foundation.shape.RoundedCornerShape(12.dp))
            .background(Color(color)),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            style = if (size >= 40) MaterialTheme.typography.titleMedium else MaterialTheme.typography.labelSmall,
            color = Color.White,
        )
    }
}
