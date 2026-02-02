# PyFTPDrive - Technical Specification

## Overview

PyFTPDrive is a Python application that mounts a remote FTP server as a local Windows drive letter, enabling seamless file access from any application (VS Code, File Explorer, etc.) without sync or third-party adware.

---

## System Requirements

- Windows 10/11
- Python 3.10+
- WinFsp (Windows File System Proxy) installed - https://winfsp.dev/
- Network access to FTP server

## Python Dependencies

- `winfspy` - Python bindings for WinFsp
- `ftplib` (standard library) - FTP protocol handling
- `threading` - Concurrent file operations
- `cachetools` - Directory listing cache
- `logging` - Debug and error logging
- `configparser` or `tomllib` - Configuration file support

---

## Core Features

### 1. Drive Mounting

- Mount FTP server to specified drive letter (e.g., Z:)
- Support custom port numbers (default 21, your case 2121)
- Support anonymous FTP (no credentials)
- Support authenticated FTP (username/password)
- Graceful unmount on application exit

### 2. File Operations (Read)

- List directories
- Read file contents
- Get file size
- Get file modification time
- Handle files and folders with spaces/special characters in names

### 3. File Operations (Write)

- Create new files
- Modify existing files
- Delete files
- Create directories
- Delete directories
- Rename files/folders

### 4. Performance

