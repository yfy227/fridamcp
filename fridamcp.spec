# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for FridaMCP

Build a standalone executable:
    pyinstaller fridamcp.spec

The resulting binary will be in dist/fridamcp/
"""

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect all frida-related data files and submodules
frida_datas = collect_data_files('frida')
frida_hiddenimports = collect_submodules('frida')

# MCP-related hidden imports
mcp_hiddenimports = [
    'mcp',
    'mcp.server',
    'mcp.server.fastmcp',
    'mcp.server.stdio',
    'mcp.server.sse',
    'mcp.types',
    'mcp.shared',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'starlette',
    'starlette.applications',
    'starlette.routing',
    'starlette.responses',
    'starlette.middleware',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',
    'h11',
    'httpx',
    'httpcore',
    'certifi',
    'idna',
    'h2',
    'hpack',
    'hyperframe',
]

# FridaMCP hidden imports
fridamcp_hiddenimports = collect_submodules('fridamcp')

a = Analysis(
    ['fridamcp/__main__.py'],
    pathex=[],
    binaries=frida_datas,
    datas=[
        ('fridamcp/templates', 'fridamcp/templates'),
        ('fridamcp/scripts', 'fridamcp/scripts'),
    ] if __import__('os').path.exists('fridamcp/templates') else [],
    hiddenimports=frida_hiddenimports + mcp_hiddenimports + fridamcp_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='fridamcp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='fridamcp',
)
