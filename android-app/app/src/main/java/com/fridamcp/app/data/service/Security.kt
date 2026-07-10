package com.fridamcp.app.data.service

private val PACKAGE_RE = Regex("""^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$""")

fun isValidPackageName(value: String): Boolean = PACKAGE_RE.matches(value)

fun requirePackageName(value: String): String {
    require(isValidPackageName(value)) { "Invalid package name: $value" }
    return value
}

fun shellQuote(value: String): String = "'" + value.replace("'", """'"'"'""") + "'"
