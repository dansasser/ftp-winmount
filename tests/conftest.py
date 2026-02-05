"""
Shared pytest fixtures for PyFTPDrive tests.
"""

import ftplib
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ftp_winmount.config import (
    AppConfig,
    CacheConfig,
    ConnectionConfig,
    FTPConfig,
    LogConfig,
    MountConfig,
)
from ftp_winmount.ftp_client import FileStats, FTPClient


@pytest.fixture
def tmp_config_file(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Creates a temporary INI configuration file for config tests.

    Returns:
        Path to the temporary config file.
    """
    config_content = """[ftp]
host = testserver.local
port = 2121
username = testuser
password = testpass
passive_mode = true
encoding = utf-8

[mount]
drive_letter = Z
volume_label = Test FTP Drive

[cache]
enabled = true
directory_ttl_seconds = 60
metadata_ttl_seconds = 120

[connection]
timeout_seconds = 45
retry_attempts = 5
retry_delay_seconds = 2
keepalive_interval_seconds = 90

[logging]
level = DEBUG
file = test.log
console = false
"""
    config_path = tmp_path / "test_config.ini"
    config_path.write_text(config_content, encoding="utf-8")
    yield config_path


@pytest.fixture
def minimal_config_file(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Creates a minimal INI configuration file with only required fields.

    Returns:
        Path to the temporary config file.
    """
    config_content = """[ftp]
host = minimal.server.com

[mount]
drive_letter = X
"""
    config_path = tmp_path / "minimal_config.ini"
    config_path.write_text(config_content, encoding="utf-8")
    yield config_path


@pytest.fixture
def mock_ftp() -> Generator[MagicMock, None, None]:
    """
    Creates a mocked ftplib.FTP instance.

    Returns:
        Mocked FTP object with common methods stubbed.
    """
    mock = MagicMock(spec=ftplib.FTP)
    mock.encoding = "utf-8"

    # Default responses
    mock.sendcmd.return_value = "200 OK"
    mock.voidcmd.return_value = None
    mock.login.return_value = "230 Login successful"
    mock.cwd.return_value = "250 OK"
    mock.pwd.return_value = "/"
    mock.quit.return_value = "221 Goodbye"

    yield mock


@pytest.fixture
def ftp_config() -> FTPConfig:
    """Creates a standard FTPConfig for testing."""
    return FTPConfig(
        host="test.ftp.local",
        port=2121,
        username="testuser",
        password="testpass",
        passive_mode=True,
        encoding="utf-8",
    )


@pytest.fixture
def conn_config() -> ConnectionConfig:
    """Creates a standard ConnectionConfig for testing."""
    return ConnectionConfig(
        timeout_seconds=30,
        retry_attempts=3,
        retry_delay_seconds=1,
        keepalive_interval_seconds=60,
    )


@pytest.fixture
def cache_config() -> CacheConfig:
    """Creates a standard CacheConfig for testing."""
    return CacheConfig(
        enabled=True,
        directory_ttl_seconds=30,
        metadata_ttl_seconds=60,
    )


@pytest.fixture
def ftp_client(
    ftp_config: FTPConfig, conn_config: ConnectionConfig, mock_ftp: MagicMock
) -> Generator[FTPClient, None, None]:
    """
    Creates an FTPClient with a mocked FTP connection.

    Returns:
        FTPClient instance with mocked underlying FTP.
    """
    with patch("ftp_winmount.ftp_client.ftplib.FTP", return_value=mock_ftp):
        client = FTPClient(ftp_config, conn_config)
        client._ftp = mock_ftp
        client._connected = True
        client._supports_mlsd = True
        client._supports_mlst = True
        client._supports_rest = True
        yield client


@pytest.fixture
def mock_ftp_client() -> Generator[MagicMock, None, None]:
    """
    Creates a fully mocked FTPClient for filesystem tests.

    Returns:
        Mocked FTPClient with common methods stubbed.
    """
    mock = MagicMock(spec=FTPClient)

    # Default file stats for root directory
    mock.get_file_info.return_value = FileStats(
        name="/",
        size=0,
        mtime=datetime.now(),
        is_dir=True,
    )

    # Default directory listing
    mock.list_dir.return_value = [
        FileStats(name="file1.txt", size=1024, mtime=datetime.now(), is_dir=False),
        FileStats(name="folder1", size=0, mtime=datetime.now(), is_dir=True),
    ]

    # Default read_file behavior
    mock.read_file.return_value = b"test file content"

    # Default write_file behavior
    mock.write_file.return_value = 17  # len("test file content")

    yield mock


@pytest.fixture
def sample_file_stats() -> FileStats:
    """Creates sample FileStats for testing."""
    return FileStats(
        name="testfile.txt",
        size=12345,
        mtime=datetime(2024, 1, 15, 10, 30, 0),
        is_dir=False,
    )


@pytest.fixture
def sample_dir_stats() -> FileStats:
    """Creates sample directory FileStats for testing."""
    return FileStats(
        name="testdir",
        size=0,
        mtime=datetime(2024, 1, 15, 10, 30, 0),
        is_dir=True,
    )


@pytest.fixture
def app_config(
    ftp_config: FTPConfig, conn_config: ConnectionConfig, cache_config: CacheConfig
) -> AppConfig:
    """Creates a complete AppConfig for testing."""
    return AppConfig(
        ftp=ftp_config,
        mount=MountConfig(drive_letter="Z", volume_label="Test FTP"),
        cache=cache_config,
        connection=conn_config,
        logging=LogConfig(level="DEBUG", file="test.log", console=False),
    )
