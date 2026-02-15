import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FTPConfig:
    host: str
    port: int = 21
    username: str | None = None
    password: str | None = None
    passive_mode: bool = True
    encoding: str = "utf-8"
    secure: bool = False  # FTPS (FTP over TLS)


@dataclass
class SSHConfig:
    host: str
    port: int = 22
    username: str | None = None
    password: str | None = None
    key_file: str | None = None  # Path to SSH private key
    key_passphrase: str | None = None  # Passphrase for encrypted keys
    use_agent: bool = True  # Try SSH agent for auth
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
    file: str = "ftp-winmount.log"
    console: bool = True


@dataclass
class AppConfig:
    ftp: FTPConfig
    mount: MountConfig
    cache: CacheConfig
    connection: ConnectionConfig
    logging: LogConfig
    protocol: str = "ftp"  # "ftp", "ftps", or "sftp"
    ssh: SSHConfig | None = None


def load_config(config_path: str | None = None, **cli_args) -> AppConfig:
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
    # Initialize with defaults
    ftp_config = {
        "host": None,
        "port": 21,
        "username": None,
        "password": None,
        "passive_mode": True,
        "encoding": "utf-8",
        "secure": False,
    }
    mount_config = {
        "drive_letter": None,
        "volume_label": "FTP Drive",
    }
    cache_config = {
        "enabled": True,
        "directory_ttl_seconds": 30,
        "metadata_ttl_seconds": 60,
    }
    connection_config = {
        "timeout_seconds": 30,
        "retry_attempts": 3,
        "retry_delay_seconds": 1,
        "keepalive_interval_seconds": 60,
    }
    log_config = {
        "level": "INFO",
        "file": "ftp-winmount.log",
        "console": True,
    }
    ssh_config = {
        "host": None,
        "port": 22,
        "username": None,
        "password": None,
        "key_file": None,
        "key_passphrase": None,
        "use_agent": True,
        "encoding": "utf-8",
    }
    protocol = "ftp"

    # Parse INI file if provided
    if config_path is not None:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        parser = configparser.ConfigParser()
        parser.read(config_file, encoding="utf-8")

        # Load [ftp] section
        if parser.has_section("ftp"):
            ftp_section = parser["ftp"]
            if ftp_section.get("host"):
                ftp_config["host"] = ftp_section.get("host")
            if ftp_section.get("port"):
                try:
                    ftp_config["port"] = int(ftp_section.get("port"))
                except ValueError:
                    raise ValueError(
                        f"Invalid port value in config: '{ftp_section.get('port')}' - must be an integer"
                    )
            if ftp_section.get("username"):
                ftp_config["username"] = ftp_section.get("username") or None
            if ftp_section.get("password"):
                ftp_config["password"] = ftp_section.get("password") or None
            if ftp_section.get("passive_mode"):
                ftp_config["passive_mode"] = ftp_section.get("passive_mode", "true").lower() in (
                    "true",
                    "1",
                    "yes",
                )
            if ftp_section.get("encoding"):
                ftp_config["encoding"] = ftp_section.get("encoding")
            if ftp_section.get("secure"):
                ftp_config["secure"] = ftp_section.get("secure", "false").lower() in (
                    "true",
                    "1",
                    "yes",
                )

        # Load [mount] section
        if parser.has_section("mount"):
            mount_section = parser["mount"]
            if mount_section.get("drive_letter"):
                mount_config["drive_letter"] = mount_section.get("drive_letter")
            if mount_section.get("volume_label"):
                mount_config["volume_label"] = mount_section.get("volume_label")

        # Load [cache] section
        if parser.has_section("cache"):
            cache_section = parser["cache"]
            if cache_section.get("enabled"):
                cache_config["enabled"] = cache_section.get("enabled", "true").lower() in (
                    "true",
                    "1",
                    "yes",
                )
            if cache_section.get("directory_ttl_seconds"):
                try:
                    cache_config["directory_ttl_seconds"] = int(
                        cache_section.get("directory_ttl_seconds")
                    )
                except ValueError:
                    raise ValueError(
                        f"Invalid directory_ttl_seconds value in config: '{cache_section.get('directory_ttl_seconds')}' - must be an integer"
                    )
            if cache_section.get("metadata_ttl_seconds"):
                try:
                    cache_config["metadata_ttl_seconds"] = int(
                        cache_section.get("metadata_ttl_seconds")
                    )
                except ValueError:
                    raise ValueError(
                        f"Invalid metadata_ttl_seconds value in config: '{cache_section.get('metadata_ttl_seconds')}' - must be an integer"
                    )

        # Load [connection] section
        if parser.has_section("connection"):
            conn_section = parser["connection"]
            if conn_section.get("timeout_seconds"):
                try:
                    connection_config["timeout_seconds"] = int(conn_section.get("timeout_seconds"))
                except ValueError:
                    raise ValueError(
                        f"Invalid timeout_seconds value in config: '{conn_section.get('timeout_seconds')}' - must be an integer"
                    )
            if conn_section.get("retry_attempts"):
                try:
                    connection_config["retry_attempts"] = int(conn_section.get("retry_attempts"))
                except ValueError:
                    raise ValueError(
                        f"Invalid retry_attempts value in config: '{conn_section.get('retry_attempts')}' - must be an integer"
                    )
            if conn_section.get("retry_delay_seconds"):
                try:
                    connection_config["retry_delay_seconds"] = int(
                        conn_section.get("retry_delay_seconds")
                    )
                except ValueError:
                    raise ValueError(
                        f"Invalid retry_delay_seconds value in config: '{conn_section.get('retry_delay_seconds')}' - must be an integer"
                    )
            if conn_section.get("keepalive_interval_seconds"):
                try:
                    connection_config["keepalive_interval_seconds"] = int(
                        conn_section.get("keepalive_interval_seconds")
                    )
                except ValueError:
                    raise ValueError(
                        f"Invalid keepalive_interval_seconds value in config: '{conn_section.get('keepalive_interval_seconds')}' - must be an integer"
                    )

        # Load [logging] section
        if parser.has_section("logging"):
            log_section = parser["logging"]
            if log_section.get("level"):
                log_config["level"] = log_section.get("level")
            if log_section.get("file"):
                log_config["file"] = log_section.get("file")
            if log_section.get("console"):
                log_config["console"] = log_section.get("console", "false").lower() in (
                    "true",
                    "1",
                    "yes",
                )

        # Load [ssh] section
        if parser.has_section("ssh"):
            ssh_section = parser["ssh"]
            if ssh_section.get("host"):
                ssh_config["host"] = ssh_section.get("host")
            if ssh_section.get("port"):
                try:
                    ssh_config["port"] = int(ssh_section.get("port"))
                except ValueError:
                    raise ValueError(
                        f"Invalid SSH port value in config: '{ssh_section.get('port')}' - must be an integer"
                    )
            if ssh_section.get("username"):
                ssh_config["username"] = ssh_section.get("username") or None
            if ssh_section.get("password"):
                ssh_config["password"] = ssh_section.get("password") or None
            if ssh_section.get("key_file"):
                ssh_config["key_file"] = ssh_section.get("key_file") or None
            if ssh_section.get("key_passphrase"):
                ssh_config["key_passphrase"] = ssh_section.get("key_passphrase") or None
            if ssh_section.get("use_agent"):
                ssh_config["use_agent"] = ssh_section.get("use_agent", "true").lower() in (
                    "true",
                    "1",
                    "yes",
                )
            if ssh_section.get("encoding"):
                ssh_config["encoding"] = ssh_section.get("encoding")

        # Load protocol from config (can be in [general] or [ftp] section)
        if parser.has_section("general") and parser["general"].get("protocol"):
            protocol = parser["general"]["protocol"].lower()

    # Override with CLI arguments (cli_args take precedence)
    if cli_args.get("protocol") is not None:
        protocol = cli_args["protocol"].lower()
    if cli_args.get("secure") is not None and cli_args["secure"]:
        protocol = "ftps"
    if cli_args.get("host") is not None:
        if protocol == "sftp":
            ssh_config["host"] = cli_args["host"]
        else:
            ftp_config["host"] = cli_args["host"]
    if cli_args.get("port") is not None:
        if protocol == "sftp":
            ssh_config["port"] = int(cli_args["port"])
        else:
            ftp_config["port"] = int(cli_args["port"])
    if cli_args.get("username") is not None:
        if protocol == "sftp":
            ssh_config["username"] = cli_args["username"] or None
        else:
            ftp_config["username"] = cli_args["username"] or None
    if cli_args.get("password") is not None:
        if protocol == "sftp":
            ssh_config["password"] = cli_args["password"] or None
        else:
            ftp_config["password"] = cli_args["password"] or None
    if cli_args.get("drive_letter") is not None:
        mount_config["drive_letter"] = cli_args["drive_letter"]
    if cli_args.get("key_file") is not None:
        ssh_config["key_file"] = cli_args["key_file"]
    if cli_args.get("key_passphrase") is not None:
        ssh_config["key_passphrase"] = cli_args["key_passphrase"]
    if cli_args.get("debug"):
        log_config["level"] = "DEBUG"
        log_config["console"] = True

    # Validate required fields
    missing_fields = []
    if protocol == "sftp":
        if not ssh_config["host"]:
            missing_fields.append("host")
    else:
        if not ftp_config["host"]:
            missing_fields.append("host")
    if not mount_config["drive_letter"]:
        missing_fields.append("drive_letter")

    if missing_fields:
        raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")

    # Normalize drive letter (remove colon if present, uppercase)
    drive_letter = mount_config["drive_letter"].upper().rstrip(":")
    if len(drive_letter) != 1 or not drive_letter.isalpha():
        raise ValueError(
            f"Invalid drive letter: {mount_config['drive_letter']}. Must be a single letter A-Z."
        )
    mount_config["drive_letter"] = drive_letter

    # Handle protocol normalization (ftps sets secure flag on FTP)
    if protocol == "ftps":
        ftp_config["secure"] = True
        protocol = "ftp"  # FTPS uses FTPClient with secure=True

    # Build SSH config object if needed
    ssh_obj = None
    if protocol == "sftp" and ssh_config["host"]:
        ssh_obj = SSHConfig(
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            key_file=ssh_config["key_file"],
            key_passphrase=ssh_config["key_passphrase"],
            use_agent=ssh_config["use_agent"],
            encoding=ssh_config["encoding"],
        )

    # Build and return AppConfig
    return AppConfig(
        ftp=FTPConfig(
            host=ftp_config["host"] or "",
            port=ftp_config["port"],
            username=ftp_config["username"],
            password=ftp_config["password"],
            passive_mode=ftp_config["passive_mode"],
            encoding=ftp_config["encoding"],
            secure=ftp_config["secure"],
        ),
        mount=MountConfig(
            drive_letter=mount_config["drive_letter"],
            volume_label=mount_config["volume_label"],
        ),
        cache=CacheConfig(
            enabled=cache_config["enabled"],
            directory_ttl_seconds=cache_config["directory_ttl_seconds"],
            metadata_ttl_seconds=cache_config["metadata_ttl_seconds"],
        ),
        connection=ConnectionConfig(
            timeout_seconds=connection_config["timeout_seconds"],
            retry_attempts=connection_config["retry_attempts"],
            retry_delay_seconds=connection_config["retry_delay_seconds"],
            keepalive_interval_seconds=connection_config["keepalive_interval_seconds"],
        ),
        logging=LogConfig(
            level=log_config["level"],
            file=log_config["file"],
            console=log_config["console"],
        ),
        protocol=protocol,
        ssh=ssh_obj,
    )
