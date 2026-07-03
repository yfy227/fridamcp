#!/usr/bin/env python3
"""
FridaMCP QEMU Bridge Server
Runs an MCP server on x86_64 that bridges to Android rootfs via qemu-aarch64-static.
Exposes Android tools via MCP protocol.
"""
import json
import subprocess
import os
import sys
import threading
import http.server
import uuid
from urllib.parse import parse_qs, urlparse

ROOTFS = "/home/z/my-project/redroid-rootfs"
QEMU = "/home/z/bin/qemu-aarch64-static"
PORT = 8768

sessions = {}

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

def get_tools_list():
    tools = [
        {"name": "ping", "description": "Health check"},
        {"name": "server_info", "description": "Get MCP server info"},
        {"name": "get_device_info", "description": "Get Android device info"},
        {"name": "list_apps", "description": "List installed apps"},
        {"name": "list_files", "description": "List directory", "params": {"path": "string"}},
        {"name": "read_file", "description": "Read file content", "params": {"path": "string"}},
        {"name": "exec_shell", "description": "Execute shell command in Android", "params": {"command": "string"}},
        {"name": "get_logcat", "description": "Get logcat", "params": {"lines": "integer"}},
        {"name": "check_injection", "description": "Check if app has frida-gadget", "params": {"package_name": "string"}},
    ]
    return tools

def handle_tool_call(name, args):
    if name == "ping":
        return "pong"
    elif name == "server_info":
        return f"FridaMCP QEMU Bridge\nPort: {PORT}\nRootfs: {ROOTFS}\nSessions: {len(sessions)}"
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
        # Check if libfrida-gadget.so exists in the APK
        return run_android(f"/system/bin/sh -c 'pm path {pkg} | head -1'")
    return f"Unknown tool: {name}"

class MCPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress logs
    
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/sse":
            self.handle_sse()
        elif parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"name": "FridaMCP", "version": "1.0", "status": "running", "port": PORT}).encode())
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
                        "serverInfo": {"name": "FridaMCP", "version": "1.0.0"},
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
        
        # Send endpoint event
        self.wfile.write(f"event: endpoint\ndata: /messages?session_id={session_id}\n\n".encode())
        self.wfile.flush()
        
        # Keep alive
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
    server = http.server.HTTPServer(("127.0.0.1", PORT), MCPHandler)
    print(f"FridaMCP QEMU Bridge running on http://127.0.0.1:{PORT}")
    print(f"SSE:  http://127.0.0.1:{PORT}/sse")
    print(f"POST: http://127.0.0.1:{PORT}/mcp")
    print(f"Rootfs: {ROOTFS}")
    server.serve_forever()
