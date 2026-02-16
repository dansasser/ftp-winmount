"""
Unit tests for ftp_winmount.gdrive_auth module.

Tests cover:
- Token path resolution (default and custom)
- Credential loading from file
- Credential saving to file
- Credential refresh logic
- Auth flow execution
- get_or_refresh_credentials orchestration
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ftp_winmount.gdrive_auth import (
    DEFAULT_TOKEN_DIR,
    DEFAULT_TOKEN_FILE,
    SCOPES,
    get_or_refresh_credentials,
    get_token_path,
    load_credentials,
    refresh_credentials,
    run_auth_flow,
    save_credentials,
)


class TestGetTokenPath:
    """Tests for token path resolution."""

    def test_default_path_when_none(self):
        """Returns default token path when no custom path given."""
        result = get_token_path(None)
        assert result == DEFAULT_TOKEN_FILE

    def test_custom_path(self):
        """Returns custom path when provided."""
        result = get_token_path("/custom/token.json")
        assert result == Path("/custom/token.json")

    def test_default_path_is_in_home(self):
        """Default token path is under user home directory."""
        assert DEFAULT_TOKEN_DIR == Path.home() / ".ftp-winmount"
        assert DEFAULT_TOKEN_FILE == DEFAULT_TOKEN_DIR / "gdrive-token.json"


class TestLoadCredentials:
    """Tests for loading saved credentials."""

    def test_returns_none_when_file_missing(self, tmp_path):
        """Returns None when token file doesn't exist."""
        result = load_credentials(tmp_path / "nonexistent.json")
        assert result is None

    @patch("ftp_winmount.gdrive_auth.Credentials")
    def test_loads_from_valid_file(self, mock_creds_class, tmp_path):
        """Loads credentials from a valid token file."""
        token_path = tmp_path / "token.json"
        token_path.write_text('{"token": "test"}', encoding="utf-8")

        mock_creds = MagicMock()
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        result = load_credentials(token_path)

        assert result == mock_creds
        mock_creds_class.from_authorized_user_file.assert_called_once_with(
            str(token_path), SCOPES
        )

    def test_returns_none_on_invalid_json(self, tmp_path):
        """Returns None when token file contains invalid JSON."""
        token_path = tmp_path / "token.json"
        token_path.write_text("not json at all", encoding="utf-8")

        result = load_credentials(token_path)
        assert result is None

    @patch("ftp_winmount.gdrive_auth.Credentials")
    def test_returns_none_on_value_error(self, mock_creds_class, tmp_path):
        """Returns None when credential parsing raises ValueError."""
        token_path = tmp_path / "token.json"
        token_path.write_text('{"bad": "data"}', encoding="utf-8")
        mock_creds_class.from_authorized_user_file.side_effect = ValueError("bad creds")

        result = load_credentials(token_path)
        assert result is None


class TestSaveCredentials:
    """Tests for saving credentials to disk."""

    def test_saves_to_file(self, tmp_path):
        """Saves credential JSON to the specified path."""
        token_path = tmp_path / "subdir" / "token.json"
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "saved"}'

        save_credentials(mock_creds, token_path)

        assert token_path.exists()
        content = token_path.read_text(encoding="utf-8")
        assert content == '{"token": "saved"}'

    def test_creates_parent_directories(self, tmp_path):
        """Creates parent directories if they don't exist."""
        token_path = tmp_path / "deep" / "nested" / "token.json"
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = "{}"

        save_credentials(mock_creds, token_path)

        assert token_path.parent.exists()


class TestRefreshCredentials:
    """Tests for credential refresh logic."""

    def test_returns_none_when_no_creds(self):
        """Returns None when credentials are None."""
        assert refresh_credentials(None) is None

    def test_returns_none_when_no_refresh_token(self):
        """Returns None when credentials have no refresh token."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = None

        assert refresh_credentials(mock_creds) is None

    def test_returns_creds_if_still_valid(self):
        """Returns credentials immediately if they're still valid."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = "refresh_tok"
        mock_creds.valid = True

        result = refresh_credentials(mock_creds)
        assert result == mock_creds

    @patch("ftp_winmount.gdrive_auth.Request")
    def test_refreshes_expired_creds(self, mock_request_class):
        """Refreshes expired credentials using refresh token."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = "refresh_tok"
        mock_creds.valid = False

        # After refresh, creds become valid
        def set_valid(req):
            mock_creds.valid = True

        mock_creds.refresh.side_effect = set_valid

        result = refresh_credentials(mock_creds)
        assert result == mock_creds
        mock_creds.refresh.assert_called_once()

    @patch("ftp_winmount.gdrive_auth.Request")
    def test_returns_none_on_refresh_failure(self, mock_request_class):
        """Returns None when refresh fails."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = "refresh_tok"
        mock_creds.valid = False
        mock_creds.refresh.side_effect = Exception("network error")

        result = refresh_credentials(mock_creds)
        assert result is None


