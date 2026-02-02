import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class FTPConfig:
    host: str
    port: int = 21
    username: Optional[str] = None
    password: Optional[str] = None
    passive_mode: bool = True
    encoding: str = "utf-8"

@dataclass
class MountConfig:
    drive_letter: str
    volume_label: str = "FTP Drive"

@dataclass
class CacheConfig:
    enabled: bool = True
    directory_ttl_seconds: int = 30
    metadata_ttl_seconds: int = 60

@dataclass
class ConnectionConfig:
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: int = 1
    keepalive_interval_seconds: int = 60

@dataclass
class LogConfig:
    level: str = "INFO"
    file: str = "pyftpdrive.log"
    console: bool = True

@dataclass
class AppConfig:
    ftp: FTPConfig
    mount: MountConfig
    cache: CacheConfig
    connection: ConnectionConfig
    logging: LogConfig

def load_config(config_path: Optional[str] = None, **cli_args) -> AppConfig:
    """
    Load configuration from an INI file and/or CLI arguments.
    CLI arguments take precedence over config file.

    Args:
        config_path: Path to the INI configuration file.
        **cli_args: Key-value pairs from command line arguments.

    Returns:
        AppConfig: The populated configuration object.

    Raises:
        FileNotFoundError: If config_path is provided but does not exist.
        ValueError: If required fields (host, drive_letter) are missing.
    """
    # TODO: Implement configuration loading logic
    # 1. Parse INI file if provided
    # 2. Override with CLI arguments
    # 3. Validate required fields
    # 4. Return AppConfig
    raise NotImplementedError("Configuration loading not implemented")
