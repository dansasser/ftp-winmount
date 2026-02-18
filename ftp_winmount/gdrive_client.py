"""
Google Drive client implementation.

Provides the same RemoteClient interface as FTPClient and SFTPClient,
allowing the filesystem layer to mount Google Drive transparently.
"""

import io
import logging
import threading
import time
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from .config import ConnectionConfig, GoogleDriveConfig
from .ftp_client import FileStats
from .gdrive_auth import get_or_refresh_credentials
from .gdrive_path_cache import FOLDER_MIME, PathCache

logger = logging.getLogger(__name__)

# Google Workspace MIME types and their export formats
WORKSPACE_EXPORT_MAP = {
    "application/vnd.google-apps.document": {
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "ext": ".docx",
    },
    "application/vnd.google-apps.spreadsheet": {
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ext": ".xlsx",
    },
    "application/vnd.google-apps.presentation": {
        "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ext": ".pptx",
    },
    "application/vnd.google-apps.drawing": {
        "mime": "application/pdf",
        "ext": ".pdf",
    },
}

# All Google Workspace MIME types (including ones we don't export)
WORKSPACE_MIMES = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.drawing",
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.map",
    "application/vnd.google-apps.site",
    "application/vnd.google-apps.jam",
    "application/vnd.google-apps.script",
}

# Fields to request from the Drive API for file metadata
FILE_FIELDS = "id, name, mimeType, size, modifiedTime, trashed"
LIST_FIELDS = f"nextPageToken, files({FILE_FIELDS})"


