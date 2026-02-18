__version__ = "0.2.0"

# Public API exports
from .cache import DirectoryCache, MetadataCache
from .config import (
    AppConfig,
    CacheConfig,
    ConnectionConfig,
    FTPConfig,
    GoogleDriveConfig,
    LogConfig,
    MountConfig,
    SSHConfig,
    load_config,
)
from .filesystem import FTPFileSystem
from .ftp_client import FileStats, FTPClient
from .remote_client import RemoteClient
from .sftp_client import SFTPClient


def get_google_drive_client():
    """Lazy loader for GoogleDriveClient.

    Returns the GoogleDriveClient class, importing it on first use so that
    importing ftp_winmount does not require google-api-python-client.
    """
    from .gdrive_client import GoogleDriveClient

    return GoogleDriveClient


__all__ = [
    "__version__",
    # Configuration
    "AppConfig",
    "FTPConfig",
    "SSHConfig",
    "GoogleDriveConfig",
    "MountConfig",
    "CacheConfig",
    "ConnectionConfig",
    "LogConfig",
    "load_config",
    # Clients
    "RemoteClient",
    "FTPClient",
    "SFTPClient",
    "get_google_drive_client",
    "FileStats",
    # Cache
    "DirectoryCache",
    "MetadataCache",
    # Filesystem
    "FTPFileSystem",
]
