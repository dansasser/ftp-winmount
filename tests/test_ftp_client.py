"""
Unit tests for ftp_winmount.ftp_client module.

Tests cover:
- Connect with anonymous auth
- Connect with credentials
- List_dir parsing (MLSD format)
- List_dir parsing (LIST format fallback)
- Read_file returns bytes
- Write_file calls STOR
- Error translation (550 -> FileNotFoundError)
- Retry logic on transient errors
"""

import ftplib
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ftp_winmount.config import ConnectionConfig, FTPConfig
from ftp_winmount.ftp_client import FileStats, FTPClient


class TestFTPClientConnect:
    """Tests for FTPClient.connect method."""

    def test_connect_with_anonymous_auth(self):
        """Test connecting with anonymous authentication (no username)."""
        ftp_config = FTPConfig(
            host="test.server.com",
            port=21,
            username=None,
            password=None,
        )
        conn_config = ConnectionConfig()

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "211-Features:\r\n MLSD\r\n211 End"

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            # Verify connection was made
            mock_ftp.connect.assert_called_once_with(
                host="test.server.com",
                port=21,
                timeout=30,
            )

            # Verify anonymous login (no args to login)
            mock_ftp.login.assert_called_once_with()

    def test_connect_with_credentials(self):
        """Test connecting with username and password."""
        ftp_config = FTPConfig(
            host="test.server.com",
            port=2121,
            username="myuser",
            password="mypass",
        )
        conn_config = ConnectionConfig()

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "211-Features:\r\n MLSD\r\n211 End"

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            mock_ftp.login.assert_called_once_with(
                user="myuser",
                passwd="mypass",
            )

    def test_connect_sets_passive_mode(self):
        """Test that passive mode is set according to config."""
        ftp_config = FTPConfig(host="test.server.com", passive_mode=True)
        conn_config = ConnectionConfig()

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "200 OK"

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            mock_ftp.set_pasv.assert_called_once_with(True)

    def test_connect_sets_encoding(self):
        """Test that encoding is set on FTP object."""
        ftp_config = FTPConfig(host="test.server.com", encoding="utf-8")
        conn_config = ConnectionConfig()

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "200 OK"

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            assert mock_ftp.encoding == "utf-8"

    def test_connect_login_failure_raises_permission_error(self):
        """Test that login failure raises PermissionError."""
        ftp_config = FTPConfig(host="test.server.com", username="bad", password="creds")
        conn_config = ConnectionConfig()

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.login.side_effect = ftplib.error_perm("530 Login incorrect")

            client = FTPClient(ftp_config, conn_config)

            with pytest.raises(PermissionError) as exc_info:
                client.connect()

            assert "530" in str(exc_info.value) or "Login" in str(exc_info.value)

    def test_connect_timeout_raises_timeout_error(self):
        """Test that connection timeout raises TimeoutError."""
        ftp_config = FTPConfig(host="test.server.com")
        conn_config = ConnectionConfig(timeout_seconds=5)

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.connect.side_effect = TimeoutError("Connection timed out")

            client = FTPClient(ftp_config, conn_config)

            with pytest.raises(TimeoutError):
                client.connect()

    def test_connect_network_error_raises_connection_error(self):
        """Test that network error raises ConnectionError."""
        ftp_config = FTPConfig(host="test.server.com")
        conn_config = ConnectionConfig()

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.connect.side_effect = OSError("Network unreachable")

            client = FTPClient(ftp_config, conn_config)

            with pytest.raises(ConnectionError):
                client.connect()


