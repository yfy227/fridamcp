#!/usr/bin/env python3
"""
FridaMCP QEMU Bridge — JS 脚本加载专项测试
测试核心的 frida_load_script, frida_hook_function, frida_scan_memory 等
"""
import requests
import subprocess as sp
import time
import json
import sys

BASE = "http://127.0.0.1:8768"
PASS = 0
FAIL = 0

def call_tool(name, args=None, timeout=30):
    try:
        r = requests.post(f"{BASE}/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args or {}}
        }, timeout=timeout).json()
        text = r.get("result", {}).get("content", [{}])[0].get("text", "")
        try:
            return json.loads(text), text
        except:
            return None, text
    except Exception as e:
        return None, str(e)

def test(name, ok, detail=""):
    global PASS, FAIL
    print(f'  {"✅" if ok else "❌"} {name}')
    if not ok and detail:
        print(f'      {detail[:200]}')
    if ok: PASS += 1
    else: FAIL += 1

print("=" * 55)
print("FridaMCP — JS 脚本加载专项测试")
print("=" * 55)

# ==========================================
# 1. frida_load_script — 内联脚本
# ==========================================
print("\n[1] frida_load_script — 内联 JS 脚本")
p = sp.Popen(["sleep", "5"])
data, text = call_tool("frida_load_script", {
    "pid": p.pid,
    "script": """
    var libc = Process.findModuleByName("libc.so.6");
    send({type: "info", arch: Process.arch, modules: Process.enumerateModules().length});
    send({type: "libc", base: libc.base.toString(), size: libc.size});
    send({type: "done"});
    """,
    "timeout": 2
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("返回消息列表", len(messages) >= 1, text[:200])
test("包含 arch=x64", any("x64" in str(m) for m in messages), str(messages)[:200])
test("包含 modules 数量", any("modules" in str(m) for m in messages))
test("包含 libc 信息", any("libc" in str(m) for m in messages))

# ==========================================
# 2. frida_load_script — 从文件加载
# ==========================================
print("\n[2] frida_load_script — 从文件加载 JS")
# 创建测试脚本文件
with open("/tmp/hook_test.js", "w") as f:
    f.write("""
var mods = Process.enumerateModules();
send({type: "file_loaded", module_count: mods.length});
mods.forEach(function(m) {
    if (m.name.indexOf("libc") >= 0) {
        send({type: "module", name: m.name, base: m.base.toString(), size: m.size});
    }
});
send({type: "file_done"});
""")
p = sp.Popen(["sleep", "5"])
data, text = call_tool("frida_load_script", {
    "pid": p.pid,
    "script_file": "/tmp/hook_test.js",
    "timeout": 2
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("文件脚本加载成功", len(messages) >= 1, text[:200])
test("包含 file_loaded", any("file_loaded" in str(m) for m in messages))
test("包含 module 信息", any("module" in str(m) for m in messages))

# ==========================================
# 3. frida_hook_function — hook sleep()
# ==========================================
print("\n[3] frida_hook_function — hook libc sleep()")
p = sp.Popen(["sleep", "3"])
data, text = call_tool("frida_hook_function", {
    "pid": p.pid,
    "module": "libc.so.6",
    "function": "sleep",
    "on_enter": "send({type:'sleep_called', seconds: args[0].toInt32()})",
    "on_leave": "send({type:'sleep_returned', ret: retval.toInt32()})",
    "timeout": 3
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("hook_installed 确认", any("hook_installed" in str(m) for m in messages), str(messages)[:200])
test("sleep_called 触发", any("sleep_called" in str(m) for m in messages))
test("sleep_returned 触发", any("sleep_returned" in str(m) for m in messages))

# ==========================================
# 4. frida_hook_function — hook write()
# ==========================================
print("\n[4] frida_hook_function — hook libc write()")
p = sp.Popen(["/home/z/.venv/bin/python3", "-c",
              "import time;time.sleep(0.5);print('HOOK_FN_TEST');time.sleep(3)"])
time.sleep(0.5)
data, text = call_tool("frida_hook_function", {
    "pid": p.pid,
    "module": "libc.so.6",
    "function": "write",
    "on_enter": """
        var fd = args[0].toInt32();
        if (fd == 1) {
            var n = args[2].toInt32();
            if (n > 0 && n < 256) {
                try {
                    var d = args[1].readUtf8String(n);
                    if (d) send({type:'write_captured', data: d.trim()});
                } catch(e) {}
            }
        }
    """,
    "timeout": 3
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("write hook_installed", any("hook_installed" in str(m) for m in messages))
test("write_captured HOOK_FN_TEST", any("HOOK_FN_TEST" in str(m) for m in messages), str(messages)[:200])

# ==========================================
# 5. frida_scan_memory — 在 libc 中扫描 ELF 头
# ==========================================
print("\n[5] frida_scan_memory — 扫描 ELF 头模式 (7f 45 4c 46)")
p = sp.Popen(["sleep", "5"])
data, text = call_tool("frida_scan_memory", {
    "pid": p.pid,
    "pattern": "7f 45 4c 46",
    "module": "libc.so.6",
    "max_results": 3
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("扫描返回结果", len(messages) >= 1, text[:200])
test("找到 match", any("match" in str(m) for m in messages), str(messages)[:200])
test("包含 complete", any("complete" in str(m) for m in messages))

# ==========================================
# 6. frida_load_script — 复杂多函数 hook
# ==========================================
print("\n[6] frida_load_script — 复杂多函数 hook 脚本")
p = sp.Popen(["/home/z/.venv/bin/python3", "-c",
              "import time,os;time.sleep(0.5);os.path.exists('/etc/hostname');print('COMPLEX_TEST');time.sleep(3)"])
time.sleep(0.5)
data, text = call_tool("frida_load_script", {
    "pid": p.pid,
    "script": """
    var libc = Process.findModuleByName("libc.so.6");
    
    // Hook openat
    var openat = libc.findExportByName("openat");
    if (openat) {
        Interceptor.attach(openat, {
            onEnter: function(args) {
                try {
                    var path = args[1].readUtf8String();
                    if (path) send({type: "openat", path: path});
                } catch(e) {}
            }
        });
    }
    
    // Hook write
    var write = libc.findExportByName("write");
    if (write) {
        Interceptor.attach(write, {
            onEnter: function(args) {
                var fd = args[0].toInt32();
                if (fd == 1) {
                    var n = args[2].toInt32();
                    if (n > 0 && n < 256) {
                        try {
                            var d = args[1].readUtf8String(n);
                            if (d) send({type: "write", data: d.trim()});
                        } catch(e) {}
                    }
                }
            }
        });
    }
    
    // Hook read
    var read = libc.findExportByName("read");
    if (read) {
        Interceptor.attach(read, {
            onLeave: function(retval) {
                send({type: "read", bytes: retval.toInt32()});
            }
        });
    }
    
    send({type: "all_hooks_installed", count: 3});
    """,
    "timeout": 3
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("all_hooks_installed", any("all_hooks_installed" in str(m) for m in messages), str(messages)[:200])
test("捕获 openat 调用", any("openat" in str(m) for m in messages))
test("捕获 write 调用", any("write" in str(m) and "COMPLEX_TEST" in str(m) for m in messages), str(messages)[:300])

# ==========================================
# 7. frida_hook_function — hook getpid()
# ==========================================
print("\n[7] frida_hook_function — hook getpid()")
p = sp.Popen(["/home/z/.venv/bin/python3", "-c",
              "import os,time;os.getpid();time.sleep(3)"])
time.sleep(0.3)
data, text = call_tool("frida_hook_function", {
    "pid": p.pid,
    "module": "libc.so.6",
    "function": "getpid",
    "on_enter": "send({type:'getpid_called'})",
    "on_leave": "send({type:'getpid_returned', pid: retval.toInt32()})",
    "timeout": 3
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("getpid hook_installed", any("hook_installed" in str(m) for m in messages), str(messages)[:200])
test("getpid_returned", any("getpid_returned" in str(m) for m in messages))

# ==========================================
# 8. frida_load_script — 读取内存 + 反汇编
# ==========================================
print("\n[8] frida_load_script — 读取内存 + 分析函数")
p = sp.Popen(["sleep", "5"])
data, text = call_tool("frida_load_script", {
    "pid": p.pid,
    "script": """
    var libc = Process.findModuleByName("libc.so.6");
    
    // 读取 sleep 函数的前 16 字节
    var sleepAddr = libc.findExportByName("sleep");
    if (sleepAddr) {
        var bytes = sleepAddr.readByteArray(16);
        var arr = new Uint8Array(bytes);
        var hex = [];
        for (var i = 0; i < arr.length; i++) {
            hex.push(arr[i].toString(16).padStart(2, "0"));
        }
        send({type: "sleep_bytes", addr: sleepAddr.toString(), hex: hex.join(" ")});
    }
    
    // 读取 libc 基地址的前 64 字节 (ELF 头)
    var elfHeader = libc.base.readByteArray(64);
    var elfArr = new Uint8Array(elfHeader);
    var elfHex = [];
    for (var i = 0; i < elfArr.length; i++) {
        elfHex.push(elfArr[i].toString(16).padStart(2, "0"));
    }
    send({type: "elf_header", hex: elfHex.join(" ")});
    
    // 列出 libc 所有导出函数 (前 10 个)
    var exports = libc.enumerateExports();
    var names = exports.slice(0, 10).map(function(e) {
        return e.name;
    });
    send({type: "exports", total: exports.length, samples: names});
    """,
    "timeout": 2
})
p.terminate(); p.wait()
messages = data if isinstance(data, list) else []
test("sleep_bytes 返回", any("sleep_bytes" in str(m) for m in messages), str(messages)[:200])
test("elf_header 返回", any("elf_header" in str(m) for m in messages))
test("exports 列表返回", any("exports" in str(m) for m in messages))
test("ELF 头以 7f 45 4c 46 开头", any("7f 45 4c 46" in str(m) for m in messages), str(messages)[:200])

# ==========================================
# Summary
# ==========================================
print("\n" + "=" * 55)
print(f"JS 脚本加载测试: {PASS} 通过 / {FAIL} 失败 / {PASS+FAIL} 总计")
print("=" * 55)

sys.exit(0 if FAIL == 0 else 1)
