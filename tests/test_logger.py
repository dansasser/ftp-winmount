"""
Unit tests for pyftpdrive.logger module.

Tests cover:
- FileHandler creation when file is specified
- StreamHandler creation when console=True
- Log level setting
- Log format validation (timestamp, level, thread name)
"""

import logging
from pathlib import Path

import pytest

from pyftpdrive.config import LogConfig
from pyftpdrive.logger import LOG_FORMAT, setup_logging


class TestSetupLoggingFileHandler:
    """Tests for file handler creation."""

    def test_file_handler_created_when_file_specified(self, tmp_path: Path):
        """Test that FileHandler is created when config.file is set."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]

        assert len(file_handlers) == 1
        assert Path(file_handlers[0].baseFilename) == log_file

        # Cleanup
        root_logger.handlers.clear()

    def test_file_handler_not_created_when_file_empty(self):
        """Test that FileHandler is not created when config.file is empty."""
        config = LogConfig(level="INFO", file="", console=True)

        setup_logging(config)

        root_logger = logging.getLogger()
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]

        assert len(file_handlers) == 0

        # Cleanup
        root_logger.handlers.clear()

    def test_file_handler_creates_parent_directories(self, tmp_path: Path):
        """Test that parent directories are created if they don't exist."""
        nested_log_file = tmp_path / "subdir" / "nested" / "test.log"
        config = LogConfig(level="INFO", file=str(nested_log_file), console=False)

        setup_logging(config)

        # Parent directory should be created
        assert nested_log_file.parent.exists()

        root_logger = logging.getLogger()
        root_logger.handlers.clear()

    def test_file_handler_appends_to_existing_file(self, tmp_path: Path):
        """Test that file handler appends to existing log file."""
        log_file = tmp_path / "existing.log"
        log_file.write_text("existing content\n", encoding="utf-8")

        config = LogConfig(level="INFO", file=str(log_file), console=False)
        setup_logging(config)

        # Write a log message
        logger = logging.getLogger()
        logger.info("new log message")

        # Force flush
        for handler in logger.handlers:
            handler.flush()

        # Check content
        content = log_file.read_text(encoding="utf-8")
        assert "existing content" in content
        assert "new log message" in content

        logger.handlers.clear()


class TestSetupLoggingConsoleHandler:
    """Tests for console handler creation."""

    def test_console_handler_created_when_console_true(self, tmp_path: Path):
        """Test that StreamHandler is created when config.console=True."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=True)

        setup_logging(config)

        root_logger = logging.getLogger()
        stream_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]

        assert len(stream_handlers) == 1

        root_logger.handlers.clear()

    def test_console_handler_not_created_when_console_false(self, tmp_path: Path):
        """Test that StreamHandler is not created when config.console=False."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        stream_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]

        assert len(stream_handlers) == 0

        root_logger.handlers.clear()

    def test_console_handler_uses_stderr(self, tmp_path: Path):
        """Test that StreamHandler writes to stderr."""
        import sys

        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=True)

        setup_logging(config)

        root_logger = logging.getLogger()
        stream_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]

        assert len(stream_handlers) == 1
        assert stream_handlers[0].stream is sys.stderr

        root_logger.handlers.clear()


class TestSetupLoggingLevel:
    """Tests for log level setting."""

    @pytest.mark.parametrize(
        "level_str,expected_level",
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ],
    )
    def test_log_level_set_correctly(self, tmp_path: Path, level_str: str, expected_level: int):
        """Test that log level is set correctly from config."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level=level_str, file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        assert root_logger.level == expected_level

        root_logger.handlers.clear()

    def test_log_level_case_insensitive(self, tmp_path: Path):
        """Test that log level parsing is case insensitive."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="debug", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

        root_logger.handlers.clear()

    def test_invalid_log_level_defaults_to_info(self, tmp_path: Path):
        """Test that invalid log level defaults to INFO."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INVALID_LEVEL", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

        root_logger.handlers.clear()

    def test_handler_level_matches_root_level(self, tmp_path: Path):
        """Test that handler level matches root logger level."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="WARNING", file=str(log_file), console=True)

        setup_logging(config)

        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            assert handler.level == logging.WARNING

        root_logger.handlers.clear()


