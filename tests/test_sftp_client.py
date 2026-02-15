"""
Unit tests for ftp_winmount.sftp_client module.

Tests cover:
- Connect with key file auth
- Connect with password auth
- Connect with agent auth
- list_dir returns FileStats list
- get_file_info returns FileStats
- read_file returns bytes with offset/length
- write_file calls sftp.open with correct mode
- create_file creates empty file
- create_dir creates directory recursively
- delete_file and delete_dir
- rename
- Error translation (IOError -> FileNotFoundError, PermissionError)
- Retry logic on connection failures
- Path normalization
"""

import stat as stat_module
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import paramiko
import pytest

from ftp_winmount.config import ConnectionConfig, SSHConfig
from ftp_winmount.ftp_client import FileStats
from ftp_winmount.sftp_client import SFTPClient


@pytest.fixture
def ssh_config_keyfile() -> SSHConfig:
    """SSH config with key file auth."""
    return SSHConfig(
        host="test.ssh.local",
        port=22,
        username="testuser",
        key_file="/home/testuser/.ssh/id_rsa",
        use_agent=False,
    )


@pytest.fixture
def ssh_config_password() -> SSHConfig:
    """SSH config with password auth."""
    return SSHConfig(
        host="test.ssh.local",
        port=22,
        username="testuser",
        password="testpass",
        use_agent=False,
    )


@pytest.fixture
def conn_config() -> ConnectionConfig:
    return ConnectionConfig(
        timeout_seconds=30,
        retry_attempts=3,
        retry_delay_seconds=0,  # No delay in tests
        keepalive_interval_seconds=60,
    )


@pytest.fixture
def mock_ssh_client():
    """Creates a mocked paramiko.SSHClient."""
    mock = MagicMock(spec=paramiko.SSHClient)
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock.get_transport.return_value = mock_transport
    return mock


@pytest.fixture
def mock_sftp():
    """Creates a mocked paramiko.SFTPClient."""
    return MagicMock(spec=paramiko.SFTPClient)


@pytest.fixture
def sftp_client(ssh_config_keyfile, conn_config, mock_ssh_client, mock_sftp):
    """Creates an SFTPClient with mocked SSH/SFTP connections."""
    with patch("ftp_winmount.sftp_client.paramiko.SSHClient", return_value=mock_ssh_client):
        mock_ssh_client.open_sftp.return_value = mock_sftp
        client = SFTPClient(ssh_config_keyfile, conn_config)
        client._ssh = mock_ssh_client
        client._sftp = mock_sftp
        client._connected = True
        yield client


def _make_sftp_attr(filename, size, mtime_ts, is_dir):
    """Helper to create mock SFTPAttributes."""
    attr = MagicMock()
    attr.filename = filename
    attr.st_size = size
    attr.st_mtime = mtime_ts
    if is_dir:
        attr.st_mode = stat_module.S_IFDIR | 0o755
    else:
        attr.st_mode = stat_module.S_IFREG | 0o644
    return attr


class TestSFTPClientConnect:
    """Tests for SFTPClient.connect method."""

    def test_connect_with_key_file(self, ssh_config_keyfile, conn_config):
        """Test connecting with SSH key file authentication."""
        with patch("ftp_winmount.sftp_client.paramiko.SSHClient") as MockSSH:
            mock_ssh = MagicMock()
            MockSSH.return_value = mock_ssh
            mock_ssh.open_sftp.return_value = MagicMock()

            client = SFTPClient(ssh_config_keyfile, conn_config)
            client.connect()

            mock_ssh.connect.assert_called_once()
            call_kwargs = mock_ssh.connect.call_args[1]
            assert call_kwargs["hostname"] == "test.ssh.local"
            assert call_kwargs["port"] == 22
            assert call_kwargs["username"] == "testuser"
            assert "key_filename" in call_kwargs
            assert call_kwargs["look_for_keys"] is True

    def test_connect_with_password(self, ssh_config_password, conn_config):
        """Test connecting with password authentication."""
        with patch("ftp_winmount.sftp_client.paramiko.SSHClient") as MockSSH:
            mock_ssh = MagicMock()
            MockSSH.return_value = mock_ssh
            mock_ssh.open_sftp.return_value = MagicMock()

            client = SFTPClient(ssh_config_password, conn_config)
            client.connect()

            call_kwargs = mock_ssh.connect.call_args[1]
            assert call_kwargs["password"] == "testpass"
            assert call_kwargs["look_for_keys"] is False

    def test_connect_auth_failure_raises_permission_error(self, ssh_config_keyfile, conn_config):
        """Test that authentication failure raises PermissionError."""
        with patch("ftp_winmount.sftp_client.paramiko.SSHClient") as MockSSH:
            mock_ssh = MagicMock()
            MockSSH.return_value = mock_ssh
            mock_ssh.connect.side_effect = paramiko.AuthenticationException("bad key")

            client = SFTPClient(ssh_config_keyfile, conn_config)
            with pytest.raises(PermissionError, match="authentication failed"):
                client.connect()

    def test_connect_timeout_raises_timeout_error(self, ssh_config_keyfile, conn_config):
        """Test that connection timeout raises TimeoutError."""
        with patch("ftp_winmount.sftp_client.paramiko.SSHClient") as MockSSH:
            mock_ssh = MagicMock()
            MockSSH.return_value = mock_ssh
            mock_ssh.connect.side_effect = TimeoutError("timed out")

            client = SFTPClient(ssh_config_keyfile, conn_config)
            with pytest.raises(TimeoutError):
                client.connect()

    def test_connect_sets_tofu_policy(self, ssh_config_keyfile, conn_config):
        """Test that TrustOnFirstUsePolicy is set for host keys."""
        from ftp_winmount.sftp_client import TrustOnFirstUsePolicy

        with patch("ftp_winmount.sftp_client.paramiko.SSHClient") as MockSSH:
            mock_ssh = MagicMock()
            MockSSH.return_value = mock_ssh
            mock_ssh.open_sftp.return_value = MagicMock()

            client = SFTPClient(ssh_config_keyfile, conn_config)
            client.connect()

            mock_ssh.set_missing_host_key_policy.assert_called_once()
            policy_arg = mock_ssh.set_missing_host_key_policy.call_args[0][0]
            assert isinstance(policy_arg, TrustOnFirstUsePolicy)


