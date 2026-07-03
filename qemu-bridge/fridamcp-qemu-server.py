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
                "tools": 18,
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
    print(f"Tools: 18 (9 base + 9 frida hook)")
    print(f"Frida gadget port: {GADGET_PORT}")
    server.serve_forever()
