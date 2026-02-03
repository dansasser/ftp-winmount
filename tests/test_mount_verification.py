"""
Verification tests for mount fixes.

These tests verify the code is correct WITHOUT mounting a drive.
ALL tests must pass before attempting mount.
"""

import threading
from datetime import datetime
from unittest.mock import MagicMock


def test_filesystem_creation_has_required_params():
    """Verify __main__.py passes critical params to FileSystem."""
    with open("pyftpdrive/__main__.py", encoding="utf-8") as f:
        source = f.read()

    assert "um_file_context_is_user_context2=1" in source, (
        "MISSING: um_file_context_is_user_context2=1"
    )
    assert "post_cleanup_when_modified_only=1" in source, (
        "MISSING: post_cleanup_when_modified_only=1"
    )
    assert "volume_creation_time=" in source, "MISSING: volume_creation_time"
    print("[OK] FileSystem parameters verified")


def test_operation_decorator_exists():
    """Verify the operation decorator is defined and works."""
    from pyftpdrive.filesystem import operation

    # Test it actually locks
    class FakeFS:
        def __init__(self):
            self._thread_lock = threading.Lock()

        @operation
        def test_method(self):
            return "works"

    fs = FakeFS()
    assert fs.test_method() == "works"
    print("[OK] @operation decorator works")


def test_all_methods_have_operation_decorator():
    """Verify every public method has @operation."""
    from pyftpdrive.filesystem import FTPFileSystem

    required_methods = [
        "get_volume_info",
        "get_security_by_name",
        "open",
        "close",
        "read",
        "read_directory",
        "get_file_info",
        "write",
        "flush",
        "set_file_info",
        "create",
        "cleanup",
        "rename",
    ]

    for method_name in required_methods:
        method = getattr(FTPFileSystem, method_name, None)
        assert method is not None, f"MISSING method: {method_name}"
        # Check if wrapped (has __wrapped__ attribute from @wraps)
        assert hasattr(method, "__wrapped__"), f"Method {method_name} missing @operation decorator"

    print("[OK] All methods have @operation decorator")


def test_opened_context_has_required_attributes():
    """Verify OpenedContext has all required attributes with FILETIME integers."""
    from pyftpdrive.filesystem import OpenedContext

    ctx = OpenedContext(
        path="/test",
        is_directory=False,
        file_size=100,
        attributes=0x80,
        mtime_filetime=132500000000000000,
    )

    # All required attributes
    assert hasattr(ctx, "path")
    assert hasattr(ctx, "is_directory")
    assert hasattr(ctx, "file_size")
    assert hasattr(ctx, "attributes")
    assert hasattr(ctx, "creation_time")
    assert hasattr(ctx, "last_access_time")
    assert hasattr(ctx, "last_write_time")
    assert hasattr(ctx, "change_time")

    # Times must be integers (FILETIME)
    assert isinstance(ctx.creation_time, int), (
        f"creation_time must be int, got {type(ctx.creation_time)}"
    )
    assert isinstance(ctx.last_access_time, int), (
        f"last_access_time must be int, got {type(ctx.last_access_time)}"
    )
    assert isinstance(ctx.last_write_time, int), (
        f"last_write_time must be int, got {type(ctx.last_write_time)}"
    )
    assert isinstance(ctx.change_time, int), f"change_time must be int, got {type(ctx.change_time)}"

    print("[OK] OpenedContext class verified")


def test_get_file_info_return_format():
    """Verify get_file_info returns correct dict format with FILETIME integers."""
    from pyftpdrive.filesystem import FTPFileSystem, OpenedContext

    mock_ftp = MagicMock()
    mock_config = MagicMock()
    mock_config.directory_ttl_seconds = 30
    mock_config.metadata_ttl_seconds = 60

    fs = FTPFileSystem(mock_ftp, mock_config)

    ctx = OpenedContext(
        path="/test.txt",
        is_directory=False,
        file_size=1234,
        attributes=0x80,
        mtime_filetime=132500000000000000,
    )

    info = fs.get_file_info(ctx)

    # Verify required keys
    required_keys = [
        "file_attributes",
        "file_size",
        "allocation_size",
        "creation_time",
        "last_access_time",
        "last_write_time",
        "change_time",
    ]
    for key in required_keys:
        assert key in info, f"MISSING key in get_file_info: {key}"

    # Verify times are integers
    assert isinstance(info["creation_time"], int), "creation_time must be int"
    assert isinstance(info["last_access_time"], int), "last_access_time must be int"
    assert isinstance(info["last_write_time"], int), "last_write_time must be int"
    assert isinstance(info["change_time"], int), "change_time must be int"

    print("[OK] get_file_info return format verified")


