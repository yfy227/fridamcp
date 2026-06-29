from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="fridamcp",
    version="1.0.0",
    author="yfy227",
    author_email="yfy227@users.noreply.github.com",
    description="AI-Powered Frida MCP Server for Android - 在 Android 上运行 Frida 并通过 MCP 协议让 AI 便捷使用",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yfy227/fridamcp",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: Software Development :: Debuggers",
    ],
    python_requires=">=3.9",
    install_requires=[
        "mcp>=1.0.0",
        "frida>=16.0.0",
        "frida-tools>=12.0.0",
        "uvicorn>=0.24.0",
        "starlette>=0.32.0",
        "pydantic>=2.0.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "loguru>=0.7.0",
        "httpx>=0.25.0",
    ],
    entry_points={
        "console_scripts": [
            "fridamcp=fridamcp.server:main",
            "fridamcp-inject=injector.inject_apk:main",
        ],
    },
)
