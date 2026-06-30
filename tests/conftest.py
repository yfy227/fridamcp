"""
pytest 配置：在所有测试前启用模拟模式
"""
import os

# 在导入任何 fridamcp 模块前启用模拟模式
os.environ["FRIDAMCP_MOCK_DEVICE"] = "1"