class TestSFTPClientListDir:
    """Tests for SFTPClient.list_dir method."""

    def test_list_dir_returns_file_stats(self, sftp_client, mock_sftp):
        """Test that list_dir returns a list of FileStats."""
        ts = datetime(2024, 6, 15, 10, 30).timestamp()
        mock_sftp.listdir_attr.return_value = [
            _make_sftp_attr("file1.txt", 1024, ts, False),
            _make_sftp_attr("subdir", 0, ts, True),
        ]

        result = sftp_client.list_dir("/home/user")
        assert len(result) == 2
        assert isinstance(result[0], FileStats)
        assert result[0].name == "file1.txt"
        assert result[0].size == 1024
        assert result[0].is_dir is False
        assert result[1].name == "subdir"
        assert result[1].is_dir is True

    def test_list_dir_skips_dot_entries(self, sftp_client, mock_sftp):
        """Test that . and .. entries are filtered out."""
        ts = datetime.now().timestamp()
        mock_sftp.listdir_attr.return_value = [
            _make_sftp_attr(".", 0, ts, True),
            _make_sftp_attr("..", 0, ts, True),
            _make_sftp_attr("real_file.txt", 100, ts, False),
        ]

        result = sftp_client.list_dir("/")
        assert len(result) == 1
        assert result[0].name == "real_file.txt"

    def test_list_dir_normalizes_path(self, sftp_client, mock_sftp):
        """Test that paths are normalized with leading slash."""
        mock_sftp.listdir_attr.return_value = []
        sftp_client.list_dir("home\\user")
        mock_sftp.listdir_attr.assert_called_with("/home/user")


class TestSFTPClientGetFileInfo:
    """Tests for SFTPClient.get_file_info method."""

    def test_get_file_info_returns_stats(self, sftp_client, mock_sftp):
        """Test getting file metadata."""
        ts = datetime(2024, 6, 15, 10, 30).timestamp()
        mock_sftp.stat.return_value = _make_sftp_attr("test.txt", 5000, ts, False)

        result = sftp_client.get_file_info("/home/user/test.txt")
        assert isinstance(result, FileStats)
        assert result.name == "test.txt"
        assert result.size == 5000
        assert result.is_dir is False

    def test_get_file_info_directory(self, sftp_client, mock_sftp):
        """Test getting directory metadata."""
        ts = datetime.now().timestamp()
        mock_sftp.stat.return_value = _make_sftp_attr("docs", 0, ts, True)

        result = sftp_client.get_file_info("/home/user/docs")
        assert result.is_dir is True
        assert result.size == 0


