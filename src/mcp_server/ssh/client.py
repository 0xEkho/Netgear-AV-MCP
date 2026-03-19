"""
Async SSH client for NETGEAR M4250/M4300/M4350 switches.

Uses *asyncssh* to open a one-shot SSH connection with an interactive shell,
execute a single CLI command, and return the output as a plain string.

NETGEAR switches require interactive shell mode:
 - Connect via SSH
 - Open interactive shell (``create_process`` with ``term_type``)
 - Wait for initial prompt
 - Send ``terminal length 0`` to disable paging
 - Send the actual command
 - Collect output until the prompt returns
 - Strip ANSI escape codes and pager artifacts

Errors are **never raised** — they are returned as
``"ERROR: <Type>: <message>"``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

import asyncssh

from mcp_server.ssh.auth import get_credentials

logging.basicConfig(stream=sys.stderr)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment-based tunables
# ---------------------------------------------------------------------------
_CONNECT_TIMEOUT: int = int(os.getenv("SSH_CONNECT_TIMEOUT", "10"))
_COMMAND_TIMEOUT: int = int(os.getenv("SSH_COMMAND_TIMEOUT", "30"))
_STRICT_HOST_KEY: bool = os.getenv("SSH_STRICT_HOST_KEY", "false").lower() == "true"
_KNOWN_HOSTS_FILE: str | None = os.getenv("SSH_KNOWN_HOSTS_FILE") or None

# ---------------------------------------------------------------------------
# ANSI / pager helpers
# ---------------------------------------------------------------------------
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07|\x1b[()][AB012]|\x1b=|\x1b>")

# NETGEAR pager patterns: --More--, ---More---, (q)uit, Press any key…
_PAGER_RE = re.compile(
    r"-{2,3}More-{2,3}\s*"
    r"|Press any key to continue.*"
    r"|\(q\)uit\s*"
    r"|RETURN for next line.*",
    re.IGNORECASE,
)

# NETGEAR prompt: "(DeviceName) #" or "(DeviceName) >" or just "# " / "> "
_PROMPT_RE = re.compile(r"(?:\(.+?\)\s*[#>]|^[A-Za-z0-9_-]+\s*[#>])\s*$", re.MULTILINE)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


def _clean_output(raw: str, command: str) -> str:
    """Clean switch output: strip ANSI, pager artifacts, echoed command and trailing prompt."""
    text = _strip_ansi(raw)
    text = _PAGER_RE.sub("", text)

    # Remove the echoed command line (first occurrence)
    cmd_escaped = re.escape(command.strip())
    text = re.sub(rf"^.*{cmd_escaped}\s*\r?\n?", "", text, count=1)

    # Remove trailing prompt line
    text = _PROMPT_RE.sub("", text)

    # Collapse excessive blank lines and trim
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def _read_until_prompt(
    process: asyncssh.SSHClientProcess,
    timeout: int,
) -> str:
    """Read from the process stdout until a NETGEAR prompt is detected."""
    buf = ""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            chunk = await asyncio.wait_for(
                process.stdout.read(4096),
                timeout=min(remaining, 2.0),
            )
        except asyncio.TimeoutError:
            # Check if we already have a prompt in the buffer
            if _PROMPT_RE.search(_strip_ansi(buf)):
                break
            continue
        except Exception:
            break

        if not chunk:
            break

        buf += chunk

        # Check for prompt in cleaned buffer
        cleaned = _strip_ansi(buf)
        if _PROMPT_RE.search(cleaned):
            break

    return buf


async def execute_command(host: str, command: str) -> str:
    """Execute a CLI command on a NETGEAR switch via interactive SSH.

    Opens a one-shot SSH connection, sends the command inside an interactive
    shell session, collects output, and returns it as a cleaned string.

    Args:
        host: IP address of the target NETGEAR switch.
        command: CLI command to execute (e.g. ``"show version"``).

    Returns:
        Cleaned command output as a string, or an ``"ERROR: …"`` string on
        failure.
    """
    username, password = get_credentials(host)

    known_hosts: object = _KNOWN_HOSTS_FILE if _STRICT_HOST_KEY else None

    try:
        conn = await asyncio.wait_for(
            asyncssh.connect(
                host,
                username=username,
                password=password,
                known_hosts=known_hosts,
            ),
            timeout=_CONNECT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return f"ERROR: TimeoutError: SSH connection to {host} timed out after {_CONNECT_TIMEOUT}s"
    except OSError as exc:
        return f"ERROR: OSError: Cannot reach {host}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"

    try:
        async with conn:
            # Open interactive shell
            process = await conn.create_process(
                term_type="xterm",
                term_size=(200, 24),
            )

            # Wait for initial prompt
            await _read_until_prompt(process, timeout=_CONNECT_TIMEOUT)

            # Disable paging
            process.stdin.write("terminal length 0\n")
            await _read_until_prompt(process, timeout=5)

            # Send the actual command
            process.stdin.write(command.strip() + "\n")
            raw_output = await _read_until_prompt(process, timeout=_COMMAND_TIMEOUT)

            # Close gracefully
            process.stdin.write("exit\n")
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()

            return _clean_output(raw_output, command)

    except asyncio.TimeoutError:
        return f"ERROR: TimeoutError: Command '{command}' timed out after {_COMMAND_TIMEOUT}s on {host}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"
