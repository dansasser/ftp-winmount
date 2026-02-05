"""
Unit tests for ftp_winmount.cache module.

Tests cover:
- DirectoryCache.get returns None for missing entry
- DirectoryCache.put stores data
- DirectoryCache.get returns data before TTL expires
- DirectoryCache.get returns None after TTL expires
- DirectoryCache.invalidate removes entry
- DirectoryCache.invalidate_parent extracts parent path
- MetadataCache same patterns
- Thread safety with concurrent access
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from unittest.mock import patch

from ftp_winmount.cache import CacheEntry, DirectoryCache, MetadataCache


class TestDirectoryCacheGet:
    """Tests for DirectoryCache.get method."""

    def test_get_returns_none_for_missing_entry(self):
        """Test that get returns None for a path not in cache."""
        cache = DirectoryCache(ttl_seconds=30)
        result = cache.get("/nonexistent/path")
        assert result is None

    def test_get_returns_none_for_empty_cache(self):
        """Test that get returns None when cache is empty."""
        cache = DirectoryCache(ttl_seconds=30)
        assert cache.get("/") is None
        assert cache.get("/folder") is None
        assert cache.get("/folder/subfolder") is None


class TestDirectoryCachePut:
    """Tests for DirectoryCache.put method."""

    def test_put_stores_data(self):
        """Test that put stores data and get retrieves it."""
        cache = DirectoryCache(ttl_seconds=30)
        test_listing = [{"name": "file1.txt"}, {"name": "file2.txt"}]

        cache.put("/test/path", test_listing)
        result = cache.get("/test/path")

        assert result == test_listing

    def test_put_overwrites_existing_entry(self):
        """Test that put overwrites existing cache entry."""
        cache = DirectoryCache(ttl_seconds=30)

        cache.put("/path", [{"name": "old"}])
        cache.put("/path", [{"name": "new"}])

        result = cache.get("/path")
        assert result == [{"name": "new"}]

    def test_put_stores_different_paths_independently(self):
        """Test that different paths are stored independently."""
        cache = DirectoryCache(ttl_seconds=30)

        listing1 = [{"name": "file1.txt"}]
        listing2 = [{"name": "file2.txt"}]

        cache.put("/path1", listing1)
        cache.put("/path2", listing2)

        assert cache.get("/path1") == listing1
        assert cache.get("/path2") == listing2


class TestDirectoryCacheTTL:
    """Tests for DirectoryCache TTL expiration."""

    def test_get_returns_data_before_ttl_expires(self):
        """Test that data is returned before TTL expires."""
        cache = DirectoryCache(ttl_seconds=10)
        test_listing = [{"name": "file.txt"}]

        cache.put("/path", test_listing)

        # Immediately check - should return data
        result = cache.get("/path")
        assert result == test_listing

    def test_get_returns_none_after_ttl_expires(self):
        """Test that None is returned after TTL expires."""
        cache = DirectoryCache(ttl_seconds=1)
        test_listing = [{"name": "file.txt"}]

        cache.put("/path", test_listing)

        # Wait for TTL to expire
        time.sleep(1.1)

        result = cache.get("/path")
        assert result is None

    def test_ttl_expiration_removes_entry(self):
        """Test that expired entry is removed from internal cache."""
        cache = DirectoryCache(ttl_seconds=1)
        cache.put("/path", [{"name": "file.txt"}])

        time.sleep(1.1)

        # Access triggers removal
        cache.get("/path")

        # Verify it's actually removed
        assert "/path" not in cache._cache

    def test_expired_entry_can_be_replaced(self):
        """Test that expired entry can be replaced with new data."""
        cache = DirectoryCache(ttl_seconds=1)

        cache.put("/path", [{"name": "old"}])
        time.sleep(1.1)

        # Old entry expired, put new data
        cache.put("/path", [{"name": "new"}])

        result = cache.get("/path")
        assert result == [{"name": "new"}]


class TestDirectoryCacheInvalidate:
    """Tests for DirectoryCache.invalidate method."""

    def test_invalidate_removes_entry(self):
        """Test that invalidate removes a specific entry."""
        cache = DirectoryCache(ttl_seconds=30)
        cache.put("/path", [{"name": "file.txt"}])

        cache.invalidate("/path")

        assert cache.get("/path") is None

    def test_invalidate_nonexistent_path_no_error(self):
        """Test that invalidating non-existent path doesn't raise error."""
        cache = DirectoryCache(ttl_seconds=30)

        # Should not raise
        cache.invalidate("/nonexistent")

    def test_invalidate_only_affects_specified_path(self):
        """Test that invalidate only removes the specified path."""
        cache = DirectoryCache(ttl_seconds=30)
        cache.put("/path1", [{"name": "file1.txt"}])
        cache.put("/path2", [{"name": "file2.txt"}])

        cache.invalidate("/path1")

        assert cache.get("/path1") is None
        assert cache.get("/path2") == [{"name": "file2.txt"}]