class TestSetupLoggingFormat:
    """Tests for log format validation."""

    def test_log_format_includes_timestamp(self, tmp_path: Path):
        """Test that log format includes timestamp."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        root_logger.info("test message")

        for handler in root_logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        # Timestamp format: YYYY-MM-DD HH:MM:SS,mmm
        assert "-" in content  # Date separators
        assert ":" in content  # Time separators

        root_logger.handlers.clear()

    def test_log_format_includes_level(self, tmp_path: Path):
        """Test that log format includes log level."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        root_logger.info("test message")
        root_logger.warning("warning message")

        for handler in root_logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "INFO" in content
        assert "WARNING" in content

        root_logger.handlers.clear()

    def test_log_format_includes_thread_name(self, tmp_path: Path):
        """Test that log format includes thread name."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        root_logger.info("test message")

        for handler in root_logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        # MainThread is the default thread name
        assert "MainThread" in content or "Thread" in content

        root_logger.handlers.clear()

    def test_log_format_includes_message(self, tmp_path: Path):
        """Test that log format includes the actual message."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        test_message = "this is a unique test message 12345"
        root_logger.info(test_message)

        for handler in root_logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert test_message in content

        root_logger.handlers.clear()

    def test_log_format_constant_matches_expected(self):
        """Test that LOG_FORMAT constant has expected placeholders."""
        assert "%(asctime)s" in LOG_FORMAT
        assert "%(levelname)s" in LOG_FORMAT
        assert "%(threadName)s" in LOG_FORMAT
        assert "%(message)s" in LOG_FORMAT


class TestSetupLoggingHandlerManagement:
    """Tests for handler management."""

    def test_existing_handlers_cleared(self, tmp_path: Path):
        """Test that existing handlers are cleared before adding new ones."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=True)

        # Setup logging twice
        setup_logging(config)
        setup_logging(config)

        root_logger = logging.getLogger()

        # Should not have duplicate handlers
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]
        stream_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]

        assert len(file_handlers) == 1
        assert len(stream_handlers) == 1

        root_logger.handlers.clear()

    def test_file_handler_uses_utf8_encoding(self, tmp_path: Path):
        """Test that file handler uses UTF-8 encoding."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]

        assert len(file_handlers) == 1
        assert file_handlers[0].encoding == "utf-8"

        root_logger.handlers.clear()

    def test_file_handler_append_mode(self, tmp_path: Path):
        """Test that file handler uses append mode."""
        log_file = tmp_path / "test.log"
        config = LogConfig(level="INFO", file=str(log_file), console=False)

        setup_logging(config)

        root_logger = logging.getLogger()
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]

        assert len(file_handlers) == 1
        assert file_handlers[0].mode == "a"

        root_logger.handlers.clear()


class TestSetupLoggingIntegration:
    """Integration tests for logging setup."""

    def test_full_logging_workflow(self, tmp_path: Path):
        """Test complete logging workflow with file and console."""
        log_file = tmp_path / "integration.log"
        config = LogConfig(level="DEBUG", file=str(log_file), console=False)

        setup_logging(config)

        logger = logging.getLogger("test.integration")
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")

        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")

        assert "debug message" in content
        assert "info message" in content
        assert "warning message" in content
        assert "error message" in content
        assert "DEBUG" in content
        assert "INFO" in content
        assert "WARNING" in content
        assert "ERROR" in content

        root_logger.handlers.clear()

    def test_log_messages_filtered_by_level(self, tmp_path: Path):
        """Test that messages below log level are filtered."""
        log_file = tmp_path / "filtered.log"
        config = LogConfig(level="WARNING", file=str(log_file), console=False)

        setup_logging(config)

        logger = logging.getLogger("test.filtered")
        logger.debug("debug message should not appear")
        logger.info("info message should not appear")
        logger.warning("warning message should appear")
        logger.error("error message should appear")

        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")

        assert "debug message should not appear" not in content
        assert "info message should not appear" not in content
        assert "warning message should appear" in content
        assert "error message should appear" in content

        root_logger.handlers.clear()
