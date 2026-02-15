# FTP-WinMount

[![PyPI version](https://badge.fury.io/py/ftp-winmount.svg)](https://badge.fury.io/py/ftp-winmount)
[![CI](https://github.com/dansasser/ftp-winmount/actions/workflows/ci.yml/badge.svg)](https://github.com/dansasser/ftp-winmount/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/platform-Windows-blue.svg)](https://www.microsoft.com/windows)

Mount any FTP or SFTP server as a local Windows drive. No sync, no ads, no telemetry.

---

## Download

**No Python required.** Download the latest release:

| Download | Description |
|----------|-------------|
| [Installer (.exe)](https://github.com/dansasser/ftp-winmount/releases/latest) | Installs to Program Files, adds to PATH |
| [Portable (.exe)](https://github.com/dansasser/ftp-winmount/releases/latest) | No installation, run from anywhere |

### Installer (Recommended)

1. Install [WinFsp](https://winfsp.dev/rel/) (required dependency)
2. Download `ftp-winmount-*-setup.exe` from [Releases](https://github.com/dansasser/ftp-winmount/releases/latest)
3. Run the installer (installs to Program Files and adds to PATH)
4. Open any terminal and run:
   ```bash
   ftp-winmount mount --host 192.168.0.130 --port 2121 --drive Z
   ```

### Portable

If you don't want to install:

1. Install [WinFsp](https://winfsp.dev/rel/) (required dependency)
2. Download `ftp-winmount-*-portable.exe` from [Releases](https://github.com/dansasser/ftp-winmount/releases/latest)
3. Run from wherever you saved it:
   ```bash
   C:\Downloads\ftp-winmount-0.1.1-portable.exe mount --host 192.168.0.130 --port 2121 --drive Z
   ```

---

## Why?

- VS Code's FTP plugins only sync files, they don't mount
- Commercial tools like RaiDrive and NetDrive come with ads and tracking
- Windows can't natively mount FTP as a drive letter
- You want to own your tools

---

## Features

- Mount FTP or SFTP server as a Windows drive letter (Z:, Y:, etc.)
- Full read/write support
- SSH key authentication (RSA, ECDSA, Ed25519), password, and SSH agent support
- Works with any application (VS Code, File Explorer, Notepad, etc.)
- Anonymous or authenticated FTP
- FTPS (FTP over TLS) support
- Auto-reconnect on connection drop
- Lightweight, no background services when not in use
- Open source, no ads, no tracking

---

## Requirements

### Windows Dependencies

FTP-WinMount requires **WinFsp** (Windows File System Proxy) - a free, open-source file system driver that enables user-mode filesystems on Windows.

| Dependency | Version | Required | Download |
|------------|---------|----------|----------|
| Windows | 10 or 11 | Yes | - |
| Python | 3.10+ | Yes | [python.org](https://www.python.org/downloads/) |
| WinFsp | 2.0+ | Yes | [winfsp.dev/rel](https://winfsp.dev/rel/) |

### Installing WinFsp

**Option 1: Download installer (Recommended)**
1. Go to https://winfsp.dev/rel/
2. Download the latest `.msi` installer
3. Run the installer (requires admin rights)
4. Restart any open terminals

**Option 2: Winget**
```powershell
winget install WinFsp.WinFsp
```

**Option 3: Chocolatey**
```powershell
choco install winfsp
```

**Verify Installation:**
```powershell
# Check WinFsp is installed
dir "C:\Program Files (x86)\WinFsp"
```

---

## Installation

### Installer (Easiest)

See [Download](#download) section above. No Python required. Installs to Program Files and adds to PATH.

### From PyPI

```bash
pip install ftp-winmount
```

This installs `ftp-winmount` to your Python Scripts folder. Make sure that folder is in your PATH.

**Note:** If you install inside a virtual environment, the command will only work when that venv is activated.

### From Source

```bash
git clone https://github.com/dansasser/ftp-winmount.git
cd ftp-winmount
pip install .
```

### Development Install

```bash
git clone https://github.com/dansasser/ftp-winmount.git
cd ftp-winmount
pip install -e ".[dev]"
```

### Building Standalone Executable

To build `ftp-winmount.exe` yourself:

```bash
git clone https://github.com/dansasser/ftp-winmount.git
cd ftp-winmount
pip install -e ".[dev]"
python build_exe.py
```

The executable will be at `dist/ftp-winmount.exe`.

### Building Installer

To build the Windows installer (requires [Inno Setup](https://jrsoftware.org/isinfo.php)):

```bash
python build_exe.py
iscc installer.iss
```

The installer will be at `dist/ftp-winmount-X.X.X-setup.exe`.

---

## Quick Start

Mount an anonymous FTP server:
```bash
ftp-winmount mount --host 192.168.0.130 --port 2121 --drive Z
```

Mount an SFTP server with SSH key:
```bash
ftp-winmount mount --protocol sftp --host myserver.com --key-file ~/.ssh/id_rsa --drive Z
```

Your remote server is now accessible at `Z:\`

To unmount:
```bash
ftp-winmount unmount --drive Z
```

Or just press `Ctrl+C` in the terminal.

---

## Usage

### Command Line

**FTP:**
```bash
# Mount with minimal options
ftp-winmount mount --host 192.168.0.130 --drive Z

# Mount with custom port
ftp-winmount mount --host 192.168.0.130 --port 2121 --drive Z

# Mount with authentication
ftp-winmount mount --host ftp.example.com --user myuser --password mypass --drive Z

# Mount with FTPS (FTP over TLS)
ftp-winmount mount --protocol ftps --host ftp.example.com --drive Z
```

**SFTP (SSH):**
```bash
# Mount with SSH key file
ftp-winmount mount --protocol sftp --host myserver.com --key-file ~/.ssh/id_rsa --drive Z

# Mount with SSH key + custom port and username
ftp-winmount mount --protocol sftp --host myserver.com --port 2222 --user deploy --key-file ~/.ssh/id_ed25519 --drive Z

# Mount with SSH key that has a passphrase
ftp-winmount mount --protocol sftp --host myserver.com --key-file ~/.ssh/id_rsa --key-passphrase "my passphrase" --drive Z

# Mount with SSH password auth
ftp-winmount mount --protocol sftp --host myserver.com --user myuser --password mypass --drive Z
```

**General:**
```bash
# Mount with config file
ftp-winmount mount --config config.ini

# Check status
ftp-winmount status

# Unmount
ftp-winmount unmount --drive Z
```

### Configuration File

Create `config.ini` for FTP:
```ini
[ftp]
host = 192.168.0.130
port = 2121
username =
password =

[mount]
drive_letter = Z
volume_label = My FTP Drive

[cache]
directory_ttl_seconds = 30

[logging]
level = INFO
file = ftp-winmount.log
```

Or for SFTP:
```ini
[general]
protocol = sftp

[ssh]
host = myserver.com
port = 22
username = deploy
key_file = ~/.ssh/id_ed25519

[mount]
drive_letter = Z
volume_label = My SSH Drive

[cache]
directory_ttl_seconds = 30

[logging]
level = INFO
file = ftp-winmount.log
```

Then run:
```bash
ftp-winmount mount --config config.ini
```

---

## Use with VS Code

1. Mount your FTP server:
```bash
   ftp-winmount mount --host 192.168.0.130 --port 2121 --drive Z
```

2. Open VS Code

3. File -> Open Folder -> Select `Z:\`

4. Edit files normally. Changes save directly to the FTP server.

---

## Use with Python's pyftpdlib

If you're running a simple FTP server with pyftpdlib:

**Server (host machine):**
```bash
pip install pyftpdlib
cd /path/to/your/files
python -m pyftpdlib -p 2121 -i 0.0.0.0 -w
```

**Client (your machine):**
```bash
ftp-winmount mount --host SERVER_IP --port 2121 --drive Z
```

---

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Server hostname or IP | Required |
| `--port` | Server port | 21 (FTP) / 22 (SFTP) |
| `--drive` | Drive letter to mount | Required |
| `--protocol` | Protocol: `ftp`, `ftps`, or `sftp` | `ftp` |
| `--user` | Username | Anonymous (FTP) |
| `--password` | Password | None |
| `--key-file` | Path to SSH private key (SFTP only) | None |
| `--key-passphrase` | Passphrase for encrypted SSH key | None |
| `--secure` | Use FTPS (FTP over TLS) | False |
| `--config` | Path to config file | None |
| `--verbose` | Enable debug logging | False |

---

## Troubleshooting

### "WinFsp not found" or "winfspy not available"

WinFsp must be installed system-wide. The Python package `winfspy` is just bindings.

1. Download WinFsp from https://winfsp.dev/rel/
2. Run the installer as administrator
3. Restart your terminal
4. Try again

### "Drive letter in use"

Choose a different drive letter or unmount the existing drive:
```bash
net use Z: /delete
```

### "Connection refused"

- Check the FTP server is running
- Check the IP address and port are correct
- Check firewall isn't blocking the connection

### "Permission denied"

- For anonymous FTP, ensure the server allows anonymous access
- For authenticated FTP, check username and password
- For SFTP, check your SSH key file path and permissions
- For SFTP with passphrase-protected keys, use `--key-passphrase`

### "SSH authentication failed"

- Verify the key file path is correct and the file exists
- If using a passphrase-protected key, provide it with `--key-passphrase`
- Try connecting with `ssh user@host` to verify the key works
- Check that the server allows key-based authentication

### Files appear but can't be read

- FTP server may have disconnected
- Try unmounting and remounting

### Slow performance

- Enable caching in config file
- Increase `directory_ttl_seconds`
- Check network connection to FTP server

### Mount crashes or hangs

- Update to the latest version of WinFsp
- Check Windows Event Viewer for errors
- Run with `--verbose` flag for detailed logs

---

## Limitations

- **Windows only** - This tool uses WinFsp which is Windows-specific
- FTP protocol does not support file locking. Concurrent writes from multiple clients may cause issues.
- Some FTP servers don't report accurate file sizes or timestamps.
- Very large files (>1GB) may be slow due to FTP protocol overhead (SFTP handles large files better).

---

## Development

### Setup

```bash
git clone https://github.com/dansasser/ftp-winmount.git
cd ftp-winmount
python -m venv venv
venv\Scripts\activate
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

### Linting

```bash
ruff check ftp_winmount tests
ruff format ftp_winmount tests
```

### Build Package

```bash
python -m build
twine check dist/*
```

---

## Contributing

Contributions welcome. Please open an issue first to discuss major changes.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License. See [LICENSE](LICENSE) file.

---

## Acknowledgments

- [WinFsp](https://winfsp.dev/) - Windows File System Proxy
- [winfspy](https://github.com/Scille/winfspy) - Python bindings for WinFsp
- [paramiko](https://www.paramiko.org/) - Python SSH/SFTP library

---

## Related Projects

- [WinFsp](https://winfsp.dev/) - The underlying filesystem driver
- [SSHFS-Win](https://github.com/winfsp/sshfs-win) - Mount SSH/SFTP as drives (uses WinFsp)
- [rclone](https://rclone.org/) - Mount cloud storage (supports many providers)
