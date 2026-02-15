"""
SFTP client implementation using paramiko.

Provides the same interface as FTPClient but over SSH/SFTP,
allowing the filesystem layer to use either transport transparently.
"""

import logging
import os
import stat
import threading
import time
from datetime import datetime
from pathlib import Path

import paramiko

from .config import ConnectionConfig, SSHConfig
from .ftp_client import FileStats

logger = logging.getLogger(__name__)


class TrustOnFirstUsePolicy(paramiko.MissingHostKeyPolicy):
    """
    Trust-on-first-use host key policy (same model as OpenSSH).

    - Unknown host: accept and save key to ~/.ssh/known_hosts
    - Known host, same key: accept
    - Known host, CHANGED key: reject (possible MITM attack)
    """

    def __init__(self):
        self._known_hosts_path = Path.home() / ".ssh" / "known_hosts"

    def missing_host_key(self, client, hostname, key):
        # Check if we have a DIFFERENT key for this host already
        host_keys = client.get_host_keys()
        existing = host_keys.lookup(hostname)

        if existing is not None:
            # Host is known -- check if the key type exists but differs
            key_type = key.get_name()
            existing_key = existing.get(key_type)
            if existing_key is not None and existing_key != key:
                raise paramiko.SSHException(
                    f"Host key for {hostname} has CHANGED. "
                    f"This could indicate a man-in-the-middle attack. "
                    f"If the server key was legitimately changed, remove the old "
                    f"entry from {self._known_hosts_path} and try again."
                )

        # Unknown host or new key type -- trust on first use
        logger.info("Adding host key for %s to known_hosts", hostname)
        host_keys.add(hostname, key.get_name(), key)

        # Persist to disk
        try:
            self._known_hosts_path.parent.mkdir(parents=True, exist_ok=True)
            host_keys.save(str(self._known_hosts_path))
        except OSError as e:
            logger.warning("Could not save known_hosts: %s", e)


