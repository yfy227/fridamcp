"""模块注册完整性测试

用 FakeMCP 收集全部 8 个模块注册的工具，
防止后续修改悄悄删减/破坏工具集。
"""
from fridamcp.modules import ALL_MODULES

EXPECTED_MODULES = [
    "process", "hook", "memory", "network",
    "filesystem", "ui_automation", "crypto", "log",
]


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def test_module_roster():
    assert [m.__name__.rsplit(".", 1)[-1] for m in ALL_MODULES] == EXPECTED_MODULES


def test_all_modules_register_tools():
    for mod in ALL_MODULES:
        mcp = FakeMCP()
        mod.register_tools(mcp)
        assert len(mcp.tools) > 0, f"{mod.__name__} 注册了 0 个工具"


def test_tool_functions_have_docstrings():
    """MCP 工具的 docstring 会成为 LLM 可见的工具描述"""
    for mod in ALL_MODULES:
        mcp = FakeMCP()
        mod.register_tools(mcp)
        for name, fn in mcp.tools.items():
            assert fn.__doc__ and fn.__doc__.strip(), (
                f"{mod.__name__}.{name} 缺少 docstring"
            )
