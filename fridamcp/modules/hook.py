"""
Hook 管理模块

提供 Java 方法 Hook、Native 函数 Hook、Hook 列表、Hook 移除、方法追踪等工具。

所有 Hook 脚本默认经过沙箱包装（hook_sandbox.wrap_script_safely），
异常会被捕获并通过 send() 回传，不会导致目标进程崩溃。
"""

import json
import uuid
from typing import Dict, Any, List, Optional

from ..core.frida_client import frida_client
from ..core.session_manager import session_manager
from ..utils.logger import logger
from ..utils.hook_sandbox import (
    wrap_script_safely,
    validate_script,
    extract_sandbox_errors,
)


# Hook 脚本模板
HOOK_JAVA_METHOD_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";
    var className = "%(class_name)s";
    var methodName = "%(method_name)s";

    rpc.exports = {
        info: function() {
            return { hookId: hookId, className: className, methodName: methodName };
        }
    };

    var handler = function() {
        try {
            var clazz = Java.use(className);
            var overloads = clazz[methodName].overloads;
            if (overloads.length === 0) {
                send({ type: "error", hookId: hookId, message: "Method has no overloads" });
                return;
            }
            overloads.forEach(function(overload, idx) {
                overload.implementation = function() {
                    var args = [];
                    for (var i = 0; i < arguments.length; i++) {
                        try {
                            args.push(arguments[i] !== null ? arguments[i].toString() : "null");
                        } catch(e) {
                            args.push("<unstringifiable>");
                        }
                    }
                    send({
                        type: "hook_call",
                        hookId: hookId,
                        className: className,
                        methodName: methodName,
                        overloadIndex: idx,
                        args: args
                    });
                    var retval = this[methodName].apply(this, arguments);
                    try {
                        var retStr = retval !== null && retval !== undefined ? retval.toString() : "void";
                    } catch(e) {
                        retStr = "<unstringifiable>";
                    }
                    send({
                        type: "hook_return",
                        hookId: hookId,
                        className: className,
                        methodName: methodName,
                        retval: retStr
                    });
                    return retval;
                };
            });
            send({ type: "hook_attached", hookId: hookId, className: className, methodName: methodName, overloadCount: overloads.length });
        } catch(e) {
            send({ type: "error", hookId: hookId, message: "Hook failed: " + e.message });
        }
    };

    if (Java.available) {
        Java.perform(handler);
    } else {
        send({ type: "error", hookId: hookId, message: "Java runtime not available" });
    }
})();
"""

HOOK_NATIVE_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";
    var moduleName = "%(module_name)s";
    var funcName = "%(func_name)s";
    var offset = %(offset)s;

    rpc.exports = {
        info: function() {
            return { hookId: hookId, moduleName: moduleName, funcName: funcName, offset: offset };
        }
    };

    try {
        var addr = null;
        if (offset > 0) {
            var module = Process.findModuleByName(moduleName);
            if (!module) {
                send({ type: "error", hookId: hookId, message: "Module not found: " + moduleName });
                return;
            }
            addr = module.base.add(offset);
        } else {
            addr = Module.findExportByName(moduleName, funcName);
        }
        if (!addr) {
            send({ type: "error", hookId: hookId, message: "Function not found" });
            return;
        }
        Interceptor.attach(addr, {
            onEnter: function(args) {
                send({
                    type: "native_call",
                    hookId: hookId,
                    moduleName: moduleName,
                    funcName: funcName,
                    args: [args[0].toString(), args[1].toString(), args[2].toString()]
                });
            },
            onLeave: function(retval) {
                send({
                    type: "native_return",
                    hookId: hookId,
                    retval: retval.toString()
                });
            }
        });
        send({ type: "hook_attached", hookId: hookId, target: addr.toString() });
    } catch(e) {
        send({ type: "error", hookId: hookId, message: "Native hook failed: " + e.message });
    }
})();
"""