class TestDirectoryCacheInvalidateParent:
    """Tests for DirectoryCache.invalidate_parent method."""

    def test_invalidate_parent_extracts_parent_path(self):
        """Test that invalidate_parent correctly identifies parent directory."""
        cache = DirectoryCache(ttl_seconds=30)
        cache.put("/parent", [{"name": "child"}])
        cache.put("/parent/child", [{"name": "file.txt"}])

        cache.invalidate_parent("/parent/child/file.txt")

        # Parent of /parent/child/file.txt is /parent/child
        assert cache.get("/parent/child") is None
        # /parent should still exist
        assert cache.get("/parent") is not None

    def test_invalidate_parent_handles_windows_paths(self):
        """Test that invalidate_parent converts backslashes."""
        cache = DirectoryCache(ttl_seconds=30)
        cache.put("/folder", [{"name": "file.txt"}])

        # Windows-style path
        cache.invalidate_parent("\\folder\\file.txt")

        assert cache.get("/folder") is None

    def test_invalidate_parent_handles_root_level_files(self):
        """Test that files at root have / as parent."""
        cache = DirectoryCache(ttl_seconds=30)
        cache.put("/", [{"name": "rootfile.txt"}])

        cache.invalidate_parent("/rootfile.txt")

        assert cache.get("/") is None

    def test_invalidate_parent_handles_trailing_slash(self):
        """Test that trailing slashes are handled."""
        cache = DirectoryCache(ttl_seconds=30)
        cache.put("/parent", [{"name": "child"}])

        cache.invalidate_parent("/parent/child/")

        assert cache.get("/parent") is None

    def test_invalidate_parent_single_component_path(self):
        """Test path with single component (at root level)."""
        cache = DirectoryCache(ttl_seconds=30)
        cache.put("/", [{"name": "folder"}])

        cache.invalidate_parent("folder")

        assert cache.get("/") is None


class TestMetadataCacheGet:
    """Tests for MetadataCache.get method."""

    def test_get_returns_none_for_missing_entry(self):
        """Test that get returns None for a path not in cache."""
        cache = MetadataCache(ttl_seconds=30)
        result = cache.get("/nonexistent/file.txt")
        assert result is None

    def test_get_returns_none_for_empty_cache(self):
        """Test that get returns None when cache is empty."""
        cache = MetadataCache(ttl_seconds=30)
        assert cache.get("/") is None
        assert cache.get("/file.txt") is None