class SFTPClient:
    """
    High-level wrapper around paramiko's SSH/SFTP with connection management,
    retry logic, and the same interface as FTPClient.
    """

    def __init__(self, ssh_config: SSHConfig, conn_config: ConnectionConfig):
        self.ssh_config = ssh_config
        self.conn_config = conn_config
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._lock = threading.Lock()
        self._connected = False

    def connect(self) -> None:
        """Establish SSH connection and open SFTP session."""
        with self._lock:
            self._connect_internal()

    def _connect_internal(self) -> None:
        """Internal connect without lock - caller must hold lock."""
        try:
            self._ssh = paramiko.SSHClient()
            self._ssh.load_system_host_keys()
            try:
                known_hosts = str(Path.home() / ".ssh" / "known_hosts")
                self._ssh.load_host_keys(known_hosts)
            except FileNotFoundError:
                pass
            self._ssh.set_missing_host_key_policy(TrustOnFirstUsePolicy())

            connect_kwargs: dict = {
                "hostname": self.ssh_config.host,
                "port": self.ssh_config.port,
                "timeout": self.conn_config.timeout_seconds,
                "allow_agent": self.ssh_config.use_agent,
            }

            if self.ssh_config.username:
                connect_kwargs["username"] = self.ssh_config.username

            # Auth priority: key file -> agent -> password
            if self.ssh_config.key_file:
                key_path = os.path.expanduser(self.ssh_config.key_file)
                connect_kwargs["key_filename"] = key_path
                if self.ssh_config.key_passphrase:
                    connect_kwargs["passphrase"] = self.ssh_config.key_passphrase
                # Disable password auth when using key
                connect_kwargs["look_for_keys"] = True
                logger.debug(
                    "Connecting to SSH %s:%d with key file: %s",
                    self.ssh_config.host,
                    self.ssh_config.port,
                    key_path,
                )
            elif self.ssh_config.password:
                connect_kwargs["password"] = self.ssh_config.password
                connect_kwargs["look_for_keys"] = False
                logger.debug(
                    "Connecting to SSH %s:%d with password",
                    self.ssh_config.host,
                    self.ssh_config.port,
                )
            else:
                # Rely on agent or default keys
                connect_kwargs["look_for_keys"] = True
                logger.debug(
                    "Connecting to SSH %s:%d with agent/default keys",
                    self.ssh_config.host,
                    self.ssh_config.port,
                )

            self._ssh.connect(**connect_kwargs)
            self._sftp = self._ssh.open_sftp()
            self._connected = True
            logger.info(
                "Connected to SSH server %s:%d",
                self.ssh_config.host,
                self.ssh_config.port,
            )

        except paramiko.AuthenticationException as e:
            self._connected = False
            self._cleanup_connections()
            logger.error("SSH authentication failed: %s", e)
            raise PermissionError(f"SSH authentication failed: {e}") from e
        except TimeoutError as e:
            self._connected = False
            self._cleanup_connections()
            logger.error("SSH connection timeout: %s", e)
            raise TimeoutError(f"SSH connection timeout: {e}") from e
        except OSError as e:
            self._connected = False
            self._cleanup_connections()
            logger.error("SSH connection failed: %s", e)
            raise ConnectionError(f"SSH connection failed: {e}") from e
        except paramiko.SSHException as e:
            self._connected = False
            self._cleanup_connections()
            logger.error("SSH error: %s", e)
            raise ConnectionError(f"SSH error: {e}") from e

    def _cleanup_connections(self) -> None:
        """Close SFTP and SSH without raising."""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._ssh:
            try:
                self._ssh.close()
            except Exception:
                pass
            self._ssh = None

    def disconnect(self) -> None:
        """Close SFTP session and SSH connection."""
        with self._lock:
            self._disconnect_internal()

    def _disconnect_internal(self) -> None:
        """Internal disconnect without lock - caller must hold lock."""
        self._cleanup_connections()
        self._connected = False
        logger.debug("SSH connection closed")

    def _ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed. Caller must hold lock."""
        if not self._connected or not self._sftp or not self._ssh:
            logger.debug("SSH connection not active, reconnecting")
            self._connect_internal()
            return

        # Check if transport is still alive
        transport = self._ssh.get_transport()
        if transport is None or not transport.is_active():
            logger.debug("SSH transport lost, reconnecting")
            self._disconnect_internal()
            self._connect_internal()

    def _normalize_path(self, path: str) -> str:
        """Ensure path has leading slash and uses forward slashes."""
        path = path.replace("\\", "/")
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _with_retry(self, operation: str, func, *args, **kwargs):
        """Execute a function with retry logic."""
        last_exception = None

        for attempt in range(self.conn_config.retry_attempts):
            try:
                with self._lock:
                    self._ensure_connected()
                    return func(*args, **kwargs)
            except FileNotFoundError:
                raise
            except PermissionError:
                raise
            except (TimeoutError, OSError, ConnectionError, paramiko.SSHException) as e:
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
                    with self._lock:
                        self._disconnect_internal()

        logger.error(
            "%s failed after %d attempts", operation, self.conn_config.retry_attempts
        )
        raise OSError(f"{operation} failed: {last_exception}") from last_exception

    def _translate_io_error(self, error: IOError, path: str) -> Exception:
        """Translate SFTP IOError to standard Python exceptions."""
        errno = getattr(error, "errno", None)
        if errno == 2:  # ENOENT
            return FileNotFoundError(f"No such file or directory: {path}")
        elif errno == 13:  # EACCES
            return PermissionError(f"Permission denied: {path}")
        elif errno == 39 or errno == 66:  # ENOTEMPTY
            return OSError(f"Directory not empty: {path}")
        else:
            return OSError(str(error))

    def list_dir(self, path: str) -> list[FileStats]:
        """List contents of a directory."""
        path = self._normalize_path(path)
        logger.debug("Listing directory: %s", path)

        def _list_dir_internal() -> list[FileStats]:
            results = []
            for attr in self._sftp.listdir_attr(path):
                name = attr.filename
                if name in (".", ".."):
                    continue

                is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
                size = attr.st_size if attr.st_size and not is_dir else 0
                mtime = datetime.fromtimestamp(attr.st_mtime) if attr.st_mtime else datetime.now()

                results.append(
                    FileStats(name=name, size=size, mtime=mtime, is_dir=is_dir)
                )

            logger.debug("Listed %d entries in %s", len(results), path)
            return results

        try:
            return self._with_retry(f"list_dir({path})", _list_dir_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def get_file_info(self, path: str) -> FileStats:
        """Get metadata for a single file or directory."""
        path = self._normalize_path(path)
        logger.debug("Getting file info: %s", path)

        def _get_file_info_internal() -> FileStats:
            attr = self._sftp.stat(path)
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
            size = attr.st_size if attr.st_size and not is_dir else 0
            mtime = datetime.fromtimestamp(attr.st_mtime) if attr.st_mtime else datetime.now()
            name = path.rsplit("/", 1)[-1] if "/" in path else path

            return FileStats(name=name, size=size, mtime=mtime, is_dir=is_dir)

        try:
            return self._with_retry(f"get_file_info({path})", _get_file_info_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def read_file(self, path: str, offset: int = 0, length: int | None = None) -> bytes:
        """Read bytes from a file."""
        path = self._normalize_path(path)
        logger.debug("Reading file: %s (offset=%d, length=%s)", path, offset, length)

        def _read_file_internal() -> bytes:
            with self._sftp.open(path, "rb") as f:
                if offset > 0:
                    f.seek(offset)
                if length is not None:
                    data = f.read(length)
                else:
                    data = f.read()

            logger.debug("Read %d bytes from %s", len(data), path)
            return data

        try:
            return self._with_retry(f"read_file({path})", _read_file_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def write_file(self, path: str, data: bytes, offset: int = 0) -> int:
        """Write bytes to a file."""
        path = self._normalize_path(path)
        logger.debug("Writing file: %s (%d bytes at offset %d)", path, len(data), offset)

        def _write_file_internal() -> int:
            if offset == 0:
                # Simple case: overwrite entire file
                with self._sftp.open(path, "wb") as f:
                    f.write(data)
            else:
                # Write at offset -- SFTP supports this natively
                with self._sftp.open(path, "r+b") as f:
                    f.seek(offset)
                    f.write(data)

            logger.debug("Wrote %d bytes to %s at offset %d", len(data), path, offset)
            return len(data)

        try:
            return self._with_retry(f"write_file({path})", _write_file_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def create_file(self, path: str) -> None:
        """Create an empty file."""
        path = self._normalize_path(path)
        logger.debug("Creating empty file: %s", path)

        def _create_file_internal() -> None:
            with self._sftp.open(path, "wb") as f:
                pass
            logger.debug("Created empty file: %s", path)

        try:
            self._with_retry(f"create_file({path})", _create_file_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def create_dir(self, path: str) -> None:
        """Create a directory (recursively if needed)."""
        path = self._normalize_path(path)
        logger.debug("Creating directory: %s", path)

        def _create_dir_internal() -> None:
            # Try direct creation first
            try:
                self._sftp.mkdir(path)
                logger.debug("Created directory: %s", path)
                return
            except IOError:
                pass

            # Recursive creation
            parts = path.strip("/").split("/")
            current = ""
            for part in parts:
                current = current + "/" + part
                try:
                    self._sftp.stat(current)
                except IOError:
                    self._sftp.mkdir(current)
                    logger.debug("Created directory: %s", current)

        try:
            self._with_retry(f"create_dir({path})", _create_dir_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def delete_file(self, path: str) -> None:
        """Delete a file."""
        path = self._normalize_path(path)
        logger.debug("Deleting file: %s", path)

        def _delete_file_internal() -> None:
            self._sftp.remove(path)
            logger.debug("Deleted file: %s", path)

        try:
            self._with_retry(f"delete_file({path})", _delete_file_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def delete_dir(self, path: str) -> None:
        """Delete a directory (must be empty)."""
        path = self._normalize_path(path)
        logger.debug("Deleting directory: %s", path)

        def _delete_dir_internal() -> None:
            self._sftp.rmdir(path)
            logger.debug("Deleted directory: %s", path)

        try:
            self._with_retry(f"delete_dir({path})", _delete_dir_internal)
        except IOError as e:
            raise self._translate_io_error(e, path)

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename or move a file/directory."""
        old_path = self._normalize_path(old_path)
        new_path = self._normalize_path(new_path)
        logger.debug("Renaming: %s -> %s", old_path, new_path)

        def _rename_internal() -> None:
            self._sftp.rename(old_path, new_path)
            logger.debug("Renamed: %s -> %s", old_path, new_path)

        try:
            self._with_retry(f"rename({old_path}, {new_path})", _rename_internal)
        except IOError as e:
            raise self._translate_io_error(e, old_path)
