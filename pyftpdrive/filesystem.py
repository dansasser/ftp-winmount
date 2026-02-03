"""
FTP Filesystem implementation for WinFsp.

This module implements WinFsp filesystem callbacks that translate
Windows file operations into FTP protocol commands.
"""

from functools import wraps

try:
    from winfspy import (
        FILE_ATTRIBUTE,
        BaseFileSystemOperations,
        FileSystem,
        NTStatusAccessDenied,
        NTStatusDirectoryNotEmpty,
        NTStatusEndOfFile,
        NTStatusMediaWriteProtected,
        NTStatusObjectNameCollision,
        NTStatusObjectNameNotFound,
    )
    from winfspy.plumbing import SecurityDescriptor
    from winfspy.plumbing.win32_filetime import filetime_now

    # Try to import NTStatusIOTimeout, fall back to custom exception if not available
    try:
        from winfspy import NTStatusIOTimeout
    except ImportError:

        class NTStatusIOTimeout(Exception):
            """IO timeout status - fallback when winfspy doesn't export it."""

            pass

    FILE_ATTRIBUTE_DIRECTORY = FILE_ATTRIBUTE.FILE_ATTRIBUTE_DIRECTORY
    FILE_ATTRIBUTE_NORMAL = FILE_ATTRIBUTE.FILE_ATTRIBUTE_NORMAL
    _DEFAULT_SD = SecurityDescriptor.from_string("O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;WD)")
    WINFSPY_AVAILABLE = True
except ImportError:
    WINFSPY_AVAILABLE = False

    class FileSystem:
        pass

    class BaseFileSystemOperations:
        pass

    FILE_ATTRIBUTE_DIRECTORY = 0x10
    FILE_ATTRIBUTE_NORMAL = 0x80
    _DEFAULT_SD = None

    def filetime_now():
        return 0

    class NTStatusObjectNameNotFound(Exception):
        pass

    class NTStatusAccessDenied(Exception):
        pass

    class NTStatusEndOfFile(Exception):
        pass

    class NTStatusMediaWriteProtected(Exception):
        pass

    class NTStatusObjectNameCollision(Exception):
        pass

    class NTStatusDirectoryNotEmpty(Exception):
        pass

    class NTStatusIOTimeout(Exception):
        """IO timeout status - fallback when winfspy not available."""

        pass


import logging
import threading
from datetime import datetime
from io import BytesIO
from typing import Any

from .cache import DirectoryCache, MetadataCache
from .ftp_client import FileStats, FTPClient

logger = logging.getLogger(__name__)

# Windows CreateFile flags
FILE_DIRECTORY_FILE = 0x00000001

# WinFsp cleanup flags
FspCleanupDelete = 0x01
FspCleanupSetAllocationSize = 0x02
FspCleanupSetArchiveBit = 0x10
FspCleanupSetLastAccessTime = 0x20
FspCleanupSetLastWriteTime = 0x40
FspCleanupSetChangeTime = 0x80

# Aliases for test compatibility
FSP_CLEANUP_DELETE = FspCleanupDelete


def datetime_to_filetime(dt: datetime) -> int:
    """Convert Python datetime to Windows FILETIME integer."""
    if dt is None:
        return filetime_now()
    EPOCH_DIFF = 116444736000000000
    timestamp = dt.timestamp()
    return int(timestamp * 10000000) + EPOCH_DIFF


def operation(fn):
    """Decorator for filesystem operations - provides thread safety and logging."""
    name = fn.__name__

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._thread_lock:
            try:
                result = fn(self, *args, **kwargs)
                logger.debug("%s: OK", name)
                return result
            except Exception as exc:
                logger.debug("%s: FAIL - %s", name, exc)
                raise

    return wrapper


