# Keep Frida related classes
-keep class com.fridamcp.app.data.service.** { *; }
-keepclassmembers class * {
    @androidx.annotation.Keep <methods>;
}
