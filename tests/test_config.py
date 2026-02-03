"""
Unit tests for pyftpdrive.config module.

Tests cover:
- Loading configuration from INI files
- Loading configuration from CLI arguments only
- CLI override precedence (CLI wins over INI)
- Missing required field validation
- Missing config file handling
- Drive letter validation and normalization
"""

from pathlib import Path

import pytest

from pyftpdrive.config import (
    AppConfig,
    CacheConfig,
    ConnectionConfig,
    FTPConfig,
    LogConfig,
    MountConfig,
    load_config,
)


class TestLoadConfigWithINIFile:
    """Tests for load_config with INI file."""

    def test_load_config_reads_all_sections(self, tmp_config_file: Path):
        """Test that load_config correctly reads all sections from INI file."""
        config = load_config(str(tmp_config_file))

        # Verify FTP section
        assert config.ftp.host == "testserver.local"
        assert config.ftp.port == 2121
        assert config.ftp.username == "testuser"
        assert config.ftp.password == "testpass"
        assert config.ftp.passive_mode is True
        assert config.ftp.encoding == "utf-8"

        # Verify mount section
        assert config.mount.drive_letter == "Z"
        assert config.mount.volume_label == "Test FTP Drive"

        # Verify cache section
        assert config.cache.enabled is True
        assert config.cache.directory_ttl_seconds == 60
        assert config.cache.metadata_ttl_seconds == 120

        # Verify connection section
        assert config.connection.timeout_seconds == 45
        assert config.connection.retry_attempts == 5
        assert config.connection.retry_delay_seconds == 2
        assert config.connection.keepalive_interval_seconds == 90

        # Verify logging section
        assert config.logging.level == "DEBUG"
        assert config.logging.file == "test.log"
        assert config.logging.console is False

    def test_load_config_returns_appconfig_type(self, tmp_config_file: Path):
        """Test that load_config returns correct types."""
        config = load_config(str(tmp_config_file))

        assert isinstance(config, AppConfig)
        assert isinstance(config.ftp, FTPConfig)
        assert isinstance(config.mount, MountConfig)
        assert isinstance(config.cache, CacheConfig)
        assert isinstance(config.connection, ConnectionConfig)
        assert isinstance(config.logging, LogConfig)

    def test_load_config_minimal_file(self, minimal_config_file: Path):
        """Test loading config with only required fields uses defaults for others."""
        config = load_config(str(minimal_config_file))

        # Required fields from file
        assert config.ftp.host == "minimal.server.com"
        assert config.mount.drive_letter == "X"

        # Default values
        assert config.ftp.port == 21
        assert config.ftp.username is None
        assert config.ftp.password is None
        assert config.ftp.passive_mode is True
        assert config.cache.enabled is True
        assert config.cache.directory_ttl_seconds == 30
        assert config.connection.timeout_seconds == 30
        assert config.connection.retry_attempts == 3
        assert config.logging.level == "INFO"
        assert config.logging.console is True


class TestLoadConfigCLIOnly:
    """Tests for load_config with CLI arguments only (no INI file)."""

    def test_load_config_cli_only(self):
        """Test loading config from CLI arguments only."""
        config = load_config(
            config_path=None,
            host="cli.server.com",
            port=2222,
            username="cliuser",
            password="clipass",
            drive_letter="Y",
        )

        assert config.ftp.host == "cli.server.com"
        assert config.ftp.port == 2222
        assert config.ftp.username == "cliuser"
        assert config.ftp.password == "clipass"
        assert config.mount.drive_letter == "Y"

    def test_load_config_cli_minimal(self):
        """Test loading config with only required CLI arguments."""
        config = load_config(
            config_path=None,
            host="minimal.cli.com",
            drive_letter="W",
        )

        assert config.ftp.host == "minimal.cli.com"
        assert config.mount.drive_letter == "W"
        # Defaults should be applied
        assert config.ftp.port == 21
        assert config.ftp.username is None

    def test_load_config_debug_flag_sets_console_and_level(self):
        """Test that debug=True sets console=True and level=DEBUG."""
        config = load_config(
            config_path=None,
            host="debug.server.com",
            drive_letter="V",
            debug=True,
        )

        assert config.logging.level == "DEBUG"
        assert config.logging.console is True


