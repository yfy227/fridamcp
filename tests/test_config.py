"""配置模块测试

覆盖环境变量覆盖、frida_device_spec 组合逻辑，
以及 CLI 参数直改单例所需的字段存在性（回归：
server.py main() 曾用无效的 reload(config_module)）。
"""
import importlib

import fridamcp.config as config_module
from fridamcp.config import Config, config


def test_defaults():
    c = Config()
    assert c.MCP_PORT == 8768
    assert c.GUI_PORT == 7860
    assert c.FRIDA_DEVICE_TYPE == "usb"
    assert c.FRIDA_DEVICE_ID is None


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("FRIDAMCP_PORT", "9999")
    monkeypatch.setenv("FRIDAMCP_GUI_PORT", "8888")
    monkeypatch.setenv("FRIDA_DEVICE_TYPE", "remote")
    c = Config()
    assert c.MCP_PORT == 9999
    assert c.GUI_PORT == 8888
    assert c.FRIDA_DEVICE_TYPE == "remote"


def test_frida_device_spec():
    c = Config()
    c.FRIDA_DEVICE_TYPE = "remote"
    c.FRIDA_REMOTE_HOST = "192.168.1.50"
    c.FRIDA_REMOTE_PORT = 27042
    assert c.frida_device_spec == "remote@192.168.1.50:27042"

    c.FRIDA_DEVICE_TYPE = "usb"
    c.FRIDA_DEVICE_ID = "ABC123"
    assert c.frida_device_spec == "ABC123"

    c.FRIDA_DEVICE_ID = None
    assert c.frida_device_spec == "usb"


def test_cli_writable_fields_exist():
    """server.py main() 直接写入这些字段——存在性回归"""
    for field in (
        "MCP_HOST", "MCP_PORT", "FRIDA_DEVICE_TYPE",
        "FRIDA_DEVICE_ID", "SERVER_AUTO_RESTART_MAX",
    ):
        assert hasattr(config, field), f"config 缺少 CLI 目标字段: {field}"


def test_singleton_identity():
    assert config is config_module.config
    # importlib.reload 产生新单例对象——所有旧引用指向旧对象：
    # 这正是 CLI 参数必须直改单例而非 reload 的原因
    reloaded = importlib.reload(config_module)
    assert reloaded.config is not config
    importlib.reload(config_module)  # 恢复
