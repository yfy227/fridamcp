#!/usr/bin/env python3
"""
FridaMCP QEMU Bridge — 全功能测试脚本
逐个测试所有 MCP 工具，验证返回结果。
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
        r = requests.post(f"{BASE}/mcp", json=payload, timeout=30)
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

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(f"  ✅ {name}")
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        RESULTS.append(f"  ❌ {name} — {detail}")
        print(f"  ❌ {name} — {detail}")

print("=" * 60)
print("FridaMCP QEMU Bridge — 全功能测试")
print("=" * 60)

# 1. Health check
print("\n[1] 健康检查")
r = requests.get(f"{BASE}/", timeout=5)
data = r.json()
test("GET / 返回服务器信息", data.get("name") == "FridaMCP", f"got {data}")
test("服务器状态 running", data.get("status") == "running", f"got {data}")
test("端口 8768", data.get("port") == 8768, f"got {data}")

# 2. MCP Initialize
print("\n[2] MCP 初始化")
resp = call("initialize")
result = resp.get("result", {})
test("initialize 返回 protocolVersion", result.get("protocolVersion") == "2024-11-05", str(resp))
test("serverInfo.name = FridaMCP", result.get("serverInfo", {}).get("name") == "FridaMCP", str(resp))
test("capabilities.tools 存在", "tools" in result.get("capabilities", {}), str(resp))

# 3. tools/list
print("\n[3] 工具列表")
resp = call("tools/list")
tools = resp.get("result", {}).get("tools", [])
tool_names = [t["name"] for t in tools]
test("返回工具列表", len(tools) >= 9, f"got {len(tools)} tools")
expected_tools = ["ping", "server_info", "get_device_info", "list_apps", "list_files", "read_file", "exec_shell", "get_logcat", "check_injection"]
for t in expected_tools:
    test(f"工具 {t} 存在", t in tool_names, f"missing {t}")

# 4. ping
print("\n[4] ping")
text, err = call_tool("ping")
test("ping 返回 pong", text == "pong", f"got '{text}' err={err}")

# 5. server_info
print("\n[5] server_info")
text, err = call_tool("server_info")
test("server_info 包含端口", text and "8768" in text, f"got '{text}'")
test("server_info 包含 Rootfs", text and "Rootfs" in text, f"got '{text}'")

# 6. get_device_info
print("\n[6] get_device_info")
text, err = call_tool("get_device_info")
test("get_device_info 包含 arm64", text and "arm64" in text, f"got '{text[:100]}'")
test("get_device_info 包含 QEMU", text and "QEMU" in text, f"got '{text[:100]}'")

# 7. list_files
print("\n[7] list_files")
text, err = call_tool("list_files", {"path": "/system/bin"})
test("list_files /system/bin 返回内容", text and len(text) > 50, f"got '{text[:100]}'" if text else f"err={err}")
test("list_files 包含 toybox 或 ls", text and ("toybox" in text or "ls" in text), f"got '{text[:100]}'")

# 8. list_files (root)
print("\n[8] list_files /")
text, err = call_tool("list_files", {"path": "/"})
test("list_files / 返回内容", text and len(text) > 10, f"got '{text[:100]}'" if text else f"err={err}")

# 9. read_file
print("\n[9] read_file")
text, err = call_tool("read_file", {"path": "/system/build.prop"})
test("read_file build.prop 返回内容", text and len(text) > 50, f"got '{text[:100]}'" if text else f"err={err}")
test("read_file 包含 ro.build", text and "ro.build" in text, f"got '{text[:100]}'")

# 10. exec_shell
print("\n[10] exec_shell")
text, err = call_tool("exec_shell", {"command": "ls /system/lib64/"})
test("exec_shell ls 返回内容", text and len(text) > 10, f"got '{text[:100]}'" if text else f"err={err}")

# 11. exec_shell (echo)
print("\n[11] exec_shell echo")
text, err = call_tool("exec_shell", {"command": "echo FRIDAMCP_TEST_OK"})
test("exec_shell echo 返回 FRIDAMCP_TEST_OK", text and "FRIDAMCP_TEST_OK" in text, f"got '{text}'")

# 12. get_logcat
print("\n[12] get_logcat")
text, err = call_tool("get_logcat", {"lines": 5})
test("get_logcat 返回内容（可能为空，因为无 Android runtime）", text is not None, f"err={err}")

# 13. check_injection
print("\n[13] check_injection")
text, err = call_tool("check_injection", {"package_name": "com.android.settings"})
test("check_injection 返回内容", text is not None, f"err={err}")

# 14. list_apps
print("\n[14] list_apps")
text, err = call_tool("list_apps")
test("list_apps 返回内容（可能为空，因为无 PackageManager）", text is not None, f"err={err}")

# 15. notifications/initialized
print("\n[15] notifications/initialized")
resp = call("notifications/initialized")
test("notifications/initialized 无错误", "error" not in resp, str(resp))

# 16. ping (JSON-RPC method)
print("\n[16] ping (JSON-RPC)")
resp = call("ping")
test("ping method 返回 ok", resp.get("result", {}).get("status") == "ok", str(resp))

# 17. SSE endpoint
print("\n[17] SSE 端点")
try:
    import subprocess as sp
    result = sp.run(
        ["curl", "-sN", "--max-time", "3", f"{BASE}/sse"],
        capture_output=True, text=True, timeout=5
    )
    output = result.stdout
    test("SSE 返回 endpoint 事件", "endpoint" in output, f"got '{output[:100]}'")
except Exception as e:
    test("SSE 端点可连接", False, str(e))

# 18. Unknown method
print("\n[18] 未知方法")
resp = call("unknown/method")
test("未知方法返回错误", resp.get("error", {}).get("code") == -32601, str(resp))

# Summary
print("\n" + "=" * 60)
print(f"测试结果: {PASS} 通过 / {FAIL} 失败 / {PASS+FAIL} 总计")
print("=" * 60)

if FAIL > 0:
    print("\n失败项:")
    for r in RESULTS:
        if "❌" in r:
            print(r)

sys.exit(0 if FAIL == 0 else 1)
