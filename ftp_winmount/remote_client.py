"""
Remote client protocol definition.

Defines the interface that both FTPClient and SFTPClient implement,
allowing the filesystem layer to work with either transport.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .ftp_client import FileStats


@runtime_checkable
class RemoteClient(Protocol):
    """Protocol defining the remote filesystem client interface.

    Any class implementing these methods can be used as a backend
    for FTPFileSystem, regardless of the underlying transport (FTP, SFTP, etc.).
    """

    def connect(self) -> None:
        """Establish connection to the remote server."""
        ...

    def disconnect(self) -> None:
        """Close connection to the remote server."""
        ...

    def list_dir(self, path: str) -> list[FileStats]:
        """List contents of a directory.

        Args:
            path: Absolute remote path.

        Returns:
            List of FileStats objects for directory entries.

        Raises:
            FileNotFoundError: If path does not exist.
            PermissionError: If access denied.
        """
        ...

    def get_file_info(self, path: str) -> FileStats:
        """Get metadata for a single file or directory.

        Args:
            path: Absolute remote path.

        Returns:
            FileStats object.

        Raises:
            FileNotFoundError: If path does not exist.
        """
        ...

    def read_file(self, path: str, offset: int = 0, length: int | None = None) -> bytes:
        """Read bytes from a file.

        Args:
            path: Absolute remote path.
            offset: Byte offset to start reading from.
            length: Number of bytes to read (None for rest of file).

        Returns:
            File content as bytes.
        """
        ...

    def write_file(self, path: str, data: bytes, offset: int = 0) -> int:
        """Write bytes to a file.

        Args:
            path: Absolute remote path.
            data: Bytes to write.
            offset: Byte offset to write at.

        Returns:
            Number of bytes written.
        """
        ...

    def create_file(self, path: str) -> None:
        """Create an empty file."""
        ...

    def create_dir(self, path: str) -> None:
        """Create a directory (recursively if needed)."""
        ...

    def delete_file(self, path: str) -> None:
        """Delete a file."""
        ...

    def delete_dir(self, path: str) -> None:
        """Delete a directory (must be empty)."""
        ...

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename or move a file/directory."""
        ...
