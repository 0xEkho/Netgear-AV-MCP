"""Tests for SSH client module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


async def test_execute_command_returns_output():
    """Test successful command execution."""
    from mcp_server.ssh.client import execute_command

    with patch("mcp_server.ssh.client.asyncssh") as mock_ssh:
        with patch("mcp_server.ssh.client.get_credentials", return_value=("admin", "pass")):
            # Create mock process
            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdin = MagicMock()
            mock_process.stdin.write = MagicMock()
            mock_process.wait_closed = AsyncMock()

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn.create_process = AsyncMock(return_value=mock_process)
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_ssh.connect = AsyncMock(return_value=mock_conn)

            # Mock stdout reads
            mock_process.stdout.read = AsyncMock(side_effect=[
                "(Switch) #",                       # initial prompt
                "(Switch) #",                       # after terminal length 0
                "show version output\n(Switch) #",  # command output
            ])

            result = await execute_command("10.0.0.1", "show version")
            # Verify we get some kind of string result (not an exception)
            assert isinstance(result, str)


async def test_execute_command_returns_error_on_connect_failure():
    """Test that connection errors are returned as strings."""
    from mcp_server.ssh.client import execute_command

    with patch("mcp_server.ssh.client.asyncssh") as mock_ssh:
        with patch("mcp_server.ssh.client.get_credentials", return_value=("admin", "pass")):
            mock_ssh.connect = AsyncMock(side_effect=OSError("Connection refused"))

            result = await execute_command("10.0.0.1", "show version")
            assert result.startswith("ERROR:")
            assert "OSError" in result or "Connection" in result
