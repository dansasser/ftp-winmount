import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    data: Any
    expires_at: float


class DirectoryCache:
    """
    Cache for directory listings (ls commands).

    Thread-safe cache that stores directory listings with TTL-based expiration.
    Used to reduce FTP round-trips for directory enumeration.
    """

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, path: str) -> list[Any] | None:
        """
        Retrieve directory listing if cached and not expired.

        Args:
            path: The directory path to look up.

        Returns:
            The cached listing if present and not expired, else None.
        """
        with self._lock:
            entry = self._cache.get(path)
            if entry is None:
                return None
            if time.time() >= entry.expires_at:
                # Entry expired, remove it
                del self._cache[path]
                return None
            return entry.data

    def put(self, path: str, listing: list[Any]) -> None:
        """
        Cache a directory listing.

        Args:
            path: The directory path.
            listing: The directory listing to cache.
        """
        with self._lock:
            expires_at = time.time() + self.ttl_seconds
            self._cache[path] = CacheEntry(data=listing, expires_at=expires_at)

    def invalidate(self, path: str) -> None:
        """
        Invalidate cache for a specific path.

        Args:
            path: The directory path to invalidate.
        """
        with self._lock:
            self._cache.pop(path, None)

    def invalidate_parent(self, path: str) -> None:
        """
        Invalidate the parent directory of a path (useful when adding/removing files).

        Args:
            path: The path whose parent should be invalidated.
        """
        # Normalize path separators and extract parent
        normalized = path.replace("\\", "/")
        # Remove trailing slash if present
        normalized = normalized.rstrip("/")

        if "/" in normalized:
            parent = normalized.rsplit("/", 1)[0]
            # Handle root case
            if not parent:
                parent = "/"
        else:
            # Path is at root level, parent is root
            parent = "/"

        self.invalidate(parent)


class MetadataCache:
    """
    Cache for file metadata (size, mtime, etc.).

    Thread-safe cache that stores file metadata with TTL-based expiration.
    Used to reduce FTP round-trips for stat operations.
    """

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, path: str) -> dict[str, Any] | None:
        """
        Retrieve file metadata if cached and not expired.

        Args:
            path: The file path to look up.

        Returns:
            The cached metadata dict if present and not expired, else None.
        """
        with self._lock:
            entry = self._cache.get(path)
            if entry is None:
                return None
            if time.time() >= entry.expires_at:
                # Entry expired, remove it
                del self._cache[path]
                return None
            return entry.data

    def put(self, path: str, metadata: dict[str, Any]) -> None:
        """
        Cache file metadata.

        Args:
            path: The file path.
            metadata: The metadata dict to cache.
        """
        with self._lock:
            expires_at = time.time() + self.ttl_seconds
            self._cache[path] = CacheEntry(data=metadata, expires_at=expires_at)

    def invalidate(self, path: str) -> None:
        """
        Invalidate cache for a specific path.

        Args:
            path: The file path to invalidate.
        """
        with self._lock:
            self._cache.pop(path, None)
