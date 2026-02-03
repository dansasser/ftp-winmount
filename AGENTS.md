# Instructions for Windows Agent

## Context
This project, **PyFTPDrive**, has been scaffolded in a Linux environment. The directory structure, configuration files, and code skeletons are in place. However, the core logic relies on `winfspy` (WinFsp), which is Windows-specific.

Your task is to implement the logic within the provided skeletons.

## Prerequisites
1.  **Environment:** Windows 10/11.
2.  **Dependencies:**
    - Install WinFsp: <https://winfsp.dev/rel/> (or generic WinFsp installer).
    - Install Python dependencies: `pip install -e .[dev]`.

## Implementation Guide

### 1. Configuration & Logging (Low Hanging Fruit)
- **Files:** `pyftpdrive/config.py`, `pyftpdrive/logger.py`
- **Task:** Implement `load_config` to read the INI file and `setup_logging` to configure the Python logger.
- **Verification:** Run `python -c "from pyftpdrive.config import load_config; print(load_config('config.example.ini'))"`

### 2. FTP Client (Platform Independent)
- **File:** `pyftpdrive/ftp_client.py`
- **Task:** Implement the wrapper around `ftplib`.
- **Key Requirements:**
    - `connect()`: Handle passive mode and timeouts.
    - `list_dir()`: Parse MLSD or LIST output into `FileStats`.
    - `read_file()`/`write_file()`: Handle binary streams.
- **Testing:**
    - Spin up a local server: `python -m pyftpdlib -w -p 2121`
    - Write a unit test to verify `FTPClient` against localhost:2121.

### 3. Caching (Performance)
- **File:** `pyftpdrive/cache.py`
- **Task:** Implement `DirectoryCache` using `cachetools` or a simple dictionary with expiry.
- **Logic:**
    - `get(path)`: Return listing if `now < expires_at`.
    - `put(path, data)`: Store with `expires_at = now + ttl`.
    - `invalidate(path)`: Remove entry.

### 4. Filesystem (The Core)
- **File:** `pyftpdrive/filesystem.py`
- **Reference:** `docs/ROUTING_MATRIX.md` (Crucial!)
- **Task:** Implement the WinFsp callbacks.
- **Strategy:**
    - **Phase 1 (Read-Only):** Implement `get_security`, `open`, `read`, `read_directory`, `get_file_info`.
    - **Phase 2 (Write):** Implement `create`, `write`, `flush`, `close` (with upload), `rename`, `cleanup`.
- **Important:**
    - Map `ftp_client` exceptions to `winfspy` status codes (e.g., `STATUS_OBJECT_NAME_NOT_FOUND`).
    - Use `DirectoryCache` in `read_directory`.

### 5. CLI Entry Point
- **File:** `pyftpdrive/__main__.py`
- **Task:** Wire everything together.
    - Initialize `FTPClient`.
    - Initialize `FTPFileSystem`.
    - Create `winfspy.Mount`.
    - Start the mount.

## Testing & verification
- Use the provided `config.example.ini`.
- Run `pyftpdrive mount --config config.example.ini`.
- Open File Explorer to `Z:\`.
- Verify you can read, write, and list files.

## Documentation
- `docs/specs.md`: The original requirements.
- `docs/ROUTING_MATRIX.md`: Detailed mapping logic.
- `CLAUDE.md`: Project overview.
