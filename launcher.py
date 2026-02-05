#!/usr/bin/env python3
"""
Launcher script for PyInstaller builds.

This script is the entry point for the standalone executable.
It imports and runs the main function from the ftp_winmount package.
"""

import sys

# Import the main function from the package
from ftp_winmount.__main__ import main

if __name__ == "__main__":
    sys.exit(main() or 0)
