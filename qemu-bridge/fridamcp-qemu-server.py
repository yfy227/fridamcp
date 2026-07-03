#!/usr/bin/env python3
"""
FridaMCP QEMU Bridge Server
Runs an MCP server on x86_64 that bridges to Android rootfs via qemu-aarch64-static.
Exposes Android tools + Frida hook functionality via MCP protocol.
"""
import json
import subprocess
import os
import sys
import time
import threading
import http.server
import uuid
from urllib.parse import parse_qs, urlparse

ROOTFS = "/home/z/my-project/redroid-rootfs"
QEMU = "/home/z/bin/qemu-aarch64-static"
GADGET_ARM64 = "/system/lib64/frida-gadget-arm64.so"
GADGET_PORT = 27042
PORT = 8768

sessions = {}
hook_sessions = {}  # frida hook sessions


def run_android(cmd, timeout=10):
    """Run a command in the Android rootfs via qemu-user"""
    try:
        result = subprocess.run(
            [QEMU, "-L", ROOTFS, f"{ROOTFS}{cmd.split()[0]}"] + cmd.split()[1:],
            capture_output=True, text=True, timeout=timeout,
            env={"HOME": "/data", "PATH": "/system/bin:/system/xbin"}
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    except Exception as e:
        return f"Error: {e}"


def frida_hook_process(pid, script_code, timeout=10):
    """Attach frida to a local process and run a hook script"""
    try:
        import frida
        session = frida.attach(pid)
        script = session.create_script(script_code)

        messages = []

        def on_message(msg, data):
            messages.append(msg)

        script.on('message', on_message)
        script.load()
        time.sleep(timeout)
        session.detach()

        results = []
        for m in messages:
            if 'payload' in m:
                results.append(m['payload'])
            elif 'description' in m:
                results.append({'error': m['description']})
        return results
    except Exception as e:
        return [{'error': str(e)}]


def frida_hook_arm64(binary_path, script_code, timeout=10):
    """Run an arm64 binary under qemu with frida-gadget injected, then hook it"""
    try:
        import frida
        import socket

        # Start qemu with frida-gadget preloaded
        qemu_proc = subprocess.Popen(
            [QEMU, "-L", ROOTFS,
             "-E", f"LD_PRELOAD={GADGET_ARM64}",
             f"{ROOTFS}{binary_path}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Wait for gadget to start listening
        time.sleep(2)

        # Check if gadget port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        port_open = sock.connect_ex(('127.0.0.1', GADGET_PORT)) == 0
        sock.close()

        if not port_open:
            qemu_proc.terminate()
            qemu_proc.wait()
            return [{'error': 'frida-gadget did not start listening on port 27042'}]

        # Connect to gadget
        device = frida.get_device_manager().add_remote_device(f'127.0.0.1:{GADGET_PORT}')
        procs = device.enumerate_processes()

        if not procs:
            qemu_proc.terminate()
            qemu_proc.wait()
            return [{'error': 'No processes found in gadget'}]

        session = device.attach(procs[0])
        script = session.create_script(script_code)

        messages = []

        def on_message(msg, data):
            messages.append(msg)

        script.on('message', on_message)
        script.load()
        time.sleep(timeout)
        session.detach()

        qemu_proc.terminate()
        try:
            qemu_proc.wait(timeout=3)
        except:
            qemu_proc.kill()

        results = []
        for m in messages:
            if 'payload' in m:
                results.append(m['payload'])
            elif 'description' in m:
                results.append({'error': m['description']})
        return results
    except Exception as e:
        return [{'error': str(e)}]


def get_tools_list():
    tools = [
        # 基础工具
        {"name": "ping", "description": "Health check"},
        {"name": "server_info", "description": "Get MCP server info"},
        {"name": "get_device_info", "description": "Get Android device info"},
        {"name": "list_apps", "description": "List installed apps"},
        {"name": "list_files", "description": "List directory", "params": {"path": "string"}},
        {"name": "read_file", "description": "Read file content", "params": {"path": "string"}},
        {"name": "exec_shell", "description": "Execute shell command in Android", "params": {"command": "string"}},
        {"name": "get_logcat", "description": "Get logcat", "params": {"lines": "integer"}},
        {"name": "check_injection", "description": "Check if app has frida-gadget", "params": {"package_name": "string"}},
        # Frida hook 工具
        {"name": "frida_list_processes", "description": "List local processes visible to frida"},
        {"name": "frida_hook_local", "description": "Hook a local (x86_64) process by PID", "params": {"pid": "integer", "script": "string", "timeout": "integer"}},
        {"name": "frida_hook_arm64", "description": "Run arm64 binary with frida-gadget and hook it", "params": {"binary_path": "string", "script": "string", "timeout": "integer"}},
        {"name": "frida_hook_write", "description": "Hook write() to capture stdout/stderr of a process", "params": {"pid": "integer", "timeout": "integer"}},
        {"name": "frida_hook_open", "description": "Hook openat() to monitor file access of a process", "params": {"pid": "integer", "timeout": "integer"}},
        {"name": "frida_memory_read", "description": "Read memory at a module's base address", "params": {"pid": "integer", "module_name": "string", "size": "integer"}},
        {"name": "frida_list_modules", "description": "List loaded modules of a process", "params": {"pid": "integer"}},
        {"name": "frida_test", "description": "Run frida self-test (hook sleep + memory read + process enum)"},
        {"name": "frida_inject_gadget", "description": "Inject frida-gadget into arm64 binary and return port", "params": {"binary_path": "string"}},
        # 高级 JS 脚本加载
        {"name": "frida_load_script", "description": "加载 JS 脚本到进程 (支持内联脚本/文件路径), 返回所有 hook 消息", "params": {"pid": "integer", "script": "string", "script_file": "string", "timeout": "integer"}},
        {"name": "frida_hook_function", "description": "Hook 指定模块的函数 (Interceptor.attach)", "params": {"pid": "integer", "module": "string", "function": "string", "on_enter": "string", "on_leave": "string", "timeout": "integer"}},
        {"name": "frida_replace_function", "description": "替换函数实现 (Interceptor.replace)", "params": {"pid": "integer", "module": "string", "function": "string", "replacement": "string", "timeout": "integer"}},
        {"name": "frida_call_export", "description": "调用模块导出函数", "params": {"pid": "integer", "module": "string", "function": "string", "args": "string"}},
        {"name": "frida_scan_memory", "description": "扫描进程内存中的模式匹配", "params": {"pid": "integer", "pattern": "string", "module": "string", "max_results": "integer"}},
        {"name": "frida_trace_classes", "description": "Hook arm64 进程的 Java 类方法 (需 frida-gadget)", "params": {"binary_path": "string", "class_pattern": "string", "timeout": "integer"}},
    ]
    return tools


def handle_tool_call(name, args):
    # 基础工具
    if name == "ping":
        return "pong"
    elif name == "server_info":
        return f"FridaMCP QEMU Bridge\nPort: {PORT}\nRootfs: {ROOTFS}\nSessions: {len(sessions)}\nHook sessions: {len(hook_sessions)}\nFrida gadget port: {GADGET_PORT}"
    elif name == "get_device_info":
        version = run_android("/system/bin/getprop ro.build.version.release")
        model = run_android("/system/bin/getprop ro.product.model")
        return f"Model: {model or 'redroid_arm64'}\nAndroid: {version or '13'}\nABI: arm64-v8a\nKernel: QEMU user mode"
    elif name == "list_apps":
        output = run_android("/system/bin/pm list packages")
        return output or "pm not available in user mode"
    elif name == "list_files":
        path = args.get("path", "/")
        return run_android(f"/system/bin/ls -la {path}")
    elif name == "read_file":
        path = args.get("path", "/")
        return run_android(f"/system/bin/cat {path}")
    elif name == "exec_shell":
        cmd = args.get("command", "")
        return run_android(f"/system/bin/sh -c '{cmd}'")
    elif name == "get_logcat":
        lines = args.get("lines", 100)
        return run_android(f"/system/bin/logcat -d -t {lines}")
    elif name == "check_injection":
        pkg = args.get("package_name", "")
        return run_android(f"/system/bin/sh -c 'pm path {pkg} | head -1'")

    # Frida hook 工具
    elif name == "frida_list_processes":
        try:
            import frida
            device = frida.get_local_device()
            procs = device.enumerate_processes()
            lines = [f"  {p.pid}: {p.name}" for p in procs]
            return f"Frida processes ({len(procs)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    elif name == "frida_hook_local":
        pid = args.get("pid", 0)
        script_code = args.get("script", "send({status: 'connected'})")
        timeout = args.get("timeout", 5)
        results = frida_hook_process(pid, script_code, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_hook_arm64":
        binary_path = args.get("binary_path", "/system/bin/toybox")
        script_code = args.get("script", "send({status: 'connected', arch: Process.arch})")
        timeout = args.get("timeout", 5)
        results = frida_hook_arm64(binary_path, script_code, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_hook_write":
        pid = args.get("pid", 0)
        timeout = args.get("timeout", 5)
        script = """
        var libc = Process.findModuleByName("libc.so.6");
        if (!libc) { send({error: "libc not found"}); }
        else {
            var writeFn = libc.findExportByName("write");
            if (writeFn) {
                Interceptor.attach(writeFn, {
                    onEnter: function(args) {
                        var fd = args[0].toInt32();
                        if (fd <= 2) {
                            var n = args[2].toInt32();
                            if (n > 0 && n < 1024) {
                                try {
                                    var d = args[1].readUtf8String(n);
                                    if (d) send({type: "write", fd: fd, data: d.trim()});
                                } catch(e) {}
                            }
                        }
                    }
                });
                send({status: "hook_installed", function: "write", addr: writeFn.toString()});
            }
        }
        """
        results = frida_hook_process(pid, script, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_hook_open":
        pid = args.get("pid", 0)
        timeout = args.get("timeout", 5)
        script = """
        var libc = Process.findModuleByName("libc.so.6");
        if (!libc) { send({error: "libc not found"}); }
        else {
            var openatFn = libc.findExportByName("openat");
            if (openatFn) {
                Interceptor.attach(openatFn, {
                    onEnter: function(args) {
                        try {
                            var path = args[1].readUtf8String();
                            if (path) send({type: "open", path: path});
                        } catch(e) {}
                    }
                });
                send({status: "hook_installed", function: "openat", addr: openatFn.toString()});
            }
        }
        """
        results = frida_hook_process(pid, script, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_memory_read":
        pid = args.get("pid", 0)
        module_name = args.get("module_name", "libc.so.6")
        size = args.get("size", 32)
        script = f"""
        var mod = Process.findModuleByName("{module_name}");
        if (!mod) {{ send({{error: "module not found: {module_name}"}}); }}
        else {{
            var data = mod.base.readByteArray({size});
            var arr = new Uint8Array(data);
            var hex = [];
            for (var i = 0; i < arr.length; i++) hex.push(arr[i].toString(16).padStart(2, "0"));
            send({{type: "memory", module: "{module_name}", base: mod.base.toString(), size: {size}, hex: hex.join(" ")}});
        }}
        """
        results = frida_hook_process(pid, script, 3)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_list_modules":
        pid = args.get("pid", 0)
        script = """
        var mods = Process.enumerateModules();
        var list = [];
        for (var i = 0; i < mods.length; i++) {
            list.push({name: mods[i].name, base: mods[i].base.toString(), size: mods[i].size, path: mods[i].path});
        }
        send({type: "modules", count: mods.length, modules: list});
        """
        results = frida_hook_process(pid, script, 3)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_test":
        # Run self-test: hook sleep + memory read + process enum
        test_results = []

        # Test 1: Process enumeration
        try:
            import frida
            device = frida.get_local_device()
            procs = device.enumerate_processes()
            test_results.append(f"✅ Process enumeration: {len(procs)} processes")
        except Exception as e:
            test_results.append(f"❌ Process enumeration: {e}")

        # Test 2: Hook sleep()
        try:
            import frida
            proc = subprocess.Popen(["sleep", "5"])
            results = frida_hook_process(proc.pid, """
                var libc = Process.findModuleByName("libc.so.6");
                var fn = libc.findExportByName("sleep");
                Interceptor.attach(fn, {onEnter: function(a) { send({type: "hook", function: "sleep", arg: a[0].toInt32()}); }});
                send({type: "status", function: "sleep", addr: fn.toString()});
            """, 2)
            proc.terminate(); proc.wait()
            ok = any(r.get('type') == 'status' for r in results)
            test_results.append(f"{'✅' if ok else '❌'} Hook sleep(): {results[0] if results else 'no msg'}")
        except Exception as e:
            test_results.append(f"❌ Hook sleep(): {e}")

        # Test 3: Memory read
        try:
            import frida
            proc = subprocess.Popen(["sleep", "5"])
            results = frida_hook_process(proc.pid, """
                var libc = Process.findModuleByName("libc.so.6");
                var data = libc.base.readByteArray(16);
                var arr = new Uint8Array(data);
                var hex = [];
                for (var i = 0; i < arr.length; i++) hex.push(arr[i].toString(16).padStart(2, "0"));
                send({type: "memory", hex: hex.join(" ")});
            """, 2)
            proc.terminate(); proc.wait()
            ok = any(r.get('type') == 'memory' for r in results)
            test_results.append(f"{'✅' if ok else '❌'} Memory read: {results[0] if results else 'no msg'}")
        except Exception as e:
            test_results.append(f"❌ Memory read: {e}")

        # Test 4: Hook write()
        try:
            import frida
            proc = subprocess.Popen(["/home/z/.venv/bin/python3", "-c",
                                     "import time;time.sleep(1);print('FRIDA_TEST');time.sleep(3)"])
            time.sleep(0.5)
            results = frida_hook_process(proc.pid, """
                var libc = Process.findModuleByName("libc.so.6");
                var w = libc.findExportByName("write");
                Interceptor.attach(w, {
                    onEnter: function(a) {
                        var fd = a[0].toInt32();
                        if (fd == 1) {
                            var n = a[2].toInt32();
                            if (n > 0 && n < 256) {
                                try { var d = a[1].readUtf8String(n); if (d) send({type: "write", data: d.trim()}); } catch(e) {}
                            }
                        }
                    }
                });
                send({type: "status"});
            """, 3)
            proc.terminate(); proc.wait()
            writes = [r.get('data', '') for r in results if r.get('type') == 'write']
            ok = any('FRIDA' in w for w in writes)
            test_results.append(f"{'✅' if ok else '❌'} Hook write(): captured {writes}")
        except Exception as e:
            test_results.append(f"❌ Hook write(): {e}")

        all_pass = all("✅" in r for r in test_results)
        summary = f"\n{'ALL PASS' if all_pass else 'SOME FAILED'} ({sum(1 for r in test_results if '✅' in r)}/{len(test_results)})"
        return "Frida Self-Test Results:\n" + "\n".join(test_results) + summary

    elif name == "frida_inject_gadget":
        binary_path = args.get("binary_path", "/system/bin/toybox")
        try:
            import socket
            # Start qemu with gadget
            qemu_proc = subprocess.Popen(
                [QEMU, "-L", ROOTFS,
                 "-E", f"LD_PRELOAD={GADGET_ARM64}",
                 f"{ROOTFS}{binary_path}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            time.sleep(2)

            # Check port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            port_open = sock.connect_ex(('127.0.0.1', GADGET_PORT)) == 0
            sock.close()

            if port_open:
                result = f"✅ frida-gadget injected into {binary_path}\n"
                result += f"QEMU PID: {qemu_proc.pid}\n"
                result += f"Gadget port: {GADGET_PORT}\n"
                result += f"Connect: frida -H 127.0.0.1:{GADGET_PORT}"
            else:
                result = f"❌ Gadget port not open. QEMU may have crashed."
                qemu_proc.terminate()
                qemu_proc.wait()

            return result
        except Exception as e:
            return f"Error: {e}"

    # ==========================================
    # 高级 JS 脚本加载工具
    # ==========================================

    elif name == "frida_load_script":
        """加载 JS 脚本到指定进程 — 核心功能
        支持内联脚本或文件路径，返回所有 send() 消息"""
        pid = args.get("pid", 0)
        script_code = args.get("script", "")
        script_file = args.get("script_file", "")
        timeout = args.get("timeout", 5)

        # 从文件加载脚本
        if script_file and not script_code:
            try:
                # 支持 rootfs 内的路径
                if script_file.startswith("/system") or script_file.startswith("/data"):
                    real_path = f"{ROOTFS}{script_file}"
                else:
                    real_path = script_file
                with open(real_path, 'r') as f:
                    script_code = f.read()
            except Exception as e:
                return json.dumps({"error": f"Cannot read script file: {e}"}, ensure_ascii=False)

        if not script_code:
            return json.dumps({"error": "No script provided. Use 'script' or 'script_file' parameter."}, ensure_ascii=False)

        results = frida_hook_process(pid, script_code, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_hook_function":
        """Hook 指定模块的导出函数 — Interceptor.attach 的封装"""
        pid = args.get("pid", 0)
        module_name = args.get("module", "libc.so.6")
        func_name = args.get("function", "")
        on_enter = args.get("on_enter", "send({type:'enter', args: [args[0], args[1], args[2]]})")
        on_leave = args.get("on_leave", "send({type:'leave', retval: retval})")
        timeout = args.get("timeout", 5)

        if not func_name:
            return json.dumps({"error": "function parameter required"}, ensure_ascii=False)

        script_code = f"""
        var mod = Process.findModuleByName("{module_name}");
        if (!mod) {{
            send({{type: "error", msg: "Module not found: {module_name}"}});
        }} else {{
            var addr = mod.findExportByName("{func_name}");
            if (!addr) {{
                send({{type: "error", msg: "Function not found: {func_name} in {module_name}"}});
            }} else {{
                Interceptor.attach(addr, {{
                    onEnter: function(args) {{
                        try {{ {on_enter} }} catch(e) {{ send({{type:"enter_error", err:e.toString()}}) }}
                    }},
                    onLeave: function(retval) {{
                        try {{ {on_leave} }} catch(e) {{ send({{type:"leave_error", err:e.toString()}}) }}
                    }}
                }});
                send({{type: "hook_installed", module: "{module_name}", function: "{func_name}", addr: addr.toString()}});
            }}
        }}
        """

        results = frida_hook_process(pid, script_code, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_replace_function":
        """替换函数实现 — Interceptor.replace"""
        pid = args.get("pid", 0)
        module_name = args.get("module", "libc.so.6")
        func_name = args.get("function", "")
        replacement = args.get("replacement", "")
        timeout = args.get("timeout", 3)

        if not func_name or not replacement:
            return json.dumps({"error": "function and replacement required"}, ensure_ascii=False)

        script_code = f"""
        var mod = Process.findModuleByName("{module_name}");
        if (!mod) {{ send({{error: "Module not found: {module_name}"}}); }}
        else {{
            var orig = mod.findExportByName("{func_name}");
            if (!orig) {{ send({{error: "Function not found: {func_name}"}}); }}
            else {{
                var origCall = new NativeFunction(orig, 'int', ['int']);
                Interceptor.replace(orig, new NativeCallback(function() {{
                    {replacement}
                }}, 'int', ['int']));
                send({{type: "replaced", function: "{func_name}", addr: orig.toString()}});
            }}
        }}
        """

        results = frida_hook_process(pid, script_code, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_call_export":
        """调用模块导出函数"""
        pid = args.get("pid", 0)
        module_name = args.get("module", "libc.so.6")
        func_name = args.get("function", "")
        call_args = args.get("args", "[]")

        if not func_name:
            return json.dumps({"error": "function parameter required"}, ensure_ascii=False)

        script_code = f"""
        var mod = Process.findModuleByName("{module_name}");
        if (!mod) {{ send({{error: "Module not found"}}); }}
        else {{
            var addr = mod.findExportByName("{func_name}");
            if (!addr) {{ send({{error: "Export not found: {func_name}"}}); }}
            else {{
                // 自动推断参数个数 (最多8个)
                var fn = new NativeFunction(addr, 'pointer', ['pointer','pointer','pointer','pointer','pointer','pointer','pointer','pointer']);
                var args = {call_args};
                var a = [];
                for (var i = 0; i < 8; i++) {{
                    a.push(args[i] ? ptr(args[i]) : ptr(0));
                }}
                var ret = fn(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]);
                send({{type: "call_result", function: "{func_name}", ret: ret.toString()}});
            }}
        }}
        """

        results = frida_hook_process(pid, script_code, 3)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_scan_memory":
        """扫描进程内存中的模式匹配 (Memory.scan)"""
        pid = args.get("pid", 0)
        pattern = args.get("pattern", "")
        module_name = args.get("module", "")
        max_results = args.get("max_results", 10)

        if not pattern:
            return json.dumps({"error": "pattern parameter required (hex pattern like '7f 45 4c 46')"}, ensure_ascii=False)

        scan_range = ""
        if module_name:
            scan_range = f"""
            var mod = Process.findModuleByName("{module_name}");
            if (!mod) {{ send({{error: "Module not found"}}); }}
            else {{
                Memory.scan(mod.base, mod.size, "{pattern}", {{
                    onMatch: function(addr, size) {{
                        send({{type:"match", addr: addr.toString(), size: size}});
                        count++;
                        if (count >= {max_results}) return 'stop';
                    }},
                    onComplete: function() {{ send({{type:"complete", found: count}}); }}
                }});
            }}
            """
        else:
            scan_range = f"""
            var ranges = Process.enumerateRanges('r--');
            var count = 0;
            var found = 0;
            function scanNext(i) {{
                if (i >= ranges.length || found >= {max_results}) {{
                    send({{type:"complete", found: found, scanned: i}});
                    return;
                }}
                var r = ranges[i];
                Memory.scan(r.base, r.size, "{pattern}", {{
                    onMatch: function(addr, size) {{
                        found++;
                        send({{type:"match", addr: addr.toString(), size: size, range_base: r.base.toString()}});
                    }},
                    onComplete: function() {{ scanNext(i + 1); }}
                }});
            }}
            scanNext(0);
            """

        script_code = f"""
        var count = 0;
        {scan_range}
        send({{type: "scan_started", pattern: "{pattern}", module: "{module_name}"}})
        """

        results = frida_hook_process(pid, script_code, 5)
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif name == "frida_trace_classes":
        """Hook arm64 进程的 Java 类方法 (需 frida-gadget)"""
        binary_path = args.get("binary_path", "/system/bin/toybox")
        class_pattern = args.get("class_pattern", "*")
        timeout = args.get("timeout", 5)

        script_code = f"""
        send({{type: "status", msg: "gadget connected", arch: Process.arch}});

        // 尝试枚举 Java 类 (需要 Android runtime)
        if (typeof Java !== 'undefined') {{
            Java.perform(function() {{
                send({{type: "java_available"}});
                try {{
                    var classes = Java.enumerateLoadedClassesSync();
                    var matched = classes.filter(function(c) {{
                        return c.match(/{class_pattern}/);
                    }});
                    send({{type: "classes", total: classes.length, matched: matched.length, samples: matched.slice(0, 20)}});
                }} catch(e) {{
                    send({{type: "error", msg: e.toString()}});
                }}
            }});
        }} else {{
            send({{type: "error", msg: "Java runtime not available in qemu-user mode"}});
        }}

        // 列出 native 模块
        var mods = Process.enumerateModules();
        send({{type: "modules", count: mods.length, names: mods.map(m => m.name).slice(0, 10)}});
        """

        results = frida_hook_arm64(binary_path, script_code, timeout)
        return json.dumps(results, indent=2, ensure_ascii=False)

    return f"Unknown tool: {name}"


class MCPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/sse":
            self.handle_sse()
        elif parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "name": "FridaMCP",
                "version": "2.0",
                "status": "running",
                "port": PORT,
                "tools": 24,
                "frida_gadget_port": GADGET_PORT
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/mcp" or parsed.path == "/messages":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode()

            try:
                msg = json.loads(body)
                method = msg.get("method", "")
                msg_id = msg.get("id")
                params = msg.get("params", {})

                if method == "initialize":
                    result = {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "FridaMCP", "version": "2.0.0"},
                        "capabilities": {"tools": {}}
                    }
                    resp = {"jsonrpc": "2.0", "id": msg_id, "result": result}
                elif method == "notifications/initialized":
                    resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
                elif method == "tools/list":
                    resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": get_tools_list()}}
                elif method == "tools/call":
                    tool_name = params.get("name", "")
                    tool_args = params.get("arguments", {})
                    result = handle_tool_call(tool_name, tool_args)
                    resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": result}]}}
                elif method == "ping":
                    resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"status": "ok"}}
                else:
                    resp = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode())
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def handle_sse(self):
        session_id = str(uuid.uuid4())[:8]
        sessions[session_id] = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        self.wfile.write(f"event: endpoint\ndata: /messages?session_id={session_id}\n\n".encode())
        self.wfile.flush()

        import time
        while sessions.get(session_id):
            try:
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(15)
            except:
                break

        sessions.pop(session_id, None)


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), MCPHandler)
    print(f"FridaMCP QEMU Bridge v2.0 running on http://127.0.0.1:{PORT}")
    print(f"SSE:  http://127.0.0.1:{PORT}/sse")
    print(f"POST: http://127.0.0.1:{PORT}/mcp")
    print(f"Rootfs: {ROOTFS}")
    print(f"Tools: 24 (9 base + 9 frida hook + 6 advanced JS)")
    print(f"Frida gadget port: {GADGET_PORT}")
    server.serve_forever()
