"""FridaMCP setup.py — version is read from fridamcp/__init__.py (single source of truth)."""

import re
import os

from setuptools import setup, find_packages


def read_version():
    """Read __version__ from fridamcp/__init__.py (single source of truth)."""
    here = os.path.dirname(os.path.abspath(__file__))
    init_path = os.path.join(here, "fridamcp", "__init__.py")
    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.M)
    if not match:
        raise RuntimeError("Cannot find __version__ in fridamcp/__init__.py")
    return match.group(1)


def read_long_description():
    with open("README.md", "r", encoding="utf-8") as f:
        return f.read()


setup(
    name="fridamcp",
    version=read_version(),
    author="yfy227",
    author_email="yfy227@users.noreply.github.com",
    description="AI-Powered Frida MCP Server for Android - 在 Android 上运行 Frida 并通过 MCP 协议让 AI 便捷使用",
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/yfy227/fridamcp",
    project_urls={
        "GitHub": "https://github.com/yfy227/fridamcp",
        "Changelog": "https://github.com/yfy227/fridamcp/blob/main/CHANGELOG.md",
        "Issues": "https://github.com/yfy227/fridamcp/issues",
    },
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
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pyinstaller>=6.0.0",
            "build>=1.0.0",
            "twine>=4.0.0",
        ],
        "injector": [
            "apkutils2>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "fridamcp=fridamcp.server:main",
            "fridamcp-inject=injector.inject_apk:main",
        ],
    },
    include_package_data=True,
    package_data={
        "fridamcp": ["templates/*", "scripts/*"],
    },
)
