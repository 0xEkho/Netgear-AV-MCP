"""
LLDP tools for NETGEAR AV switches.

Provides tools to inspect LLDP (Link Layer Discovery Protocol) neighbor
information on NETGEAR M4250/M4300/M4350 managed switches.
"""

from __future__ import annotations

import json
import logging
import re
import sys

from mcp.server.fastmcp import FastMCP

from mcp_server.ssh.client import execute_command

logging.basicConfig(stream=sys.stderr)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_lldp_remote(output: str) -> list[dict]:
    """Parse ``show lldp remote-device all`` output.

    Handles M4300 format where the header spans two lines (``Local`` on one
    line, ``Interface  RemID ...`` on the next), followed by a dashes separator.
    Skips bare port lines (no neighbor) and OUI continuation lines.
    """
    neighbors: list[dict] = []
    lines = output.splitlines()

    # Find the dashes separator line
    dash_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^-+\s+-+", line.strip()):
            dash_idx = i
            break

    if dash_idx is None:
        return neighbors

    for line in lines[dash_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        # Valid neighbor line starts with a port ID and has a numeric RemID
        if len(tokens) >= 4 and re.match(r"\d+/\d+/\d+|lag\s*\d+", tokens[0]):
            try:
                int(tokens[1])  # RemID must be numeric
            except ValueError:
                continue
            entry: dict[str, str] = {
                "local_interface": tokens[0],
                "remote_id": tokens[1],
                "chassis_id": tokens[2],
                "port_id": tokens[3],
            }
            if len(tokens) >= 5:
                entry["system_name"] = tokens[4]
            neighbors.append(entry)

    return neighbors


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register LLDP tools on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_show_lldp(host: str) -> str:
        """Return LLDP neighbor information for a NETGEAR switch.

        Runs ``show lldp remote-device all`` and returns all discovered
        neighbors with local interface, chassis ID, port ID and system name.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show lldp remote-device all")
        if output.startswith("ERROR:"):
            return output
        neighbors = _parse_lldp_remote(output)
        return json.dumps(
            {"host": host, "command": "show lldp remote-device all", "neighbors": neighbors},
            indent=2,
        )
