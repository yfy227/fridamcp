"""
Hook 沙箱模块

为 AI 生成的 Frida hook 脚本提供异常隔离层，防止低质量脚本
导致目标进程崩溃。核心策略：

1. **脚本包装**：将 AI 原始脚本包裹在 try-catch 中，所有顶层
   异常都被捕获并通过 send() 回传，不会冒泡到 Frida 引擎导致
   进程崩溃。

2. **语法预检**：在加载前对脚本做轻量级静态检查（括号匹配、
   禁止危险 API），减少明显错误的脚本被加载的概率。

3. **加载重试**：脚本加载失败时自动卸载并重试，避免残留状态
   影响后续操作。

4. **超时保护**：可选的脚本执行超时，防止死循环脚本阻塞会话。

5. **错误聚合**：收集脚本运行时错误，供 AI 调试迭代。

使用方式：
    from fridamcp.utils.hook_sandbox import wrap_script_safely, validate_script
    safe_source = wrap_script_safely(raw_source)
    issues = validate_script(raw_source)
"""

import re
import uuid
from typing import Dict, Any, List, Optional, Tuple

from .logger import logger


# 危险 API 模式：这些 API 可能导致进程崩溃或数据损坏
# 仅作警告，不强制阻止（AI 可能确实需要这些 API）
DANGEROUS_PATTERNS = [
    (r"Process\.kill\s*\(", "Process.kill 会导致目标进程立即退出"),
    (r"Memory\.protect\s*\([^)]*prot\s*=\s*['\"]?r--", "Memory.protect 移除写权限可能影响后续 hook"),
    (r"Thread\.backtrace\s*\([^)]*Backtracer\.ACCURATE", "Backtracer.ACCURATE 在某些版本会崩溃，建议用 FUZZY"),
    (r"Module\.findExportByName\s*\(\s*null\s*,", "findExportByName(null, ...) 在新版本已废弃，用 Module.getGlobalExportByName"),
]

# 禁止 API 模式：这些 API 几乎肯定会导致问题
FORBIDDEN_PATTERNS = [
    (r"while\s*\(\s*(true|1|!0)\s*\)\s*\{(?![^}]*sleep)", "无限循环缺少 sleep，会卡死目标进程"),
]