def test_read_directory_return_format():
    """Verify read_directory returns list of dicts with file_name key."""
    from pyftpdrive.filesystem import FTPFileSystem, OpenedContext
    from pyftpdrive.ftp_client import FileStats

    mock_ftp = MagicMock()
    mock_ftp.list_dir.return_value = [
        FileStats(name="file1.txt", size=100, mtime=datetime.now(), is_dir=False),
        FileStats(name="folder1", size=0, mtime=datetime.now(), is_dir=True),
    ]

    mock_config = MagicMock()
    mock_config.directory_ttl_seconds = 30
    mock_config.metadata_ttl_seconds = 60

    fs = FTPFileSystem(mock_ftp, mock_config)

    ctx = OpenedContext(
        path="/", is_directory=True, file_size=0, attributes=0x10, mtime_filetime=132500000000000000
    )

    entries = fs.read_directory(ctx, None)

    # Verify it's a list
    assert isinstance(entries, list), f"read_directory must return list, got {type(entries)}"

    # Verify each entry is a dict with file_name
    for entry in entries:
        assert isinstance(entry, dict), f"Entry must be dict, got {type(entry)}"
        assert "file_name" in entry, "MISSING 'file_name' key in entry"
        # Verify times are integers
        if "creation_time" in entry:
            assert isinstance(entry["creation_time"], int), "creation_time must be int"

    print(f"[OK] read_directory returns {len(entries)} entries in correct format")


def test_close_does_nothing():
    """Verify close() has no side effects."""
    from pyftpdrive.filesystem import FTPFileSystem, OpenedContext

    mock_ftp = MagicMock()
    mock_config = MagicMock()
    mock_config.directory_ttl_seconds = 30
    mock_config.metadata_ttl_seconds = 60

    fs = FTPFileSystem(mock_ftp, mock_config)

    ctx = OpenedContext(
        path="/test.txt",
        is_directory=False,
        file_size=100,
        attributes=0x80,
        mtime_filetime=132500000000000000,
    )

    # close() should not raise
    fs.close(ctx)

    # Verify no FTP calls were made
    mock_ftp.read_file.assert_not_called()
    mock_ftp.write_file.assert_not_called()

    print("[OK] close() does nothing (no side effects)")


def test_full_open_get_file_info_close_cycle():
    """Test complete file operation cycle without mounting."""
    from pyftpdrive.filesystem import FTPFileSystem, OpenedContext
    from pyftpdrive.ftp_client import FileStats

    mock_ftp = MagicMock()
    mock_ftp.get_file_info.return_value = FileStats(
        name="test.txt", size=5, mtime=datetime.now(), is_dir=False
    )
    mock_ftp.read_file.return_value = b"hello"

    mock_config = MagicMock()
    mock_config.directory_ttl_seconds = 30
    mock_config.metadata_ttl_seconds = 60

    fs = FTPFileSystem(mock_ftp, mock_config)

    # 1. Open
    ctx = fs.open("\\test.txt", 0, 0)
    assert isinstance(ctx, OpenedContext), "open() must return OpenedContext"

    # 2. get_file_info
    info = fs.get_file_info(ctx)
    assert isinstance(info, dict), "get_file_info must return dict"
    time_keys = ["creation_time", "last_access_time", "last_write_time", "change_time"]
    for key in time_keys:
        assert isinstance(info.get(key, 0), int), f"{key} must be int"

    # 3. Read
    data = fs.read(ctx, 0, 100)
    assert data == b"hello"

    # 4. Close (should not raise)
    fs.close(ctx)

    print("[OK] Full open/get_file_info/read/close cycle works")
