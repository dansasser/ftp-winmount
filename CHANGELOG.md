# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-02-05

### Fixed

- Complete package rename cleanup: replaced 12 remaining `PyFTPDrive` references across 10 files missed in the initial rename
  - README.md, AGENTS.md, .gitignore, requirements-dev.txt, docs/specs.md
  - tests/conftest.py, tests/__init__.py, tests/test_memory_leak.py, tests/test_integration.py
- Updated .gitignore spec exclusion from `pyftpdrive.spec` to `ftp_winmount.spec`
- Fixed Inno Setup installer to use compatible Windows API types

## [0.1.0] - 2026-02-05

### Added

- Mount FTP servers as local Windows drive letters using WinFsp
- Full read/write support - create, modify, delete files and directories
- FTPS (FTP over TLS) support for secure connections
- Directory and metadata caching with configurable TTLs
- Automatic reconnection and retry logic
- Configuration via INI file or command-line arguments
- Windows installer with Start Menu entry and PATH integration
- Standalone portable executable (no installation required)
- Comprehensive test suite

### Changed

- **BREAKING:** Package renamed from `pyftpdrive` to `ftp-winmount`
  - PyPI: `pip install ftp-winmount`
  - CLI: `ftp-winmount mount ...`
  - Executable: `ftp-winmount.exe`
  - Installer: `ftp-winmount-X.X.X-setup.exe`

### Installation

**Windows Installer (Recommended):**
```
Download ftp-winmount-0.1.0-setup.exe from GitHub Releases
```

**Portable:**
```
Download ftp-winmount-0.1.0-portable.exe from GitHub Releases
```

**PyPI:**
```bash
pip install ftp-winmount
```

### Requirements

- Windows 10/11
- [WinFsp](https://winfsp.dev/) must be installed