class TestFTPClientDisconnect:
    """Tests for FTPClient.disconnect method."""

    def test_disconnect_calls_quit(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that disconnect calls FTP quit."""
        ftp_client.disconnect()
        mock_ftp.quit.assert_called_once()

    def test_disconnect_handles_quit_error(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that disconnect handles quit error gracefully."""
        mock_ftp.quit.side_effect = Exception("Connection lost")

        # Should not raise
        ftp_client.disconnect()

        # Should try to close as fallback
        mock_ftp.close.assert_called_once()


class TestFTPClientListDirMLSD:
    """Tests for list_dir with MLSD format."""

    def test_list_dir_mlsd_parses_files(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test MLSD parsing for files."""
        mock_ftp.mlsd.return_value = [
            ("file1.txt", {"type": "file", "size": "1024", "modify": "20240115103000"}),
            ("file2.txt", {"type": "file", "size": "2048", "modify": "20240116120000"}),
        ]

        result = ftp_client.list_dir("/test")

        assert len(result) == 2
        assert result[0].name == "file1.txt"
        assert result[0].size == 1024
        assert result[0].is_dir is False
        assert result[0].mtime == datetime(2024, 1, 15, 10, 30, 0)

    def test_list_dir_mlsd_parses_directories(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test MLSD parsing for directories."""
        mock_ftp.mlsd.return_value = [
            ("folder", {"type": "dir", "size": "0", "modify": "20240115103000"}),
        ]

        result = ftp_client.list_dir("/test")

        assert len(result) == 1
        assert result[0].name == "folder"
        assert result[0].is_dir is True
        assert result[0].size == 0

    def test_list_dir_mlsd_skips_dot_entries(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that . and .. entries are skipped."""
        mock_ftp.mlsd.return_value = [
            (".", {"type": "cdir"}),
            ("..", {"type": "pdir"}),
            ("file.txt", {"type": "file", "size": "100"}),
        ]

        result = ftp_client.list_dir("/test")

        assert len(result) == 1
        assert result[0].name == "file.txt"

    def test_list_dir_mlsd_handles_fractional_seconds(
        self, ftp_client: FTPClient, mock_ftp: MagicMock
    ):
        """Test MLSD time parsing with fractional seconds."""
        mock_ftp.mlsd.return_value = [
            ("file.txt", {"type": "file", "size": "100", "modify": "20240115103000.123"}),
        ]

        result = ftp_client.list_dir("/test")

        assert result[0].mtime == datetime(2024, 1, 15, 10, 30, 0)


class TestFTPClientListDirLIST:
    """Tests for list_dir with LIST format fallback."""

    def test_list_dir_list_parses_unix_format(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test LIST parsing for Unix format."""
        ftp_client._supports_mlsd = False

        def capture_list(cmd, callback):
            for line in [
                "-rw-r--r--  1 owner group     1024 Jan 15 10:30 file.txt",
                "drwxr-xr-x  2 owner group     4096 Jan 16 12:00 folder",
            ]:
                callback(line)

        mock_ftp.retrlines.side_effect = capture_list

        result = ftp_client.list_dir("/test")

        assert len(result) == 2

        # Check file
        file_entry = next((r for r in result if r.name == "file.txt"), None)
        assert file_entry is not None
        assert file_entry.is_dir is False
        assert file_entry.size == 1024

        # Check directory
        dir_entry = next((r for r in result if r.name == "folder"), None)
        assert dir_entry is not None
        assert dir_entry.is_dir is True

    def test_list_dir_list_parses_windows_format(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test LIST parsing for Windows format."""
        ftp_client._supports_mlsd = False

        def capture_list(cmd, callback):
            for line in [
                "01-15-24  10:30AM              1024 file.txt",
                "01-16-24  12:00PM       <DIR>       folder",
            ]:
                callback(line)

        mock_ftp.retrlines.side_effect = capture_list

        result = ftp_client.list_dir("/test")

        assert len(result) == 2

    def test_list_dir_list_handles_filenames_with_spaces(
        self, ftp_client: FTPClient, mock_ftp: MagicMock
    ):
        """Test LIST parsing for filenames with spaces."""
        ftp_client._supports_mlsd = False

        def capture_list(cmd, callback):
            callback("-rw-r--r--  1 owner group     1024 Jan 15 10:30 file with spaces.txt")

        mock_ftp.retrlines.side_effect = capture_list

        result = ftp_client.list_dir("/test")

        assert len(result) == 1
        assert result[0].name == "file with spaces.txt"


class TestFTPClientReadFile:
    """Tests for read_file method."""

    def test_read_file_returns_bytes(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that read_file returns bytes."""
        test_content = b"Hello, World!"

        def mock_retrbinary(cmd, callback):
            callback(test_content)

        mock_ftp.retrbinary.side_effect = mock_retrbinary

        result = ftp_client.read_file("/test/file.txt")

        assert isinstance(result, bytes)
        assert result == test_content

    def test_read_file_with_offset(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test read_file with offset using REST command."""
        full_content = b"Hello, World!"

        def mock_retrbinary(cmd, callback):
            # In real REST scenario, server would skip first 7 bytes
            # Here we simulate full download
            callback(full_content)

        mock_ftp.retrbinary.side_effect = mock_retrbinary

        ftp_client.read_file("/test/file.txt", offset=7)

        # With REST support, sendcmd should be called
        mock_ftp.sendcmd.assert_any_call("REST 7")

    def test_read_file_with_length(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test read_file with length limit."""
        full_content = b"Hello, World!"

        def mock_retrbinary(cmd, callback):
            callback(full_content)

        mock_ftp.retrbinary.side_effect = mock_retrbinary

        result = ftp_client.read_file("/test/file.txt", offset=0, length=5)

        assert result == b"Hello"

    def test_read_file_normalizes_path(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that read_file normalizes the path."""

        def mock_retrbinary(cmd, callback):
            # Verify command uses normalized path
            assert "RETR /test/file.txt" in cmd
            callback(b"content")

        mock_ftp.retrbinary.side_effect = mock_retrbinary

        # Pass path without leading slash
        ftp_client.read_file("test/file.txt")

        mock_ftp.retrbinary.assert_called_once()


class TestFTPClientWriteFile:
    """Tests for write_file method."""

    def test_write_file_calls_stor(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that write_file uses STOR command."""
        test_data = b"test content"

        ftp_client.write_file("/test/file.txt", test_data)

        # Verify STOR was called
        assert mock_ftp.storbinary.called
        call_args = mock_ftp.storbinary.call_args
        assert "STOR /test/file.txt" in call_args[0][0]

    def test_write_file_returns_bytes_written(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that write_file returns number of bytes written."""
        test_data = b"test content"

        result = ftp_client.write_file("/test/file.txt", test_data)

        assert result == len(test_data)

    def test_write_file_with_offset_does_read_modify_write(
        self, ftp_client: FTPClient, mock_ftp: MagicMock
    ):
        """Test that write_file with offset reads existing content first."""
        existing_content = b"existing data here"

        def mock_retrbinary(cmd, callback):
            callback(existing_content)

        mock_ftp.retrbinary.side_effect = mock_retrbinary

        # Write at offset 9 (overwrite "data here" with "new stuff")
        ftp_client.write_file("/test/file.txt", b"new stuff", offset=9)

        # Should have read existing content
        mock_ftp.retrbinary.assert_called()

        # Should have written modified content
        mock_ftp.storbinary.assert_called()


class TestFTPClientCreateFile:
    """Tests for create_file method."""

    def test_create_file_creates_empty_file(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that create_file creates an empty file."""
        ftp_client.create_file("/test/newfile.txt")

        # Should use STOR with empty buffer
        mock_ftp.storbinary.assert_called_once()
        call_args = mock_ftp.storbinary.call_args
        assert "STOR /test/newfile.txt" in call_args[0][0]


class TestFTPClientCreateDir:
    """Tests for create_dir method."""

    def test_create_dir_calls_mkd(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that create_dir calls MKD command."""
        ftp_client.create_dir("/test/newdir")

        mock_ftp.mkd.assert_called_with("/test/newdir")

    def test_create_dir_handles_existing_directory(
        self, ftp_client: FTPClient, mock_ftp: MagicMock
    ):
        """Test that create_dir handles 'already exists' error."""
        mock_ftp.mkd.side_effect = ftplib.error_perm("550 Directory already exists")

        # Should not raise
        ftp_client.create_dir("/test/existing")


class TestFTPClientDeleteFile:
    """Tests for delete_file method."""

    def test_delete_file_calls_delete(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that delete_file calls DELETE command."""
        ftp_client.delete_file("/test/file.txt")

        mock_ftp.delete.assert_called_once_with("/test/file.txt")


class TestFTPClientDeleteDir:
    """Tests for delete_dir method."""

    def test_delete_dir_calls_rmd(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that delete_dir calls RMD command."""
        ftp_client.delete_dir("/test/dir")

        mock_ftp.rmd.assert_called_once_with("/test/dir")


class TestFTPClientRename:
    """Tests for rename method."""

    def test_rename_calls_ftp_rename(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that rename calls FTP rename command."""
        ftp_client.rename("/old/path.txt", "/new/path.txt")

        mock_ftp.rename.assert_called_once_with("/old/path.txt", "/new/path.txt")


class TestFTPClientErrorTranslation:
    """Tests for error translation."""

    def test_550_file_not_found_translated(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that 550 'not found' error is translated to FileNotFoundError."""
        mock_ftp.mlsd.side_effect = ftplib.error_perm("550 No such file or directory")

        with pytest.raises(FileNotFoundError):
            ftp_client.list_dir("/nonexistent")

    def test_550_permission_denied_translated(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that 550 'permission denied' error is translated to PermissionError."""
        mock_ftp.mlsd.side_effect = ftplib.error_perm("550 Permission denied")

        with pytest.raises(PermissionError):
            ftp_client.list_dir("/restricted")

    def test_553_permission_denied_translated(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that 553 error is translated to PermissionError."""
        mock_ftp.storbinary.side_effect = ftplib.error_perm("553 Could not create file")

        with pytest.raises(PermissionError):
            ftp_client.write_file("/readonly/file.txt", b"data")

    def test_530_auth_required_translated(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test that 530 error is translated to PermissionError."""
        mock_ftp.mlsd.side_effect = ftplib.error_perm("530 Not logged in")

        with pytest.raises(PermissionError) as exc_info:
            ftp_client.list_dir("/test")

        assert "Authentication required" in str(exc_info.value)


class TestFTPClientRetryLogic:
    """Tests for retry logic on transient errors."""

    def test_retry_on_connection_error(self):
        """Test that transient errors trigger retry."""
        ftp_config = FTPConfig(host="test.server.com")
        conn_config = ConnectionConfig(retry_attempts=3, retry_delay_seconds=0)

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "211-Features:\r\n MLSD\r\n211 End"

            call_count = [0]

            def mlsd_side_effect(path):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise OSError("Connection reset")
                return [("file.txt", {"type": "file", "size": "100"})]

            mock_ftp.mlsd.side_effect = mlsd_side_effect

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            result = client.list_dir("/test")

            assert len(result) == 1
            assert call_count[0] == 3

    def test_retry_on_timeout(self):
        """Test that timeout errors trigger retry."""
        ftp_config = FTPConfig(host="test.server.com")
        conn_config = ConnectionConfig(retry_attempts=2, retry_delay_seconds=0)

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "211-Features:\r\n MLSD\r\n211 End"

            call_count = [0]

            def mlsd_side_effect(path):
                call_count[0] += 1
                if call_count[0] < 2:
                    raise TimeoutError("Read timed out")
                return [("file.txt", {"type": "file", "size": "100"})]

            mock_ftp.mlsd.side_effect = mlsd_side_effect

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            result = client.list_dir("/test")

            assert len(result) == 1
            assert call_count[0] == 2

    def test_no_retry_on_permanent_error(self):
        """Test that permanent errors (550) do not trigger retry."""
        ftp_config = FTPConfig(host="test.server.com")
        conn_config = ConnectionConfig(retry_attempts=3, retry_delay_seconds=0)

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "211-Features:\r\n MLSD\r\n211 End"
            mock_ftp.mlsd.side_effect = ftplib.error_perm("550 File not found")

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            with pytest.raises(FileNotFoundError):
                client.list_dir("/nonexistent")

            # Should only be called once (no retry)
            assert mock_ftp.mlsd.call_count == 1

    def test_raises_after_all_retries_exhausted(self):
        """Test that error is raised after all retries are exhausted."""
        ftp_config = FTPConfig(host="test.server.com")
        conn_config = ConnectionConfig(retry_attempts=3, retry_delay_seconds=0)

        with patch("ftp_winmount.ftp_client.ftplib.FTP") as MockFTP:
            mock_ftp = MagicMock()
            MockFTP.return_value = mock_ftp
            mock_ftp.sendcmd.return_value = "211-Features:\r\n MLSD\r\n211 End"

            # All calls fail
            mock_ftp.mlsd.side_effect = OSError("Connection reset")

            client = FTPClient(ftp_config, conn_config)
            client.connect()

            with pytest.raises(IOError):
                client.list_dir("/test")

            assert mock_ftp.mlsd.call_count == 3


class TestFTPClientPathNormalization:
    """Tests for path normalization."""

    def test_path_without_leading_slash_normalized(self, ftp_client: FTPClient):
        """Test that paths without leading slash are normalized."""
        result = ftp_client._normalize_path("test/path")
        assert result == "/test/path"

    def test_path_with_leading_slash_unchanged(self, ftp_client: FTPClient):
        """Test that paths with leading slash remain unchanged."""
        result = ftp_client._normalize_path("/test/path")
        assert result == "/test/path"

    def test_path_with_backslashes_converted(self, ftp_client: FTPClient):
        """Test that backslashes are converted to forward slashes."""
        result = ftp_client._normalize_path("\\test\\path")
        assert result == "/test/path"

    def test_mixed_slashes_normalized(self, ftp_client: FTPClient):
        """Test that mixed slashes are all converted."""
        result = ftp_client._normalize_path("test\\sub/path")
        assert result == "/test/sub/path"


class TestFTPClientGetFileInfo:
    """Tests for get_file_info method."""

    def test_get_file_info_uses_mlst_when_supported(
        self, ftp_client: FTPClient, mock_ftp: MagicMock
    ):
        """Test that MLST is used when supported."""
        mock_ftp.sendcmd.return_value = "250-Listing /test/file.txt\r\n type=file;size=1024;modify=20240115103000; file.txt\r\n250 End"

        result = ftp_client.get_file_info("/test/file.txt")

        assert result.size == 1024
        assert result.is_dir is False

    def test_get_file_info_root_directory(self, ftp_client: FTPClient, mock_ftp: MagicMock):
        """Test get_file_info for root directory."""
        ftp_client._supports_mlst = False

        result = ftp_client.get_file_info("/")

        assert result.name == "/"
        assert result.is_dir is True
        assert result.size == 0


class TestFileStats:
    """Tests for FileStats dataclass."""

    def test_filestats_creation(self):
        """Test FileStats creation."""
        stats = FileStats(
            name="test.txt",
            size=1024,
            mtime=datetime(2024, 1, 15),
            is_dir=False,
        )

        assert stats.name == "test.txt"
        assert stats.size == 1024
        assert stats.is_dir is False

    def test_filestats_default_attributes(self):
        """Test FileStats default attributes value."""
        stats = FileStats(
            name="test.txt",
            size=1024,
            mtime=datetime.now(),
            is_dir=False,
        )

        assert stats.attributes == 0
