"""
PyFTPDrive - Main Entry Point

This module provides the CLI interface and wires up all components
to mount an FTP server as a local Windows drive using WinFsp.
"""

import argparse
import logging
import subprocess
import sys
import time

from .config import load_config
from .filesystem import WINFSPY_AVAILABLE, FTPFileSystem
from .ftp_client import FTPClient
from .logger import setup_logging

if WINFSPY_AVAILABLE:
    from winfspy import FileSystem, FileSystemAlreadyStarted, FileSystemNotStarted
    from winfspy.plumbing.win32_filetime import filetime_now

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="PyFTPDrive - Mount FTP as Local Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pyftpdrive mount --host 192.168.0.130 --port 2121 --drive Z
  pyftpdrive mount --config config.ini
  pyftpdrive unmount --drive Z
  pyftpdrive status
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
    mount_parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    # Unmount command
    unmount_parser = subparsers.add_parser("unmount", help="Unmount a drive")
    unmount_parser.add_argument("--drive", required=True, help="Drive letter to unmount")

    # Status command
    subparsers.add_parser("status", help="Show mounted drives")

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
            debug=args.verbose,
        )

        # 2. Setup Logging
        setup_logging(config.logging)
        logger.info("Starting PyFTPDrive v0.1.0")
        logger.info(
            "Mounting %s:%d to %s:", config.ftp.host, config.ftp.port, config.mount.drive_letter
        )

        # 3. Check WinFsp availability
        if not WINFSPY_AVAILABLE:
            logger.error("WinFsp is not installed or winfspy package not found.")
            print("[ERROR] WinFsp is required but not installed.")
            print("Please install WinFsp from: https://winfsp.dev/")
            print("Then install winfspy: pip install winfspy")
            return 1

        # 4. Initialize FTP Client
        logger.info("Connecting to FTP server...")
        ftp_client = FTPClient(config.ftp, config.connection)
        try:
            ftp_client.connect()
            logger.info("FTP connection established")
        except ConnectionError as e:
            logger.error("Failed to connect to FTP server: %s", e)
            print(f"[ERROR] Could not connect to FTP server at {config.ftp.host}:{config.ftp.port}")
            print(f"        {e}")
            return 1
        except PermissionError as e:
            logger.error("FTP authentication failed: %s", e)
            print(f"[ERROR] FTP authentication failed: {e}")
            return 1
        except TimeoutError as e:
            logger.error("FTP connection timed out: %s", e)
            print(f"[ERROR] Connection to {config.ftp.host}:{config.ftp.port} timed out")
            return 1

        # 5. Initialize Filesystem
        logger.info("Initializing FTP filesystem...")
        ftp_fs_ops = FTPFileSystem(ftp_client, config.cache)

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
        protocol = "FTPS" if config.ftp.secure else "FTP"
        print(f"[OK] {protocol} server mounted at {mountpoint}")
        print(f"     Host: {config.ftp.host}:{config.ftp.port}")
        if config.ftp.secure:
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
                logger.info("Disconnecting from FTP...")
                ftp_client.disconnect()
                logger.info("FTP disconnected")
            except Exception as e:
                logger.warning("Error disconnecting FTP: %s", e)


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


def main():
    """Main entry point."""
    args = parse_args()

    if args.command == "mount":
        return cmd_mount(args)
    elif args.command == "unmount":
        return cmd_unmount(args)
    elif args.command == "status":
        return cmd_status(args)
    else:
        print("Usage: pyftpdrive <command> [options]")
        print()
        print("Commands:")
        print("  mount    Mount an FTP server as a local drive")
        print("  unmount  Unmount a drive")
        print("  status   Show mounted drives")
        print()
        print("Run 'pyftpdrive <command> --help' for more information.")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
