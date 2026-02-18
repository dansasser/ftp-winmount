"""
Path-to-ID resolver for Google Drive.

Google Drive is ID-based, not path-based. This module resolves filesystem
paths (e.g., "/Documents/notes.txt") to Google Drive file IDs by walking
the folder hierarchy. Results are cached with TTL expiration.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# Google Drive folder MIME type
FOLDER_MIME = "application/vnd.google-apps.folder"


class PathCache:
    """
    Thread-safe path-to-ID cache with TTL expiration.

    Resolves paths by querying the Google Drive API one folder level at a time,
    caching each segment's ID for future lookups.
    """

    def __init__(self, drive_service, ttl_seconds: int = 120, shared_drive_id: str | None = None):
        """
        Args:
            drive_service: Google Drive API service object (from googleapiclient).
            ttl_seconds: How long cached entries remain valid.
            shared_drive_id: If set, resolve paths within this shared drive.
        """
        self._service = drive_service
        self._ttl = ttl_seconds
        self._shared_drive_id = shared_drive_id
        self._lock = threading.Lock()
        # Cache: path_str -> (file_id, timestamp)
        self._cache: dict[str, tuple[str, float]] = {}
        # Root ID
        self._root_id = shared_drive_id or "root"

    def _is_valid(self, entry: tuple[str, float]) -> bool:
        """Check if a cache entry is still within TTL."""
        _, timestamp = entry
        return (time.time() - timestamp) < self._ttl

    def resolve(self, path: str) -> str | None:
        """
        Resolve a filesystem path to a Google Drive file ID.

        Args:
            path: Filesystem path like "/Documents/notes.txt"

        Returns:
            Google Drive file ID, or None if not found.
        """
        path = self._normalize_path(path)

        if path == "/":
            return self._root_id

        # Check cache first
        with self._lock:
            cached = self._cache.get(path)
            if cached and self._is_valid(cached):
                return cached[0]

        # Walk path segments
        segments = [s for s in path.split("/") if s]
        current_id = self._root_id

        for i, segment in enumerate(segments):
            partial_path = "/" + "/".join(segments[: i + 1])

            # Check cache for this partial path
            with self._lock:
                cached = self._cache.get(partial_path)
                if cached and self._is_valid(cached):
                    current_id = cached[0]
                    continue

            # Query Drive API for this segment
            file_id = self._find_child(current_id, segment)
            if file_id is None:
                logger.debug("Path segment not found: %s in parent %s", segment, current_id)
                return None

            # Cache the result
            with self._lock:
                self._cache[partial_path] = (file_id, time.time())

            current_id = file_id

        return current_id

    def _find_child(self, parent_id: str, name: str) -> str | None:
        """
        Find a child file/folder by name within a parent folder.

        If multiple files have the same name, returns the first match.
        """
        # Escape single quotes in name for the query
        escaped_name = name.replace("'", "\\'")
        query = f"name='{escaped_name}' and '{parent_id}' in parents and trashed=false"

        try:
            kwargs = {
                "q": query,
                "fields": "files(id, name)",
                "pageSize": 1,
            }
            if self._shared_drive_id:
                kwargs["corpora"] = "drive"
                kwargs["driveId"] = self._shared_drive_id
                kwargs["includeItemsFromAllDrives"] = True
                kwargs["supportsAllDrives"] = True

            result = self._service.files().list(**kwargs).execute()
            files = result.get("files", [])

            if files:
                file_id = files[0]["id"]
                logger.debug("Resolved '%s' in %s -> %s", name, parent_id, file_id)
                return file_id

            return None

        except Exception as e:
            logger.warning("Drive API query failed for '%s': %s", name, e)
            return None

    def invalidate(self, path: str) -> None:
        """Remove a specific path from the cache."""
        path = self._normalize_path(path)
        with self._lock:
            self._cache.pop(path, None)

    def invalidate_children(self, path: str) -> None:
        """Remove all cached entries under a path (e.g., after dir mutation)."""
        path = self._normalize_path(path)
        prefix = path if path.endswith("/") else path + "/"
        with self._lock:
            to_remove = [k for k in self._cache if k.startswith(prefix) or k == path]
            for k in to_remove:
                del self._cache[k]

    def clear(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._cache.clear()

    def _normalize_path(self, path: str) -> str:
        """Ensure path has leading slash and uses forward slashes."""
        path = path.replace("\\", "/")
        if not path.startswith("/"):
            path = "/" + path
        # Remove trailing slash unless root
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path
