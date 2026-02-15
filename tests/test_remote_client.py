"""
Tests for the RemoteClient Protocol.

Verifies that both FTPClient and SFTPClient satisfy the RemoteClient protocol,
ensuring they can be used interchangeably by FTPFileSystem.
"""

from ftp_winmount.ftp_client import FTPClient
from ftp_winmount.remote_client import RemoteClient
from ftp_winmount.sftp_client import SFTPClient


class TestRemoteClientProtocol:
    """Verify that concrete client classes satisfy the RemoteClient protocol."""

    def test_ftp_client_is_remote_client(self):
        """FTPClient should satisfy the RemoteClient protocol."""
        assert issubclass(FTPClient, RemoteClient) or isinstance(
            FTPClient, type
        ), "FTPClient must be compatible with RemoteClient"
        # Check all required methods exist
        required_methods = [
            "connect",
            "disconnect",
            "list_dir",
            "get_file_info",
            "read_file",
            "write_file",
            "create_file",
            "create_dir",
            "delete_file",
            "delete_dir",
            "rename",
        ]
        for method in required_methods:
            assert hasattr(FTPClient, method), f"FTPClient missing method: {method}"

    def test_sftp_client_is_remote_client(self):
        """SFTPClient should satisfy the RemoteClient protocol."""
        assert issubclass(SFTPClient, RemoteClient) or isinstance(
            SFTPClient, type
        ), "SFTPClient must be compatible with RemoteClient"
        required_methods = [
            "connect",
            "disconnect",
            "list_dir",
            "get_file_info",
            "read_file",
            "write_file",
            "create_file",
            "create_dir",
            "delete_file",
            "delete_dir",
            "rename",
        ]
        for method in required_methods:
            assert hasattr(SFTPClient, method), f"SFTPClient missing method: {method}"

    def test_runtime_checkable_ftp(self, ftp_config, conn_config):
        """FTPClient instance passes runtime isinstance check."""
        client = FTPClient(ftp_config, conn_config)
        assert isinstance(client, RemoteClient)

    def test_runtime_checkable_sftp(self, ssh_config, conn_config):
        """SFTPClient instance passes runtime isinstance check."""
        client = SFTPClient(ssh_config, conn_config)
        assert isinstance(client, RemoteClient)
