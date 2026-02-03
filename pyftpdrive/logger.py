import logging
import sys
from pathlib import Path

from .config import LogConfig

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(threadName)s - %(message)s"


def setup_logging(config: LogConfig) -> None:
    """
    Configure the global logging configuration.

    Args:
        config: LogConfig object containing settings.

    Note:
        - Should set up a FileHandler if config.file is set.
        - Should set up a StreamHandler (stderr) if config.console is True.
        - Should set the logging level based on config.level.
        - Format should include timestamp, level, thread name, and message.
    """
    # Get numeric logging level from string
    level = getattr(logging, config.level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT)

    # Set up FileHandler if config.file is set
    if config.file:
        log_path = Path(config.file)
        # Create log directory if it doesn't exist
        if log_path.parent and not log_path.parent.exists():
            log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set up StreamHandler (stderr) if config.console is True
    if config.console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