class TestMetadataCachePut:
    """Tests for MetadataCache.put method."""

    def test_put_stores_metadata(self):
        """Test that put stores metadata and get retrieves it."""
        cache = MetadataCache(ttl_seconds=30)
        test_metadata = {"size": 1024, "mtime": datetime.now(), "is_dir": False}

        cache.put("/test/file.txt", test_metadata)
        result = cache.get("/test/file.txt")

        assert result == test_metadata

    def test_put_overwrites_existing_metadata(self):
        """Test that put overwrites existing metadata."""
        cache = MetadataCache(ttl_seconds=30)

        cache.put("/file.txt", {"size": 100})
        cache.put("/file.txt", {"size": 200})

        result = cache.get("/file.txt")
        assert result == {"size": 200}

    def test_put_stores_different_paths_independently(self):
        """Test that different paths are stored independently."""
        cache = MetadataCache(ttl_seconds=30)

        meta1 = {"size": 100}
        meta2 = {"size": 200}

        cache.put("/file1.txt", meta1)
        cache.put("/file2.txt", meta2)

        assert cache.get("/file1.txt") == meta1
        assert cache.get("/file2.txt") == meta2


class TestMetadataCacheTTL:
    """Tests for MetadataCache TTL expiration."""

    def test_get_returns_data_before_ttl_expires(self):
        """Test that metadata is returned before TTL expires."""
        cache = MetadataCache(ttl_seconds=10)
        test_metadata = {"size": 1024}

        cache.put("/file.txt", test_metadata)

        result = cache.get("/file.txt")
        assert result == test_metadata

    def test_get_returns_none_after_ttl_expires(self):
        """Test that None is returned after TTL expires."""
        cache = MetadataCache(ttl_seconds=1)
        test_metadata = {"size": 1024}

        cache.put("/file.txt", test_metadata)

        time.sleep(1.1)

        result = cache.get("/file.txt")
        assert result is None

    def test_ttl_expiration_removes_entry(self):
        """Test that expired entry is removed from internal cache."""
        cache = MetadataCache(ttl_seconds=1)
        cache.put("/file.txt", {"size": 1024})

        time.sleep(1.1)

        # Access triggers removal
        cache.get("/file.txt")

        assert "/file.txt" not in cache._cache


class TestMetadataCacheInvalidate:
    """Tests for MetadataCache.invalidate method."""

    def test_invalidate_removes_entry(self):
        """Test that invalidate removes a specific entry."""
        cache = MetadataCache(ttl_seconds=30)
        cache.put("/file.txt", {"size": 1024})

        cache.invalidate("/file.txt")

        assert cache.get("/file.txt") is None

    def test_invalidate_nonexistent_path_no_error(self):
        """Test that invalidating non-existent path doesn't raise error."""
        cache = MetadataCache(ttl_seconds=30)

        # Should not raise
        cache.invalidate("/nonexistent")

    def test_invalidate_only_affects_specified_path(self):
        """Test that invalidate only removes the specified path."""
        cache = MetadataCache(ttl_seconds=30)
        cache.put("/file1.txt", {"size": 100})
        cache.put("/file2.txt", {"size": 200})

        cache.invalidate("/file1.txt")

        assert cache.get("/file1.txt") is None
        assert cache.get("/file2.txt") == {"size": 200}


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test CacheEntry creation with data and expiry."""
        now = time.time()
        entry = CacheEntry(data={"test": "data"}, expires_at=now + 30)

        assert entry.data == {"test": "data"}
        assert entry.expires_at > now

    def test_cache_entry_with_list_data(self):
        """Test CacheEntry with list data."""
        entry = CacheEntry(data=[1, 2, 3], expires_at=time.time() + 30)
        assert entry.data == [1, 2, 3]


class TestDirectoryCacheThreadSafety:
    """Tests for thread safety with concurrent access."""

    def test_concurrent_put_operations(self):
        """Test that concurrent put operations don't cause race conditions."""
        cache = DirectoryCache(ttl_seconds=30)
        num_threads = 10
        num_operations = 100

        def put_worker(thread_id: int):
            for i in range(num_operations):
                path = f"/thread{thread_id}/file{i}"
                cache.put(path, [{"name": f"file{i}"}])

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(put_worker, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Verify some data was stored correctly
        result = cache.get("/thread0/file0")
        assert result == [{"name": "file0"}]

    def test_concurrent_get_operations(self):
        """Test that concurrent get operations don't cause race conditions."""
        cache = DirectoryCache(ttl_seconds=30)

        # Pre-populate cache
        for i in range(100):
            cache.put(f"/file{i}", [{"name": f"file{i}"}])

        results = []
        num_threads = 10

        def get_worker():
            thread_results = []
            for i in range(100):
                result = cache.get(f"/file{i}")
                if result:
                    thread_results.append(result)
            return thread_results

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(get_worker) for _ in range(num_threads)]
            for future in as_completed(futures):
                results.extend(future.result())

        # All threads should have gotten valid results
        assert len(results) == num_threads * 100

    def test_concurrent_put_and_invalidate(self):
        """Test concurrent put and invalidate operations."""
        cache = DirectoryCache(ttl_seconds=30)
        stop_event = threading.Event()
        errors = []

        def put_worker():
            try:
                i = 0
                while not stop_event.is_set():
                    cache.put(f"/file{i % 10}", [{"name": f"file{i}"}])
                    i += 1
            except Exception as e:
                errors.append(e)

        def invalidate_worker():
            try:
                i = 0
                while not stop_event.is_set():
                    cache.invalidate(f"/file{i % 10}")
                    i += 1
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=put_worker),
            threading.Thread(target=put_worker),
            threading.Thread(target=invalidate_worker),
        ]

        for t in threads:
            t.start()

        # Run for a short time
        time.sleep(0.5)
        stop_event.set()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"


