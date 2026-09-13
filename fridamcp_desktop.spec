# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: 把 FridaMCP 打包为单文件桌面独立应用

用法（在项目根目录）:
    pip install pyinstaller pywebview
    pyinstaller --clean -y fridamcp_desktop.spec

产物:
    dist/FridaMCP        (Linux/macOS)
    dist/FridaMCP.exe    (Windows)

特性: 无控制台窗口（console=False）、独立任务栏图标、
双击即用——GUI 与 MCP 服务器全部内嵌。
"""

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)

block_cipher = None

datas = [("static", "static")]  # PWA manifest + 图标
binaries = []
hiddenimports = []

# Gradio 生态运行时需要完整的前端静态资源与动态导入。
# gradio 6 生态有一批包运行时读取包内数据文件（safehttpx/groovy/
# pypdfium2/rfc3987_syntax 的 version.txt 与 .lark 语法文件——
# 缺失时 FileNotFoundError），全部 collect_all 覆盖。
for pkg in ("gradio", "gradio_client", "mcp",
            "safehttpx", "groovy", "pypdfium2", "pypdfium2_raw",
            "rfc3987_syntax", "lark", "certifi"):
    pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_bins
    hiddenimports += pkg_hidden

# 预防性数据文件收集（只收数据不收整模块，控制体积）
for pkg in ("fastmcp", "branca", "choreographer"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

# Gradio Dataframe 组件 postprocess 无条件 import pandas
# （顶层是可选依赖，静态分析会树摇掉）——显式收集。
# pandas._libs 的 C 扩展（pandas_parser 等）需显式声明给
# FrozenImporter 索引，否则运行时 ModuleNotFoundError。
for pkg in ("pandas", "numpy"):
    pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_bins
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("pandas._libs")
hiddenimports += [
    "pandas._libs.pandas_parser",
    "pandas._libs.pandas_writer",
    "pandas._libs.tslibs.parsing",
]

# 项目自身的包（防止动态导入被树摇掉）
hiddenimports += collect_submodules("fridamcp")
hiddenimports += collect_submodules("injector")
hiddenimports += ["app", "desktop_app"]

# pywebview 各平台后端（打包机上有哪个收哪个）
import importlib.util

for _mod in (
    "webview.platforms.edgechromium",  # Windows
    "webview.platforms.cocoa",         # macOS
    "webview.platforms.gtk",           # Linux
    "webview.platforms.qt",
):
    if importlib.util.find_spec(_mod) is not None:
        hiddenimports.append(_mod)

a = Analysis(
    ["desktop_app.py"],
    pathex=[os.path.abspath(SPECPATH)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "matplotlib", "IPython"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="FridaMCP",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # 无终端黑窗：独立应用形态
    disable_windowed_traceback=False,
    icon="static/icon.ico" if os.path.exists("static/icon.ico") else None,
)
