"""
配置模块单元测试
"""
import os
import pytest
from fridamcp.config import Config, config


class TestConfig:
    """配置模块测试"""

    def test_config_is_singleton(self):
        """config 应为单例实例"""
        assert isinstance(config, Config)

    def test_default_transport_is_stdio(self):
        """默认传输模式应为 stdio"""
        # 重置环境变量
        old = os.environ.pop("FRIDAMCP_TRANSPORT", None)
        try:
            fresh = Config()
            assert fresh.MCP_TRANSPORT == "stdio"
        finally:
            if old is not None:
                os.environ["FRIDAMCP_TRANSPORT"] = old

    def test_transport_from_env(self):
        """应能从环境变量读取传输模式"""
        old = os.environ.get("FRIDAMCP_TRANSPORT")
        os.environ["FRIDAMCP_TRANSPORT"] = "http"
        try:
            fresh = Config()
            assert fresh.MCP_TRANSPORT == "http"
        finally:
            if old is None:
                os.environ.pop("FRIDAMCP_TRANSPORT", None)
            else:
                os.environ["FRIDAMCP_TRANSPORT"] = old

    def test_session_idle_timeout_default(self):
        """默认空闲超时应为 600 秒"""
        old = os.environ.pop("FRIDAMCP_SESSION_IDLE_TIMEOUT", None)
        try:
            fresh = Config()
            assert fresh.SESSION_IDLE_TIMEOUT == 600.0
        finally:
            if old is not None:
                os.environ["FRIDAMCP_SESSION_IDLE_TIMEOUT"] = old

    def test_session_lock_timeout_default(self):
        """默认锁超时应为 30 秒"""
        old = os.environ.pop("FRIDAMCP_SESSION_LOCK_TIMEOUT", None)
        try:
            fresh = Config()
            assert fresh.SESSION_LOCK_TIMEOUT == 30.0
        finally:
            if old is not None:
                os.environ["FRIDAMCP_SESSION_LOCK_TIMEOUT"] = old

    def test_max_sessions_default(self):
        """默认最大会话数应为 10"""
        old = os.environ.pop("FRIDAMCP_MAX_SESSIONS", None)
        try:
            fresh = Config()
            assert fresh.MAX_SESSIONS == 10
        finally:
            if old is not None:
                os.environ["FRIDAMCP_MAX_SESSIONS"] = old

    def test_update_config(self):
        """update 方法应能更新配置"""
        fresh = Config()
        original_port = fresh.MCP_PORT
        try:
            fresh.update(MCP_PORT=99999)
            assert fresh.MCP_PORT == 99999
        finally:
            fresh.update(MCP_PORT=original_port)

    def test_update_ignores_none(self):
        """update 方法应忽略 None 值"""
        fresh = Config()
        original_port = fresh.MCP_PORT
        fresh.update(MCP_PORT=None)
        assert fresh.MCP_PORT == original_port
