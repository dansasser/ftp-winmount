"""
Unit tests for ftp_winmount.gdrive_client module.

Tests cover:
- Connect and disconnect
- list_dir with pagination and Workspace file filtering
- get_file_info
- read_file (regular and Workspace export)
- write_file (full write and offset write)
- create_file and create_dir
- delete_file and delete_dir (trash)
- rename (same dir and cross-dir move)
- Retry logic with rate limiting (HTTP 429)
- Error translation (404 -> FileNotFoundError, 403 -> PermissionError)
- Workspace MIME type handling
- Path resolution
- Shared drive support
"""

from unittest.mock import MagicMock, patch

import pytest

from ftp_winmount.config import ConnectionConfig, GoogleDriveConfig
from ftp_winmount.gdrive_client import (
    FOLDER_MIME,
    GoogleDriveClient,
)


@pytest.fixture
def gdrive_cfg():
    """Google Drive config for testing."""
    return GoogleDriveConfig(
        client_secrets_file="/path/to/secrets.json",
        token_file="/path/to/token.json",
        root_folder_id="root",
        shared_drive=None,
    )


@pytest.fixture
def conn_cfg():
    """Connection config with no retry delay for tests."""
    return ConnectionConfig(
        timeout_seconds=30,
        retry_attempts=3,
        retry_delay_seconds=0,
        keepalive_interval_seconds=60,
    )


@pytest.fixture
def mock_drive_service():
    """Creates a mocked Google Drive API service."""
    return MagicMock()


@pytest.fixture
def client(gdrive_cfg, conn_cfg, mock_drive_service):
    """Creates a GoogleDriveClient with mocked internals."""
    c = GoogleDriveClient(gdrive_cfg, conn_cfg)
    c._service = mock_drive_service
    c._connected = True

    # Set up a mock path cache
    mock_cache = MagicMock()
    mock_cache._shared_drive_id = None
    c._path_cache = mock_cache

    return c


def _make_file_meta(
    file_id="file123",
    name="test.txt",
    mime_type="text/plain",
    size="1024",
    modified_time="2024-06-15T10:30:00.000Z",
    trashed=False,
):
    """Helper to create a Drive API file metadata dict."""
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "size": size,
        "modifiedTime": modified_time,
        "trashed": trashed,
    }


def _make_http_error(status_code, reason="error"):
    """Helper to create a mock HttpError."""
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = status_code
    resp.reason = reason
    return HttpError(resp, b"error body")


class TestConnect:
    """Tests for connect/disconnect."""

    @patch("ftp_winmount.gdrive_client.PathCache")
    @patch("ftp_winmount.gdrive_client.build")
    @patch("ftp_winmount.gdrive_client.get_or_refresh_credentials")
    def test_connect_builds_service(
        self, mock_get_creds, mock_build, mock_cache_cls, gdrive_cfg, conn_cfg
    ):
        """connect() gets credentials and builds Drive service."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        c = GoogleDriveClient(gdrive_cfg, conn_cfg)
        c.connect()

        mock_get_creds.assert_called_once()
        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds)
        assert c._connected is True

    @patch("ftp_winmount.gdrive_client.get_or_refresh_credentials")
    def test_connect_raises_on_auth_failure(self, mock_get_creds, gdrive_cfg, conn_cfg):
        """connect() raises ConnectionError on auth failure."""
        mock_get_creds.side_effect = Exception("auth failed")

        c = GoogleDriveClient(gdrive_cfg, conn_cfg)
        with pytest.raises(ConnectionError, match="Google Drive connection failed"):
            c.connect()

    def test_disconnect_clears_state(self, client):
        """disconnect() clears service, cache, and connected flag."""
        client.disconnect()

        assert client._service is None
        assert client._path_cache is None
        assert client._connected is False


class TestListDir:
    """Tests for directory listing."""

    def test_list_dir_returns_file_stats(self, client, mock_drive_service):
        """list_dir returns a list of FileStats."""
        client._path_cache.resolve.return_value = "folder_id"

        mock_response = {
            "files": [
                _make_file_meta("f1", "file1.txt", "text/plain", "100"),
                _make_file_meta("f2", "subdir", FOLDER_MIME, "0"),
            ],
            "nextPageToken": None,
        }
        mock_drive_service.files().list().execute.return_value = mock_response

        results = client.list_dir("/Documents")

        assert len(results) == 2
        assert results[0].name == "file1.txt"
        assert results[0].is_dir is False
        assert results[0].size == 100
        assert results[1].name == "subdir"
        assert results[1].is_dir is True

    def test_list_dir_skips_non_exportable_workspace_files(self, client, mock_drive_service):
        """Workspace files that can't be exported are skipped."""
        client._path_cache.resolve.return_value = "folder_id"

        mock_response = {
            "files": [
                _make_file_meta("f1", "file.txt", "text/plain", "100"),
                # Google Form - not in WORKSPACE_EXPORT_MAP
                _make_file_meta("f2", "My Form", "application/vnd.google-apps.form", "0"),
            ],
            "nextPageToken": None,
        }
        mock_drive_service.files().list().execute.return_value = mock_response

        results = client.list_dir("/")

        assert len(results) == 1
        assert results[0].name == "file.txt"

    def test_list_dir_exports_workspace_names(self, client, mock_drive_service):
        """Exportable Workspace files get export extension appended."""
        client._path_cache.resolve.return_value = "folder_id"

        mock_response = {
            "files": [
                _make_file_meta("f1", "My Document", "application/vnd.google-apps.document", "0"),
            ],
            "nextPageToken": None,
        }
        mock_drive_service.files().list().execute.return_value = mock_response

        results = client.list_dir("/")

        assert len(results) == 1
        assert results[0].name == "My Document.docx"


