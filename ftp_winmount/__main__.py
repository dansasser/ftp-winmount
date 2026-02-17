"""
FTP-WinMount - Main Entry Point

This module provides the CLI interface and wires up all components
to mount a remote server (FTP or SFTP) as a local Windows drive using WinFsp.
"""

import argparse
import logging
import subprocess
import sys
import time

from .config import load_config
from .filesystem import WINFSPY_AVAILABLE, FTPFileSystem
from .ftp_client import FTPClient
from .gdrive_client import GoogleDriveClient
from .logger import setup_logging
from .sftp_client import SFTPClient

if WINFSPY_AVAILABLE:
    from winfspy import FileSystem, FileSystemAlreadyStarted, FileSystemNotStarted
    from winfspy.plumbing.win32_filetime import filetime_now

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="FTP-WinMount - Mount FTP/SFTP as Local Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ftp-winmount mount --host 192.168.0.130 --port 2121 --drive Z
  ftp-winmount mount --protocol sftp --host myserver.com --key-file ~/.ssh/id_rsa --drive Z
  ftp-winmount mount --config config.ini
  ftp-winmount unmount --drive Z
  ftp-winmount status
        """,
    )

    # Mode selection
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Mount command
    mount_parser = subparsers.add_parser("mount", help="Mount an FTP server")
    mount_parser.add_argument("--config", help="Path to configuration file")
    mount_parser.add_argument("--host", help="FTP Host")
    mount_parser.add_argument("--port", type=int, help="FTP Port")
    mount_parser.add_argument("--user", help="FTP Username")
    mount_parser.add_argument("--password", help="FTP Password")
    mount_parser.add_argument("--drive", help="Drive letter to mount (e.g. Z)")
    mount_parser.add_argument("--secure", action="store_true", help="Use FTPS (FTP over TLS)")
    mount_parser.add_argument(
        "--protocol",
        choices=["ftp", "ftps", "sftp", "gdrive"],
        default=None,
        help="Protocol to use (default: ftp)",
    )
    mount_parser.add_argument("--key-file", help="Path to SSH private key (SFTP only)")
    mount_parser.add_argument("--key-passphrase", help="Passphrase for encrypted SSH key")
    mount_parser.add_argument("--client-secrets", help="Path to Google OAuth client_secrets.json")
    mount_parser.add_argument("--root-folder", help="Google Drive folder to mount (default: root)")
    mount_parser.add_argument("--shared-drive", help="Name or ID of shared/team drive")
    mount_parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    # Unmount command
    unmount_parser = subparsers.add_parser("unmount", help="Unmount a drive")
    unmount_parser.add_argument("--drive", required=True, help="Drive letter to unmount")

    # Status command
    subparsers.add_parser("status", help="Show mounted drives")

    # Auth command (Google Drive OAuth setup)
    auth_parser = subparsers.add_parser("auth", help="Authenticate with a cloud service")
    auth_parser.add_argument("service", choices=["google"], help="Service to authenticate with")
    auth_parser.add_argument(
        "--client-secrets", required=True, help="Path to Google OAuth client_secrets.json"
    )
    auth_parser.add_argument(
        "--token-file", help="Where to save the token (default: ~/.ftp-winmount/gdrive-token.json)"
    )

    return parser.parse_args()


def cmd_mount(args):
    """
    Handle the mount command.

    Loads configuration, connects to FTP, creates filesystem, and mounts.
    Blocks until Ctrl+C is pressed.
    """
    ftp_client = None
    fs = None

    try:
        # 1. Load Configuration
        config = load_config(
            config_path=args.config,
            host=args.host,
            port=args.port,
            username=args.user,
            password=args.password,
            drive_letter=args.drive,
            secure=args.secure if args.secure else None,
            protocol=args.protocol,
            key_file=getattr(args, "key_file", None),
            key_passphrase=getattr(args, "key_passphrase", None),
            client_secrets=getattr(args, "client_secrets", None),
            root_folder=getattr(args, "root_folder", None),
            shared_drive=getattr(args, "shared_drive", None),
            debug=args.verbose,
        )

        # 2. Setup Logging
        setup_logging(config.logging)
        from . import __version__

        logger.info("Starting FTP-WinMount v%s", __version__)
        if config.protocol == "gdrive":
            logger.info("Mounting Google Drive to %s:", config.mount.drive_letter)
        elif config.protocol == "sftp":
            logger.info(
                "Mounting %s:%d to %s:",
                config.ssh.host,
                config.ssh.port,
                config.mount.drive_letter,
            )
        else:
            logger.info(
                "Mounting %s:%d to %s:",
                config.ftp.host,
                config.ftp.port,
                config.mount.drive_letter,
            )

        # 3. Check WinFsp availability
        if not WINFSPY_AVAILABLE:
            logger.error("WinFsp is not installed or winfspy package not found.")
            print("[ERROR] WinFsp is required but not installed.")
            print("Please install WinFsp from: https://winfsp.dev/")
            print("Then install winfspy: pip install winfspy")
            return 1

        # 4. Initialize Remote Client (FTP, SFTP, or Google Drive)
        if config.protocol == "gdrive":
            logger.info("Connecting to Google Drive...")
            remote_client = GoogleDriveClient(config.gdrive, config.connection)
            server_desc = "Google Drive"
        elif config.protocol == "sftp":
            logger.info("Connecting to SSH/SFTP server...")
            remote_client = SFTPClient(config.ssh, config.connection)
            server_desc = f"{config.ssh.host}:{config.ssh.port}"
        else:
            logger.info("Connecting to FTP server...")
            remote_client = FTPClient(config.ftp, config.connection)
            server_desc = f"{config.ftp.host}:{config.ftp.port}"

        ftp_client = remote_client  # Keep variable name for cleanup block
        try:
            remote_client.connect()
            logger.info("Connection established")
        except ConnectionError as e:
            logger.error("Failed to connect to server: %s", e)
            print(f"[ERROR] Could not connect to server at {server_desc}")
            print(f"        {e}")
            return 1
        except PermissionError as e:
            logger.error("Authentication failed: %s", e)
            print(f"[ERROR] Authentication failed: {e}")
            return 1
        except TimeoutError as e:
            logger.error("Connection timed out: %s", e)
            print(f"[ERROR] Connection to {server_desc} timed out")
            return 1

        # 5. Initialize Filesystem
        logger.info("Initializing filesystem...")
        ftp_fs_ops = FTPFileSystem(remote_client, config.cache)

        # 6. Create WinFsp FileSystem
        mountpoint = f"{config.mount.drive_letter}:"
        logger.info("Creating mount at %s", mountpoint)

        try:
            fs = FileSystem(
                mountpoint,
                ftp_fs_ops,
                debug=config.logging.level.upper() == "DEBUG",
                # Volume parameters
                sector_size=512,
                sectors_per_allocation_unit=1,
                volume_creation_time=filetime_now(),
                file_info_timeout=1000,  # 1 second cache
                case_sensitive_search=0,  # Windows is case-insensitive
                case_preserved_names=1,
                unicode_on_disk=1,
                persistent_acls=0,  # FTP doesn't support Windows ACLs
                volume_serial_number=0,
                file_system_name="FTP",
                post_cleanup_when_modified_only=1,
                um_file_context_is_user_context2=1,
            )
        except Exception as e:
            logger.error("Failed to create FileSystem: %s", e)
            print(f"[ERROR] Failed to create mount: {e}")
            print("        Check that WinFsp is installed and the drive letter is available.")
            return 1

        # 7. Start the mount
        logger.info("Starting mount...")
        try:
            fs.start()
        except FileSystemAlreadyStarted:
            logger.error("Filesystem already started")
            print("[ERROR] Filesystem already started")
            return 1
        except Exception as e:
            logger.error("Failed to start mount: %s", e)
            print(f"[ERROR] Failed to start mount: {e}")
            if "drive" in str(e).lower() or "in use" in str(e).lower():
                print(f"        Drive {mountpoint} may already be in use.")
            return 1

        logger.info("Mount successful at %s", mountpoint)
        if config.protocol == "gdrive":
            proto_label = "Google Drive"
            host_label = "drive.google.com"
        elif config.protocol == "sftp":
            proto_label = "SFTP"
            host_label = f"{config.ssh.host}:{config.ssh.port}"
        elif config.ftp.secure:
            proto_label = "FTPS"
            host_label = f"{config.ftp.host}:{config.ftp.port}"
        else:
            proto_label = "FTP"
            host_label = f"{config.ftp.host}:{config.ftp.port}"
        print(f"[OK] {proto_label} mounted at {mountpoint}")
        print(f"     Host: {host_label}")
        if config.protocol == "gdrive":
            print("     Mode: Google Drive API")
            if config.gdrive.shared_drive:
                print(f"     Shared Drive: {config.gdrive.shared_drive}")
        elif config.protocol == "sftp":
            print("     Mode: SSH/SFTP")
        elif config.ftp.secure:
            print("     Mode: Secure (TLS)")
        print("     Press Ctrl+C to stop.")

        # 8. Keep alive - block until interrupted
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print()  # Newline after ^C
            logger.info("Received interrupt, stopping...")

        return 0

    except ValueError as e:
        # Configuration validation errors
        print(f"[ERROR] Configuration error: {e}")
        return 1
    except FileNotFoundError as e:
        # Config file not found
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        print(f"[ERROR] Fatal error: {e}")
        return 1
    finally:
        # Cleanup
        if fs is not None:
            try:
                logger.info("Stopping filesystem...")
                fs.stop()
                logger.info("Filesystem stopped")
                print("[OK] Mount stopped")
            except FileSystemNotStarted:
                pass  # Already stopped
            except Exception as e:
                logger.warning("Error stopping filesystem: %s", e)

        if ftp_client is not None:
            try:
                logger.info("Disconnecting from server...")
                ftp_client.disconnect()
                logger.info("Disconnected")
            except Exception as e:
                logger.warning("Error disconnecting: %s", e)


def cmd_unmount(args):
    """
    Handle the unmount command.

    Uses 'net use /delete' to forcefully unmount a drive on Windows.
    """
    drive_letter = args.drive.upper().rstrip(":")

    if len(drive_letter) != 1 or not drive_letter.isalpha():
        print(f"[ERROR] Invalid drive letter: {args.drive}")
        return 1

    mountpoint = f"{drive_letter}:"
    print(f"Unmounting {mountpoint}...")

    try:
        # Use 'net use /delete' to unmount
        result = subprocess.run(
            ["net", "use", mountpoint, "/delete", "/y"], capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            print(f"[OK] Drive {mountpoint} unmounted successfully")
            return 0
        else:
            # net use returns error if drive wasn't a network drive
            # Try checking if it's still accessible
            error_msg = result.stderr.strip() or result.stdout.strip()
            print(f"[ERROR] Failed to unmount {mountpoint}")
            if error_msg:
                print(f"        {error_msg}")
            print("        Note: If this is a WinFsp mount, use Ctrl+C in the mount process.")
            return 1

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Unmount timed out for {mountpoint}")
        return 1
    except FileNotFoundError:
        print("[ERROR] 'net' command not found. Are you on Windows?")
        return 1
    except Exception as e:
        print(f"[ERROR] Failed to unmount: {e}")
        return 1


def cmd_status(args):
    """
    Handle the status command.

    Shows currently mounted drives using 'net use'.
    """
    print("Checking mounted drives...")
    print()

    try:
        result = subprocess.run(["net", "use"], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            output = result.stdout
            if output.strip():
                print(output)
            else:
                print("No network drives mounted.")
            return 0
        else:
            print("Failed to list drives")
            if result.stderr:
                print(result.stderr)
            return 1

    except subprocess.TimeoutExpired:
        print("[ERROR] Command timed out")
        return 1
    except FileNotFoundError:
        print("[ERROR] 'net' command not found. Are you on Windows?")
        return 1
    except Exception as e:
        print(f"[ERROR] Failed to check status: {e}")
        return 1


def cmd_auth(args):
    """
    Handle the auth command.

    Runs the OAuth flow for a cloud service and saves credentials.
    """
    if args.service == "google":
        from .gdrive_auth import get_token_path, run_auth_flow, save_credentials

        try:
            print("[INFO] Authenticating with Google Drive...")
            creds = run_auth_flow(args.client_secrets)
            token_path = get_token_path(getattr(args, "token_file", None))
            save_credentials(creds, token_path)
            print("[OK] Google Drive authorized successfully")
            print(f"     Token saved to: {token_path}")
            print("     You can now mount with: ftp-winmount mount --protocol gdrive --drive Z")
            return 0
        except FileNotFoundError as e:
            print(f"[ERROR] {e}")
            return 1
        except Exception as e:
            print(f"[ERROR] Authentication failed: {e}")
            return 1
    else:
        print(f"[ERROR] Unknown service: {args.service}")
        return 1


def main():
    """Main entry point."""
    args = parse_args()

    if args.command == "mount":
        return cmd_mount(args)
    elif args.command == "unmount":
        return cmd_unmount(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "auth":
        return cmd_auth(args)
    else:
        print("Usage: ftp-winmount <command> [options]")
        print()
        print("Commands:")
        print("  mount    Mount an FTP server as a local drive")
        print("  unmount  Unmount a drive")
        print("  status   Show mounted drives")
        print()
        print("Run 'ftp-winmount <command> --help' for more information.")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
