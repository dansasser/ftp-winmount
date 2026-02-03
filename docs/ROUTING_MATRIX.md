# Routing Matrix: WinFsp to FTP Mapping

This document details how WinFsp filesystem operations should be routed to FTP commands. It serves as the primary specification for implementing `filesystem.py`.

## Status Code Definitions

- `SUCCESS`: `STATUS_SUCCESS` (0x00000000)
- `NOT_FOUND`: `STATUS_OBJECT_NAME_NOT_FOUND` (0xC0000034)
- `ACCESS_DENIED`: `STATUS_ACCESS_DENIED` (0xC0000022)
- `EXISTS`: `STATUS_OBJECT_NAME_COLLISION` (0xC0000035)
- `NOT_EMPTY`: `STATUS_DIRECTORY_NOT_EMPTY` (0xC0000101)
- `TIMEOUT`: `STATUS_IO_TIMEOUT` (0xC00000B5)
- `EOF`: `STATUS_END_OF_FILE` (0x80000011)

## Operation Matrix

| WinFsp Method | Scenario | FTP Command Sequence | Logic | Error Mapping |
|---------------|----------|----------------------|-------|---------------|
| `get_security_by_name` | File/Dir exists | `MLST` or `SIZE` | Check if file exists. Return default security descriptor. | `550` -> `NOT_FOUND` |
| | File does not exist | | | |
| `open` | Open existing file | `SIZE` / `MDTM` | Verify existence. Create `FileContext`. | `550` -> `NOT_FOUND` |
| | Open directory | `MLSD` (check) | Verify it is a directory. | `550` -> `NOT_FOUND` |
| | Create new file | | **Do nothing** here. Wait for `create` call. | |
| `create` | Create file | `STOR` (empty) | Create empty file immediately or mark context as "new" and wait for write. | `550` -> `ACCESS_DENIED` |
| | Create directory | `MKD` | Execute `MKD <path>`. | `550` (exists) -> `EXISTS` |
| `read` | Read from offset | `RETR` | If offset=0: `RETR`. If offset>0: `REST` + `RETR` (if supported) or download & seek. | `450` -> `ACCESS_DENIED`, `Timeout` -> `TIMEOUT` |
| `write` | Write to offset | `STOR` | Buffer writes. Append not supported natively in random access. Rewrite entire file if modifying middle? **Strategy:** Cache small files in memory, large files via temp file. | `552` (Quota) -> `DISK_FULL` |
| `read_directory` | List contents | `MLSD` or `LIST` | Fetch listing. Parse entries. Return `DirectoryEntry` objects. | `550` -> `NOT_FOUND` |
| `get_file_info` | Get stats | `MLST` or `SIZE`+`MDTM` | Return size, alloc size, times, attributes. | |
| `set_file_info` | Resize (Truncate) | `STOR` (empty) | If size=0, overwrite with empty. Else not supported? | |
| | Set Times | `MFMT` or `MDTM` | Update timestamp if server supports it. | |
| | Rename | | **Handled in `rename` callback**. | |
| `rename` | Rename/Move | `RNFR` + `RNTO` | 1. `RNFR <old>`<br>2. `RNTO <new>` | `550` -> `NOT_FOUND` or `ACCESS_DENIED` |
| `cleanup` | Delete flag set | `DELE` or `RMD` | If `DeleteOnClose` is set:<br>If file: `DELE`<br>If dir: `RMD` | `550` (NotEmpty) -> `NOT_EMPTY` |
| `close` | File modified | `STOR` | If file was dirty, flush buffer to server. | |

## Special Considerations

### 1. Write Strategy (The "Buffering" Problem)
FTP is stream-based, not block-based. You cannot change byte 50 of a 1GB file without re-uploading the file (usually).
**Recommended Approach for MVP:**
- **Small Files (<10MB):** Buffer entire file in memory. On `close()`, upload via `STOR`.
- **Large Files:** Download to temporary file on disk. Perform writes on temp file. On `close()`, upload temp file to FTP.

### 2. Connection Management
- Do not open a new FTP connection for every `read()` operation.
- Use the `FTPClient` pool.
- WinFsp calls are multithreaded. `FTPClient` must be thread-safe or use a pool.

### 3. Caching
- **Directory Listing:** Essential for performance. Explorer spams `read_directory`. Cache for `directory_ttl_seconds`.
- **File Attributes:** Cache `SIZE` and `MDTM` results.
- **Invalidation:** Any `write`, `create`, `rename`, `delete` operation must invalidate the cache for that directory.

### 4. Path Handling
- WinFsp provides paths like `\folder\file.txt`.
- FTP expects `/folder/file.txt`.
- Convert backslashes to forward slashes.
- Handle encoding (UTF-8 vs CP1252) based on config.
