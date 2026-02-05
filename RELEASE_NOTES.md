# FTP-WinMount v0.1.1

## Changes in 0.1.1

- Fixed Windows installer build (Inno Setup type compatibility)

---

Mount any FTP server as a local Windows drive letter (Z:, Y:, etc.), making it accessible through **File Explorer**, **VS Code**, and any other application as if it were a local disk.

---

## Key Features

- **Native Mounting** - Map FTP servers to a Windows drive letter for seamless access
- **App Compatibility** - Works directly with File Explorer, VS Code, Notepad, and more
- **Full Access** - Supports both read and write operations
- **Flexible Auth** - Works with anonymous or authenticated FTP connections
- **Reliable** - Includes auto-reconnect functionality if the connection drops
- **Privacy-Focused** - Lightweight, open-source, no ads, and no telemetry

---

## Installation

> **Required:** [WinFsp (Windows File System Proxy)](https://winfsp.dev/rel/) must be installed before running FTP-WinMount.

### Option 1: Installer (Recommended)

1. Install [WinFsp](https://winfsp.dev/rel/)
2. Download and run `ftp-winmount-0.1.1-setup.exe`
3. Open a terminal and run:
   ```
   ftp-winmount mount --host <IP> --drive Z
   ```

### Option 2: Portable

1. Install [WinFsp](https://winfsp.dev/rel/)
2. Download `ftp-winmount-0.1.1-portable.exe`
3. Run directly from your terminal:
   ```
   ftp-winmount-0.1.1-portable.exe mount --host <IP> --drive Z
   ```

### Option 3: PyPI

```bash
pip install ftp-winmount
ftp-winmount mount --host <IP> --drive Z
```

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Windows | 10 or 11 |
| [WinFsp](https://winfsp.dev/rel/) | 2.0+ |

---

## Usage Examples

```bash
# Mount with IP and port
ftp-winmount mount --host 192.168.0.130 --port 2121 --drive Z

# Mount with authentication
ftp-winmount mount --host ftp.example.com --user myuser --password mypass --drive Z

# Mount with config file
ftp-winmount mount --config config.ini

# Unmount
ftp-winmount unmount --drive Z

# Check status
ftp-winmount status
```

---

## Links

- [Documentation](https://github.com/dansasser/ftp-winmount#readme)
- [Report Issues](https://github.com/dansasser/ftp-winmount/issues)
- [WinFsp Download](https://winfsp.dev/rel/)
