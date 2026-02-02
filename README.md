# README.md

## PyFTPDrive

Mount any FTP server as a local Windows drive. No sync, no ads, no telemetry.

---

## Why?

- VS Code's FTP plugins only sync files, they don't mount
- Commercial tools like RaiDrive and NetDrive come with ads and tracking
- Windows can't natively mount FTP as a drive letter
- You want to own your tools

---

## Features

- Mount FTP server as a Windows drive letter (Z:, Y:, etc.)
- Full read/write support
- Works with any application (VS Code, File Explorer, Notepad, etc.)
- Anonymous or authenticated FTP
- Auto-reconnect on connection drop
- Lightweight, no background services when not in use
- Open source, no ads, no tracking

---

## Requirements

- Windows 10 or 11
- Python 3.10+
- [WinFsp](https://winfsp.dev/) (free, open source)

---

## Installation

### 1. Install WinFsp

Download and install from https://winfsp.dev/rel/

### 2. Install PyFTPDrive
```bash
pip install pyftpdrive
```

Or from source:
```bash
git clone https://github.com/yourusername/pyftpdrive.git
cd pyftpdrive
pip install -e .
```

---

## Quick Start

Mount an anonymous FTP server:
```bash
pyftpdrive mount --host 192.168.0.130 --port 2121 --drive Z
```

Your FTP server is now accessible at `Z:\\`

To unmount:
```bash
pyftpdrive unmount --drive Z
```

Or just press `Ctrl+C` in the terminal.

---

## Usage

### Command Line
```bash
# Mount with minimal options
pyftpdrive mount --host 192.168.0.130 --drive Z

# Mount with custom port
pyftpdrive mount --host 192.168.0.130 --port 2121 --drive Z

# Mount with authentication
pyftpdrive mount --host ftp.example.com --user myuser --password mypass --drive Z

# Mount with config file
pyftpdrive mount --config config.ini

# Check status
pyftpdrive status

# Unmount
pyftpdrive unmount --drive Z
```

### Configuration File

Create `config.ini`:
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
file = pyftpdrive.log
```

Then run:
```bash
pyftpdrive mount --config config.ini
```

---

## Use with VS Code

1. Mount your FTP server:
```bash
   pyftpdrive mount --host 192.168.0.130 --port 2121 --drive Z
```

2. Open VS Code

3. File → Open Folder → Select `Z:\\`

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
pyftpdrive mount --host SERVER_IP --port 2121 --drive Z
```

---

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | FTP server hostname or IP | Required |
| `--port` | FTP server port | 21 |
| `--drive` | Drive letter to mount | Required |
| `--user` | FTP username | Anonymous |
| `--password` | FTP password | None |
| `--config` | Path to config file | None |
| `--verbose` | Enable debug logging | False |

---

## Troubleshooting

### "WinFsp not found"

Install WinFsp from https://winfsp.dev/rel/

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

### Files appear but can't be read

- FTP server may have disconnected
- Try unmounting and remounting

### Slow performance

- Enable caching in config file
- Increase `directory_ttl_seconds`
- Check network connection to FTP server

---

## Limitations

- FTP protocol does not support file locking. Concurrent writes from multiple clients may cause issues.
- Some FTP servers don't report accurate file sizes or timestamps.
- Very large files (>1GB) may be slow due to FTP protocol limitations.

---

## Building from Source
```bash
git clone https://github.com/yourusername/pyftpdrive.git
cd pyftpdrive
python -m venv venv
venv\\Scripts\\activate
pip install -e ".[dev]"
pytest
```

---

## Contributing

Contributions welcome. Please open an issue first to discuss major changes.

---

## License

MIT License. See LICENSE file.

---

## Acknowledgments

- [WinFsp](https://winfsp.dev/) - Windows File System Proxy
- [winfspy](https://github.com/Scille/winfspy) - Python bindings for WinFsp