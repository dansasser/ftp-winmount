__version__ = "0.2.0"

# Public API exports
from .cache import DirectoryCache, MetadataCache
from .config import (
    AppConfig,
    CacheConfig,
    ConnectionConfig,
    FTPConfig,
    LogConfig,
    MountConfig,
    SSHConfig,
    load_config,
)
from .filesystem import FTPFileSystem
from .ftp_client import FileStats, FTPClient
from .remote_client import RemoteClient
from .sftp_client import SFTPClient

__all__ = [
    "__version__",
    # Configuration
    "AppConfig",
    "FTPConfig",
    "SSHConfig",
    "MountConfig",
    "CacheConfig",
    "ConnectionConfig",
    "LogConfig",
    "load_config",
    # Clients
    "RemoteClient",
    "FTPClient",
    "SFTPClient",
    "FileStats",
    # Cache
    "DirectoryCache",
    "MetadataCache",
    # Filesystem
    "FTPFileSystem",
]