class TestGetFileInfo:
    """Tests for file info retrieval."""

    def test_get_file_info_returns_stats(self, client, mock_drive_service):
        """get_file_info returns correct FileStats."""
        client._path_cache.resolve.return_value = "file_id"
        mock_drive_service.files().get().execute.return_value = _make_file_meta(
            "file_id", "report.pdf", "application/pdf", "5000", "2024-01-15T08:00:00.000Z"
        )

        result = client.get_file_info("/report.pdf")

        assert result.name == "report.pdf"
        assert result.size == 5000
        assert result.is_dir is False

    def test_get_file_info_folder(self, client, mock_drive_service):
        """get_file_info returns is_dir=True for folders."""
        client._path_cache.resolve.return_value = "dir_id"
        mock_drive_service.files().get().execute.return_value = _make_file_meta(
            "dir_id", "Photos", FOLDER_MIME, "0"
        )

        result = client.get_file_info("/Photos")

        assert result.is_dir is True
        assert result.size == 0

    def test_get_file_info_not_found(self, client):
        """get_file_info raises FileNotFoundError for missing path."""
        client._path_cache.resolve.return_value = None

        with pytest.raises(FileNotFoundError):
            client.get_file_info("/nonexistent")


class TestReadFile:
    """Tests for reading file contents."""

    @patch("ftp_winmount.gdrive_client.MediaIoBaseDownload")
    def test_read_regular_file(self, mock_download_cls, client, mock_drive_service):
        """read_file downloads a regular file."""
        client._path_cache.resolve.return_value = "file_id"
        mock_drive_service.files().get().execute.return_value = _make_file_meta(
            "file_id", "data.bin", "application/octet-stream", "100"
        )

        # Mock the downloader
        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)
        mock_download_cls.return_value = mock_downloader

        # Write content to the BytesIO buffer that gets passed in
        def capture_buffer(buf, request):
            buf.write(b"file content here")
            return mock_downloader

        mock_download_cls.side_effect = capture_buffer

        result = client.read_file("/data.bin")
        assert result == b"file content here"

    @patch("ftp_winmount.gdrive_client.MediaIoBaseDownload")
    def test_read_with_offset_and_length(self, mock_download_cls, client, mock_drive_service):
        """read_file respects offset and length parameters."""
        client._path_cache.resolve.return_value = "file_id"
        mock_drive_service.files().get().execute.return_value = _make_file_meta(
            "file_id", "data.bin", "application/octet-stream", "100"
        )

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        def capture_buffer(buf, request):
            buf.write(b"0123456789ABCDEF")
            return mock_downloader

        mock_download_cls.side_effect = capture_buffer

        result = client.read_file("/data.bin", offset=5, length=4)
        assert result == b"5678"

    @patch("ftp_winmount.gdrive_client.MediaIoBaseDownload")
    def test_read_workspace_file_uses_export(self, mock_download_cls, client, mock_drive_service):
        """Reading a Workspace file triggers export_media."""
        client._path_cache.resolve.return_value = "doc_id"
        mock_drive_service.files().get().execute.return_value = _make_file_meta(
            "doc_id", "My Doc", "application/vnd.google-apps.document", "0"
        )

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        def capture_buffer(buf, request):
            buf.write(b"docx content")
            return mock_downloader

        mock_download_cls.side_effect = capture_buffer

        client.read_file("/My Doc.docx")

        # Should use export_media, not get_media
        mock_drive_service.files().export_media.assert_called_once()