- Directory listing cache (configurable TTL, default 30 seconds)
- Connection pooling (reuse FTP connections)
- Lazy loading (don't fetch file contents until accessed)
- Configurable read buffer size

### 5. Reliability

- Auto-reconnect on connection drop
- Retry logic for failed operations (configurable attempts)
- Timeout handling
- Proper error messages to Windows (not generic I/O errors)

### 6. Configuration (config.ini or config.toml)

- FTP host address
- FTP port
- Username (optional, blank for anonymous)
- Password (optional)
- Drive letter to mount
- Cache TTL
- Connection timeout
- Max retry attempts
- Log level
- Log file path

### 7. Logging

- Log all operations to file
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- Console output option for debugging

### 8. User Interface

- Command-line interface for basic usage
- System tray icon (optional, future enhancement)
- Show mount status
- Manual unmount command

---

## Command Line Interface
```bash
# Mount with config file
pyftpdrive mount --config config.ini

# Mount with arguments
pyftpdrive mount --host 192.168.0.130 --port 2121 --drive Z

# Unmount
pyftpdrive unmount --drive Z

# Status
pyftpdrive status
```

---

## File Structure
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
├── config.example.ini       # Example configuration
├── requirements.txt
├── setup.py
└── README.md
```

---

## Filesystem Implementation (filesystem.py)

These are the WinFsp callbacks you need to implement:

| Method | Purpose |
|--------|---------|
| `get_security_by_name(file_name)` | Get file/folder security info |
| `open(file_name, create_options, granted_access)` | Open file or directory |
| `close(file_context)` | Close file handle |
| `read(file_context, offset, length)` | Read bytes from file |
| `write(file_context, buffer, offset)` | Write bytes to file |
| `flush(file_context)` | Flush pending writes |
| `get_file_info(file_context)` | Get file metadata |
| `set_file_info(file_context, file_info)` | Set file metadata |
| `read_directory(file_context, marker)` | List directory contents |
| `create(file_name, ...)` | Create new file |
| `cleanup(file_context, flags)` | Cleanup before close |
| `overwrite(file_context, ...)` | Overwrite existing file |
| `rename(file_context, file_name, new_file_name)` | Rename file |
| `set_delete(file_context)` | Mark for deletion |

---

## FTP Client Wrapper (ftp_client.py)

| Method | Purpose |
|--------|---------|
| `connect()` | Establish FTP connection |
| `disconnect()` | Close connection |
| `reconnect()` | Reconnect after failure |
| `list_dir(path)` | Return list of files/folders with metadata |
| `get_file_size(path)` | Return file size in bytes |
| `get_file_mtime(path)` | Return modification timestamp |
| `read_file(path, offset, length)` | Read bytes from file |
| `write_file(path, data, offset)` | Write bytes to file |
| `create_file(path)` | Create empty file |
| `delete_file(path)` | Delete file |
| `create_dir(path)` | Create directory |
| `delete_dir(path)` | Delete directory |
| `rename(old_path, new_path)` | Rename file or directory |
| `exists(path)` | Check if path exists |
| `is_dir(path)` | Check if path is directory |

---

## Error Handling

Map FTP errors to Windows error codes:

| FTP Error | Windows Status Code |
|-----------|---------------------|
| File not found | `STATUS_OBJECT_NAME_NOT_FOUND` |
| Permission denied | `STATUS_ACCESS_DENIED` |
| Connection lost | `STATUS_CONNECTION_DISCONNECTED` |
| Timeout | `STATUS_IO_TIMEOUT` |
| Directory not empty | `STATUS_DIRECTORY_NOT_EMPTY` |
| Already exists | `STATUS_OBJECT_NAME_COLLISION` |
| Not a directory | `STATUS_NOT_A_DIRECTORY` |
| Is a directory | `STATUS_FILE_IS_A_DIRECTORY` |
| Invalid path | `STATUS_OBJECT_PATH_INVALID` |
| Server error | `STATUS_UNEXPECTED_IO_ERROR` |

---

## Configuration File Format (config.ini)
```ini
[ftp]
host = 192.168.0.130
port = 2121
username = 
password = 
passive_mode = true

[mount]
drive_letter = Z
volume_label = FTP Drive

[cache]
enabled = true
directory_ttl_seconds = 30
metadata_ttl_seconds = 60

[connection]
timeout_seconds = 30
retry_attempts = 3
retry_delay_seconds = 1
keepalive_interval_seconds = 60

[logging]
level = INFO
file = pyftpdrive.log
console = false
```

---

## Data Structures

### FileContext

Holds state for an open file handle:
```python
@dataclass
class FileContext:
    path: str                    # Full FTP path
    is_directory: bool           # True if directory
    file_size: int               # Size in bytes
    creation_time: datetime      # Creation timestamp
    last_access_time: datetime   # Last access timestamp
    last_write_time: datetime    # Last modification timestamp
    attributes: int              # Windows file attributes
    buffer: BytesIO | None       # Write buffer for pending writes
    dirty: bool                  # True if buffer has unwritten data
```

### DirectoryEntry

Represents a file or folder in a directory listing:
```python
@dataclass
class DirectoryEntry:
    name: str                    # Filename only, no path
    is_directory: bool
    size: int
    creation_time: datetime
    last_write_time: datetime
    attributes: int
```

### CacheEntry

Wraps cached data with expiration:
```python
@dataclass
class CacheEntry:
    data: Any
    expires_at: float            # Unix timestamp
```

---

## Threading Model

- Main thread: WinFsp event loop
- FTP operations: Synchronous within WinFsp callbacks
- Connection pool: Thread-safe with locks
- Cache: Thread-safe with locks
- Reconnection: Background thread monitors connection health

---

## Testing Checklist

### Basic Operations
- [ ] Mount drive with anonymous FTP
- [ ] Mount drive with authenticated FTP
- [ ] List root directory
- [ ] List subdirectory with spaces in name
- [ ] List subdirectory with special characters (apostrophes, unicode)
- [ ] Read small file (<1MB)
- [ ] Read large file (>100MB)
- [ ] Open file in VS Code
- [ ] Open folder in VS Code as workspace

### Write Operations
- [ ] Create new empty file
- [ ] Create file with content
- [ ] Edit existing file
- [ ] Append to existing file
- [ ] Delete file
- [ ] Create directory
- [ ] Delete empty directory
- [ ] Delete directory with contents (should fail)
- [ ] Rename file
- [ ] Rename directory
- [ ] Move file to different directory
- [ ] Copy file (read + write)

### Error Handling
- [ ] Access non-existent file
- [ ] Access non-existent directory
- [ ] Delete non-existent file
- [ ] Create file that already exists
- [ ] Write to read-only server
- [ ] Handle server disconnect mid-operation
- [ ] Handle server not available at startup
- [ ] Handle network timeout

### Reliability
- [ ] Reconnect after server restart
- [ ] Reconnect after network interruption
- [ ] Handle concurrent access from multiple apps
- [ ] Long-running session (hours)
- [ ] Mount survives sleep/wake cycle

### Unmount
- [ ] Unmount cleanly via CLI
- [ ] Unmount cleanly via Ctrl+C
- [ ] Unmount with open file handles
- [ ] Remount after unmount

---

## Development Phases

### Phase 1 - MVP (Read-Only)

**Goal:** Mount FTP as drive, browse and read files

- [ ] Project structure setup
- [ ] WinFsp basic integration
- [ ] FTP connection (anonymous)
- [ ] List root directory
- [ ] Navigate subdirectories
- [ ] Read file contents
- [ ] Handle filenames with spaces
- [ ] Basic CLI (mount command only)

**Success Criteria:** Can open FTP folder in VS Code and read files

### Phase 2 - Write Support

**Goal:** Full read/write access

- [ ] Create files
- [ ] Modify files
- [ ] Delete files
- [ ] Create directories
- [ ] Delete directories
- [ ] Rename files/directories
- [ ] Write buffering and flush

**Success Criteria:** Can edit and save files in VS Code

### Phase 3 - Reliability

**Goal:** Handle real-world conditions

- [ ] Directory listing cache
- [ ] Metadata cache
- [ ] Connection timeout handling
- [ ] Auto-reconnect on disconnect
- [ ] Retry logic with backoff
- [ ] Proper Windows error codes

**Success Criteria:** Survives network interruptions gracefully

### Phase 4 - Configuration

**Goal:** User-friendly configuration

- [ ] Configuration file support (INI)
- [ ] Full CLI with all options
- [ ] Help text and documentation
- [ ] Logging to file
- [ ] Configurable log levels

**Success Criteria:** User can configure all options without code changes

### Phase 5 - Polish

**Goal:** Production-ready

- [ ] System tray icon
- [ ] Mount status display
- [ ] Unmount from tray
- [ ] Auto-mount on startup option
- [ ] Windows service mode
- [ ] Installer/package

**Success Criteria:** Non-technical user can install and use

---

## Known Challenges

### FTP Protocol Limitations

1. **No random access:** FTP doesn't support reading from arbitrary offsets. For partial reads, must download entire file or use REST command (not universally supported).

2. **No file locking:** FT