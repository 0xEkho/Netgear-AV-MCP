"""Tests for SSH client module — pure helpers and execute_command."""

import asyncio

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mcp_server.ssh.client import _strip_ansi, _clean_output


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper tests
# ═══════════════════════════════════════════════════════════════════════════

def test_strip_ansi_removes_escape_codes():
    """Remove standard ANSI escape sequences from text."""
    raw = "\x1b[32mGreen text\x1b[0m and \x1b[1;31mred bold\x1b[0m"
    assert _strip_ansi(raw) == "Green text and red bold"


def test_strip_ansi_preserves_clean_text():
    """Return clean text unchanged."""
    assert _strip_ansi("hello world") == "hello world"


def test_strip_ansi_removes_xterm_title():
    """Remove xterm title-set sequences (OSC)."""
    raw = "\x1b]0;Switch Title\x07Normal text"
    assert _strip_ansi(raw) == "Normal text"


def test_clean_output_removes_command_echo():
    """Strip echoed command from output."""
    raw = "show version\r\nMachine Model........ M4250\r\n(Switch) #"
    result = _clean_output(raw, "show version")
    assert "show version" not in result
    assert "Machine Model" in result


def test_clean_output_removes_prompt():
    """Strip trailing NETGEAR prompt."""
    raw = "some data\r\n(MySwitch) #"
    result = _clean_output(raw, "dummy")
    assert "(MySwitch) #" not in result
    assert "some data" in result


def test_clean_output_removes_pager():
    """Strip --More-- pager artifacts."""
    raw = "line 1\n--More-- \nline 2\n---More---\nline 3"
    result = _clean_output(raw, "dummy")
    assert "--More--" not in result
    assert "line 1" in result
    assert "line 2" in result
    assert "line 3" in result


def test_clean_output_removes_carriage_returns():
    """Collapse \\r characters."""
    raw = "line 1\r\nline 2\r\n"
    result = _clean_output(raw, "dummy")
    assert "\r" not in result


# ═══════════════════════════════════════════════════════════════════════════
# execute_command tests
# ═══════════════════════════════════════════════════════════════════════════

async def test_execute_command_returns_output():
    """Successful command execution returns cleaned string."""
    from mcp_server.ssh.client import execute_command

    with patch("mcp_server.ssh.client.asyncssh") as mock_ssh:
        with patch("mcp_server.ssh.client.get_credentials", return_value=("admin", "pass")):
            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdin = MagicMock()
            mock_process.stdin.write = MagicMock()
            mock_process.wait = AsyncMock()

            mock_conn = AsyncMock()
            mock_conn.create_process = AsyncMock(return_value=mock_process)
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_ssh.connect = AsyncMock(return_value=mock_conn)

            mock_process.stdout.read = AsyncMock(side_effect=[
                "(Switch) #",
                "(Switch) #",
                "show version output\n(Switch) #",
            ])

            result = await execute_command("10.0.0.1", "show version")
            assert isinstance(result, str)


async def test_execute_command_returns_error_on_connect_failure():
    """Connection errors returned as ERROR: strings."""
    from mcp_server.ssh.client import execute_command

    with patch("mcp_server.ssh.client.asyncssh") as mock_ssh:
        with patch("mcp_server.ssh.client.get_credentials", return_value=("admin", "pass")):
            mock_ssh.connect = AsyncMock(side_effect=OSError("Connection refused"))

            result = await execute_command("10.0.0.1", "show version")
            assert result.startswith("ERROR:")
            assert "OSError" in result


async def test_execute_command_returns_error_on_timeout():
    """SSH connect timeout returned as ERROR: string."""
    from mcp_server.ssh.client import execute_command

    with patch("mcp_server.ssh.client.asyncssh") as mock_ssh:
        with patch("mcp_server.ssh.client.get_credentials", return_value=("admin", "pass")):
            mock_ssh.connect = AsyncMock(side_effect=asyncio.TimeoutError())

            result = await execute_command("10.0.0.1", "show version")
            assert result.startswith("ERROR:")
            assert "TimeoutError" in result
