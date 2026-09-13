"""MCP 工具函数测试（FakeMCP 模式）

不依赖真实 MCP 服务器：用 FakeMCP 捕获 register_tools 注册的
闭包函数，直接调用并验证安全/行为契约。
"""
import shlex
from unittest.mock import patch

import pytest

from fridamcp.modules import ui_automation, filesystem


class FakeMCP:
    """收集 @mcp.tool() 注册的函数，供测试直接调用"""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture()
def ui_tools():
    mcp = FakeMCP()
    ui_automation.register_tools(mcp)
    return mcp.tools


@pytest.fixture()
def fs_tools():
    mcp = FakeMCP()
    filesystem.register_tools(mcp)
    return mcp.tools


# ---------- press_key: keycode 白名单 ----------

@pytest.mark.parametrize("bad", [
    "KEYCODE_HOME; rm -rf /",
    "KEYCODE_HOME\n",
    "$(reboot)",
    "a && b",
    "KEYCODE_HOME`id`",
])
def test_press_key_rejects_shell_metachars(ui_tools, bad):
    result = ui_tools["press_key"](keycode=bad)
    assert "error" in result, f"恶意 keycode 未被拒绝: {bad}"
    assert "Invalid keycode" in result["error"]


def test_press_key_accepts_valid(ui_tools):
    # 合法 keycode 不被白名单误伤（adb 不存在时返回 error 但非 Invalid）
    result = ui_tools["press_key"](keycode="KEYCODE_HOME")
    assert "Invalid" not in str(result)


# ---------- screenshot: 文件名白名单 ----------

@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "x.png; rm -rf /",
    "a$(id)",
    "a`id`",
    "a/b/c.png",
    "x y.png",
])
def test_screenshot_rejects_bad_filename(ui_tools, bad):
    result = ui_tools["screenshot"](filename=bad)
    assert "error" in result, f"恶意 filename 未被拒绝: {bad}"
    assert "Invalid filename" in result["error"]


def test_screenshot_accepts_plain_filename(ui_tools):
    result = ui_tools["screenshot"](filename="screen-01.png")
    assert "Invalid" not in str(result)


# ---------- input_text: 设备端 shell 转义 ----------

def test_input_text_quotes_evil_payload(ui_tools):
    captured = {}

    def fake_shell(cmd, device=None):
        captured["cmd"] = cmd
        return ""

    with patch.object(ui_automation, "_run_adb_shell", fake_shell):
        ui_tools["input_text"](text='a"; rm -rf /; echo "b')
        cmd = captured["cmd"]

    tokens = shlex.split(cmd)
    assert tokens[0] == "input" and tokens[1] == "text"
    # payload 必须是单个独立参数（被安全引用），不得被设备 shell 切开执行。
    # shlex.split 能无损还原为 3 个 token 即证明设备 shell 也只会
    # 把它当作一个参数——payload 内容本身当然可以包含任意字符。
    assert len(tokens) == 3, f"payload 被切开: {tokens}"
    # 还原出的 payload 应为原始输入的转义形式（空格→%s）
    assert tokens[2] == 'a";%srm%s-rf%s/;%secho%s"b'


def test_input_text_space_escaping(ui_tools):
    captured = {}

    def fake_shell(cmd, device=None):
        captured["cmd"] = cmd
        return ""

    with patch.object(ui_automation, "_run_adb_shell", fake_shell):
        ui_tools["input_text"](text="hello world")
        tokens = shlex.split(captured["cmd"])

    assert tokens[2] == "hello%sworld"  # adb input text 的 %s 空格约定


# ---------- filesystem: 路径参数转义 ----------

def test_list_files_quotes_path(fs_tools):
    captured = {}

    def fake_shell(cmd, device=None):
        captured["cmd"] = cmd
        return "total 0\n"

    with patch.object(filesystem, "_run_adb_shell", fake_shell):
        fs_tools["list_files"](path='/sdcard/x"; rm -rf /')
        cmd = captured["cmd"]

    tokens = shlex.split(cmd)
    # 恶意 payload 必须保持为单个参数（不会被设备 shell 解释为命令）
    assert len(tokens) == 3, f"路径被切开: {tokens}"
    assert tokens[2] == '/sdcard/x"; rm -rf /'


def test_read_file_quotes_path(fs_tools):
    """read_file 的 stat/cat 命令中路径必须被安全引用"""
    cmds = []

    def fake_shell(cmd, device=None):
        cmds.append(cmd)
        if cmd.startswith("stat"):
            return "123"
        return "data"

    with patch.object(filesystem, "_run_adb_shell", fake_shell):
        fs_tools["read_file"](path='/data/x $(id)')

    # stat 与 cat 两条命令里的路径都应是单个被引用 token
    for cmd in cmds:
        tokens = shlex.split(cmd)
        assert tokens[-1] == '/data/x $(id)', f"路径未被正确引用: {cmd}"
    assert len(cmds) >= 2, "应产生 stat 与 cat 两条命令"