class TestRunAuthFlow:
    """Tests for the OAuth auth flow."""

    def test_raises_on_missing_secrets_file(self):
        """Raises FileNotFoundError when client_secrets.json doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Client secrets file not found"):
            run_auth_flow("/nonexistent/client_secrets.json")

    @patch("ftp_winmount.gdrive_auth.InstalledAppFlow")
    def test_runs_local_server_flow(self, mock_flow_class, tmp_path):
        """Runs InstalledAppFlow.run_local_server with correct params."""
        secrets_path = tmp_path / "client_secrets.json"
        secrets_path.write_text('{"installed": {}}', encoding="utf-8")

        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_class.from_client_secrets_file.return_value = mock_flow

        result = run_auth_flow(str(secrets_path))

        assert result == mock_creds
        mock_flow.run_local_server.assert_called_once_with(
            port=0,
            prompt="consent",
            access_type="offline",
        )

    @patch("ftp_winmount.gdrive_auth.InstalledAppFlow")
    def test_uses_correct_scopes(self, mock_flow_class, tmp_path):
        """Auth flow requests the correct Drive API scopes."""
        secrets_path = tmp_path / "client_secrets.json"
        secrets_path.write_text('{"installed": {}}', encoding="utf-8")

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = MagicMock()
        mock_flow_class.from_client_secrets_file.return_value = mock_flow

        run_auth_flow(str(secrets_path))

        call_kwargs = mock_flow_class.from_client_secrets_file.call_args
        assert call_kwargs[1]["scopes"] == SCOPES


class TestGetOrRefreshCredentials:
    """Tests for the orchestration function."""

    @patch("ftp_winmount.gdrive_auth.load_credentials")
    def test_returns_valid_saved_creds(self, mock_load):
        """Returns saved credentials when they're still valid."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_load.return_value = mock_creds

        result = get_or_refresh_credentials()
        assert result == mock_creds

    @patch("ftp_winmount.gdrive_auth.save_credentials")
    @patch("ftp_winmount.gdrive_auth.refresh_credentials")
    @patch("ftp_winmount.gdrive_auth.load_credentials")
    def test_refreshes_expired_creds(self, mock_load, mock_refresh, mock_save):
        """Refreshes expired credentials and saves them."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_tok"
        mock_load.return_value = mock_creds

        refreshed = MagicMock()
        refreshed.valid = True
        mock_refresh.return_value = refreshed

        result = get_or_refresh_credentials()
        assert result == refreshed
        mock_save.assert_called_once()

    @patch("ftp_winmount.gdrive_auth.load_credentials")
    def test_raises_when_no_saved_and_no_secrets(self, mock_load):
        """Raises ValueError when no saved credentials and no secrets file."""
        mock_load.return_value = None

        with pytest.raises(ValueError, match="No saved Google Drive credentials"):
            get_or_refresh_credentials(client_secrets_file=None)

    @patch("ftp_winmount.gdrive_auth.save_credentials")
    @patch("ftp_winmount.gdrive_auth.run_auth_flow")
    @patch("ftp_winmount.gdrive_auth.load_credentials")
    def test_runs_auth_flow_when_no_saved(self, mock_load, mock_flow, mock_save):
        """Runs full auth flow when no saved credentials exist."""
        mock_load.return_value = None
        mock_creds = MagicMock()
        mock_flow.return_value = mock_creds

        result = get_or_refresh_credentials(
            client_secrets_file="/path/to/secrets.json"
        )

        assert result == mock_creds
        mock_flow.assert_called_once_with("/path/to/secrets.json")
        mock_save.assert_called_once()
