"""
Unit tests for pyftpdrive.filesystem module.

Tests cover:
- Path conversion (_to_ftp_path)
- get_security_by_name returns attributes
- open creates FileContext
- read returns bytes from FTPClient
- read_directory uses cache
- create calls FTPClient.create_file/create_dir
- write buffers data
- flush uploads buffer
- cleanup deletes on DeleteOnClose flag
"""

from datetime import datetime
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from pyftpdrive.config import CacheConfig
from pyftpdrive.filesystem import (
    FILE_ATTRIBUTE_DIRECTORY,
    FILE_ATTRIBUTE_NORMAL,
    FILE_DIRECTORY_FILE,
    FSP_CLEANUP_DELETE,
    FTPFileSystem,
    NTStatusAccessDenied,
    NTStatusDirectoryNotEmpty,
    NTStatusObjectNameCollision,
    NTStatusObjectNameNotFound,
    OpenedContext,
)
from pyftpdrive.ftp_client import FileStats


def FileContext(
    path: str,
    is_directory: bool = False,
    file_size: int = 0,
    attributes: int | None = None,
    mtime_filetime: int = 0,
    **kwargs,  # Accept and ignore extra kwargs for backwards compat
) -> OpenedContext:
    """Helper to create OpenedContext for tests with sensible defaults."""
    if attributes is None:
        attributes = FILE_ATTRIBUTE_DIRECTORY if is_directory else FILE_ATTRIBUTE_NORMAL
    ctx = OpenedContext(
        path=path,
        is_directory=is_directory,
        file_size=file_size,
        attributes=attributes,
        mtime_filetime=mtime_filetime,
    )
    # Allow setting buffer/dirty after creation via kwargs
    if "buffer" in kwargs:
        ctx.buffer = kwargs["buffer"]
    if "dirty" in kwargs:
        ctx.dirty = kwargs["dirty"]
    return ctx


@pytest.fixture
def filesystem(mock_ftp_client: MagicMock, cache_config: CacheConfig) -> FTPFileSystem:
    """Create FTPFileSystem with mocked FTPClient."""
    return FTPFileSystem(mock_ftp_client, cache_config)


class TestPathConversion:
    """Tests for _to_ftp_path method."""

    def test_windows_path_converted_to_ftp(self, filesystem: FTPFileSystem):
        """Test Windows path with backslashes is converted."""
        result = filesystem._to_ftp_path("\\folder\\file.txt")
        assert result == "/folder/file.txt"

    def test_root_path_converted(self, filesystem: FTPFileSystem):
        """Test root path conversion."""
        result = filesystem._to_ftp_path("\\")
        assert result == "/"

    def test_empty_path_returns_root(self, filesystem: FTPFileSystem):
        """Test empty path returns root."""
        result = filesystem._to_ftp_path("")
        assert result == "/"

    def test_path_with_leading_backslash_stripped(self, filesystem: FTPFileSystem):
        """Test leading backslash is handled."""
        result = filesystem._to_ftp_path("\\test")
        assert result == "/test"

    def test_nested_path_converted(self, filesystem: FTPFileSystem):
        """Test nested path with multiple levels."""
        result = filesystem._to_ftp_path("\\a\\b\\c\\d.txt")
        assert result == "/a/b/c/d.txt"

    def test_path_without_backslash_normalized(self, filesystem: FTPFileSystem):
        """Test path without leading backslash gets leading slash."""
        result = filesystem._to_ftp_path("folder/file.txt")
        assert result == "/folder/file.txt"