TRACE_METHOD_TEMPLATE = """
(function() {
    var hookId = "%(hook_id)s";
    var className = "%(class_name)s";

    rpc.exports = {
        info: function() {
            return { hookId: hookId, className: className };
        }
    };

    Java.perform(function() {
        try {
            var clazz = Java.use(className);
            var methods = clazz.class.getDeclaredMethods();
            var hookedCount = 0;
            methods.forEach(function(method) {
                var methodName = method.getName();
                try {
                    var overloads = clazz[methodName].overloads;
                    overloads.forEach(function(overload) {
                        overload.implementation = function() {
                            var args = [];
                            for (var i = 0; i < arguments.length; i++) {
                                try {
                                    args.push(arguments[i] !== null ? arguments[i].toString() : "null");
                                } catch(e) {
                                    args.push("<unstringifiable>");
                                }
                            }
                            send({
                                type: "trace_call",
                                hookId: hookId,
                                className: className,
                                methodName: methodName,
                                args: args
                            });
                            return this[methodName].apply(this, arguments);
                        };
                        hookedCount++;
                    });
                } catch(e) {
                    // skip unhookable methods
                }
            });
            send({ type: "hook_attached", hookId: hookId, className: className, hookedCount: hookedCount });
        } catch(e) {
            send({ type: "error", hookId: hookId, message: "Trace failed: " + e.message });
        }
    });
})();
"""


