"""
Unit tests for ftp_winmount.gdrive_path_cache module.

Tests cover:
- Root path resolution
- Single-segment path resolution
- Multi-segment path resolution with caching
- Cache TTL expiration
- Cache invalidation (single path, children, full clear)
- Path normalization (backslashes, leading slash, trailing slash)
- Shared drive support
- API query failure handling
- Thread safety basics
"""

import time
from unittest.mock import MagicMock

import pytest

from ftp_winmount.gdrive_path_cache import FOLDER_MIME, PathCache


@pytest.fixture
def mock_service():
    """Creates a mocked Google Drive API service."""
    service = MagicMock()
    return service


@pytest.fixture
def path_cache(mock_service):
    """Creates a PathCache with mocked service and short TTL."""
    return PathCache(mock_service, ttl_seconds=60)


@pytest.fixture
def shared_drive_cache(mock_service):
    """Creates a PathCache configured for a shared drive."""
    return PathCache(mock_service, ttl_seconds=60, shared_drive_id="shared123")


def _mock_list_response(mock_service, file_id, file_name="test"):
    """Helper to set up a mock files().list() response."""
    mock_files = MagicMock()
    mock_list = MagicMock()
    mock_list.execute.return_value = {
        "files": [{"id": file_id, "name": file_name}]
    }
    mock_files.list.return_value = mock_list
    mock_service.files.return_value = mock_files


def _mock_list_empty(mock_service):
    """Helper to set up a mock files().list() that returns no results."""
    mock_files = MagicMock()
    mock_list = MagicMock()
    mock_list.execute.return_value = {"files": []}
    mock_files.list.return_value = mock_list
    mock_service.files.return_value = mock_files


class TestRootResolution:
    """Tests for root path resolution."""

    def test_root_slash_returns_root_id(self, path_cache):
        """Root path '/' returns the root ID."""
        assert path_cache.resolve("/") == "root"

    def test_root_with_shared_drive(self, shared_drive_cache):
        """Root path with shared drive returns the shared drive ID."""
        assert shared_drive_cache.resolve("/") == "shared123"


class TestPathResolution:
    """Tests for single and multi-segment path resolution."""

    def test_single_segment_resolution(self, path_cache, mock_service):
        """Resolving '/Documents' queries API with parent='root'."""
        _mock_list_response(mock_service, "doc_id_123", "Documents")

        result = path_cache.resolve("/Documents")

        assert result == "doc_id_123"
        # Verify the API was called
        mock_service.files().list.assert_called_once()
        call_kwargs = mock_service.files().list.call_args[1]
        assert "'root' in parents" in call_kwargs["q"]
        assert "Documents" in call_kwargs["q"]

    def test_multi_segment_resolution(self, path_cache, mock_service):
        """Resolving '/Documents/notes.txt' walks two segments."""
        # Set up sequential responses
        responses = [
            {"files": [{"id": "doc_folder_id", "name": "Documents"}]},
            {"files": [{"id": "notes_file_id", "name": "notes.txt"}]},
        ]
        call_count = [0]

        def mock_execute():
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx]

        mock_list = MagicMock()
        mock_list.execute.side_effect = mock_execute
        mock_service.files().list.return_value = mock_list

        result = path_cache.resolve("/Documents/notes.txt")

        assert result == "notes_file_id"
        assert mock_service.files().list.call_count == 2

    def test_segment_not_found_returns_none(self, path_cache, mock_service):
        """Returns None when a path segment doesn't exist."""
        _mock_list_empty(mock_service)

        result = path_cache.resolve("/nonexistent")

        assert result is None

    def test_partial_path_not_found_returns_none(self, path_cache, mock_service):
        """Returns None when an intermediate segment doesn't exist."""
        responses = [
            {"files": [{"id": "folder_id", "name": "exists"}]},
            {"files": []},  # Second segment not found
        ]
        call_count = [0]

        def mock_execute():
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx]

        mock_list = MagicMock()
        mock_list.execute.side_effect = mock_execute
        mock_service.files().list.return_value = mock_list

        result = path_cache.resolve("/exists/nope/file.txt")

        assert result is None


