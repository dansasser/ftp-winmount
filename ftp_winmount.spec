# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for FTP-WinMount

Build with: pyinstaller ftp_winmount.spec
Or use: python build_exe.py
"""

import sys
from pathlib import Path

block_cipher = None

# Get the project root
project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / 'launcher.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # winfspy and its dependencies
        'winfspy',
        'winfspy.plumbing',
        'winfspy.plumbing.winstuff',
        'winfspy.plumbing.win32_filetime',
        'winfspy.plumbing.bindings',
        'winfspy.exceptions',
        'winfspy.file_system',
        # cffi (required by winfspy)
        'cffi',
        '_cffi_backend',
        # cachetools
        'cachetools',
        # standard library modules that might be needed
        'ftplib',
        'configparser',
        'logging',
        'logging.handlers',
        'argparse',
        'dataclasses',
        'pathlib',
        'io',
        'time',
        'subprocess',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'unittest',
        'pydoc',
        'doctest',
        'test',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ftp-winmount',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console app, not GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_root / 'version_info.txt') if (project_root / 'version_info.txt').exists() else None,
    icon=str(project_root / 'icon.ico') if (project_root / 'icon.ico').exists() else None,
)
