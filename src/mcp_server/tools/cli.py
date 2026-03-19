"""
Generic read-only CLI tool for NETGEAR AV switches.

Allows executing arbitrary ``show`` commands on NETGEAR switches.  Only
commands starting with ``show `` are accepted (security: read-only).
"""

from __future__ import annotations

import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from mcp_server.ssh.client import execute_command

logging.basicConfig(stream=sys.stderr)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register the generic CLI tool on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_cli_readonly(host: str, command: str) -> str:
        """Execute a read-only CLI command on a NETGEAR switch.

        Only commands starting with ``show `` are allowed.  The raw output
        is returned as JSON together with the host and command.

        Args:
            host: IP address of the target NETGEAR switch.
            command: CLI command to execute (must start with ``show ``).
        """
        normalized = command.strip().lower()
        if not normalized.startswith("show "):
            return json.dumps(
                {
                    "host": host,
                    "command": command,
                    "error": "Only 'show' commands are allowed (read-only mode).",
                },
                indent=2,
            )

        output = await execute_command(host, command.strip())
        if output.startswith("ERROR:"):
            return output
        return json.dumps(
            {"host": host, "command": command.strip(), "output": output},
            indent=2,
        )