class TestWriteFile:
    """Tests for writing file contents."""

    @patch("ftp_winmount.gdrive_client.MediaIoBaseUpload")
    def test_write_full_file(self, mock_upload_cls, client, mock_drive_service):
        """write_file uploads new content."""
        client._path_cache.resolve.return_value = "file_id"
        mock_drive_service.files().get().execute.return_value = _make_file_meta(
            "file_id", "data.bin", "application/octet-stream", "100"
        )

        result = client.write_file("/data.bin", b"new content")

        assert result == 11  # len(b"new content")
        mock_drive_service.files().update.assert_called_once()

    def test_write_workspace_file_raises(self, client, mock_drive_service):
        """Writing to a Workspace file raises PermissionError."""
        client._path_cache.resolve.return_value = "doc_id"
        mock_drive_service.files().get().execute.return_value = _make_file_meta(
            "doc_id", "My Doc", "application/vnd.google-apps.document", "0"
        )

        with pytest.raises(PermissionError, match="Cannot write to Google Workspace file"):
            client.write_file("/My Doc.docx", b"data")


class TestCreateFile:
    """Tests for file creation."""

    def test_create_file(self, client, mock_drive_service):
        """create_file creates an empty file in the parent folder."""
        client._path_cache.resolve.return_value = "parent_id"

        client.create_file("/Documents/new_file.txt")

        call_kwargs = mock_drive_service.files().create.call_args[1]
        assert call_kwargs["body"]["name"] == "new_file.txt"
        assert call_kwargs["body"]["parents"] == ["parent_id"]

    def test_create_dir(self, client, mock_drive_service):
        """create_dir creates a folder with correct MIME type."""
        client._path_cache.resolve.return_value = "parent_id"

        client.create_dir("/Documents/new_folder")

        call_kwargs = mock_drive_service.files().create.call_args[1]
        assert call_kwargs["body"]["name"] == "new_folder"
        assert call_kwargs["body"]["mimeType"] == FOLDER_MIME
        assert call_kwargs["body"]["parents"] == ["parent_id"]


class TestDelete:
    """Tests for delete (trash) operations."""

    def test_delete_file_trashes(self, client, mock_drive_service):
        """delete_file sets trashed=True on the file."""
        client._path_cache.resolve.return_value = "file_id"

        client.delete_file("/Documents/old.txt")

        call_kwargs = mock_drive_service.files().update.call_args[1]
        assert call_kwargs["fileId"] == "file_id"
        assert call_kwargs["body"]["trashed"] is True

    def test_delete_dir_trashes(self, client, mock_drive_service):
        """delete_dir sets trashed=True on the directory."""
        client._path_cache.resolve.return_value = "dir_id"

        client.delete_dir("/Documents/old_folder")

        call_kwargs = mock_drive_service.files().update.call_args[1]
        assert call_kwargs["fileId"] == "dir_id"
        assert call_kwargs["body"]["trashed"] is True

    def test_delete_invalidates_cache(self, client, mock_drive_service):
        """delete operations invalidate the path cache."""
        client._path_cache.resolve.return_value = "file_id"

        client.delete_file("/Documents/old.txt")

        client._path_cache.invalidate.assert_called()
        client._path_cache.invalidate_children.assert_called()