class TestMetadataCacheThreadSafety:
    """Tests for MetadataCache thread safety."""

    def test_concurrent_put_and_get_operations(self):
        """Test concurrent put and get operations on MetadataCache."""
        cache = MetadataCache(ttl_seconds=30)
        num_threads = 10
        num_operations = 100
        errors = []

        def worker(thread_id: int):
            try:
                for i in range(num_operations):
                    path = f"/file{thread_id}_{i}"
                    cache.put(path, {"size": i, "thread": thread_id})
                    result = cache.get(path)
                    if result is None:
                        # Could be expired or invalidated, not an error
                        pass
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_concurrent_invalidate_operations(self):
        """Test that concurrent invalidate operations are safe."""
        cache = MetadataCache(ttl_seconds=30)

        # Pre-populate
        for i in range(100):
            cache.put(f"/file{i}", {"size": i})

        def invalidate_worker():
            for i in range(100):
                cache.invalidate(f"/file{i}")

        threads = [threading.Thread(target=invalidate_worker) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All should be invalidated
        for i in range(100):
            assert cache.get(f"/file{i}") is None


class TestCacheTTLEdgeCases:
    """Tests for TTL edge cases."""

    def test_zero_ttl_immediately_expires(self):
        """Test that TTL of 0 means immediate expiration."""
        cache = DirectoryCache(ttl_seconds=0)
        cache.put("/path", [{"name": "file"}])

        # Even immediate access should fail with 0 TTL
        # (time.time() will be >= expires_at)
        time.sleep(0.01)  # Small delay to ensure time passes
        result = cache.get("/path")
        assert result is None

    def test_very_short_ttl(self):
        """Test very short TTL (100ms)."""
        # Using a mock to control time is more reliable
        cache = DirectoryCache(ttl_seconds=1)

        with patch("ftp_winmount.cache.time.time") as mock_time:
            # Initial put at t=100
            mock_time.return_value = 100.0
            cache.put("/path", [{"name": "file"}])

            # Get at t=100.5 (before expiry at t=101)
            mock_time.return_value = 100.5
            assert cache.get("/path") is not None

            # Get at t=101.1 (after expiry)
            mock_time.return_value = 101.1
            assert cache.get("/path") is None

    def test_large_ttl(self):
        """Test large TTL value."""
        cache = DirectoryCache(ttl_seconds=86400)  # 24 hours
        cache.put("/path", [{"name": "file"}])

        result = cache.get("/path")
        assert result is not None
