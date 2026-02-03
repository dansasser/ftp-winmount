try:
    import winfspy
    from winfspy import (
        FileSystem,
        BaseFileSystemOperations,
        FILE_ATTRIBUTE_DIRECTORY,
        FILE_ATTRIBUTE_NORMAL,
        STATUS_SUCCESS,
        STATUS_OBJECT_NAME_NOT_FOUND,
        STATUS_END_OF_FILE
    )
except ImportError:
    # Allow this file to be imported in non-Windows environments for inspection
    class FileSystem: pass
    class BaseFileSystemOperations: pass
    # Define dummy constants
    FILE_ATTRIBUTE_DIRECTORY = 0x10
    FILE_ATTRIBUTE_NORMAL = 0x80
    STATUS_SUCCESS = 0
    STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034
    STATUS_END_OF_FILE = 0x80000011

from typing import Optional, List
from .ftp_client import FTPClient
from .cache import DirectoryCache, MetadataCache

class FTPFileSystem(FileSystem):
    """
    WinFsp Filesystem implementation that backs to an FTP server.
    """

    def __init__(self, ftp_client: FTPClient, cache_config):
        super().__init__()
        self.ftp = ftp_client
        # Initialize caches based on config
        self.dir_cache = DirectoryCache(cache_config.directory_ttl_seconds)
        self.meta_cache = MetadataCache(cache_config.metadata_ttl_seconds)

    def get_security_by_name(self, file_name: str):
        """
        Get security descriptor for a file.

        For FTP, we generally return a default permissive security descriptor
        to allow the user to read/write everything.

        Returns:
            Tuple of (file_attributes, security_descriptor, size)
        """
        raise NotImplementedError

    def open(self, file_name: str, create_options: int, granted_access: int):
        """
        Open a file or directory.

        Logic:
        1. Check if file exists in cache or via FTP LIST/MLSD.
        2. If file doesn't exist, return STATUS_OBJECT_NAME_NOT_FOUND.
        3. Create a FileContext object to track this handle.
        4. If it's a file we intend to read, maybe pre-fetch or prepare FTP connection.

        Args:
            file_name: Path relative to mount point (e.g., "\\folder\\file.txt")
            create_options: Windows create options
            granted_access: Requested access rights

        Returns:
            FileContext object (opaque handle passed to other methods)
        """
        raise NotImplementedError

    def close(self, file_context):
        """
        Close file handle.

        Logic:
        1. If file was written to, ensure data is flushed to FTP.
        2. Release FTP connection to pool.
        3. Free FileContext.
        """
        raise NotImplementedError

    def read(self, file_context, offset: int, length: int):
        """
        Read data from file.

        Logic:
        1. Check if data is in local read buffer.
        2. If not, fetch from FTP using `ftp.read_file(path, offset, length)`.
        3. Handle EOF (return fewer bytes than requested).

        Returns:
            bytes: Data read
        """
        raise NotImplementedError

    def write(self, file_context, buffer: bytes, offset: int):
        """
        Write data to file.

        Logic:
        1. Write to local buffer in FileContext.
        2. Mark context as 'dirty'.
        3. (Optional) Flush to FTP immediately if buffer full.

        Returns:
            int: Bytes written
        """
        raise NotImplementedError

    def flush(self, file_context):
        """
        Flush buffers to storage.

        Logic:
        1. If FileContext is dirty, upload buffer to FTP.
        2. Use `ftp.write_file()` or `ftp.stor()`.
        3. Update cache with new file size/time.
        """
        raise NotImplementedError

    def get_file_info(self, file_context):
        """
        Get file metadata (stat).

        Returns:
            FileInfo object (size, times, attributes)
        """
        raise NotImplementedError

    def set_file_info(self, file_context, file_info):
        """
        Set file metadata (chmod/chown/utime equivalent).

        Note: FTP has limited support for this (MDTM, CHMOD).
        Implement what is possible, ignore others or return success silently.
        """
        raise NotImplementedError

    def read_directory(self, file_context, marker: Optional[str]):
        """
        List directory contents.

        Logic:
        1. Check DirectoryCache.
        2. If miss, call `ftp.list_dir(path)`.
        3. Update Cache.
        4. Return list of directory entries.

        Args:
            marker: If not None, start listing after this filename (for pagination).
        """
        raise NotImplementedError

    def create(self, file_name: str, create_options: int, granted_access: int, file_attributes: int, security_descriptor: bytes, allocation_size: int):
        """
        Create a new file or directory.

        Logic:
        1. If FILE_DIRECTORY_FILE in create_options:
           Call `ftp.create_dir()`.
        2. Else:
           Call `ftp.create_file()`.
        3. Invalidate parent directory cache.

        Returns:
            FileContext for the new file.
        """
        raise NotImplementedError

    def cleanup(self, file_context, flags: int):
        """
        Called when handle is closed. Handle deletion here.

        Logic:
        1. If flags indicates DeleteOnClose:
           Call `ftp.delete_file()` or `ftp.delete_dir()`.
           Invalidate parent cache.
        """
        raise NotImplementedError

    def rename(self, file_context, file_name: str, new_file_name: str, replace_if_exists: bool):
        """
        Rename/Move file.

        Logic:
        1. Call `ftp.rename(old, new)`.
        2. Invalidate caches for old parent and new parent.
        """
        raise NotImplementedError