class TestGetSecurityByName:
    """Tests for get_security_by_name method."""

    def test_returns_attributes_for_file(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that file attributes are returned for files."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="file.txt",
            size=1024,
            mtime=datetime.now(),
            is_dir=False,
        )

        attrs, security, size = filesystem.get_security_by_name("\\file.txt")

        assert attrs == FILE_ATTRIBUTE_NORMAL
        # size is the security descriptor size, not file size
        assert size > 0

    def test_returns_attributes_for_directory(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that directory attributes are returned for directories."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="folder",
            size=0,
            mtime=datetime.now(),
            is_dir=True,
        )

        attrs, security, size = filesystem.get_security_by_name("\\folder")

        assert attrs == FILE_ATTRIBUTE_DIRECTORY
        # size is the security descriptor size, not file size
        assert size > 0

    def test_raises_not_found_for_missing_file(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that NTStatusObjectNameNotFound is raised for missing files."""
        mock_ftp_client.get_file_info.side_effect = FileNotFoundError("Not found")

        with pytest.raises(NTStatusObjectNameNotFound):
            filesystem.get_security_by_name("\\nonexistent")

    def test_raises_access_denied_for_permission_error(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that NTStatusAccessDenied is raised for permission errors."""
        mock_ftp_client.get_file_info.side_effect = PermissionError("Access denied")

        with pytest.raises(NTStatusAccessDenied):
            filesystem.get_security_by_name("\\restricted")

    def test_uses_metadata_cache(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that metadata cache is used for subsequent calls."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="file.txt",
            size=1024,
            mtime=datetime.now(),
            is_dir=False,
        )

        # First call - should hit FTP
        filesystem.get_security_by_name("\\file.txt")

        # Second call - should use cache
        filesystem.get_security_by_name("\\file.txt")

        # FTP should only be called once
        assert mock_ftp_client.get_file_info.call_count == 1

    def test_security_descriptor_is_provided(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that security descriptor handle is returned."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="file.txt",
            size=1024,
            mtime=datetime.now(),
            is_dir=False,
        )

        attrs, security, size = filesystem.get_security_by_name("\\file.txt")

        # Security descriptor handle is returned (not None)
        assert security is not None


class TestOpen:
    """Tests for open method."""

    def test_open_creates_file_context(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that open creates a FileContext."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="file.txt",
            size=1024,
            mtime=datetime(2024, 1, 15),
            is_dir=False,
        )

        context = filesystem.open("\\file.txt", 0, 0)

        assert isinstance(context, OpenedContext)
        assert context.path == "/file.txt"
        assert context.is_directory is False
        assert context.file_size == 1024

    def test_open_creates_directory_context(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that open creates a directory FileContext."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="folder",
            size=0,
            mtime=datetime(2024, 1, 15),
            is_dir=True,
        )

        context = filesystem.open("\\folder", 0, 0)

        assert context.is_directory is True
        assert context.file_size == 0

    def test_open_raises_not_found_for_missing(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that open raises NTStatusObjectNameNotFound for missing files."""
        mock_ftp_client.get_file_info.side_effect = FileNotFoundError()

        with pytest.raises(NTStatusObjectNameNotFound):
            filesystem.open("\\nonexistent", 0, 0)

    def test_open_uses_metadata_cache(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that open uses metadata cache."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="file.txt",
            size=1024,
            mtime=datetime.now(),
            is_dir=False,
        )

        # First open - populates cache
        filesystem.open("\\file.txt", 0, 0)

        # Second open - should use cache
        filesystem.open("\\file.txt", 0, 0)

        # FTP should only be called once
        assert mock_ftp_client.get_file_info.call_count == 1


class TestRead:
    """Tests for read method."""

    def test_read_returns_bytes_from_ftp_client(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that read returns bytes from FTPClient."""
        mock_ftp_client.read_file.return_value = b"file content"

        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=12,
        )

        result = filesystem.read(context, 0, 12)

        assert result == b"file content"
        mock_ftp_client.read_file.assert_called_once_with("/file.txt", 0, 12)

    def test_read_with_offset(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test read with offset."""
        mock_ftp_client.read_file.return_value = b"content"

        context = FileContext(path="/file.txt", is_directory=False, file_size=20)

        filesystem.read(context, 5, 7)

        mock_ftp_client.read_file.assert_called_once_with("/file.txt", 5, 7)

    def test_read_beyond_eof_returns_empty(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that reading beyond EOF returns empty bytes."""
        context = FileContext(path="/file.txt", is_directory=False, file_size=10)

        result = filesystem.read(context, 100, 10)

        assert result == b""
        mock_ftp_client.read_file.assert_not_called()

    def test_read_adjusts_length_at_eof(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that read length is adjusted at EOF."""
        mock_ftp_client.read_file.return_value = b"end"

        context = FileContext(path="/file.txt", is_directory=False, file_size=10)

        filesystem.read(context, 7, 100)  # Request 100 bytes but only 3 remain

        # Should adjust to actual remaining bytes
        mock_ftp_client.read_file.assert_called_once_with("/file.txt", 7, 3)


class TestReadDirectory:
    """Tests for read_directory method."""

    def test_read_directory_returns_entries(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that read_directory returns directory entries."""
        context = FileContext(path="/folder", is_directory=True, file_size=0)

        result = filesystem.read_directory(context, None)

        assert len(result) == 2
        assert result[0]["file_name"] == "file1.txt"
        assert result[1]["file_name"] == "folder1"

    def test_read_directory_uses_cache(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that read_directory uses directory cache."""
        context = FileContext(path="/folder", is_directory=True, file_size=0)

        # First call - hits FTP
        filesystem.read_directory(context, None)

        # Second call - should use cache
        filesystem.read_directory(context, None)

        # list_dir should only be called once
        assert mock_ftp_client.list_dir.call_count == 1

    def test_read_directory_with_marker_pagination(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test read_directory with marker for pagination."""
        mock_ftp_client.list_dir.return_value = [
            FileStats(name="a.txt", size=100, mtime=datetime.now(), is_dir=False),
            FileStats(name="b.txt", size=200, mtime=datetime.now(), is_dir=False),
            FileStats(name="c.txt", size=300, mtime=datetime.now(), is_dir=False),
        ]

        context = FileContext(path="/folder", is_directory=True, file_size=0)

        # Start after "a.txt"
        result = filesystem.read_directory(context, "a.txt")

        # Should only return entries after marker
        assert len(result) == 2
        assert result[0]["file_name"] == "b.txt"
        assert result[1]["file_name"] == "c.txt"

    def test_read_directory_entry_format(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that directory entries have correct format."""
        context = FileContext(path="/folder", is_directory=True, file_size=0)

        result = filesystem.read_directory(context, None)

        entry = result[0]

        assert "file_name" in entry
        assert "file_size" in entry
        assert "allocation_size" in entry
        assert "creation_time" in entry
        assert "last_access_time" in entry
        assert "last_write_time" in entry
        assert "file_attributes" in entry


class TestCreate:
    """Tests for create method."""

    def test_create_file_calls_ftp_create_file(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that create for file calls FTPClient.create_file."""
        context = filesystem.create("\\newfile.txt", 0, 0, FILE_ATTRIBUTE_NORMAL, None, 0)

        mock_ftp_client.create_file.assert_called_once_with("/newfile.txt")
        assert context.is_directory is False

    def test_create_directory_calls_ftp_create_dir(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that create for directory calls FTPClient.create_dir."""
        context = filesystem.create(
            "\\newdir", FILE_DIRECTORY_FILE, 0, FILE_ATTRIBUTE_DIRECTORY, None, 0
        )

        mock_ftp_client.create_dir.assert_called_once_with("/newdir")
        assert context.is_directory is True

    def test_create_file_returns_context_with_buffer(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that create returns FileContext with buffer for files."""
        context = filesystem.create("\\newfile.txt", 0, 0, FILE_ATTRIBUTE_NORMAL, None, 0)

        assert context.buffer is not None
        assert isinstance(context.buffer, BytesIO)

    def test_create_directory_returns_context_without_buffer(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that create returns FileContext without buffer for directories."""
        context = filesystem.create(
            "\\newdir", FILE_DIRECTORY_FILE, 0, FILE_ATTRIBUTE_DIRECTORY, None, 0
        )

        assert context.buffer is None

    def test_create_invalidates_parent_cache(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that create invalidates parent directory cache."""
        # Pre-populate cache
        filesystem.dir_cache.put("/parent", [{"name": "existing"}])

        filesystem.create("\\parent\\newfile.txt", 0, 0, FILE_ATTRIBUTE_NORMAL, None, 0)

        # Parent cache should be invalidated
        assert filesystem.dir_cache.get("/parent") is None

    def test_create_existing_raises_collision(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that creating existing file raises NTStatusObjectNameCollision."""
        mock_ftp_client.create_file.side_effect = FileExistsError("Already exists")

        with pytest.raises(NTStatusObjectNameCollision):
            filesystem.create("\\existing.txt", 0, 0, FILE_ATTRIBUTE_NORMAL, None, 0)


class TestWrite:
    """Tests for write method."""

    def test_write_buffers_data(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that write buffers data instead of immediately uploading."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=0,
            buffer=None,
        )

        filesystem.write(context, b"test data", 0)

        # Data should be buffered
        assert context.buffer is not None
        context.buffer.seek(0)
        assert context.buffer.read() == b"test data"

        # FTP write should NOT be called yet
        mock_ftp_client.write_file.assert_not_called()

    def test_write_marks_context_dirty(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that write marks context as dirty."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=0,
            dirty=False,
        )

        filesystem.write(context, b"test", 0)

        assert context.dirty is True

    def test_write_updates_file_size(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that write updates file_size when extending."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=0,
        )

        bytes_written = filesystem.write(context, b"hello world", 0)

        assert bytes_written == 11
        assert context.file_size == 11

    def test_write_at_offset(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test writing at an offset."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=11,  # "hello world" is 11 chars
            buffer=BytesIO(b"hello world"),
        )

        filesystem.write(context, b"TEST", 6)

        context.buffer.seek(0)
        # "hello world" with "TEST" written at offset 6 overwrites positions 6-9
        # Position 10 is 'd', which remains
        assert context.buffer.read() == b"hello TESTd"

    def test_write_existing_file_reads_content_first(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that writing to existing file reads content first."""
        mock_ftp_client.read_file.return_value = b"existing content"

        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=16,  # Has existing content
            buffer=None,
        )

        filesystem.write(context, b"new", 0)

        # Should have read existing content
        mock_ftp_client.read_file.assert_called_once()


class TestFlush:
    """Tests for flush method."""

    def test_flush_uploads_buffer(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that flush uploads buffered data to FTP."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=9,
            buffer=BytesIO(b"test data"),
            dirty=True,
        )

        filesystem.flush(context)

        mock_ftp_client.write_file.assert_called_once_with("/file.txt", b"test data", 0)

    def test_flush_clears_dirty_flag(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that flush clears the dirty flag."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=9,
            buffer=BytesIO(b"test data"),
            dirty=True,
        )

        filesystem.flush(context)

        assert context.dirty is False

    def test_flush_does_nothing_if_not_dirty(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that flush does nothing if not dirty."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=9,
            buffer=BytesIO(b"test data"),
            dirty=False,
        )

        filesystem.flush(context)

        mock_ftp_client.write_file.assert_not_called()

    def test_flush_does_nothing_if_no_buffer(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that flush does nothing if no buffer."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=0,
            buffer=None,
            dirty=True,
        )

        filesystem.flush(context)

        mock_ftp_client.write_file.assert_not_called()

    def test_flush_invalidates_metadata_cache(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that flush invalidates metadata cache."""
        # Pre-populate cache
        filesystem.meta_cache.put("/file.txt", {"size": 100})

        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=9,
            buffer=BytesIO(b"test data"),
            dirty=True,
        )

        filesystem.flush(context)

        # Metadata cache should be invalidated
        assert filesystem.meta_cache.get("/file.txt") is None


class TestCleanup:
    """Tests for cleanup method (handles deletion)."""

    def test_cleanup_deletes_file_on_delete_flag(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that cleanup deletes file when FSP_CLEANUP_DELETE flag is set."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=100,
        )

        filesystem.cleanup(context, "\\file.txt", FSP_CLEANUP_DELETE)

        mock_ftp_client.delete_file.assert_called_once_with("/file.txt")

    def test_cleanup_deletes_directory_on_delete_flag(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that cleanup deletes directory when FSP_CLEANUP_DELETE flag is set."""
        context = FileContext(
            path="/folder",
            is_directory=True,
            file_size=0,
        )

        filesystem.cleanup(context, "\\folder", FSP_CLEANUP_DELETE)

        mock_ftp_client.delete_dir.assert_called_once_with("/folder")

    def test_cleanup_does_nothing_without_delete_flag(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that cleanup does nothing without delete flag."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=100,
        )

        filesystem.cleanup(context, "\\file.txt", 0)

        mock_ftp_client.delete_file.assert_not_called()
        mock_ftp_client.delete_dir.assert_not_called()

    def test_cleanup_invalidates_caches(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that cleanup invalidates caches."""
        # Pre-populate caches
        filesystem.meta_cache.put("/file.txt", {"size": 100})
        filesystem.dir_cache.put("/", [{"name": "file.txt"}])

        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=100,
        )

        filesystem.cleanup(context, "\\file.txt", FSP_CLEANUP_DELETE)

        # Caches should be invalidated
        assert filesystem.meta_cache.get("/file.txt") is None
        assert filesystem.dir_cache.get("/") is None

    def test_cleanup_handles_already_deleted(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that cleanup handles already-deleted files gracefully."""
        mock_ftp_client.delete_file.side_effect = FileNotFoundError()

        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=100,
        )

        # Should not raise
        filesystem.cleanup(context, "\\file.txt", FSP_CLEANUP_DELETE)

    def test_cleanup_raises_not_empty_for_directory(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that cleanup raises NTStatusDirectoryNotEmpty for non-empty directory."""
        mock_ftp_client.delete_dir.side_effect = OSError("Directory not empty")

        context = FileContext(
            path="/folder",
            is_directory=True,
            file_size=0,
        )

        with pytest.raises(NTStatusDirectoryNotEmpty):
            filesystem.cleanup(context, "\\folder", FSP_CLEANUP_DELETE)


class TestRename:
    """Tests for rename method."""

    def test_rename_calls_ftp_rename(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that rename calls FTPClient.rename."""
        # Make get_file_info raise FileNotFoundError so rename proceeds
        mock_ftp_client.get_file_info.side_effect = FileNotFoundError()

        context = FileContext(path="/old.txt", is_directory=False, file_size=100)

        filesystem.rename(context, "\\old.txt", "\\new.txt", False)

        mock_ftp_client.rename.assert_called_once_with("/old.txt", "/new.txt")

    def test_rename_updates_context_path(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that rename updates the context path."""
        # Make get_file_info raise FileNotFoundError so rename proceeds
        mock_ftp_client.get_file_info.side_effect = FileNotFoundError()

        context = FileContext(path="/old.txt", is_directory=False, file_size=100)

        filesystem.rename(context, "\\old.txt", "\\new.txt", False)

        assert context.path == "/new.txt"

    def test_rename_invalidates_caches(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that rename invalidates caches for both paths."""
        # Make get_file_info raise FileNotFoundError so rename proceeds
        mock_ftp_client.get_file_info.side_effect = FileNotFoundError()

        # Pre-populate caches
        filesystem.meta_cache.put("/old.txt", {"size": 100})
        filesystem.meta_cache.put("/new.txt", {"size": 200})
        filesystem.dir_cache.put("/", [{"name": "old.txt"}])

        context = FileContext(path="/old.txt", is_directory=False, file_size=100)

        filesystem.rename(context, "\\old.txt", "\\new.txt", False)

        assert filesystem.meta_cache.get("/old.txt") is None
        assert filesystem.meta_cache.get("/new.txt") is None
        assert filesystem.dir_cache.get("/") is None

    def test_rename_replace_if_exists_deletes_destination(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that rename with replace_if_exists=True deletes existing destination."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="new.txt",
            size=100,
            mtime=datetime.now(),
            is_dir=False,
        )

        context = FileContext(path="/old.txt", is_directory=False, file_size=100)

        filesystem.rename(context, "\\old.txt", "\\new.txt", True)

        mock_ftp_client.delete_file.assert_called_once_with("/new.txt")
        mock_ftp_client.rename.assert_called_once()

    def test_rename_without_replace_raises_collision(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that rename raises NTStatusObjectNameCollision when destination exists."""
        mock_ftp_client.get_file_info.return_value = FileStats(
            name="new.txt",
            size=100,
            mtime=datetime.now(),
            is_dir=False,
        )

        context = FileContext(path="/old.txt", is_directory=False, file_size=100)

        with pytest.raises(NTStatusObjectNameCollision):
            filesystem.rename(context, "\\old.txt", "\\new.txt", False)


class TestClose:
    """Tests for close method."""

    def test_close_is_noop(self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock):
        """Test that close is a no-op (winfspy handles cleanup via cleanup method)."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=9,
            buffer=BytesIO(b"test data"),
            dirty=True,
        )

        # close() should not do anything - flushing happens in cleanup()
        filesystem.close(context)

        mock_ftp_client.write_file.assert_not_called()

    def test_cleanup_flushes_dirty_buffer(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that cleanup flushes dirty buffer."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=9,
            buffer=BytesIO(b"test data"),
            dirty=True,
        )

        filesystem.cleanup(context, "\\file.txt", 0)

        mock_ftp_client.write_file.assert_called_once()


class TestGetFileInfo:
    """Tests for get_file_info method."""

    def test_get_file_info_returns_context_data(self, filesystem: FTPFileSystem):
        """Test that get_file_info returns data from context."""
        # Times are FILETIME integers (100-nanosecond intervals since 1601)
        mtime_filetime = 133500000000000000  # Some arbitrary FILETIME value
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=1024,
            attributes=FILE_ATTRIBUTE_NORMAL,
            mtime_filetime=mtime_filetime,
        )

        result = filesystem.get_file_info(context)

        assert result["file_size"] == 1024
        assert result["allocation_size"] == 1024
        assert result["creation_time"] == mtime_filetime
        assert result["last_access_time"] == mtime_filetime
        assert result["last_write_time"] == mtime_filetime
        assert result["file_attributes"] == FILE_ATTRIBUTE_NORMAL


class TestSetFileInfo:
    """Tests for set_file_info method."""

    def test_set_file_info_handles_truncation(
        self, filesystem: FTPFileSystem, mock_ftp_client: MagicMock
    ):
        """Test that set_file_info handles truncation (file_size=0)."""
        context = FileContext(
            path="/file.txt",
            is_directory=False,
            file_size=1024,
            buffer=BytesIO(b"existing content"),
            dirty=False,
        )

        filesystem.set_file_info(context, {"file_size": 0})

        assert context.file_size == 0
        assert context.dirty is True
        context.buffer.seek(0)
        assert context.buffer.read() == b""


class TestFileContext:
    """Tests for FileContext/OpenedContext."""

    def test_file_context_defaults(self):
        """Test FileContext helper provides sensible defaults."""
        context = FileContext(path="/test", is_directory=False)

        assert context.path == "/test"
        assert context.file_size == 0
        assert context.attributes == FILE_ATTRIBUTE_NORMAL  # Default for files
        assert context.buffer is None
        assert context.dirty is False

    def test_directory_context_defaults(self):
        """Test FileContext helper defaults for directories."""
        context = FileContext(path="/testdir", is_directory=True)

        assert context.is_directory is True
        assert context.attributes == FILE_ATTRIBUTE_DIRECTORY  # Default for dirs

    def test_file_context_with_all_values(self):
        """Test FileContext with all values specified."""
        buffer = BytesIO()
        mtime_filetime = 133500000000000000

        context = FileContext(
            path="/test",
            is_directory=True,
            file_size=1024,
            attributes=FILE_ATTRIBUTE_DIRECTORY,
            mtime_filetime=mtime_filetime,
            buffer=buffer,
            dirty=True,
        )

        assert context.path == "/test"
        assert context.is_directory is True
        assert context.file_size == 1024
        assert context.creation_time == mtime_filetime
        assert context.buffer is buffer
        assert context.dirty is True