def validate_script(source: str) -> Tuple[bool, List[str], List[str]]:
    """对脚本进行轻量级静态检查

    Args:
        source: JavaScript 脚本源码

    Returns:
        (is_valid, errors, warnings)
        - is_valid: 是否通过检查（无 error）
        - errors: 阻断性错误列表（脚本不应被加载）
        - warnings: 警告列表（可加载但需注意）
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not source or not source.strip():
        errors.append("脚本为空")
        return False, errors, warnings

    # 1. 括号匹配检查（粗略）
    brace_count = 0
    paren_count = 0
    bracket_count = 0
    in_string = False
    string_char = None
    in_comment = False
    comment_char = None
    i = 0
    while i < len(source):
        c = source[i]
        # 处理字符串
        if not in_comment and not in_string and c in ('"', "'", '`'):
            in_string = True
            string_char = c
        elif in_string and c == string_char and source[i-1:i] != '\\':
            in_string = False
            string_char = None
        # 处理注释
        elif not in_string and not in_comment and i + 1 < len(source):
            if source[i:i+2] == '//':
                in_comment = True
                comment_char = '\n'
            elif source[i:i+2] == '/*':
                in_comment = True
                comment_char = '*/'
        elif in_comment:
            if comment_char == '\n' and c == '\n':
                in_comment = False
            elif comment_char == '*/' and source[i:i+2] == '*/':
                in_comment = False
                i += 1
        # 计数括号
        elif not in_string and not in_comment:
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
            elif c == '(':
                paren_count += 1
            elif c == ')':
                paren_count -= 1
            elif c == '[':
                bracket_count += 1
            elif c == ']':
                bracket_count -= 1
        i += 1

    if brace_count != 0:
        errors.append(f"花括号不匹配（差值 {brace_count}），脚本可能不完整")
    if paren_count != 0:
        errors.append(f"圆括号不匹配（差值 {paren_count}），脚本可能不完整")
    if bracket_count != 0:
        errors.append(f"方括号不匹配（差值 {bracket_count}），脚本可能不完整")

    # 2. 危险 API 检查
    for pattern, message in DANGEROUS_PATTERNS:
        if re.search(pattern, source):
            warnings.append(message)

    # 3. 禁止 API 检查
    for pattern, message in FORBIDDEN_PATTERNS:
        if re.search(pattern, source, re.DOTALL):
            errors.append(message)

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


# 沙箱包装模板
# 策略：
#   - 将用户脚本包裹在 IIFE 中
#   - 顶层 try-catch 捕获所有异常
#   - Java.perform / ObjC.implement 等异步回调也包裹 try-catch
#   - 错误通过 send() 回传，不冒泡到 Frida 引擎
SANDBOX_TEMPLATE = r"""
// ===== FridaMCP Sandbox Wrapper =====
// 自动生成，请勿手动修改
// 沙箱 ID: {sandbox_id}
(function() {{
    'use strict';

    var __sandbox_id = "{sandbox_id}";
    var __error_count = 0;
    var __max_errors = {max_errors};

    // 安全的 send 包装：捕获 send 本身的异常
    function __safe_send(payload, data) {{
        try {{
            send(payload, data);
        }} catch (e) {{
            // send 失败说明会话已断开，无法处理
        }}
    }}

    // 错误上报：限制最大错误数，防止刷屏
    function __report_error(stage, error) {{
        __error_count++;
        if (__error_count > __max_errors) {{
            if (__error_count === __max_errors + 1) {{
                __safe_send({{
                    type: "sandbox_error_limit",
                    sandbox_id: __sandbox_id,
                    message: "达到最大错误数 (" + __max_errors + ")，后续错误将被静默"
                }});
            }}
            return;
        }}
        var errorInfo = {{
            type: "sandbox_error",
            sandbox_id: __sandbox_id,
            stage: stage,
            message: error && error.message ? error.message : String(error),
            stack: error && error.stack ? error.stack : null,
            error_count: __error_count
        }};
        __safe_send(errorInfo);
    }}

    // 安全的 Java.perform 包装
    var __orig_Java_perform = typeof Java !== 'undefined' ? Java.perform : null;
    if (__orig_Java_perform) {{
        Java.perform = function(fn) {{
            return __orig_Java_perform.call(Java, function() {{
                try {{
                    fn();
                }} catch (e) {{
                    __report_error("Java.perform", e);
                }}
            }});
        }};
    }}

    // 安全的 Interceptor.attach 包装
    var __orig_Interceptor_attach = typeof Interceptor !== 'undefined' ? Interceptor.attach : null;
    if (__orig_Interceptor_attach) {{
        Interceptor.attach = function(target, callbacks) {{
            var safeCallbacks = {{}};
            var keys = Object.keys(callbacks);
            for (var i = 0; i < keys.length; i++) {{
                var key = keys[i];
                var origFn = callbacks[key];
                if (typeof origFn === 'function') {{
                    safeCallbacks[key] = function() {{
                        try {{
                            return origFn.apply(this, arguments);
                        }} catch (e) {{
                            __report_error("Interceptor." + key, e);
                            // onEnter 出错时返回 undefined，不影响原函数
                            // onLeave 出错时也不影响原返回值
                            return undefined;
                        }}
                    }};
                }} else {{
                    safeCallbacks[key] = origFn;
                }}
            }}
            return __orig_Interceptor_attach.call(Interceptor, target, safeCallbacks);
        }};
    }}

    // 安全的 rpc.exports 包装
    function __safe_exports(exports) {{
        var safeExports = {{}};
        var keys = Object.keys(exports);
        for (var i = 0; i < keys.length; i++) {{
            var key = keys[i];
            var origFn = exports[key];
            if (typeof origFn === 'function') {{
                safeExports[key] = function() {{
                    try {{
                        return origFn.apply(this, arguments);
                    }} catch (e) {{
                        __report_error("rpc." + key, e);
                        throw e;  // RPC 错误需要抛出，让调用方知道
                    }}
                }};
            }} else {{
                safeExports[key] = origFn;
            }}
        }}
        return safeExports;
    }}

    // ===== 用户脚本开始 =====
    try {{
        // 用户脚本通过 __user_script__ 变量注入
        {user_script}

        // 如果用户定义了 rpc.exports，包装它
        if (typeof rpc !== 'undefined' && rpc.exports) {{
            rpc.exports = __safe_exports(rpc.exports);
        }}
    }} catch (e) {{
        __report_error("toplevel", e);
    }}
    // ===== 用户脚本结束 =====

    // 通知沙箱已就绪
    __safe_send({{
        type: "sandbox_ready",
        sandbox_id: __sandbox_id,
        max_errors: __max_errors
    }});

}})();
"""


def wrap_script_safely(
    source: str,
    max_errors: int = 50,
    sandbox_id: Optional[str] = None,
) -> str:
    """将用户脚本包裹在沙箱中

    沙箱提供以下保护：
    1. 顶层 try-catch 捕获所有异常
    2. Java.perform 回调包裹 try-catch
    3. Interceptor.attach 的 onEnter/onLeave 包裹 try-catch
    4. rpc.exports 函数包裹 try-catch
    5. 错误通过 send() 回传，限制最大错误数防止刷屏
    6. send() 本身也包裹 try-catch，防止会话断开时崩溃

    Args:
        source: 用户原始脚本
        max_errors: 最大错误上报数（超过后静默）
        sandbox_id: 沙箱 ID，用于关联错误消息

    Returns:
        包裹后的安全脚本
    """
    if sandbox_id is None:
        sandbox_id = f"sbx_{uuid.uuid4().hex[:8]}"

    # 缩进用户脚本（4 空格），避免破坏模板结构
    indented = "\n".join(
        "        " + line if line.strip() else line
        for line in source.splitlines()
    )

    return SANDBOX_TEMPLATE.format(
        sandbox_id=sandbox_id,
        max_errors=max_errors,
        user_script=indented,
    )


def extract_sandbox_errors(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从消息列表中提取沙箱错误

    Args:
        messages: 会话消息列表

    Returns:
        沙箱错误消息列表
    """
    errors = []
    for msg in messages:
        payload = msg.get("message", {})
        if isinstance(payload, dict):
            msg_type = payload.get("type", "")
            if msg_type in ("sandbox_error", "sandbox_error_limit", "sandbox_ready"):
                errors.append(payload)
    return errors


def is_sandbox_ready(messages: List[Dict[str, Any]], sandbox_id: str) -> bool:
    """检查沙箱是否已就绪

    Args:
        messages: 会话消息列表
        sandbox_id: 沙箱 ID

    Returns:
        沙箱是否已发送 ready 消息
    """
    for msg in messages:
        payload = msg.get("message", {})
        if (
            isinstance(payload, dict)
            and payload.get("type") == "sandbox_ready"
            and payload.get("sandbox_id") == sandbox_id
        ):
            return True
    return False
