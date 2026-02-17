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
        # paramiko (SFTP/SSH)
        'paramiko',
        'paramiko.transport',
        'paramiko.sftp_client',
        'paramiko.rsakey',
        'paramiko.ecdsakey',
        'paramiko.ed25519key',
        'paramiko.agent',
        'paramiko.ssh_exception',
        'bcrypt',
        'cryptography',
        'nacl',
        'nacl.signing',
        'nacl.bindings',
        # Google Drive API
        'googleapiclient',
        'googleapiclient.discovery',
        'googleapiclient.http',
        'googleapiclient.errors',
        'google.auth',
        'google.auth.transport',
        'google.auth.transport.requests',
        'google.auth.credentials',
        'google.oauth2',
        'google.oauth2.credentials',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
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
