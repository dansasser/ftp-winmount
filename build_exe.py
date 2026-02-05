#!/usr/bin/env python3
"""
Build standalone executable for FTP-WinMount.

Usage:
    python build_exe.py

Output:
    dist/ftp-winmount.exe
"""

import shutil
import subprocess
import sys
from pathlib import Path


def main():
    project_root = Path(__file__).parent.resolve()
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    spec_file = project_root / "ftp_winmount.spec"

    print("[INFO] Building FTP-WinMount standalone executable...")
    print(f"[INFO] Project root: {project_root}")

    # Check PyInstaller is installed
    try:
        import PyInstaller
        print(f"[OK] PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("[ERROR] PyInstaller not found. Install with: pip install pyinstaller")
        return 1

    # Clean previous builds
    if dist_dir.exists():
        print("[INFO] Cleaning dist directory...")
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        print("[INFO] Cleaning build directory...")
        shutil.rmtree(build_dir)

    # Run PyInstaller
    print("[INFO] Running PyInstaller...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file),
    ]

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode != 0:
        print("[ERROR] PyInstaller failed")
        return result.returncode

    # Check output
    exe_path = dist_dir / "ftp-winmount.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"[OK] Build successful!")
        print(f"[OK] Output: {exe_path}")
        print(f"[OK] Size: {size_mb:.1f} MB")
    else:
        print("[ERROR] Expected output not found")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
