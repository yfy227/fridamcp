package com.fridamcp.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
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
import com.fridamcp.app.data.model.InjectionStatus
import com.fridamcp.app.data.model.MCPServiceStatus
import com.fridamcp.app.ui.theme.Error
import com.fridamcp.app.ui.theme.Info
import com.fridamcp.app.ui.theme.Primary
import com.fridamcp.app.ui.theme.Success
import com.fridamcp.app.ui.theme.Warning

@Composable
fun StatusDot(
    status: InjectionStatus,
    modifier: Modifier = Modifier,
) {
    val color = when (status) {
        InjectionStatus.INJECTED -> Primary
        InjectionStatus.RUNNING -> Success
        InjectionStatus.NOT_INJECTED -> MaterialTheme.colorScheme.outline
        InjectionStatus.ERROR -> Error
    }
    Box(
        modifier = modifier
            .size(8.dp)
            .clip(CircleShape)
            .background(color)
    )
}

@Composable
fun StatusBadge(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .clip(androidx.compose.foundation.shape.RoundedCornerShape(6.dp))
            .background(color.copy(alpha = 0.15f))
            .padding(horizontal = 8.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(color)
        )
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall,
            color = color,
            modifier = Modifier.padding(start = 4.dp),
        )
    }
}

fun InjectionStatus.badgeColor(): Color = when (this) {
    InjectionStatus.INJECTED -> Primary
    InjectionStatus.RUNNING -> Success
    InjectionStatus.NOT_INJECTED -> MaterialTheme.colorScheme.outline
    InjectionStatus.ERROR -> Error
}

fun MCPServiceStatus.badgeColor(): Color = when (this) {
    MCPServiceStatus.ONLINE -> Success
    MCPServiceStatus.OFFLINE -> MaterialTheme.colorScheme.outline
    MCPServiceStatus.STARTING -> Warning
    MCPServiceStatus.ERROR -> Error
}
