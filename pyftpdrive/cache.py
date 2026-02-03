from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import time

@dataclass
class CacheEntry:
    data: Any
    expires_at: float

class DirectoryCache:
    """
    Cache for directory listings (ls commands).
    """

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}

    def get(self, path: str) -> Optional[List[Any]]:
        """
        Retrieve directory listing if cached and not expired.
        """
        raise NotImplementedError

    def put(self, path: str, listing: List[Any]) -> None:
        """
        Cache a directory listing.
        """
        raise NotImplementedError

    def invalidate(self, path: str) -> None:
        """
        Invalidate cache for a specific path.
        """
        raise NotImplementedError

    def invalidate_parent(self, path: str) -> None:
        """
        Invalidate the parent directory of a path (useful when adding/removing files).
        """
        raise NotImplementedError

class MetadataCache:
    """
    Cache for file metadata (size, mtime, etc.).
    """

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def put(self, path: str, metadata: Dict[str, Any]) -> None:
        raise NotImplementedError

    def invalidate(self, path: str) -> None:
        raise NotImplementedError
