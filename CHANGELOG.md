# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-15

### Added

- **SFTP (SSH) protocol support** - Mount SSH/SFTP servers as Windows drive letters
  - SSH key file authentication (RSA, ECDSA, Ed25519)
  - Passphrase-protected key support (`--key-passphrase`)
  - Password authentication
  - SSH agent forwarding
  - Trust-on-first-use host key policy (auto-add unknown hosts)
- **Google Drive support** - Mount Google Drive as a Windows drive letter
  - OAuth 2.0 browser-based authentication flow
  - Offline access with persistent refresh token
  - Google Workspace files (Docs, Sheets, Slides, Drawings) shown as read-only exports (.docx, .xlsx, .pptx, .pdf)
  - Shared/team drive support (`--shared-drive`)
  - Specific folder mounting (`--root-folder`)
  - Path-to-ID caching with TTL for efficient API usage
  - Rate limit handling with exponential backoff
  - Delete operations use trash (not permanent delete)
- New CLI options:
  - `--protocol` (ftp, ftps, sftp, gdrive) - select connection protocol
  - `--key-file` - path to SSH private key
  - `--key-passphrase` - passphrase for encrypted SSH keys
  - `--client-secrets` - path to Google OAuth client_secrets.json
  - `--root-folder` - Google Drive folder to mount
  - `--shared-drive` - name or ID of shared/team drive
- New `auth` subcommand for Google Drive OAuth setup:
  - `ftp-winmount auth google --client-secrets <path>`
- `RemoteClient` Protocol abstraction - enables FTPClient, SFTPClient, and GoogleDriveClient to be used interchangeably
- SFTP configuration via INI file (`[general]` protocol and `[ssh]` section)
- Google Drive configuration via INI file (`[gdrive]` section)
- 160 new tests covering SFTP client, Google Drive client, OAuth auth, path cache, protocol compliance, and config parsing

### Dependencies

- Added `paramiko>=3.0.0` for SSH/SFTP support
- Added `google-api-python-client>=2.100.0` for Google Drive API
- Added `google-auth>=2.20.0` for OAuth 2.0
- Added `google-auth-oauthlib>=1.0.0` for OAuth browser flow

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
