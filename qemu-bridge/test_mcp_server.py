#!/usr/bin/env python3
"""
FridaMCP QEMU Bridge — 全功能测试脚本 v2
测试所有 MCP 工具 + Frida hook 功能。
"""
import json
import subprocess
import sys
import time
import requests

BASE = "http://127.0.0.1:8768"
PASS = 0
FAIL = 0
RESULTS = []


def call(method, params=None, msg_id=None):
    """Send a JSON-RPC request to the MCP server"""
    msg_id = msg_id or int(time.time() * 1000) % 100000
    payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        payload["params"] = params
    try:
        r = requests.post(f"{BASE}/mcp", json=payload, timeout=60)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def call_tool(name, args=None):
    """Call a tool and return the text result"""
    resp = call("tools/call", {"name": name, "arguments": args or {}})
    if "error" in resp:
        return None, resp["error"]
    if "result" in resp and "content" in resp["result"]:
        return resp["result"]["content"][0]["text"], None
    return None, "Unexpected response"


def test(desc, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        status = "✅"
    else:
        FAIL += 1
        status = "❌"
    line = f"  {status} {desc}"
    if detail and not condition:
        line += f" — {detail[:100]}"
    print(line)
    RESULTS.append(line)


print("=" * 60)
print("FridaMCP QEMU Bridge v2 — 全功能测试")
print("=" * 60)

# ==========================================
# Part 1: 基础 MCP 功能 (9 tools)
# ==========================================

print("\n[1] 健康检查")
r = requests.get(f"{BASE}/", timeout=5)
data = r.json()
test("GET / 返回服务器信息", data.get("name") == "FridaMCP", str(data))
test("版本 2.0", data.get("version") == "2.0", str(data))
test("工具数 18", data.get("tools") == 18, str(data))

print("\n[2] MCP 初始化")
resp = call("initialize")
test("initialize 返回 protocolVersion", "protocolVersion" in resp.get("result", {}), str(resp))
test("serverInfo.name = FridaMCP", resp.get("result", {}).get("serverInfo", {}).get("name") == "FridaMCP", str(resp))
test("版本 2.0.0", resp.get("result", {}).get("serverInfo", {}).get("version") == "2.0.0", str(resp))

print("\n[3] 工具列表 (18个)")
resp = call("tools/list")
tools = resp.get("result", {}).get("tools", [])
test("返回工具列表", len(tools) >= 18, f"got {len(tools)} tools")

expected_tools = [
    "ping", "server_info", "get_device_info", "list_apps", "list_files",
    "read_file", "exec_shell", "get_logcat", "check_injection",
    "frida_list_processes", "frida_hook_local", "frida_hook_arm64",
    "frida_hook_write", "frida_hook_open", "frida_memory_read",
    "frida_list_modules", "frida_test", "frida_inject_gadget"
]
for t in expected_tools:
    found = any(tool["name"] == t for tool in tools)
    test(f"工具 {t} 存在", found)

print("\n[4] ping")
text, err = call_tool("ping")
test("ping 返回 pong", text == "pong", err or text)

print("\n[5] server_info")
text, err = call_tool("server_info")
test("server_info 包含端口", "8768" in (text or ""), err or (text or "")[:100])
test("server_info 包含 Frida gadget port", "27042" in (text or ""), err or (text or "")[:100])

print("\n[6] get_device_info")
text, err = call_tool("get_device_info")
test("get_device_info 包含 arm64", "arm64" in (text or ""), err or (text or "")[:100])

print("\n[7] list_files")
text, err = call_tool("list_files", {"path": "/system/bin"})
test("list_files /system/bin 返回内容", len(text or "") > 50, err or (text or "")[:100])
test("list_files 包含 toybox", "toybox" in (text or ""), err or (text or "")[:100])

print("\n[8] exec_shell")
text, err = call_tool("exec_shell", {"command": "echo FRIDAMCP_TEST_OK"})
test("exec_shell echo 返回正确", "FRIDAMCP_TEST_OK" in (text or ""), err or (text or "")[:100])

print("\n[9] notifications/initialized")
resp = call("notifications/initialized")
test("notifications/initialized 无错误", "error" not in resp, str(resp))

print("\n[10] 未知方法")
resp = call("unknown/method")
test("未知方法返回 -32601", resp.get("error", {}).get("code") == -32601, str(resp))

# ==========================================
# Part 2: Frida Hook 功能 (9 tools)
# ==========================================

print("\n[11] frida_list_processes")
text, err = call_tool("frida_list_processes")
test("返回进程列表", "processes" in (text or "") or "PID" in (text or "") or ": " in (text or ""), err or (text or "")[:200])

print("\n[12] frida_test (自检: hook sleep + memory read + process enum + hook write)")
text, err = call_tool("frida_test", {}, )
if err:
    test("frida_test 自检", False, str(err))
else:
    test("frida_test 返回结果", len(text or "") > 10, (text or "")[:200])
    test("进程枚举通过", "✅" in (text or "") and "Process enumeration" in (text or ""), (text or "")[:300])
    test("Hook sleep() 通过", "Hook sleep" in (text or "") and "✅" in (text or ""), (text or "")[:300])
    test("Memory read 通过", "Memory read" in (text or "") and "✅" in (text or ""), (text or "")[:300])
    test("Hook write() 通过", "Hook write" in (text or "") and "✅" in (text or ""), (text or "")[:300])

print("\n[13] frida_hook_write (hook write 捕获输出)")
# Start a python process that prints something
import subprocess as sp
proc = sp.Popen(["/home/z/.venv/bin/python3", "-c",
                  "import time;time.sleep(1);print('HOOK_WRITE_TEST');time.sleep(3)"])
time.sleep(0.5)
text, err = call_tool("frida_hook_write", {"pid": proc.pid, "timeout": 4})
proc.terminate(); proc.wait()
test("hook_write 返回 hook_installed", "hook_installed" in (text or ""), err or (text or "")[:200])
test("hook_write 捕获 HOOK_WRITE_TEST", "HOOK_WRITE_TEST" in (text or ""), err or (text or "")[:200])

print("\n[14] frida_memory_read (读取内存)")
proc = sp.Popen(["sleep", "5"])
text, err = call_tool("frida_memory_read", {"pid": proc.pid, "module_name": "libc.so.6", "size": 16})
proc.terminate(); proc.wait()
test("memory_read 返回 hex 数据", "hex" in (text or ""), err or (text or "")[:200])
test("memory_read 包含 ELF 头 (7f 45 4c 46)", "7f 45 4c 46" in (text or "") or "7f454c46" in (text or ""), err or (text or "")[:200])

print("\n[15] frida_list_modules (列出模块)")
proc = sp.Popen(["sleep", "5"])
text, err = call_tool("frida_list_modules", {"pid": proc.pid})
proc.terminate(); proc.wait()
test("list_modules 返回模块数", "count" in (text or "") or "modules" in (text or ""), err or (text or "")[:200])
test("list_modules 包含 libc", "libc" in (text or ""), err or (text or "")[:200])

print("\n[16] frida_hook_local (自定义脚本)")
proc = sp.Popen(["sleep", "5"])
text, err = call_tool("frida_hook_local", {
    "pid": proc.pid,
    "script": "send({type: 'custom_hook', arch: Process.arch, modules: Process.enumerateModules().length})",
    "timeout": 2
})
proc.terminate(); proc.wait()
test("hook_local 返回自定义消息", "custom_hook" in (text or ""), err or (text or "")[:200])
test("hook_local arch = x64", "x64" in (text or ""), err or (text or "")[:200])

print("\n[17] frida_hook_open (hook openat)")
import time as _time
proc = sp.Popen(["/home/z/.venv/bin/python3", "-c",
                  "import time,os;time.sleep(0.5);os.path.exists('/etc/hostname');time.sleep(3)"])
_time.sleep(1)
text, err = call_tool("frida_hook_open", {"pid": proc.pid, "timeout": 3})
proc.terminate(); proc.wait()
test("hook_open 返回 hook_installed", "hook_installed" in (text or "") or "open" in (text or ""), err or (text or "")[:200])

print("\n[18] SSE 端点")
try:
    result = sp.run(
        ["curl", "-sN", "--max-time", "3", f"{BASE}/sse"],
        capture_output=True, text=True, timeout=5
    )
    test("SSE 返回 endpoint 事件", "endpoint" in result.stdout, result.stdout[:100])
except Exception as e:
    test("SSE 端点可连接", False, str(e))

# ==========================================
# Summary
# ==========================================
print("\n" + "=" * 60)
print(f"测试结果: {PASS} 通过 / {FAIL} 失败 / {PASS+FAIL} 总计")
print("=" * 60)

if FAIL > 0:
    print("\n失败项:")
    for r in RESULTS:
        if "❌" in r:
            print(r)

sys.exit(0 if FAIL == 0 else 1)