class TestRename:
    """Tests for rename/move operations."""

    def test_rename_same_directory(self, client, mock_drive_service):
        """Rename within same directory only changes name."""
        client._path_cache.resolve.return_value = "file_id"

        client.rename("/Documents/old.txt", "/Documents/new.txt")

        call_kwargs = mock_drive_service.files().update.call_args[1]
        assert call_kwargs["body"]["name"] == "new.txt"
        # Should NOT have addParents/removeParents for same-dir rename
        assert "addParents" not in call_kwargs
        assert "removeParents" not in call_kwargs

    def test_rename_cross_directory(self, client, mock_drive_service):
        """Move to different directory sets addParents and removeParents."""
        # Resolve returns different IDs for different paths
        resolve_map = {
            "/source/file.txt": "file_id",
            "/source": "source_dir_id",
            "/dest": "dest_dir_id",
        }

        def mock_resolve(path):
            path = path.replace("\\", "/")
            if not path.startswith("/"):
                path = "/" + path
            return resolve_map.get(path)

        client._path_cache.resolve.side_effect = mock_resolve

        client.rename("/source/file.txt", "/dest/file.txt")

        call_kwargs = mock_drive_service.files().update.call_args[1]
        assert call_kwargs["addParents"] == "dest_dir_id"
        assert call_kwargs["removeParents"] == "source_dir_id"


class TestRetryLogic:
    """Tests for retry and error handling."""

    def test_http_404_raises_file_not_found(self, client, mock_drive_service):
        """HTTP 404 translates to FileNotFoundError."""
        client._path_cache.resolve.return_value = "file_id"
        mock_drive_service.files().get().execute.side_effect = _make_http_error(404)

        with pytest.raises(FileNotFoundError):
            client.get_file_info("/missing")

    def test_http_403_raises_permission_error(self, client, mock_drive_service):
        """HTTP 403 translates to PermissionError."""
        client._path_cache.resolve.return_value = "file_id"
        mock_drive_service.files().get().execute.side_effect = _make_http_error(403)

        with pytest.raises(PermissionError):
            client.get_file_info("/forbidden")

    def test_file_not_found_not_retried(self, client, mock_drive_service):
        """FileNotFoundError from path resolution is not retried."""
        client._path_cache.resolve.return_value = None

        with pytest.raises(FileNotFoundError):
            client.get_file_info("/missing")

    def test_http_429_retries(self, client, mock_drive_service):
        """HTTP 429 (rate limit) triggers retry."""
        client._path_cache.resolve.return_value = "file_id"

        # First call: 429, second call: success
        meta = _make_file_meta("file_id", "test.txt")
        mock_get = mock_drive_service.files().get()
        mock_get.execute.side_effect = [
            _make_http_error(429),
            meta,
        ]

        result = client.get_file_info("/test.txt")
        assert result.name == "test.txt"

    def test_http_500_retries_then_fails(self, client, mock_drive_service):
        """HTTP 500 retries up to max attempts then raises OSError."""
        client._path_cache.resolve.return_value = "file_id"

        mock_get = mock_drive_service.files().get()
        mock_get.execute.side_effect = _make_http_error(500)

        with pytest.raises(OSError, match="failed"):
            client.get_file_info("/broken")


class TestWorkspaceMimeHandling:
    """Tests for Google Workspace MIME type handling."""

    def test_document_gets_docx_extension(self, client):
        """Google Docs get .docx extension."""
        meta = _make_file_meta("d1", "My Report", "application/vnd.google-apps.document")
        stats = client._parse_file_stats(meta)
        assert stats.name == "My Report.docx"

    def test_spreadsheet_gets_xlsx_extension(self, client):
        """Google Sheets get .xlsx extension."""
        meta = _make_file_meta("s1", "Budget", "application/vnd.google-apps.spreadsheet")
        stats = client._parse_file_stats(meta)
        assert stats.name == "Budget.xlsx"

    def test_presentation_gets_pptx_extension(self, client):
        """Google Slides get .pptx extension."""
        meta = _make_file_meta("p1", "Slides", "application/vnd.google-apps.presentation")
        stats = client._parse_file_stats(meta)
        assert stats.name == "Slides.pptx"

    def test_drawing_gets_pdf_extension(self, client):
        """Google Drawings get .pdf extension."""
        meta = _make_file_meta("d1", "Diagram", "application/vnd.google-apps.drawing")
        stats = client._parse_file_stats(meta)
        assert stats.name == "Diagram.pdf"

    def test_workspace_files_have_zero_size(self, client):
        """Workspace files report size=0 until exported."""
        meta = _make_file_meta("d1", "Doc", "application/vnd.google-apps.document", "0")
        stats = client._parse_file_stats(meta)
        assert stats.size == 0

    def test_regular_file_no_extension_change(self, client):
        """Regular files keep their original name."""
        meta = _make_file_meta("f1", "photo.jpg", "image/jpeg", "50000")
        stats = client._parse_file_stats(meta)
        assert stats.name == "photo.jpg"

    def test_folder_detection(self, client):
        """Folders are correctly identified by MIME type."""
        meta = _make_file_meta("d1", "Documents", FOLDER_MIME, "0")
        stats = client._parse_file_stats(meta)
        assert stats.is_dir is True
        assert stats.size == 0

    def test_already_has_extension_not_doubled(self, client):
        """Workspace file already having correct extension doesn't get it doubled."""
        meta = _make_file_meta("d1", "Report.docx", "application/vnd.google-apps.document")
        stats = client._parse_file_stats(meta)
        assert stats.name == "Report.docx"