class GoogleDriveClient:
    """
    Google Drive client implementing the RemoteClient interface.

    Mounts Google Drive (or a specific folder / shared drive) as a
    filesystem using the Drive API v3.
    """

    def __init__(self, gdrive_config: GoogleDriveConfig, conn_config: ConnectionConfig):
        self.gdrive_config = gdrive_config
        self.conn_config = conn_config
        self._service = None
        self._path_cache: PathCache | None = None
        self._lock = threading.Lock()
        self._connected = False

    def connect(self) -> None:
        """Authenticate and build the Drive API service."""
        with self._lock:
            try:
                creds = get_or_refresh_credentials(
                    client_secrets_file=self.gdrive_config.client_secrets_file,
                    token_file=self.gdrive_config.token_file,
                )

                self._service = build("drive", "v3", credentials=creds)
                self._path_cache = PathCache(
                    self._service,
                    ttl_seconds=120,  # Longer TTL for cloud API
                    shared_drive_id=self._resolve_shared_drive(),
                )
                self._connected = True
                logger.info("Connected to Google Drive")

            except ValueError as e:
                raise ValueError(str(e)) from e
            except Exception as e:
                logger.error("Failed to connect to Google Drive: %s", e)
                raise ConnectionError(f"Google Drive connection failed: {e}") from e

    def _resolve_shared_drive(self) -> str | None:
        """Resolve shared drive name to ID if configured."""
        sd = self.gdrive_config.shared_drive
        if not sd:
            return None

        # If it looks like a Drive ID already, use it directly
        if len(sd) > 20 and " " not in sd:
            return sd

        # Search by name
        try:
            result = (
                self._service.drives()
                .list(
                    q=f"name='{sd}'",
                    pageSize=1,
                )
                .execute()
            )
            drives = result.get("drives", [])
            if drives:
                drive_id = drives[0]["id"]
                logger.info("Resolved shared drive '%s' -> %s", sd, drive_id)
                return drive_id

            raise ValueError(f"Shared drive not found: {sd}")
        except HttpError as e:
            raise ConnectionError(f"Failed to list shared drives: {e}") from e

    def disconnect(self) -> None:
        """Close the Drive API connection."""
        with self._lock:
            self._service = None
            if self._path_cache:
                self._path_cache.clear()
                self._path_cache = None
            self._connected = False
            logger.debug("Google Drive connection closed")

    def _with_retry(self, operation: str, func, *args, **kwargs):
        """Execute with retry logic and exponential backoff for rate limits."""
        last_exception = None

        for attempt in range(self.conn_config.retry_attempts):
            try:
                with self._lock:
                    return func(*args, **kwargs)
            except FileNotFoundError:
                raise
            except PermissionError:
                raise
            except HttpError as e:
                if e.resp.status == 404:
                    raise FileNotFoundError(f"Not found: {operation}") from e
                if e.resp.status == 403:
                    raise PermissionError(f"Access denied: {operation}") from e
                if e.resp.status == 429:
                    # Rate limited -- backoff
                    delay = (2**attempt) * self.conn_config.retry_delay_seconds
                    logger.warning(
                        "%s rate limited (attempt %d/%d), waiting %ds",
                        operation,
                        attempt + 1,
                        self.conn_config.retry_attempts,
                        delay,
                    )
                    time.sleep(delay)
                    last_exception = e
                    continue

                last_exception = e
                logger.warning(
                    "%s failed (attempt %d/%d): HTTP %d %s",
                    operation,
                    attempt + 1,
                    self.conn_config.retry_attempts,
                    e.resp.status,
                    e,
                )
            except Exception as e:
                last_exception = e
                logger.warning(
                    "%s failed (attempt %d/%d): %s",
                    operation,
                    attempt + 1,
                    self.conn_config.retry_attempts,
                    e,
                )

            if attempt < self.conn_config.retry_attempts - 1:
                time.sleep(self.conn_config.retry_delay_seconds)

        logger.error("%s failed after %d attempts", operation, self.conn_config.retry_attempts)
        raise OSError(f"{operation} failed: {last_exception}") from last_exception

    # Build reverse map: synthetic extension -> original Workspace MIME
    _EXPORT_EXTENSIONS = {v["ext"] for v in WORKSPACE_EXPORT_MAP.values()}

    def _strip_workspace_extension(self, name: str) -> str | None:
        """Strip a synthetic Workspace export extension from a filename.

        Returns the original Drive name (without the extension) if the name
        ends with a known export extension, or ``None`` if no stripping was
        needed.
        """
        for ext in self._EXPORT_EXTENSIONS:
            if name.endswith(ext):
                return name[: -len(ext)]
        return None

    def _resolve_path(self, path: str) -> str:
        """Resolve a filesystem path to a Drive file ID. Raises FileNotFoundError.

        Workspace files are listed with synthetic extensions (e.g. ``.docx``),
        but Drive stores them under their original name. If a direct lookup
        fails and the final path component carries a known export extension,
        the extension is stripped and the lookup is retried so that display
        names produced by ``list_dir`` resolve correctly.
        """
        # Use configured root folder ID for root path
        path = path.replace("\\", "/")
        if not path.startswith("/"):
            path = "/" + path

        if path == "/":
            # Honour the shared-drive root when one is configured.
            # PathCache._root_id is set to the resolved shared-drive ID
            # (or "root" when no shared drive is in use), which is the
            # correct parent for root-level operations.
            if self._path_cache is not None:
                return self._path_cache._root_id
            return self.gdrive_config.root_folder_id

        file_id = self._path_cache.resolve(path)
        if file_id is not None:
            return file_id

        # Retry with the synthetic export extension stripped
        basename = path.rsplit("/", 1)[-1]
        original_name = self._strip_workspace_extension(basename)
        if original_name:
            parent = path.rsplit("/", 1)[0] or "/"
            stripped_path = parent + "/" + original_name if parent != "/" else "/" + original_name
            file_id = self._path_cache.resolve(stripped_path)
            if file_id is not None:
                return file_id

        raise FileNotFoundError(f"No such file or directory: {path}")

    def _get_metadata(self, file_id: str) -> dict:
        """Get file metadata from Drive API."""
        kwargs = {"fileId": file_id, "fields": FILE_FIELDS}
        if self.gdrive_config.shared_drive:
            kwargs["supportsAllDrives"] = True
        return self._service.files().get(**kwargs).execute()

    def _parse_file_stats(self, meta: dict) -> FileStats:
        """Convert Drive API metadata to FileStats."""
        mime = meta.get("mimeType", "")
        is_dir = mime == FOLDER_MIME
        name = meta.get("name", "")

        # Append export extension for Workspace files
        if mime in WORKSPACE_EXPORT_MAP:
            export_info = WORKSPACE_EXPORT_MAP[mime]
            if not name.endswith(export_info["ext"]):
                name = name + export_info["ext"]

        size = int(meta.get("size", 0)) if not is_dir else 0
        # Workspace files have no size -- estimate 0 until exported
        if mime in WORKSPACE_MIMES:
            size = 0

        mtime_str = meta.get("modifiedTime", "")
        if mtime_str:
            # Drive API returns RFC 3339: "2024-06-15T10:30:00.000Z"
            mtime = datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
        else:
            mtime = datetime.now()

        return FileStats(name=name, size=size, mtime=mtime, is_dir=is_dir)

    def list_dir(self, path: str) -> list[FileStats]:
        """List contents of a directory."""
        logger.debug("Listing directory: %s", path)

        def _list_dir_internal() -> list[FileStats]:
            folder_id = self._resolve_path(path)

            query = f"'{folder_id}' in parents and trashed=false"
            results = []
            page_token = None

            while True:
                kwargs = {
                    "q": query,
                    "fields": LIST_FIELDS,
                    "pageSize": 1000,
                    "orderBy": "name",
                }
                if page_token:
                    kwargs["pageToken"] = page_token
                if self.gdrive_config.shared_drive:
                    kwargs["corpora"] = "drive"
                    kwargs["driveId"] = self._path_cache._shared_drive_id
                    kwargs["includeItemsFromAllDrives"] = True
                    kwargs["supportsAllDrives"] = True

                response = self._service.files().list(**kwargs).execute()

                for meta in response.get("files", []):
                    mime = meta.get("mimeType", "")
                    # Skip Workspace files that we can't export
                    if mime in WORKSPACE_MIMES and mime not in WORKSPACE_EXPORT_MAP:
                        continue

                    results.append(self._parse_file_stats(meta))

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            logger.debug("Listed %d entries in %s", len(results), path)
            return results

        return self._with_retry(f"list_dir({path})", _list_dir_internal)

    def get_file_info(self, path: str) -> FileStats:
        """Get metadata for a single file or directory."""
        logger.debug("Getting file info: %s", path)

        def _get_file_info_internal() -> FileStats:
            file_id = self._resolve_path(path)
            meta = self._get_metadata(file_id)
            return self._parse_file_stats(meta)

        return self._with_retry(f"get_file_info({path})", _get_file_info_internal)

    def read_file(self, path: str, offset: int = 0, length: int | None = None) -> bytes:
        """Read bytes from a file."""
        logger.debug("Reading file: %s (offset=%d, length=%s)", path, offset, length)

        def _read_file_internal() -> bytes:
            file_id = self._resolve_path(path)
            meta = self._get_metadata(file_id)
            mime = meta.get("mimeType", "")

            # Workspace files need export
            if mime in WORKSPACE_EXPORT_MAP:
                export_mime = WORKSPACE_EXPORT_MAP[mime]["mime"]
                request = self._service.files().export_media(fileId=file_id, mimeType=export_mime)
            else:
                kwargs = {"fileId": file_id}
                if self.gdrive_config.shared_drive:
                    kwargs["supportsAllDrives"] = True
                request = self._service.files().get_media(**kwargs)

            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            data = buffer.getvalue()

            # Apply offset and length
            if offset > 0:
                data = data[offset:]
            if length is not None:
                data = data[:length]

            logger.debug("Read %d bytes from %s", len(data), path)
            return data

        return self._with_retry(f"read_file({path})", _read_file_internal)

    def write_file(self, path: str, data: bytes, offset: int = 0) -> int:
        """Write bytes to a file."""
        logger.debug("Writing file: %s (%d bytes at offset %d)", path, len(data), offset)

        def _write_file_internal() -> int:
            file_id = self._resolve_path(path)
            meta = self._get_metadata(file_id)
            mime = meta.get("mimeType", "")

            # Cannot write to Workspace files
            if mime in WORKSPACE_MIMES:
                raise PermissionError(f"Cannot write to Google Workspace file: {path}")

            if offset > 0:
                # Read-modify-write for offset writes
                kwargs = {"fileId": file_id}
                if self.gdrive_config.shared_drive:
                    kwargs["supportsAllDrives"] = True
                request = self._service.files().get_media(**kwargs)
                buf = io.BytesIO()
                dl = MediaIoBaseDownload(buf, request)
                done = False
                while not done:
                    _, done = dl.next_chunk()
                existing = buf.getvalue()

                # Splice in the new data at offset
                new_data = existing[:offset] + data + existing[offset + len(data) :]
            else:
                new_data = data

            media = MediaIoBaseUpload(
                io.BytesIO(new_data),
                mimetype="application/octet-stream",
                resumable=len(new_data) > 5 * 1024 * 1024,
            )

            kwargs = {"fileId": file_id, "media_body": media}
            if self.gdrive_config.shared_drive:
                kwargs["supportsAllDrives"] = True
            self._service.files().update(**kwargs).execute()

            # Invalidate cache for parent dir
            parent_path = path.rsplit("/", 1)[0] or "/"
            self._path_cache.invalidate_children(parent_path)

            logger.debug("Wrote %d bytes to %s", len(data), path)
            return len(data)

        return self._with_retry(f"write_file({path})", _write_file_internal)

    def create_file(self, path: str) -> None:
        """Create an empty file."""
        logger.debug("Creating file: %s", path)

        def _create_file_internal() -> None:
            path_normalized = path.replace("\\", "/")
            if not path_normalized.startswith("/"):
                path_normalized = "/" + path_normalized

            parent_path = path_normalized.rsplit("/", 1)[0] or "/"
            file_name = path_normalized.rsplit("/", 1)[-1]

            parent_id = self._resolve_path(parent_path)

            file_metadata = {
                "name": file_name,
                "parents": [parent_id],
            }

            kwargs = {"body": file_metadata, "fields": "id"}
            if self.gdrive_config.shared_drive:
                kwargs["supportsAllDrives"] = True
            self._service.files().create(**kwargs).execute()

            # Invalidate parent cache
            self._path_cache.invalidate_children(parent_path)
            logger.debug("Created file: %s", path)

        self._with_retry(f"create_file({path})", _create_file_internal)

    def create_dir(self, path: str) -> None:
        """Create a directory."""
        logger.debug("Creating directory: %s", path)

        def _create_dir_internal() -> None:
            path_normalized = path.replace("\\", "/")
            if not path_normalized.startswith("/"):
                path_normalized = "/" + path_normalized

            parent_path = path_normalized.rsplit("/", 1)[0] or "/"
            dir_name = path_normalized.rsplit("/", 1)[-1]

            parent_id = self._resolve_path(parent_path)

            file_metadata = {
                "name": dir_name,
                "mimeType": FOLDER_MIME,
                "parents": [parent_id],
            }

            kwargs = {"body": file_metadata, "fields": "id"}
            if self.gdrive_config.shared_drive:
                kwargs["supportsAllDrives"] = True
            self._service.files().create(**kwargs).execute()

            # Invalidate parent cache
            self._path_cache.invalidate_children(parent_path)
            logger.debug("Created directory: %s", path)

        self._with_retry(f"create_dir({path})", _create_dir_internal)

    def delete_file(self, path: str) -> None:
        """Move a file to trash."""
        logger.debug("Trashing file: %s", path)

        def _delete_file_internal() -> None:
            file_id = self._resolve_path(path)

            kwargs = {
                "fileId": file_id,
                "body": {"trashed": True},
            }
            if self.gdrive_config.shared_drive:
                kwargs["supportsAllDrives"] = True
            self._service.files().update(**kwargs).execute()

            # Invalidate caches
            self._path_cache.invalidate(path)
            parent_path = path.rsplit("/", 1)[0] or "/"
            self._path_cache.invalidate_children(parent_path)
            logger.debug("Trashed file: %s", path)

        self._with_retry(f"delete_file({path})", _delete_file_internal)

    def delete_dir(self, path: str) -> None:
        """Move a directory to trash."""
        logger.debug("Trashing directory: %s", path)

        def _delete_dir_internal() -> None:
            file_id = self._resolve_path(path)

            kwargs = {
                "fileId": file_id,
                "body": {"trashed": True},
            }
            if self.gdrive_config.shared_drive:
                kwargs["supportsAllDrives"] = True
            self._service.files().update(**kwargs).execute()

            # Invalidate caches
            self._path_cache.invalidate_children(path)
            parent_path = path.rsplit("/", 1)[0] or "/"
            self._path_cache.invalidate_children(parent_path)
            logger.debug("Trashed directory: %s", path)

        self._with_retry(f"delete_dir({path})", _delete_dir_internal)

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename or move a file/directory."""
        logger.debug("Renaming: %s -> %s", old_path, new_path)

        def _rename_internal() -> None:
            file_id = self._resolve_path(old_path)

            old_normalized = old_path.replace("\\", "/")
            new_normalized = new_path.replace("\\", "/")
            if not old_normalized.startswith("/"):
                old_normalized = "/" + old_normalized
            if not new_normalized.startswith("/"):
                new_normalized = "/" + new_normalized

            old_parent = old_normalized.rsplit("/", 1)[0] or "/"
            new_parent = new_normalized.rsplit("/", 1)[0] or "/"
            new_name = new_normalized.rsplit("/", 1)[-1]

            kwargs = {
                "fileId": file_id,
                "body": {"name": new_name},
                "fields": "id, parents",
            }
            if self.gdrive_config.shared_drive:
                kwargs["supportsAllDrives"] = True

            # If parent directory changed, move the file
            if old_parent != new_parent:
                old_parent_id = self._resolve_path(old_parent)
                new_parent_id = self._resolve_path(new_parent)
                kwargs["addParents"] = new_parent_id
                kwargs["removeParents"] = old_parent_id

            self._service.files().update(**kwargs).execute()

            # Invalidate caches
            self._path_cache.invalidate(old_path)
            self._path_cache.invalidate_children(old_parent)
            if old_parent != new_parent:
                self._path_cache.invalidate_children(new_parent)

            logger.debug("Renamed: %s -> %s", old_path, new_path)

        self._with_retry(f"rename({old_path}, {new_path})", _rename_internal)
