import sys
import argparse
import logging
from .config import load_config
from .logger import setup_logging
# from .ftp_client import FTPClient
# from .filesystem import FTPFileSystem
# from winfspy import Mount

def parse_args():
    parser = argparse.ArgumentParser(description="PyFTPDrive - Mount FTP as Local Drive")

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
    mount_parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    # Unmount command
    unmount_parser = subparsers.add_parser("unmount", help="Unmount a drive")
    unmount_parser.add_argument("--drive", required=True, help="Drive letter to unmount")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show running mounts")

    return parser.parse_args()

def main():
    args = parse_args()

    if args.command == "mount":
        try:
            # 1. Load Configuration
            config = load_config(
                config_path=args.config,
                host=args.host,
                port=args.port,
                username=args.user,
                password=args.password,
                drive_letter=args.drive,
                debug=args.verbose
            )

            # 2. Setup Logging
            setup_logging(config.logging)
            logging.info(f"Starting PyFTPDrive v0.1.0")
            logging.info(f"Mounting {config.ftp.host} to {config.mount.drive_letter}:")

            # 3. Initialize FTP Client
            # ftp_client = FTPClient(config.ftp, config.connection)
            # ftp_client.connect()

            # 4. Initialize Filesystem
            # fs = FTPFileSystem(ftp_client, config.cache)

            # 5. Mount
            # mount = Mount(config.mount.drive_letter, fs)
            # mount.start()

            logging.info("Mount successful. Press Ctrl+C to stop.")

            # Keep alive
            # while True:
            #     time.sleep(1)

        except KeyboardInterrupt:
            logging.info("Stopping...")
            # mount.stop()
        except Exception as e:
            logging.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)

    elif args.command == "unmount":
        print(f"Unmounting {args.drive}...")
        # TODO: Implement unmount logic (usually via 'net use /delete')

    else:
        print("Usage: pyftpdrive <command> [options]")
        sys.exit(1)

if __name__ == "__main__":
    main()