class TestCLIOverridePrecedence:
    """Tests for CLI override precedence over INI file."""

    def test_cli_overrides_ini_host(self, tmp_config_file: Path):
        """Test that CLI host overrides INI file host."""
        config = load_config(str(tmp_config_file), host="override.server.com")

        assert config.ftp.host == "override.server.com"
        # Other values from INI should remain
        assert config.ftp.port == 2121

    def test_cli_overrides_ini_port(self, tmp_config_file: Path):
        """Test that CLI port overrides INI file port."""
        config = load_config(str(tmp_config_file), port=9999)

        assert config.ftp.port == 9999
        # Host from INI should remain
        assert config.ftp.host == "testserver.local"

    def test_cli_overrides_ini_drive_letter(self, tmp_config_file: Path):
        """Test that CLI drive_letter overrides INI file."""
        config = load_config(str(tmp_config_file), drive_letter="A")

        assert config.mount.drive_letter == "A"

    def test_cli_overrides_ini_credentials(self, tmp_config_file: Path):
        """Test that CLI credentials override INI file."""
        config = load_config(
            str(tmp_config_file),
            username="newuser",
            password="newpass",
        )

        assert config.ftp.username == "newuser"
        assert config.ftp.password == "newpass"

    def test_cli_overrides_multiple_values(self, tmp_config_file: Path):
        """Test that multiple CLI values override INI file."""
        config = load_config(
            str(tmp_config_file),
            host="new.server.com",
            port=3333,
            username="newuser",
            drive_letter="B",
        )

        assert config.ftp.host == "new.server.com"
        assert config.ftp.port == 3333
        assert config.ftp.username == "newuser"
        assert config.mount.drive_letter == "B"
        # Non-overridden values from INI
        assert config.ftp.password == "testpass"