class OpenedContext:
    """Lightweight context for open file handles.

    All times are FILETIME integers (100-nanosecond intervals since 1601).
    """

    def __init__(
        self, path: str, is_directory: bool, file_size: int, attributes: int, mtime_filetime: int
    ):
        self.path = path
        self.is_directory = is_directory
        self.file_size = file_size
        self.attributes = attributes
        self.creation_time = mtime_filetime
        self.last_access_time = mtime_filetime
        self.last_write_time = mtime_filetime
        self.change_time = mtime_filetime
        # For write buffering
        self.buffer = None
        self.dirty = False

    def __repr__(self):
        return f"OpenedContext({self.path!r})"


# Alias for test compatibility
FileContext = OpenedContext


class FTPFileSystem(BaseFileSystemOperations):
    """WinFsp Filesystem implementation that backs to an FTP server."""

    def __init__(self, ftp_client: FTPClient, cache_config):
        super().__init__()
        self._thread_lock = threading.Lock()
        self.ftp = ftp_client
        self.dir_cache = DirectoryCache(cache_config.directory_ttl_seconds)
        self.meta_cache = MetadataCache(cache_config.metadata_ttl_seconds)
        logger.info(
            "FTPFileSystem initialized with cache TTLs: dir=%d, meta=%d",
            cache_config.directory_ttl_seconds,
            cache_config.metadata_ttl_seconds,
        )

    def _to_ftp_path(self, win_path: str) -> str:
        """Convert Windows path to FTP path."""
        path = win_path.lstrip("\\").replace("\\", "/")
        if not path:
            return "/"
        return "/" + path if not path.startswith("/") else path

    def _filestats_to_attributes(self, stats: FileStats) -> int:
        """Convert FileStats to Windows file attributes."""
        return FILE_ATTRIBUTE_DIRECTORY if stats.is_dir else FILE_ATTRIBUTE_NORMAL

    @operation
    def get_volume_info(self) -> dict[str, Any]:
        """Get volume information."""
        return {
            "total_size": 1024 * 1024 * 1024 * 1024,
            "free_size": 500 * 1024 * 1024 * 1024,
            "volume_label": "FTP Drive",
        }

    @operation
    def get_security_by_name(self, file_name: str):
        """Get security descriptor for a file."""
        ftp_path = self._to_ftp_path(file_name)
        logger.debug("get_security_by_name: %s -> %s", file_name, ftp_path)

        cached = self.meta_cache.get(ftp_path)
        if cached is not None:
            if _DEFAULT_SD is None:
                # Fallback when winfspy not available: return placeholder values
                # Security descriptor handle=0 (null), size=20 (min valid SD size)
                return (cached["attributes"], 0, 20)
            return (cached["attributes"], _DEFAULT_SD.handle, _DEFAULT_SD.size)

        try:
            stats = self.ftp.get_file_info(ftp_path)
            attributes = self._filestats_to_attributes(stats)
            mtime_filetime = datetime_to_filetime(stats.mtime)
            self.meta_cache.put(
                ftp_path,
                {
                    "file_size": stats.size,
                    "attributes": attributes,
                    "mtime_filetime": mtime_filetime,
                    "is_dir": stats.is_dir,
                },
            )
            if _DEFAULT_SD is None:
                # Fallback when winfspy not available: return placeholder values
                # Security descriptor handle=0 (null), size=20 (min valid SD size)
                return (attributes, 0, 20)
            return (attributes, _DEFAULT_SD.handle, _DEFAULT_SD.size)

        except FileNotFoundError:
            raise NTStatusObjectNameNotFound()
        except PermissionError:
            raise NTStatusAccessDenied()
        except TimeoutError:
            raise NTStatusIOTimeout()

    @operation
    def open(self, file_name: str, create_options: int, granted_access: int) -> OpenedContext:
        """Open a file or directory."""
        ftp_path = self._to_ftp_path(file_name)
        logger.debug("open: %s -> %s", file_name, ftp_path)

        cached = self.meta_cache.get(ftp_path)
        if cached is not None:
            mtime_filetime = cached.get("mtime_filetime")
            if mtime_filetime is None:
                mtime_filetime = datetime_to_filetime(cached.get("mtime"))
            return OpenedContext(
                path=ftp_path,
                is_directory=cached["is_dir"],
                file_size=cached["file_size"],
                attributes=cached["attributes"],
                mtime_filetime=mtime_filetime,
            )

        try:
            stats = self.ftp.get_file_info(ftp_path)
            attributes = self._filestats_to_attributes(stats)
            mtime_filetime = datetime_to_filetime(stats.mtime)
            self.meta_cache.put(
                ftp_path,
                {
                    "file_size": stats.size,
                    "attributes": attributes,
                    "mtime_filetime": mtime_filetime,
                    "is_dir": stats.is_dir,
                },
            )
            return OpenedContext(
                path=ftp_path,
                is_directory=stats.is_dir,
                file_size=stats.size,
                attributes=attributes,
                mtime_filetime=mtime_filetime,
            )

        except FileNotFoundError:
            raise NTStatusObjectNameNotFound()
        except PermissionError:
            raise NTStatusAccessDenied()
        except TimeoutError:
            raise NTStatusIOTimeout()

    @operation
    def close(self, file_context: OpenedContext) -> None:
        """Close file handle. winfspy handles cleanup via _opened_objs."""
        pass

    @operation
    def read(self, file_context: OpenedContext, offset: int, length: int) -> bytes:
        """Read data from file."""
        if offset >= file_context.file_size:
            return b""

        remaining = file_context.file_size - offset
        actual_length = min(length, remaining)

        try:
            return self.ftp.read_file(file_context.path, offset, actual_length)
        except FileNotFoundError:
            raise NTStatusObjectNameNotFound()
        except PermissionError:
            raise NTStatusAccessDenied()
        except TimeoutError:
            raise NTStatusIOTimeout()

    @operation
    def read_directory(
        self, file_context: OpenedContext, marker: str | None
    ) -> list[dict[str, Any]]:
        """List directory contents."""
        path = file_context.path
        cached_entries = self.dir_cache.get(path)

        if cached_entries is None:
            try:
                stats_list = self.ftp.list_dir(path)
                cached_entries = []
                for stats in stats_list:
                    attributes = self._filestats_to_attributes(stats)
                    mtime_filetime = datetime_to_filetime(stats.mtime)
                    cached_entries.append(
                        {
                            "name": stats.name,
                            "file_size": stats.size,
                            "allocation_size": stats.size,
                            "creation_time": mtime_filetime,
                            "last_access_time": mtime_filetime,
                            "last_write_time": mtime_filetime,
                            "change_time": mtime_filetime,
                            "file_attributes": attributes,
                            "is_dir": stats.is_dir,
                        }
                    )
                    file_path = path.rstrip("/") + "/" + stats.name
                    self.meta_cache.put(
                        file_path,
                        {
                            "file_size": stats.size,
                            "attributes": attributes,
                            "mtime_filetime": mtime_filetime,
                            "is_dir": stats.is_dir,
                        },
                    )
                self.dir_cache.put(path, cached_entries)

            except FileNotFoundError:
                raise NTStatusObjectNameNotFound()
            except PermissionError:
                raise NTStatusAccessDenied()
            except TimeoutError:
                raise NTStatusIOTimeout()

        result = []
        past_marker = marker is None
        for entry in cached_entries:
            name = entry["name"]
            if not past_marker:
                if name == marker:
                    past_marker = True
                continue
            result.append(
                {
                    "file_name": name,
                    "file_size": entry["file_size"],
                    "allocation_size": entry["allocation_size"],
                    "creation_time": entry["creation_time"],
                    "last_access_time": entry["last_access_time"],
                    "last_write_time": entry["last_write_time"],
                    "change_time": entry["change_time"],
                    "file_attributes": entry["file_attributes"],
                }
            )
        return result

    @operation
    def get_security(self, file_context: OpenedContext):
        """Get security descriptor for an open file handle.

        Returns a default security descriptor since FTP doesn't support
        Windows ACLs. This allows all users full access.
        """
        if _DEFAULT_SD is None:
            # Fallback when winfspy not available: return placeholder values
            # Security descriptor handle=0 (null), size=20 (min valid SD size)
            return (0, 20)
        return (_DEFAULT_SD.handle, _DEFAULT_SD.size)

    @operation
    def get_file_info(self, file_context: OpenedContext) -> dict[str, Any]:
        """Get file metadata."""
        return {
            "file_attributes": file_context.attributes,
            "file_size": file_context.file_size,
            "allocation_size": file_context.file_size,
            "creation_time": file_context.creation_time,
            "last_access_time": file_context.last_access_time,
            "last_write_time": file_context.last_write_time,
            "change_time": file_context.change_time,
            "index_number": 0,
        }

    @operation
    def write(
        self,
        file_context: OpenedContext,
        buffer: bytes,
        offset: int,
        write_to_end_of_file: bool = False,
        constrained_io: bool = False,
    ) -> int:
        """Write data to file."""
        if file_context.buffer is None:
            if file_context.file_size > 0:
                try:
                    existing_data = self.ftp.read_file(file_context.path, 0, None)
                    file_context.buffer = BytesIO(existing_data)
                except FileNotFoundError:
                    file_context.buffer = BytesIO()
            else:
                file_context.buffer = BytesIO()

        if write_to_end_of_file:
            offset = file_context.file_size

        file_context.buffer.seek(offset)
        bytes_written = file_context.buffer.write(buffer)

        new_size = offset + bytes_written
        if new_size > file_context.file_size:
            file_context.file_size = new_size

        file_context.dirty = True
        return bytes_written

    @operation
    def flush(self, file_context: OpenedContext) -> None:
        """Flush buffers to FTP server."""
        if not file_context.dirty or file_context.buffer is None:
            return

        try:
            file_context.buffer.seek(0)
            data = file_context.buffer.read()
            self.ftp.write_file(file_context.path, data, 0)
            self.meta_cache.invalidate(file_context.path)
            file_context.dirty = False
        except PermissionError:
            raise NTStatusAccessDenied()
        except FileNotFoundError:
            raise NTStatusObjectNameNotFound()
        except TimeoutError:
            raise NTStatusIOTimeout()

    @operation
    def set_file_info(self, file_context: OpenedContext, file_info: dict[str, Any]) -> None:
        """Set file metadata."""
        if "file_size" in file_info and file_info["file_size"] == 0:
            file_context.buffer = BytesIO()
            file_context.file_size = 0
            file_context.dirty = True

    @operation
    def set_file_size(
        self,
        file_context: OpenedContext,
        new_size: int,
        set_allocation_size: bool,
    ) -> None:
        """Set the file size (truncate or extend)."""
        logger.debug(
            "set_file_size: %s to %d (allocation=%s)",
            file_context.path,
            new_size,
            set_allocation_size,
        )

        # Ensure we have a buffer
        if file_context.buffer is None:
            if file_context.file_size > 0:
                try:
                    content = self.ftp.read_file(file_context.path)
                    file_context.buffer = BytesIO(content)
                except FileNotFoundError:
                    file_context.buffer = BytesIO()
            else:
                file_context.buffer = BytesIO()

        # Truncate or extend the buffer
        file_context.buffer.seek(0)
        current_content = file_context.buffer.read()

        if new_size < len(current_content):
            # Truncate
            file_context.buffer = BytesIO(current_content[:new_size])
        elif new_size > len(current_content):
            # Extend with zeros
            file_context.buffer = BytesIO(
                current_content + b"\x00" * (new_size - len(current_content))
            )
        # else: same size, no change needed

        file_context.file_size = new_size
        file_context.dirty = True

    @operation
    def overwrite(
        self,
        file_context: OpenedContext,
        file_attributes: int,
        replace_file_attributes: bool,
        allocation_size: int,
    ) -> None:
        """Overwrite an existing file (truncate to zero and prepare for writing)."""
        logger.debug("overwrite: %s", file_context.path)

        # Reset buffer to empty
        file_context.buffer = BytesIO()
        file_context.file_size = 0
        file_context.dirty = True

        # Update attributes if requested
        if replace_file_attributes:
            file_context.attributes = file_attributes

    @operation
    def create(
        self,
        file_name: str,
        create_options: int,
        granted_access: int,
        file_attributes: int,
        security_descriptor,
        allocation_size: int,
    ) -> OpenedContext:
        """Create a new file or directory."""
        ftp_path = self._to_ftp_path(file_name)
        is_directory = bool(create_options & FILE_DIRECTORY_FILE)
        logger.debug("create: %s -> %s (directory=%s)", file_name, ftp_path, is_directory)

        try:
            if is_directory:
                self.ftp.create_dir(ftp_path)
                attributes = FILE_ATTRIBUTE_DIRECTORY
            else:
                self.ftp.create_file(ftp_path)
                attributes = FILE_ATTRIBUTE_NORMAL

            self.dir_cache.invalidate_parent(ftp_path)
            now_filetime = filetime_now()

            ctx = OpenedContext(
                path=ftp_path,
                is_directory=is_directory,
                file_size=0,
                attributes=attributes,
                mtime_filetime=now_filetime,
            )
            if not is_directory:
                ctx.buffer = BytesIO()
            return ctx

        except FileExistsError:
            raise NTStatusObjectNameCollision()
        except PermissionError:
            raise NTStatusAccessDenied()
        except TimeoutError:
            raise NTStatusIOTimeout()

    @operation
    def cleanup(self, file_context: OpenedContext, file_name: str, flags: int) -> None:
        """Called when handle is closed. Handle deletion and flush here."""
        # Flush dirty buffers
        if file_context.dirty and file_context.buffer is not None:
            try:
                file_context.buffer.seek(0)
                data = file_context.buffer.read()
                self.ftp.write_file(file_context.path, data, 0)
                self.meta_cache.invalidate(file_context.path)
                file_context.dirty = False
            except Exception as e:
                logger.warning("cleanup: flush failed for %s: %s", file_context.path, e)

        # Handle deletion
        if not (flags & FspCleanupDelete):
            return

        try:
            if file_context.is_directory:
                self.ftp.delete_dir(file_context.path)
                self.dir_cache.invalidate(file_context.path)
            else:
                self.ftp.delete_file(file_context.path)

            self.dir_cache.invalidate_parent(file_context.path)
            self.meta_cache.invalidate(file_context.path)

        except FileNotFoundError:
            pass
        except PermissionError:
            raise NTStatusAccessDenied()
        except OSError as e:
            if "not empty" in str(e).lower():
                raise NTStatusDirectoryNotEmpty()
            raise NTStatusAccessDenied()

    @operation
    def rename(
        self,
        file_context: OpenedContext,
        file_name: str,
        new_file_name: str,
        replace_if_exists: bool,
    ) -> None:
        """Rename/Move file or directory."""
        old_ftp_path = self._to_ftp_path(file_name)
        new_ftp_path = self._to_ftp_path(new_file_name)

        try:
            if not replace_if_exists:
                try:
                    self.ftp.get_file_info(new_ftp_path)
                    raise NTStatusObjectNameCollision()
                except FileNotFoundError:
                    pass

            if replace_if_exists:
                try:
                    stats = self.ftp.get_file_info(new_ftp_path)
                    if stats.is_dir:
                        self.ftp.delete_dir(new_ftp_path)
                    else:
                        self.ftp.delete_file(new_ftp_path)
                except FileNotFoundError:
                    pass

            self.ftp.rename(old_ftp_path, new_ftp_path)

            self.dir_cache.invalidate_parent(old_ftp_path)
            self.dir_cache.invalidate_parent(new_ftp_path)
            self.meta_cache.invalidate(old_ftp_path)
            self.meta_cache.invalidate(new_ftp_path)

            if file_context.is_directory:
                self.dir_cache.invalidate(old_ftp_path)

            file_context.path = new_ftp_path

        except FileNotFoundError:
            raise NTStatusObjectNameNotFound()
        except PermissionError:
            raise NTStatusAccessDenied()
        except TimeoutError:
            raise NTStatusIOTimeout()
