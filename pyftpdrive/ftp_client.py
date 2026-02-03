import ftplib
import logging
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from .config import ConnectionConfig, FTPConfig

logger = logging.getLogger(__name__)


@dataclass
class FileStats:
    """Standardized file statistics independent of OS"""

    name: str
    size: int
    mtime: datetime
    is_dir: bool
    attributes: int = 0  # Windows file attributes


class FTPClient:
    """
    High-level wrapper around ftplib.FTP with connection pooling,
    retry logic, and simplified API.
    """

    def __init__(self, ftp_config: FTPConfig, conn_config: ConnectionConfig):
        self.ftp_config = ftp_config
        self.conn_config = conn_config
        self._ftp: ftplib.FTP | None = None
        self._lock = threading.Lock()
        self._connected = False
        # Track server capabilities
        self._supports_mlsd = None
        self._supports_mlst = None
        self._supports_rest = None

    def connect(self) -> None:
        """
        Establish initial connection to the FTP server.
        Handles authentication and passive mode setting.
        """
        with self._lock:
            self._connect_internal()

    def _connect_internal(self) -> None:
        """Internal connect without lock - caller must hold lock."""
        try:
            # Create FTP instance with timeout
            self._ftp = ftplib.FTP()
            self._ftp.encoding = self.ftp_config.encoding

            logger.debug(
                "Connecting to FTP server %s:%d", self.ftp_config.host, self.ftp_config.port
            )

            # Connect with timeout
            self._ftp.connect(
                host=self.ftp_config.host,
                port=self.ftp_config.port,
                timeout=self.conn_config.timeout_seconds,
            )

            # Login - anonymous if no credentials
            if self.ftp_config.username:
                logger.debug("Logging in as user: %s", self.ftp_config.username)
                self._ftp.login(
                    user=self.ftp_config.username, passwd=self.ftp_config.password or ""
                )
            else:
                logger.debug("Logging in anonymously")
                self._ftp.login()

            # Set passive mode
            self._ftp.set_pasv(self.ftp_config.passive_mode)
            logger.debug("Passive mode: %s", self.ftp_config.passive_mode)

            self._connected = True
            logger.info("Connected to FTP server %s:%d", self.ftp_config.host, self.ftp_config.port)

            # Probe server capabilities
            self._probe_capabilities()

        except (ftplib.error_perm, ftplib.error_temp) as e:
            self._connected = False
            self._ftp = None
            logger.error("FTP login failed: %s", e)
            raise PermissionError(f"FTP login failed: {e}") from e
        except TimeoutError as e:
            self._connected = False
            self._ftp = None
            logger.error("Connection timeout: %s", e)
            raise TimeoutError(f"Connection timeout: {e}") from e
        except OSError as e:
            self._connected = False
            self._ftp = None
            logger.error("Connection failed: %s", e)
            raise ConnectionError(f"Connection failed: {e}") from e

    def _probe_capabilities(self) -> None:
        """Probe server capabilities for MLSD, MLST, and REST support."""
        if not self._ftp:
            return

        try:
            # Check FEAT response for capabilities
            features = []
            try:
                resp = self._ftp.sendcmd("FEAT")
                features = resp.upper().split()
            except ftplib.error_perm:
                # Server doesn't support FEAT
                pass

            self._supports_mlsd = "MLSD" in features
            self._supports_mlst = "MLST" in features
            self._supports_rest = "REST" in features or "REST STREAM" in " ".join(features)

            logger.debug(
                "Server capabilities - MLSD: %s, MLST: %s, REST: %s",
                self._supports_mlsd,
                self._supports_mlst,
                self._supports_rest,
            )
        except Exception as e:
            logger.warning("Failed to probe server capabilities: %s", e)
            # Assume no advanced features
            self._supports_mlsd = False
            self._supports_mlst = False
            self._supports_rest = False

    def disconnect(self) -> None:
        """Safely close connection(s)."""
        with self._lock:
            self._disconnect_internal()

    def _disconnect_internal(self) -> None:
        """Internal disconnect without lock - caller must hold lock."""
        if self._ftp:
            try:
                self._ftp.quit()
                logger.debug("FTP connection closed gracefully")
            except Exception as e:
                logger.debug("FTP quit failed, forcing close: %s", e)
                try:
                    self._ftp.close()
                except Exception:
                    pass
            finally:
                self._ftp = None
                self._connected = False

    def _ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed. Caller must hold lock."""
        if not self._connected or not self._ftp:
            logger.debug("Connection not active, reconnecting")
            self._connect_internal()
            return

        # Check if connection is still alive with NOOP
        try:
            self._ftp.voidcmd("NOOP")
        except Exception as e:
            logger.debug("Connection lost, reconnecting: %s", e)
            self._disconnect_internal()
            self._connect_internal()

    def _normalize_path(self, path: str) -> str:
        """Ensure path has leading slash and uses forward slashes."""
        path = path.replace("\\", "/")
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _with_retry(self, operation: str, func, *args, **kwargs):
        """
        Execute a function with retry logic.

        Args:
            operation: Description of the operation for logging
            func: Function to execute
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result of the function

        Raises:
            The last exception if all retries fail
        """
        last_exception = None

        for attempt in range(self.conn_config.retry_attempts):
            try:
                with self._lock:
                    self._ensure_connected()
                    return func(*args, **kwargs)
            except (TimeoutError, ftplib.error_temp, OSError, ConnectionError) as e:
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
                    # Force reconnect on next attempt
                    with self._lock:
                        self._disconnect_internal()
            except ftplib.error_perm as e:
                # Permanent errors should not be retried
                raise self._translate_ftp_error(e)

        # All retries exhausted
        logger.error("%s failed after %d attempts", operation, self.conn_config.retry_attempts)
        if isinstance(last_exception, socket.timeout):
            raise TimeoutError(f"{operation} timed out") from last_exception
        raise OSError(f"{operation} failed: {last_exception}") from last_exception

    def _translate_ftp_error(self, error: ftplib.error_perm) -> Exception:
        """Translate FTP permanent errors to standard Python exceptions."""
        error_str = str(error).lower()
        error_code = str(error)[:3] if len(str(error)) >= 3 else ""

        if error_code == "550":
            # Could be file not found or permission denied
            if "not found" in error_str or "no such" in error_str or "doesn't exist" in error_str:
                return FileNotFoundError(str(error))
            elif "permission" in error_str or "denied" in error_str:
                return PermissionError(str(error))
            elif "not empty" in error_str:
                return OSError(str(error))  # Directory not empty
            else:
                # Default to FileNotFoundError for 550
                return FileNotFoundError(str(error))
        elif error_code == "553":
            return PermissionError(str(error))
        elif error_code == "530":
            return PermissionError(f"Authentication required: {error}")
        else:
            return OSError(str(error))

    def list_dir(self, path: str) -> list[FileStats]:
        """
        List contents of a directory.

        Args:
            path: Absolute FTP path.

        Returns:
            List[FileStats]: List of file/directory objects with metadata.

        Raises:
            FileNotFoundError: If path does not exist.
            PermissionError: If access denied.
        """
        path = self._normalize_path(path)
        logger.debug("Listing directory: %s", path)

        def _list_dir_internal() -> list[FileStats]:
            if self._supports_mlsd:
                return self._list_dir_mlsd(path)
            else:
                return self._list_dir_list(path)

        return self._with_retry(f"list_dir({path})", _list_dir_internal)

    def _list_dir_mlsd(self, path: str) -> list[FileStats]:
        """List directory using MLSD command (modern, structured)."""
        results = []
        for name, facts in self._ftp.mlsd(path):
            # Skip . and .. entries
            if name in (".", ".."):
                continue

            is_dir = facts.get("type", "").lower() in ("dir", "cdir", "pdir")
            size = int(facts.get("size", 0)) if not is_dir else 0

            # Parse modify time
            mtime_str = facts.get("modify", "")
            mtime = self._parse_mlsd_time(mtime_str)

            results.append(FileStats(name=name, size=size, mtime=mtime, is_dir=is_dir))

        logger.debug("MLSD listed %d entries in %s", len(results), path)
        return results

    def _parse_mlsd_time(self, time_str: str) -> datetime:
        """Parse MLSD modify time format (YYYYMMDDHHmmSS or YYYYMMDDHHmmSS.sss)."""
        if not time_str:
            return datetime.now()

        try:
            # Remove fractional seconds if present
            if "." in time_str:
                time_str = time_str.split(".")[0]
            return datetime.strptime(time_str, "%Y%m%d%H%M%S")
        except ValueError:
            logger.warning("Failed to parse MLSD time: %s", time_str)
            return datetime.now()

    def _list_dir_list(self, path: str) -> list[FileStats]:
        """List directory using LIST command (legacy, needs parsing)."""
        lines = []
        self._ftp.cwd(path)
        self._ftp.retrlines("LIST", lines.append)

        results = []
        for line in lines:
            stats = self._parse_list_line(line)
            if stats and stats.name not in (".", ".."):
                results.append(stats)

        logger.debug("LIST listed %d entries in %s", len(results), path)
        return results

    def _parse_list_line(self, line: str) -> FileStats | None:
        """
        Parse a single line from LIST output.
        Handles both Unix and Windows FTP server formats.
        """
        line = line.strip()
        if not line:
            return None

        # Try Unix format: drwxr-xr-x  2 user group 4096 Dec 10 12:34 filename
        # Try Windows format: 12-10-20  12:34PM       <DIR>          dirname
        # Try Windows format: 12-10-20  12:34PM              1234 filename

        parts = line.split()
        if len(parts) < 4:
            return None

        # Check for Unix format (starts with permissions like drwxr-xr-x or -rw-r--r--)
        if len(parts[0]) >= 10 and parts[0][0] in "dl-":
            return self._parse_unix_list_line(parts, line)

        # Check for Windows format (starts with date like MM-DD-YY)
        if "-" in parts[0] and len(parts[0]) <= 10:
            return self._parse_windows_list_line(parts, line)

        logger.warning("Unknown LIST format: %s", line)
        return None

    def _parse_unix_list_line(self, parts: list[str], original_line: str) -> FileStats | None:
        """Parse Unix-style LIST output."""
        try:
            is_dir = parts[0][0] == "d"
            size = int(parts[4]) if not is_dir else 0

            # Filename is everything after the date/time (parts 5-7 typically)
            # Find the position after the size field
            size_end_pos = original_line.find(parts[4]) + len(parts[4])
            # Skip whitespace after size
            name_start = size_end_pos
            while name_start < len(original_line) and original_line[name_start] in " \t":
                name_start += 1
            # Skip month day time fields (3 fields)
            for _ in range(3):
                while name_start < len(original_line) and original_line[name_start] not in " \t":
                    name_start += 1
                while name_start < len(original_line) and original_line[name_start] in " \t":
                    name_start += 1

            name = original_line[name_start:].strip()

            # Parse modification time (month day time/year)
            mtime = self._parse_unix_list_time(parts[5:8])

            return FileStats(name=name, size=size, mtime=mtime, is_dir=is_dir)
        except (IndexError, ValueError) as e:
            logger.warning("Failed to parse Unix LIST line: %s - %s", original_line, e)
            return None

    def _parse_unix_list_time(self, time_parts: list[str]) -> datetime:
        """Parse Unix LIST time format (e.g., 'Dec 10 12:34' or 'Dec 10  2020')."""
        if len(time_parts) < 3:
            return datetime.now()

        month_str, day_str, time_or_year = time_parts[0], time_parts[1], time_parts[2]

        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }

        try:
            month = months.get(month_str.lower(), 1)
            day = int(day_str)

            if ":" in time_or_year:
                # Time format - assume current year
                hour, minute = map(int, time_or_year.split(":"))
                year = datetime.now().year
            else:
                # Year format - assume midnight
                year = int(time_or_year)
                hour, minute = 0, 0

            return datetime(year, month, day, hour, minute)
        except (ValueError, KeyError):
            return datetime.now()

    def _parse_windows_list_line(self, parts: list[str], original_line: str) -> FileStats | None:
        """Parse Windows-style LIST output."""
        try:
            # Format: MM-DD-YY  HH:MMPM  <DIR>  dirname
            # Format: MM-DD-YY  HH:MMPM  size  filename
            is_dir = "<DIR>" in original_line
            size = 0
            name_start_idx = 3

            if is_dir:
                # Find <DIR> and name after it
                dir_idx = parts.index("<DIR>")
                name_start_idx = dir_idx + 1
            else:
                # Size is the third element
                size = int(parts[2])
                name_start_idx = 3

            # Name is everything after size/<DIR>
            name = " ".join(parts[name_start_idx:])

            # Parse date/time
            mtime = self._parse_windows_list_time(parts[0], parts[1])

            return FileStats(name=name, size=size, mtime=mtime, is_dir=is_dir)
        except (IndexError, ValueError) as e:
            logger.warning("Failed to parse Windows LIST line: %s - %s", original_line, e)
            return None

    def _parse_windows_list_time(self, date_str: str, time_str: str) -> datetime:
        """Parse Windows LIST time format (MM-DD-YY HH:MMAM/PM)."""
        try:
            # Parse date
            month, day, year = map(int, date_str.split("-"))
            if year < 100:
                year += 2000 if year < 70 else 1900

            # Parse time
            time_str = time_str.upper()
            is_pm = "PM" in time_str
            time_str = time_str.replace("AM", "").replace("PM", "")
            hour, minute = map(int, time_str.split(":"))

            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0

            return datetime(year, month, day, hour, minute)
        except (ValueError, IndexError):
            return datetime.now()

    def get_file_info(self, path: str) -> FileStats:
        """
        Get metadata for a single file or directory.

        Args:
            path: Absolute FTP path.

        Returns:
            FileStats object.
        """
        path = self._normalize_path(path)
        logger.debug("Getting file info: %s", path)

        def _get_file_info_internal() -> FileStats:
            if self._supports_mlst:
                return self._get_file_info_mlst(path)
            else:
                return self._get_file_info_list(path)

        return self._with_retry(f"get_file_info({path})", _get_file_info_internal)

    def _get_file_info_mlst(self, path: str) -> FileStats:
        """Get file info using MLST command."""
        response = self._ftp.sendcmd(f"MLST {path}")

        # Response format:
        # 250-Listing path
        #  type=file;size=1234;modify=20201210123456; filename
        # 250 End

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith(" ") or ";" in line:
                # This is the facts line
                parts = line.strip().split(";")
                facts = {}
                name = ""

                for part in parts:
                    if "=" in part:
                        key, value = part.split("=", 1)
                        facts[key.lower()] = value
                    else:
                        # Last part without = is the filename
                        name = part.strip()

                if not name:
                    # Filename might be the path itself
                    name = path.rsplit("/", 1)[-1]

                is_dir = facts.get("type", "").lower() in ("dir", "cdir", "pdir")
                size = int(facts.get("size", 0)) if not is_dir else 0
                mtime = self._parse_mlsd_time(facts.get("modify", ""))

                return FileStats(name=name, size=size, mtime=mtime, is_dir=is_dir)

        raise FileNotFoundError(f"Could not parse MLST response for {path}")

    def _get_file_info_list(self, path: str) -> FileStats:
        """Get file info by listing parent directory and finding entry."""
        # Handle root directory specially
        if path == "/":
            return FileStats(name="/", size=0, mtime=datetime.now(), is_dir=True)

        # Get parent directory and filename
        if "/" in path.rstrip("/"):
            parent = path.rsplit("/", 1)[0] or "/"
            filename = path.rsplit("/", 1)[1]
        else:
            parent = "/"
            filename = path.lstrip("/")

        # List parent directory
        entries = self._list_dir_list(parent)

        for entry in entries:
            if entry.name == filename:
                return entry

        raise FileNotFoundError(f"File not found: {path}")

    def read_file(self, path: str, offset: int = 0, length: int | None = None) -> bytes:
        """
        Read bytes from a file.

        Args:
            path: Absolute FTP path.
            offset: Byte offset to start reading from.
            length: Number of bytes to read (None for rest of file).

        Returns:
            bytes: File content.
        """
        path = self._normalize_path(path)
        logger.debug("Reading file: %s (offset=%d, length=%s)", path, offset, length)

        def _read_file_internal() -> bytes:
            buffer = BytesIO()

            # Try to use REST for offset
            if offset > 0 and self._supports_rest:
                try:
                    self._ftp.sendcmd(f"REST {offset}")
                except ftplib.error_perm:
                    # REST not actually supported, download all
                    pass

            # Download file
            self._ftp.retrbinary(f"RETR {path}", buffer.write)
            data = buffer.getvalue()

            # Apply offset/length if REST wasn't used or for length
            if offset > 0 and not self._supports_rest:
                data = data[offset:]

            if length is not None:
                data = data[:length]

            logger.debug("Read %d bytes from %s", len(data), path)
            return data

        return self._with_retry(f"read_file({path})", _read_file_internal)

    def write_file(self, path: str, data: bytes, offset: int = 0) -> int:
        """
        Write bytes to a file.

        Args:
            path: Absolute FTP path.
            data: Bytes to write.
            offset: Byte offset to write at.

        Returns:
            int: Number of bytes written.
        """
        path = self._normalize_path(path)
        logger.debug("Writing file: %s (%d bytes at offset %d)", path, len(data), offset)

        def _write_file_internal() -> int:
            if offset == 0:
                # Simple case: write entire file
                buffer = BytesIO(data)
                self._ftp.storbinary(f"STOR {path}", buffer)
                logger.debug("Wrote %d bytes to %s", len(data), path)
                return len(data)
            else:
                # Complex case: read-modify-write
                # First, read existing file
                try:
                    existing_buffer = BytesIO()
                    self._ftp.retrbinary(f"RETR {path}", existing_buffer.write)
                    existing_data = bytearray(existing_buffer.getvalue())
                except ftplib.error_perm:
                    # File doesn't exist, create with padding
                    existing_data = bytearray()

                # Extend if needed
                if offset > len(existing_data):
                    existing_data.extend(b"\x00" * (offset - len(existing_data)))

                # Modify at offset
                existing_data[offset : offset + len(data)] = data

                # Write back
                buffer = BytesIO(bytes(existing_data))
                self._ftp.storbinary(f"STOR {path}", buffer)
                logger.debug("Wrote %d bytes to %s at offset %d", len(data), path, offset)
                return len(data)

        return self._with_retry(f"write_file({path})", _write_file_internal)

    def create_file(self, path: str) -> None:
        """Create an empty file."""
        path = self._normalize_path(path)
        logger.debug("Creating empty file: %s", path)

        def _create_file_internal() -> None:
            buffer = BytesIO(b"")
            self._ftp.storbinary(f"STOR {path}", buffer)
            logger.debug("Created empty file: %s", path)

        self._with_retry(f"create_file({path})", _create_file_internal)

    def create_dir(self, path: str) -> None:
        """Create a directory (recursively if needed)."""
        path = self._normalize_path(path)
        logger.debug("Creating directory: %s", path)

        def _create_dir_internal() -> None:
            # Try to create directly first
            try:
                self._ftp.mkd(path)
                logger.debug("Created directory: %s", path)
                return
            except ftplib.error_perm as e:
                # Directory might already exist, or parent doesn't exist
                error_str = str(e).lower()
                if "exists" in error_str or "already" in error_str:
                    logger.debug("Directory already exists: %s", path)
                    return
                # Otherwise, try creating parent directories
                pass

            # Create parent directories recursively
            parts = path.strip("/").split("/")
            current = ""
            for part in parts:
                current = current + "/" + part
                try:
                    self._ftp.mkd(current)
                    logger.debug("Created directory: %s", current)
                except ftplib.error_perm as e:
                    # Already exists, continue
                    error_str = str(e).lower()
                    if "exists" not in error_str and "already" not in error_str:
                        raise

        self._with_retry(f"create_dir({path})", _create_dir_internal)

    def delete_file(self, path: str) -> None:
        """Delete a file."""
        path = self._normalize_path(path)
        logger.debug("Deleting file: %s", path)

        def _delete_file_internal() -> None:
            self._ftp.delete(path)
            logger.debug("Deleted file: %s", path)

        self._with_retry(f"delete_file({path})", _delete_file_internal)

    def delete_dir(self, path: str) -> None:
        """Delete a directory (must be empty)."""
        path = self._normalize_path(path)
        logger.debug("Deleting directory: %s", path)

        def _delete_dir_internal() -> None:
            self._ftp.rmd(path)
            logger.debug("Deleted directory: %s", path)

        self._with_retry(f"delete_dir({path})", _delete_dir_internal)

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename or move a file/directory."""
        old_path = self._normalize_path(old_path)
        new_path = self._normalize_path(new_path)
        logger.debug("Renaming: %s -> %s", old_path, new_path)

        def _rename_internal() -> None:
            self._ftp.rename(old_path, new_path)
            logger.debug("Renamed: %s -> %s", old_path, new_path)

        self._with_retry(f"rename({old_path}, {new_path})", _rename_internal)