class TestMissingRequiredFields:
    """Tests for missing required field validation."""

    def test_missing_host_raises_valueerror(self):
        """Test that missing host raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            load_config(config_path=None, drive_letter="Z")

        assert "host" in str(exc_info.value)
        assert "Missing required" in str(exc_info.value)

    def test_missing_drive_letter_raises_valueerror(self):
        """Test that missing drive_letter raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            load_config(config_path=None, host="test.server.com")

        assert "drive_letter" in str(exc_info.value)
        assert "Missing required" in str(exc_info.value)

    def test_missing_both_required_raises_valueerror(self):
        """Test that missing both required fields raises ValueError with both listed."""
        with pytest.raises(ValueError) as exc_info:
            load_config(config_path=None)

        error_msg = str(exc_info.value)
        assert "host" in error_msg
        assert "drive_letter" in error_msg

    def test_empty_ini_file_raises_valueerror(self, tmp_path: Path):
        """Test that an empty INI file raises ValueError for missing fields."""
        empty_config = tmp_path / "empty.ini"
        empty_config.write_text("", encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            load_config(str(empty_config))

        assert "Missing required" in str(exc_info.value)


class TestMissingConfigFile:
    """Tests for missing config file handling."""

    def test_missing_config_file_raises_filenotfounderror(self):
        """Test that non-existent config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_config("/nonexistent/path/config.ini")

        assert "Configuration file not found" in str(exc_info.value)
        assert "/nonexistent/path/config.ini" in str(exc_info.value)

    def test_missing_config_file_with_cli_override_still_raises(self):
        """Test that non-existent config file raises even with CLI args."""
        with pytest.raises(FileNotFoundError):
            load_config(
                "/missing/config.ini",
                host="test.server.com",
                drive_letter="Z",
            )


class TestDriveLetterValidation:
    """Tests for drive letter validation and normalization."""

    def test_drive_letter_uppercase_normalization(self):
        """Test that lowercase drive letters are uppercased."""
        config = load_config(
            config_path=None,
            host="test.server.com",
            drive_letter="z",
        )

        assert config.mount.drive_letter == "Z"

    def test_drive_letter_with_colon_is_stripped(self):
        """Test that drive letter with colon has colon stripped."""
        config = load_config(
            config_path=None,
            host="test.server.com",
            drive_letter="Z:",
        )

        assert config.mount.drive_letter == "Z"

    def test_drive_letter_lowercase_with_colon(self):
        """Test that lowercase drive letter with colon is normalized."""
        config = load_config(
            config_path=None,
            host="test.server.com",
            drive_letter="y:",
        )

        assert config.mount.drive_letter == "Y"

    def test_invalid_drive_letter_numeric_raises_valueerror(self):
        """Test that numeric drive letter raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            load_config(
                config_path=None,
                host="test.server.com",
                drive_letter="1",
            )

        assert "Invalid drive letter" in str(exc_info.value)

    def test_invalid_drive_letter_multiple_chars_raises_valueerror(self):
        """Test that multi-character drive letter raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            load_config(
                config_path=None,
                host="test.server.com",
                drive_letter="ZZ",
            )

        assert "Invalid drive letter" in str(exc_info.value)

    def test_invalid_drive_letter_special_char_raises_valueerror(self):
        """Test that special character drive letter raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            load_config(
                config_path=None,
                host="test.server.com",
                drive_letter="@",
            )

        assert "Invalid drive letter" in str(exc_info.value)

    def test_valid_drive_letters_a_to_z(self):
        """Test that all letters A-Z are valid drive letters."""
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            config = load_config(
                config_path=None,
                host="test.server.com",
                drive_letter=letter,
            )
            assert config.mount.drive_letter == letter


class TestConfigBooleanParsing:
    """Tests for boolean value parsing from INI files."""

    def test_boolean_true_variations(self, tmp_path: Path):
        """Test that various 'true' representations parse correctly."""
        for true_val in ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]:
            config_content = f"""[ftp]
host = test.server.com

[mount]
drive_letter = Z

[cache]
enabled = {true_val}
"""
            config_path = tmp_path / f"bool_test_{true_val}.ini"
            config_path.write_text(config_content, encoding="utf-8")

            config = load_config(str(config_path))
            assert config.cache.enabled is True, f"Failed for value: {true_val}"

    def test_boolean_false_variations(self, tmp_path: Path):
        """Test that various 'false' representations parse correctly."""
        for false_val in ["false", "False", "FALSE", "0", "no", "No", "NO"]:
            config_content = f"""[ftp]
host = test.server.com

[mount]
drive_letter = Z

[cache]
enabled = {false_val}

[logging]
console = {false_val}
"""
            config_path = tmp_path / f"bool_test_{false_val}.ini"
            config_path.write_text(config_content, encoding="utf-8")

            config = load_config(str(config_path))
            assert config.cache.enabled is False, f"Failed for enabled with: {false_val}"
            assert config.logging.console is False, f"Failed for console with: {false_val}"


class TestConfigIntegerParsing:
    """Tests for integer value parsing from INI files."""

    def test_integer_values_parsed_correctly(self, tmp_path: Path):
        """Test that integer values are parsed as int, not str."""
        config_content = """[ftp]
host = test.server.com
port = 9999

[mount]
drive_letter = Z

[cache]
directory_ttl_seconds = 100
metadata_ttl_seconds = 200

[connection]
timeout_seconds = 60
retry_attempts = 10
"""
        config_path = tmp_path / "int_test.ini"
        config_path.write_text(config_content, encoding="utf-8")

        config = load_config(str(config_path))

        assert config.ftp.port == 9999
        assert isinstance(config.ftp.port, int)
        assert config.cache.directory_ttl_seconds == 100
        assert isinstance(config.cache.directory_ttl_seconds, int)
        assert config.cache.metadata_ttl_seconds == 200
        assert config.connection.timeout_seconds == 60
        assert config.connection.retry_attempts == 10
