import logging
import sys
from .config import LogConfig

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
    # TODO: Implement logging setup
    raise NotImplementedError("Logging setup not implemented")
