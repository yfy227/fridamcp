"""Frida JS 模板测试

验证所有注入到目标进程的 JS 脚本模板：
1. 语法合法（node --check）
2. 用户参数经 json.dumps 注入，恶意输入不破坏语法、不产生裸代码
3. 关键回归：不使用不存在的 Ptr 构造函数、SSL 符号走全局查找
"""
import json
import shutil
import subprocess

import pytest

from fridamcp.modules.hook import (
    HOOK_JAVA_METHOD_TEMPLATE,
    HOOK_NATIVE_TEMPLATE,
    TRACE_METHOD_TEMPLATE,
)
from fridamcp.modules.memory import (
    MEMORY_READ_TEMPLATE,
    MEMORY_WRITE_TEMPLATE,
)
from fridamcp.modules.network import (
    SSL_HOOK_TEMPLATE,
    SOCKET_HOOK_TEMPLATE,
)
from fridamcp.modules.crypto import (
    HOOK_CRYPTO_TEMPLATE,
    DUMP_SSL_KEYS_TEMPLATE,
)

NODE = shutil.which("node")

EVIL = 'com.x"; process.kill() — \\ \n "Claude" says'


def node_check(js: str) -> bool:
    """用 node 校验 JS 语法合法性"""
    if NODE is None:
        pytest.skip("node not available")
    p = subprocess.run(
        [NODE, "--check"], input=js.encode(), capture_output=True
    )
    assert p.returncode == 0, f"invalid JS:\n{p.stderr.decode()[:400]}\n---\n{js[:400]}"
    return True


# ---------- hook 模板：恶意参数注入安全 ----------

def test_java_method_template_evil_input():
    js = HOOK_JAVA_METHOD_TEMPLATE % {
        "hook_id": json.dumps("hook_deadbeef"),
        "class_name": json.dumps(EVIL),
        "method_name": json.dumps(EVIL),
    }
    assert node_check(js)
    # 恶意代码不得以裸 JS 形式出现在源码中（只允许转义后的字符串内容）
    assert "process.kill() —" not in js


def test_native_template_evil_input():
    js = HOOK_NATIVE_TEMPLATE % {
        "hook_id": json.dumps("native_deadbeef"),
        "module_name": json.dumps(EVIL),
        "func_name": json.dumps(EVIL),
        "offset": 0,
    }
    assert node_check(js)
    assert "process.kill() —" not in js


def test_trace_template_evil_input():
    js = TRACE_METHOD_TEMPLATE % {
        "hook_id": json.dumps("trace_deadbeef"),
        "class_name": json.dumps(EVIL),
    }
    assert node_check(js)
    assert "process.kill() —" not in js


# ---------- memory 模板：Ptr 回归 ----------

def test_memory_templates_no_bogus_ptr():
    """Frida JS 运行时没有 Ptr 构造函数（回归：new Ptr() 曾导致
    read_memory/write_memory 永远抛 ReferenceError）"""
    for tpl in (MEMORY_READ_TEMPLATE, MEMORY_WRITE_TEMPLATE):
        # 只检查实际构造调用，注释中的说明文字不算
        assert "= new Ptr(" not in tpl, tpl[:80]


def test_memory_templates_use_global_ptr():
    for tpl in (MEMORY_READ_TEMPLATE, MEMORY_WRITE_TEMPLATE):
        assert "ptr(address)" in tpl
        # 变量名不得遮蔽全局 ptr() 函数
        assert "var ptr =" not in tpl


def test_memory_templates_syntax():
    node_check(MEMORY_READ_TEMPLATE)
    node_check(MEMORY_WRITE_TEMPLATE)


# ---------- network / crypto 模板 ----------

def test_ssl_hook_uses_global_lookup():
    """SSL 符号应先走全局符号表（覆盖静态链接 BoringSSL 场景）"""
    assert "Module.findExportByName(null" in SSL_HOOK_TEMPLATE
    assert 'Module.findExportByName("libssl.so", "SSL_write")' not in SSL_HOOK_TEMPLATE


def test_ssl_keys_template_uses_global_lookup():
    assert "null" in DUMP_SSL_KEYS_TEMPLATE
    assert 'var modules = ["libssl.so", "libboringssl.so"]' not in DUMP_SSL_KEYS_TEMPLATE


def test_network_crypto_templates_syntax():
    # hook_id 为内部 uuid hex，直接嵌入安全
    js = SSL_HOOK_TEMPLATE % {"hook_id": "ssl_deadbeef"}
    node_check(js)
    node_check(SOCKET_HOOK_TEMPLATE % {"hook_id": "sock_deadbeef"})
    node_check(HOOK_CRYPTO_TEMPLATE % {"hook_id": "crypto_deadbeef"})
    node_check(DUMP_SSL_KEYS_TEMPLATE % {"hook_id": "keys_deadbeef"})
