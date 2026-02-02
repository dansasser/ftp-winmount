# CLAUDE.md

## Project Overview

PyFTPDrive is a Python application that mounts a remote FTP server as a local Windows drive letter using WinFsp. This enables seamless file access from any application (VS Code, File Explorer, etc.) without sync operations or third-party adware.

## Tech Stack

- Python 3.10+
- WinFsp (Windows File System Proxy) - kernel driver for virtual filesystems
- winfspy - Python bindings for WinFsp
- ftplib (standard library) - FTP protocol

## Project Structure
```
pyftpdrive/
├── pyftpdrive/
│   ├── __init__.py
│   ├── __main__.py          # Entry point, CLI handling
│   ├── config.py            # Configuration loading
│   ├── ftp_client.py        # FTP operations wrapper
│   ├── filesystem.py        # WinFsp filesystem implementation
│   ├── cache.py             # Directory/metadata caching
│   └── logger.py            # Logging setup
├── config.example.ini
├── requirements.txt
├── setup.py
└── README.md
```

## Development Setup

1. Install WinFsp from https://winfsp.dev/
2. Create virtual environment: `python -m venv venv`
3. Activate: `venv\\Scripts\\activate`
4. Install dependencies: `pip install -r requirements.txt`

## Dependencies
```
winfspy
cachetools
```

## Build Commands
```bash
# Install in development mode
pip install -e .

# Run directly
python -m pyftpdrive mount --host 192.168.0.130 --port 2121 --drive Z

# Run tests
pytest

# Build distributable
python -m build
```

## Architecture

### filesystem.py
Implements WinFsp filesystem callbacks. This is the core that translates Windows file operations into FTP commands. Key callbacks:
- `open()` - Open file or directory
- `close()` - Close file handle
- `read()` - Read bytes from file
- `write()` - Write bytes to file
- `read_directory()` - List directory contents
- `create()` - Create new file
- `cleanup()` - Handle deletion flags
- `rename()` - Rename files/folders

### ftp_client.py
Wraps ftplib with connection management, retry logic, and reconnection handling. Exposes clean methods like `list_dir()`, `read_file()`, `write_file()`, etc. Handles connection pooling and error translation.

### cache.py
Caches directory listings and file metadata to reduce FTP round-trips. Uses TTL-based expiration (default 30 seconds). Invalidates on write operations.

### config.py
Loads configuration from INI file or command-line arguments. Supports: host, port, username, password, drive letter, cache TTL, timeout, retry attempts, log level.

### logger.py
Configures logging to file and optionally console. Log levels: DEBUG, INFO, WARNING, ERROR.

## Code Style

- Use type hints on all function signatures
- Docstrings on public methods
- Handle all exceptions explicitly - never let FTP errors bubble up as generic I/O errors
- Map FTP errors to appropriate Windows NTSTATUS codes
- Log all file operations at DEBUG level
- Log errors at ERROR level with full context

## Error Handling

Map FTP errors to Windows error codes:
- File not found → `STATUS_OBJECT_NAME_NOT_FOUND`
- Permission denied → `STATUS_ACCESS_DENIED`
- Connection lost → `STATUS_CONNECTION_DISCONNECTED`
- Timeout → `STATUS_IO_TIMEOUT`
- Directory not empty → `STATUS_DIRECTORY_NOT_EMPTY`

Never return generic errors. Windows applications need proper error codes to display meaningful messages.

## FTP Specifics

Target server uses pyftpdlib with anonymous access:
```bash
python -m pyftpdlib -p 2121 -i 0.0.0.0 -w
```

Key considerations:
- Anonymous FTP (no username/password)
- Non-standard port (2121)
- Full read/write access (-w flag)
- Folder names contain spaces and special characters
- UTF-8 encoding for filenames

## Testing

Test against local pyftpdlib server:
```bash
# Start test server in a temp directory
python -m pyftpdlib -p 2121 -w
```

Test cases must cover:
- Folder names with spaces
- Folder names with special characters (apostrophes, dashes, unicode)
- Large files (>100MB)
- Concurrent access from multiple applications
- Connection drop and reconnection
- Server unavailable at mount time

## Phase Implementation

### Phase 1 (MVP)
- Basic mount/unmount
- Read-only file access
- Directory listing
- Handle filenames with spaces

### Phase 2
- Write support (create, modify, delete)
- Caching layer
- Reconnect logic

### Phase 3
- Configuration file support
- Full CLI with help
- File logging

### Phase 4
- System tray icon
- Windows service option
- Auto-mount on Windows startup

## Common Issues

### "WinFsp not found"
WinFsp must be installed system-wide from https://winfsp.dev/. The Python package winfspy is just bindings.

### "Drive letter in use"
Check if another application mounted to that letter. Use `net use` to see mapped drives.

### "Access denied" on mount
Run as administrator or check WinFsp is properly installed.

### I/O errors on subdirectories
Usually means FTP connection dropped or server-side issue. Check FTP server is running and accessible via `ftp <host> <port>` command.

## Reference

- WinFsp documentation: https://winfsp.dev/doc/
- winfspy examples: https://github.com/Scille/winfspy
- ftplib documentation: https://docs.python.org/3/library/ftplib.html
- NTSTATUS codes: https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55