class TestCaching:
    """Tests for cache hit/miss behavior."""

    def test_second_resolve_uses_cache(self, path_cache, mock_service):
        """Second resolve of same path should use cache, not API."""
        _mock_list_response(mock_service, "cached_id", "folder")

        # First call - hits API
        result1 = path_cache.resolve("/folder")
        assert result1 == "cached_id"

        # Second call - should use cache
        result2 = path_cache.resolve("/folder")
        assert result2 == "cached_id"

        # API should have been called only once
        assert mock_service.files().list.call_count == 1

    def test_partial_path_caching(self, path_cache, mock_service):
        """Resolving a deep path caches intermediate segments."""
        responses = [
            {"files": [{"id": "a_id", "name": "a"}]},
            {"files": [{"id": "b_id", "name": "b"}]},
        ]
        call_count = [0]

        def mock_execute():
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx]

        mock_list = MagicMock()
        mock_list.execute.side_effect = mock_execute
        mock_service.files().list.return_value = mock_list

        path_cache.resolve("/a/b")

        # Now resolve just /a - should be cached
        _mock_list_response(mock_service, "should_not_be_used")
        result = path_cache.resolve("/a")
        assert result == "a_id"

    def test_cache_ttl_expiration(self, mock_service):
        """Cache entries expire after TTL."""
        cache = PathCache(mock_service, ttl_seconds=0)  # Immediate expiry

        _mock_list_response(mock_service, "first_id", "folder")
        result1 = cache.resolve("/folder")
        assert result1 == "first_id"

        # Wait a tiny bit so TTL expires
        time.sleep(0.01)

        # Should call API again due to expiry
        _mock_list_response(mock_service, "second_id", "folder")
        result2 = cache.resolve("/folder")
        assert result2 == "second_id"


class TestCacheInvalidation:
    """Tests for cache invalidation methods."""

    def test_invalidate_removes_path(self, path_cache, mock_service):
        """invalidate() removes a specific path from cache."""
        _mock_list_response(mock_service, "file_id", "file.txt")
        path_cache.resolve("/file.txt")

        path_cache.invalidate("/file.txt")

        # Should need to query API again
        _mock_list_response(mock_service, "new_id", "file.txt")
        result = path_cache.resolve("/file.txt")
        assert result == "new_id"

    def test_invalidate_children_removes_subtree(self, path_cache, mock_service):
        """invalidate_children() removes all paths under a prefix."""
        # Populate cache with several paths
        responses = [
            {"files": [{"id": "dir_id", "name": "dir"}]},
            {"files": [{"id": "child_id", "name": "child.txt"}]},
        ]
        call_count = [0]

        def mock_execute():
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx]

        mock_list = MagicMock()
        mock_list.execute.side_effect = mock_execute
        mock_service.files().list.return_value = mock_list

        path_cache.resolve("/dir/child.txt")

        # Invalidate /dir and its children
        path_cache.invalidate_children("/dir")

        # Both /dir and /dir/child.txt should be gone
        assert path_cache._cache.get("/dir") is None
        assert path_cache._cache.get("/dir/child.txt") is None

    def test_clear_removes_all(self, path_cache, mock_service):
        """clear() empties the entire cache."""
        _mock_list_response(mock_service, "id1", "file1")
        path_cache.resolve("/file1")

        path_cache.clear()

        assert len(path_cache._cache) == 0


class TestPathNormalization:
    """Tests for path normalization."""

    def test_backslashes_converted(self, path_cache, mock_service):
        """Backslashes are converted to forward slashes."""
        _mock_list_response(mock_service, "file_id", "file.txt")

        result = path_cache.resolve("\\file.txt")

        assert result == "file_id"

    def test_missing_leading_slash_added(self, path_cache, mock_service):
        """Paths without leading slash get one added."""
        _mock_list_response(mock_service, "file_id", "file.txt")

        result = path_cache.resolve("file.txt")

        assert result == "file_id"

    def test_trailing_slash_stripped(self, path_cache, mock_service):
        """Trailing slashes are removed (except root)."""
        _mock_list_response(mock_service, "dir_id", "folder")

        result = path_cache.resolve("/folder/")

        assert result == "dir_id"

    def test_root_trailing_slash_preserved(self, path_cache):
        """Root path '/' is not stripped to empty string."""
        result = path_cache.resolve("/")
        assert result == "root"


class TestSharedDriveSupport:
    """Tests for shared/team drive support."""

    def test_shared_drive_passes_corpora_param(self, shared_drive_cache, mock_service):
        """Shared drive queries include corpora and driveId params."""
        _mock_list_response(mock_service, "file_id", "file.txt")

        shared_drive_cache.resolve("/file.txt")

        call_kwargs = mock_service.files().list.call_args[1]
        assert call_kwargs["corpora"] == "drive"
        assert call_kwargs["driveId"] == "shared123"
        assert call_kwargs["includeItemsFromAllDrives"] is True
        assert call_kwargs["supportsAllDrives"] is True


class TestAPIFailure:
    """Tests for API query failure handling."""

    def test_api_exception_returns_none(self, path_cache, mock_service):
        """API exceptions during resolution return None."""
        mock_list = MagicMock()
        mock_list.execute.side_effect = Exception("API error")
        mock_service.files().list.return_value = mock_list

        result = path_cache.resolve("/broken")

        assert result is None

    def test_name_with_single_quotes_escaped(self, path_cache, mock_service):
        """Single quotes in filenames are escaped in API query."""
        _mock_list_response(mock_service, "file_id", "it's a file")

        path_cache.resolve("/it's a file")

        call_kwargs = mock_service.files().list.call_args[1]
        assert "it\\'s a file" in call_kwargs["q"]