def register_tools(mcp):
    """向 MCP 服务器注册 Hook 管理工具"""

    def _load_sandboxed_script(
        session_id: str,
        source: str,
        script_name: str,
    ) -> Dict[str, Any]:
        """加载经过沙箱包装的脚本

        统一处理：
        1. 脚本静态校验（括号匹配、危险 API）
        2. 沙箱包装（异常隔离）
        3. 加载失败重试（卸载残留后重试一次）
        4. 沙箱就绪检查

        Args:
            session_id: 会话 ID
            source: 原始脚本源码
            script_name: 脚本名称

        Returns:
            包含 script_id / sandbox_id / warnings 的字典
        """
        # 1. 静态校验
        is_valid, errors, warnings = validate_script(source)
        if not is_valid:
            return {
                "error": "Script validation failed",
                "validation_errors": errors,
                "warnings": warnings,
            }

        # 2. 沙箱包装
        sandbox_id = f"sbx_{uuid.uuid4().hex[:8]}"
        safe_source = wrap_script_safely(source, sandbox_id=sandbox_id)

        # 3. 加载（带重试）
        try:
            result = frida_client.execute_script(
                session_id, safe_source, script_name=script_name
            )
        except Exception as load_err:
            logger.warning(
                f"First load failed for {script_name}: {load_err}, retrying..."
            )
            # 重试：可能是上次脚本残留导致
            try:
                session = session_manager.get_session(session_id)
                if session:
                    session.unload_all_scripts()
                result = frida_client.execute_script(
                    session_id, safe_source, script_name=script_name
                )
            except Exception as retry_err:
                return {
                    "error": f"Script load failed after retry: {retry_err}",
                    "original_error": str(load_err),
                    "warnings": warnings,
                }

        return {
            "script_id": result["script_id"],
            "sandbox_id": sandbox_id,
            "warnings": warnings,
        }

    @mcp.tool()
    def hook_method(
        session_id: str,
        class_name: str,
        method_name: str,
    ) -> Dict[str, Any]:
        """Hook 一个 Java 方法（沙箱保护）

        当目标方法被调用时，会记录参数和返回值到会话消息中。
        使用 get_messages(session_id) 查看调用记录。

        脚本经过沙箱包装，hook 回调中的异常会被捕获并通过 send() 回传，
        不会导致目标进程崩溃。

        Args:
            session_id: 会话 ID（通过 attach_process 或 spawn_app 获取）
            class_name: 完整类名，例如 com.example.app.LoginActivity
            method_name: 方法名，例如 checkPassword

        Returns:
            包含 hook_id / script_id / sandbox_id 的字典
        """
        try:
            hook_id = f"hook_{uuid.uuid4().hex[:8]}"
            source = HOOK_JAVA_METHOD_TEMPLATE % {
                "hook_id": hook_id,
                "class_name": class_name,
                "method_name": method_name,
            }
            load_result = _load_sandboxed_script(
                session_id, source, script_name=hook_id
            )
            if "error" in load_result:
                return load_result

            session = session_manager.get_session(session_id)
            if session:
                session.add_hook(
                    hook_id,
                    {
                        "type": "java_method",
                        "class_name": class_name,
                        "method_name": method_name,
                        "script_id": load_result["script_id"],
                        "sandbox_id": load_result.get("sandbox_id"),
                    },
                )
            return {
                "hook_id": hook_id,
                "script_id": load_result["script_id"],
                "sandbox_id": load_result.get("sandbox_id"),
                "session_id": session_id,
                "class_name": class_name,
                "method_name": method_name,
                "warnings": load_result.get("warnings", []),
            }
        except Exception as e:
            logger.error(f"hook_method failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def hook_native(
        session_id: str,
        module_name: str,
        func_name: Optional[str] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Hook 一个 Native 函数（沙箱保护）

        可以通过函数名或偏移量指定 Hook 目标。
        脚本经过沙箱包装，onEnter/onLeave 中的异常会被捕获。

        Args:
            session_id: 会话 ID
            module_name: 模块名，例如 libnative.so
            func_name: 函数名（与 offset 二选一）
            offset: 函数在模块中的偏移量（与 func_name 二选一）

        Returns:
            包含 hook_id / script_id / sandbox_id 的字典
        """
        try:
            hook_id = f"native_{uuid.uuid4().hex[:8]}"
            source = HOOK_NATIVE_TEMPLATE % {
                "hook_id": hook_id,
                "module_name": module_name,
                "func_name": func_name or "",
                "offset": offset,
            }
            load_result = _load_sandboxed_script(
                session_id, source, script_name=hook_id
            )
            if "error" in load_result:
                return load_result

            session = session_manager.get_session(session_id)
            if session:
                session.add_hook(
                    hook_id,
                    {
                        "type": "native",
                        "module_name": module_name,
                        "func_name": func_name,
                        "offset": offset,
                        "script_id": load_result["script_id"],
                        "sandbox_id": load_result.get("sandbox_id"),
                    },
                )
            return {
                "hook_id": hook_id,
                "script_id": load_result["script_id"],
                "sandbox_id": load_result.get("sandbox_id"),
                "session_id": session_id,
                "module_name": module_name,
                "func_name": func_name,
                "offset": offset,
                "warnings": load_result.get("warnings", []),
            }
        except Exception as e:
            logger.error(f"hook_native failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def trace_method(
        session_id: str,
        class_name: str,
    ) -> Dict[str, Any]:
        """追踪一个类的所有方法调用（沙箱保护）

        会 Hook 指定类的所有方法，记录每次调用。
        脚本经过沙箱包装，单个方法 hook 失败不影响其他方法。

        Args:
            session_id: 会话 ID
            class_name: 完整类名

        Returns:
            包含 hook_id / script_id / sandbox_id 的字典
        """
        try:
            hook_id = f"trace_{uuid.uuid4().hex[:8]}"
            source = TRACE_METHOD_TEMPLATE % {
                "hook_id": hook_id,
                "class_name": class_name,
            }
            load_result = _load_sandboxed_script(
                session_id, source, script_name=hook_id
            )
            if "error" in load_result:
                return load_result

            session = session_manager.get_session(session_id)
            if session:
                session.add_hook(
                    hook_id,
                    {
                        "type": "trace",
                        "class_name": class_name,
                        "script_id": load_result["script_id"],
                        "sandbox_id": load_result.get("sandbox_id"),
                    },
                )
            return {
                "hook_id": hook_id,
                "script_id": load_result["script_id"],
                "sandbox_id": load_result.get("sandbox_id"),
                "session_id": session_id,
                "class_name": class_name,
                "warnings": load_result.get("warnings", []),
            }
        except Exception as e:
            logger.error(f"trace_method failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def run_hook_script(
        session_id: str,
        script_source: str,
        script_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """运行自定义 Hook 脚本（沙箱保护）

        允许 AI 编写任意 Frida JS 脚本进行 hook，脚本会经过沙箱包装：
        - 顶层异常被捕获，通过 send() 回传
        - Java.perform / Interceptor.attach 回调被包裹 try-catch
        - rpc.exports 函数被包裹 try-catch
        - 错误数量限制，防止刷屏

        加载前会进行静态校验（括号匹配、危险 API 检测），
        校验失败会返回错误而非加载。

        Args:
            session_id: 会话 ID
            script_source: Frida JavaScript 脚本源码
            script_name: 可选，脚本名称

        Returns:
            包含 script_id / sandbox_id / warnings 的字典，
            或校验/加载错误信息
        """
        try:
            name = script_name or f"custom_{uuid.uuid4().hex[:8]}"
            load_result = _load_sandboxed_script(
                session_id, script_source, script_name=name
            )
            if "error" in load_result:
                return load_result
            return {
                "script_id": load_result["script_id"],
                "sandbox_id": load_result.get("sandbox_id"),
                "session_id": session_id,
                "script_name": name,
                "warnings": load_result.get("warnings", []),
                "status": "loaded",
            }
        except Exception as e:
            logger.error(f"run_hook_script failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def validate_hook_script(script_source: str) -> Dict[str, Any]:
        """校验 Hook 脚本（不加载）

        对脚本进行轻量级静态检查，返回校验结果。
        可用于 AI 在加载前预检脚本质量。

        检查项：
        - 括号匹配（花括号/圆括号/方括号）
        - 危险 API 使用（Process.kill、Backtracer.ACCURATE 等）
        - 禁止模式（无 sleep 的无限循环）

        Args:
            script_source: Frida JavaScript 脚本源码

        Returns:
            校验结果，包含 is_valid / errors / warnings
        """
        try:
            is_valid, errors, warnings = validate_script(script_source)
            return {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings,
            }
        except Exception as e:
            logger.error(f"validate_hook_script failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_sandbox_errors(
        session_id: str,
        clear: bool = False,
    ) -> List[Dict[str, Any]]:
        """获取会话中沙箱捕获的错误

        沙箱包装的脚本在运行时捕获的异常会通过 send() 回传，
        此工具提取这些错误消息，供 AI 调试迭代。

        Args:
            session_id: 会话 ID
            clear: 是否在读取后清空消息

        Returns:
            沙箱错误消息列表
        """
        try:
            messages = frida_client.get_messages(session_id, clear=clear)
            return extract_sandbox_errors(messages)
        except Exception as e:
            logger.error(f"get_sandbox_errors failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def list_hooks(session_id: str) -> List[Dict[str, Any]]:
        """列出指定会话的所有 Hook

        Args:
            session_id: 会话 ID

        Returns:
            Hook 列表
        """
        try:
            session = session_manager.get_session(session_id)
            if session is None:
                return [{"error": f"Session not found: {session_id}"}]
            return [
                {"hook_id": hid, **info}
                for hid, info in session.hooks.items()
            ]
        except Exception as e:
            logger.error(f"list_hooks failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def unhook(
        session_id: str,
        hook_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """移除 Hook

        Args:
            session_id: 会话 ID
            hook_id: Hook ID，None 则移除所有 Hook

        Returns:
            操作结果
        """
        try:
            session = session_manager.get_session(session_id)
            if session is None:
                return {"error": f"Session not found: {session_id}"}

            if hook_id:
                info = session.hooks.get(hook_id)
                if info:
                    session.unload_script(info["script_id"])
                    session.remove_hook(hook_id)
                    return {"success": True, "removed": hook_id}
                return {"error": f"Hook not found: {hook_id}"}
            else:
                # 移除所有 Hook
                count = len(session.hooks)
                session.unload_all_scripts()
                session.hooks.clear()
                return {"success": True, "removed_count": count}
        except Exception as e:
            logger.error(f"unhook failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_hook_messages(
        session_id: str,
        hook_id: Optional[str] = None,
        clear: bool = False,
    ) -> List[Dict[str, Any]]:
        """获取 Hook 捕获的消息

        Args:
            session_id: 会话 ID
            hook_id: 可选，只返回指定 Hook 的消息
            clear: 是否在读取后清空消息

        Returns:
            消息列表
        """
        try:
            messages = frida_client.get_messages(session_id, clear=clear)
            if hook_id:
                messages = [
                    m for m in messages
                    if m.get("message", {}).get("hookId") == hook_id
                ]
            return messages
        except Exception as e:
            logger.error(f"get_hook_messages failed: {e}")
            return [{"error": str(e)}]

    logger.info("Hook module tools registered")