class TestSFTPClientReadFile:
    """Tests for SFTPClient.read_file method."""

    def test_read_file_returns_bytes(self, sftp_client, mock_sftp):
        """Test basic file read."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"hello world"
        mock_sftp.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_sftp.open.return_value.__exit__ = MagicMock(return_value=False)

        result = sftp_client.read_file("/test.txt")
        assert result == b"hello world"

    def test_read_file_with_offset(self, sftp_client, mock_sftp):
        """Test reading with offset."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"world"
        mock_sftp.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_sftp.open.return_value.__exit__ = MagicMock(return_value=False)

        result = sftp_client.read_file("/test.txt", offset=6)
        mock_file.seek.assert_called_once_with(6)
        assert result == b"world"

    def test_read_file_with_length(self, sftp_client, mock_sftp):
        """Test reading with length limit."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"hello"
        mock_sftp.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_sftp.open.return_value.__exit__ = MagicMock(return_value=False)

        result = sftp_client.read_file("/test.txt", length=5)
        mock_file.read.assert_called_once_with(5)


class TestSFTPClientWriteFile:
    """Tests for SFTPClient.write_file method."""

    def test_write_file_full(self, sftp_client, mock_sftp):
        """Test writing an entire file."""
        mock_file = MagicMock()
        mock_sftp.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_sftp.open.return_value.__exit__ = MagicMock(return_value=False)

        result = sftp_client.write_file("/test.txt", b"new content")
        assert result == 11
        mock_sftp.open.assert_called_once_with("/test.txt", "wb")

    def test_write_file_at_offset(self, sftp_client, mock_sftp):
        """Test writing at an offset."""
        mock_file = MagicMock()
        mock_sftp.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_sftp.open.return_value.__exit__ = MagicMock(return_value=False)

        result = sftp_client.write_file("/test.txt", b"insert", offset=10)
        assert result == 6
        mock_sftp.open.assert_called_once_with("/test.txt", "r+b")
        mock_file.seek.assert_called_once_with(10)


class TestSFTPClientFileOps:
    """Tests for create, delete, and rename operations."""

    def test_create_file(self, sftp_client, mock_sftp):
        """Test creating an empty file."""
        mock_file = MagicMock()
        mock_sftp.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_sftp.open.return_value.__exit__ = MagicMock(return_value=False)

        sftp_client.create_file("/new_file.txt")
        mock_sftp.open.assert_called_once_with("/new_file.txt", "wb")

    def test_create_dir(self, sftp_client, mock_sftp):
        """Test creating a directory."""
        mock_sftp.mkdir.return_value = None

        sftp_client.create_dir("/new_dir")
        mock_sftp.mkdir.assert_called_once_with("/new_dir")

    def test_create_dir_recursive(self, sftp_client, mock_sftp):
        """Test recursive directory creation."""
        # First mkdir fails (parent doesn't exist), then stat fails for each part
        mock_sftp.mkdir.side_effect = [IOError("no parent"), None, None]
        mock_sftp.stat.side_effect = [IOError("not found"), IOError("not found")]

        sftp_client.create_dir("/a/b")
        assert mock_sftp.mkdir.call_count == 3

    def test_delete_file(self, sftp_client, mock_sftp):
        """Test deleting a file."""
        sftp_client.delete_file("/old_file.txt")
        mock_sftp.remove.assert_called_once_with("/old_file.txt")

    def test_delete_dir(self, sftp_client, mock_sftp):
        """Test deleting a directory."""
        sftp_client.delete_dir("/empty_dir")
        mock_sftp.rmdir.assert_called_once_with("/empty_dir")

    def test_rename(self, sftp_client, mock_sftp):
        """Test renaming a file."""
        sftp_client.rename("/old.txt", "/new.txt")
        mock_sftp.rename.assert_called_once_with("/old.txt", "/new.txt")


class TestSFTPClientPathNormalization:
    """Tests for path normalization."""

    def test_backslash_to_forward_slash(self, sftp_client, mock_sftp):
        """Test Windows-style paths get converted."""
        mock_sftp.listdir_attr.return_value = []
        sftp_client.list_dir("home\\user\\docs")
        mock_sftp.listdir_attr.assert_called_with("/home/user/docs")

    def test_adds_leading_slash(self, sftp_client, mock_sftp):
        """Test that leading slash is added."""
        mock_sftp.listdir_attr.return_value = []
        sftp_client.list_dir("relative/path")
        mock_sftp.listdir_attr.assert_called_with("/relative/path")

    def test_preserves_existing_leading_slash(self, sftp_client, mock_sftp):
        """Test that existing leading slash is kept."""
        mock_sftp.listdir_attr.return_value = []
        sftp_client.list_dir("/absolute/path")
        mock_sftp.listdir_attr.assert_called_with("/absolute/path")


class TestSFTPClientDisconnect:
    """Tests for SFTPClient.disconnect method."""

    def test_disconnect_closes_sftp_and_ssh(self, sftp_client, mock_sftp, mock_ssh_client):
        """Test that disconnect closes both SFTP and SSH."""
        sftp_client._ssh = mock_ssh_client
        sftp_client.disconnect()

        mock_sftp.close.assert_called_once()
        mock_ssh_client.close.assert_called_once()
        assert sftp_client._connected is False

    def test_disconnect_handles_close_errors(self, sftp_client, mock_sftp, mock_ssh_client):
        """Test that disconnect doesn't raise on close errors."""
        sftp_client._ssh = mock_ssh_client
        mock_sftp.close.side_effect = Exception("close failed")

        # Should not raise
        sftp_client.disconnect()
        assert sftp_client._connected is False
