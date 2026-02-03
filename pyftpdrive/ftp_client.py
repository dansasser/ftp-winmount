import ftplib
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Generator, List, Optional, Tuple, Dict
from .config import FTPConfig, ConnectionConfig

@dataclass
class FileStats:
    """Standardized file statistics independent of OS"""
    name: str
    size: int
    mtime: datetime
    is_dir: bool
    attributes: int = 0  # Windows file attributes

class FTPClient:
    """
    High-level wrapper around ftplib.FTP with connection pooling,
    retry logic, and simplified API.
    """

    def __init__(self, ftp_config: FTPConfig, conn_config: ConnectionConfig):
        self.ftp_config = ftp_config
        self.conn_config = conn_config
        # TODO: Initialize connection pool or state

    def connect(self) -> None:
        """
        Establish initial connection to the FTP server.
        Should handle authentication and passive mode setting.
        """
        raise NotImplementedError

    def disconnect(self) -> None:
        """
        Safely close connection(s).
        """
        raise NotImplementedError

    def list_dir(self, path: str) -> List[FileStats]:
        """
        List contents of a directory.

        Args:
            path: Absolute FTP path.

        Returns:
            List[FileStats]: List of file/directory objects with metadata.

        Raises:
            FileNotFoundError: If path does not exist.
            PermissionError: If access denied.
        """
        raise NotImplementedError

    def get_file_info(self, path: str) -> FileStats:
        """
        Get metadata for a single file or directory.

        Args:
            path: Absolute FTP path.

        Returns:
            FileStats object.
        """
        raise NotImplementedError

    def read_file(self, path: str, offset: int = 0, length: Optional[int] = None) -> bytes:
        """
        Read bytes from a file.

        Args:
            path: Absolute FTP path.
            offset: Byte offset to start reading from.
            length: Number of bytes to read (None for rest of file).

        Note:
            FTP RETR command usually retrieves the whole file.
            For offset/length, consider using REST command if supported,
            or download and seek.
        """
        raise NotImplementedError

    def write_file(self, path: str, data: bytes, offset: int = 0) -> int:
        """
        Write bytes to a file.

        Args:
            path: Absolute FTP path.
            data: Bytes to write.
            offset: Byte offset to write at.

        Returns:
            int: Number of bytes written.

        Note:
            If offset > 0, requires REST support or read-modify-write cycle.
        """
        raise NotImplementedError

    def create_file(self, path: str) -> None:
        """Create an empty file."""
        raise NotImplementedError

    def create_dir(self, path: str) -> None:
        """Create a directory recursively if needed."""
        raise NotImplementedError

    def delete_file(self, path: str) -> None:
        """Delete a file."""
        raise NotImplementedError

    def delete_dir(self, path: str) -> None:
        """Delete a directory (must be empty)."""
        raise NotImplementedError

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename or move a file/directory."""
        raise NotImplementedError
