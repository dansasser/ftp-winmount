"""
Google Drive OAuth 2.0 authentication flow.

Handles the browser-based consent flow, token storage, and refresh.
Users must provide their own client_secrets.json from Google Cloud Console.
"""

import json
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

# Full drive access (read/write/delete) + offline for refresh token
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Default token storage location
DEFAULT_TOKEN_DIR = Path.home() / ".ftp-winmount"
DEFAULT_TOKEN_FILE = DEFAULT_TOKEN_DIR / "gdrive-token.json"


def get_token_path(token_file: str | None = None) -> Path:
    """Get the token file path, using default if not specified."""
    if token_file:
        return Path(token_file)
    return DEFAULT_TOKEN_FILE


def load_credentials(token_path: Path) -> Credentials | None:
    """
    Load saved OAuth credentials from disk.

    Returns None if no saved credentials exist or they can't be loaded.
    """
    if not token_path.exists():
        logger.debug("No saved token at %s", token_path)
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        logger.debug("Loaded credentials from %s", token_path)
        return creds
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("Failed to load saved token: %s", e)
        return None


def save_credentials(creds: Credentials, token_path: Path) -> None:
    """Save OAuth credentials to disk for future use."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    logger.info("Saved credentials to %s", token_path)


def refresh_credentials(creds: Credentials) -> Credentials | None:
    """
    Refresh expired credentials using the refresh token.

    Returns refreshed credentials, or None if refresh fails.
    """
    if not creds or not creds.refresh_token:
        return None

    if creds.valid:
        return creds

    try:
        creds.refresh(Request())
        logger.debug("Refreshed access token")
        return creds
    except Exception as e:
        logger.warning("Token refresh failed: %s", e)
        return None


def run_auth_flow(client_secrets_file: str) -> Credentials:
    """
    Run the OAuth 2.0 authorization flow.

    Opens the user's browser to Google's consent page. A temporary
    local HTTP server receives the callback.

    Args:
        client_secrets_file: Path to client_secrets.json from Google Cloud Console.

    Returns:
        Authorized credentials with refresh token.

    Raises:
        FileNotFoundError: If client_secrets_file doesn't exist.
        ValueError: If client_secrets_file is invalid.
    """
    secrets_path = Path(client_secrets_file)
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"Client secrets file not found: {client_secrets_file}\n"
            "Download it from Google Cloud Console > APIs & Services > Credentials"
        )

    logger.info("Starting OAuth authorization flow...")
    print("[INFO] Opening browser for Google authorization...")
    print("       If the browser doesn't open, copy the URL from the terminal.")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(secrets_path),
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )

    # run_local_server starts a temporary HTTP server for the OAuth callback
    creds = flow.run_local_server(
        port=0,  # Use any available port
        prompt="consent",
        access_type="offline",  # Required for refresh token
    )

    logger.info("Authorization successful")
    return creds


def get_or_refresh_credentials(
    client_secrets_file: str | None = None,
    token_file: str | None = None,
) -> Credentials:
    """
    Get valid credentials: load saved, refresh if expired, or run auth flow.

    Args:
        client_secrets_file: Path to client_secrets.json (needed for first-time auth).
        token_file: Path to saved token file (uses default if not specified).

    Returns:
        Valid OAuth credentials.

    Raises:
        ValueError: If no saved token and no client_secrets_file provided.
        FileNotFoundError: If client_secrets_file doesn't exist.
    """
    token_path = get_token_path(token_file)

    # Try loading saved credentials
    creds = load_credentials(token_path)

    if creds and creds.valid:
        return creds

    # Try refreshing expired credentials
    if creds and creds.expired and creds.refresh_token:
        refreshed = refresh_credentials(creds)
        if refreshed and refreshed.valid:
            save_credentials(refreshed, token_path)
            return refreshed

    # Need to run auth flow
    if not client_secrets_file:
        raise ValueError(
            "No saved Google Drive credentials found.\n"
            "Run: ftp-winmount auth google --client-secrets <path-to-client_secrets.json>\n"
            "to authorize access to your Google Drive."
        )

    creds = run_auth_flow(client_secrets_file)
    save_credentials(creds, token_path)
    return creds