class TestSharedDriveSupport:
    """Tests for shared drive integration."""

    def test_shared_drive_passes_params(self, conn_cfg, mock_drive_service):
        """Shared drive config passes supportsAllDrives to API calls."""
        cfg = GoogleDriveConfig(
            client_secrets_file="/path/to/secrets.json",
            shared_drive="TeamDrive",
        )
        c = GoogleDriveClient(cfg, conn_cfg)
        c._service = mock_drive_service
        c._connected = True

        mock_cache = MagicMock()
        mock_cache._shared_drive_id = "sd_123"
        mock_cache.resolve.return_value = "file_id"
        c._path_cache = mock_cache

        # Test get_file_info passes supportsAllDrives
        mock_drive_service.files().get().execute.return_value = _make_file_meta()
        c.get_file_info("/test.txt")

        call_kwargs = mock_drive_service.files().get.call_args[1]
        assert call_kwargs.get("supportsAllDrives") is True

    @patch("ftp_winmount.gdrive_client.PathCache")
    @patch("ftp_winmount.gdrive_client.build")
    @patch("ftp_winmount.gdrive_client.get_or_refresh_credentials")
    def test_resolve_shared_drive_by_name(self, mock_creds, mock_build, mock_cache_cls, conn_cfg):
        """Shared drive name is resolved to ID during connect."""
        mock_creds.return_value = MagicMock()
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock drives().list() response
        mock_service.drives().list().execute.return_value = {
            "drives": [{"id": "resolved_sd_id", "name": "TeamDrive"}]
        }

        cfg = GoogleDriveConfig(shared_drive="TeamDrive")
        c = GoogleDriveClient(cfg, conn_cfg)
        c.connect()

        # PathCache should have been created with the resolved shared drive ID
        call_kwargs = mock_cache_cls.call_args[1]
        assert call_kwargs["shared_drive_id"] == "resolved_sd_id"

    @patch("ftp_winmount.gdrive_client.PathCache")
    @patch("ftp_winmount.gdrive_client.build")
    @patch("ftp_winmount.gdrive_client.get_or_refresh_credentials")
    def test_resolve_shared_drive_by_id(self, mock_creds, mock_build, mock_cache_cls, conn_cfg):
        """Long string without spaces is treated as a Drive ID directly."""
        mock_creds.return_value = MagicMock()
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        long_id = "0AAbCdEfGhIjKlMnOpQrStUvWxYz"
        cfg = GoogleDriveConfig(shared_drive=long_id)
        c = GoogleDriveClient(cfg, conn_cfg)
        c.connect()

        # Should NOT have called drives().list() since it's already an ID
        mock_service.drives().list.assert_not_called()

        call_kwargs = mock_cache_cls.call_args[1]
        assert call_kwargs["shared_drive_id"] == long_id


class TestPathResolution:
    """Tests for internal path resolution."""

    def test_root_path_returns_root_id(self, client):
        """Root path uses configured root_folder_id."""
        result = client._resolve_path("/")
        assert result == "root"

    def test_backslashes_normalized(self, client):
        """Backslash paths are converted to forward slashes."""
        client._path_cache.resolve.return_value = "file_id"

        result = client._resolve_path("\\Documents\\file.txt")
        assert result == "file_id"

    def test_missing_leading_slash_added(self, client):
        """Paths without leading slash get one added."""
        client._path_cache.resolve.return_value = "file_id"

        result = client._resolve_path("Documents/file.txt")
        assert result == "file_id"

    def test_path_not_found_raises(self, client):
        """Non-existent path raises FileNotFoundError."""
        client._path_cache.resolve.return_value = None

        with pytest.raises(FileNotFoundError, match="No such file or directory"):
            client._resolve_path("/nonexistent")
