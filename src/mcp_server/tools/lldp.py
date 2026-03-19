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

    Typical tabular output::

        Local Interface  RemID  Chassis ID             Port ID      System Name
        ---------------  -----  ----------             -------      -----------
        0/1              1      AA:BB:CC:DD:EE:FF      0/1          Switch-A
        0/2              2      11:22:33:44:55:66      Gi0/1        Switch-B
    """
    neighbors: list[dict] = []
    lines = output.splitlines()

    header_idx: int | None = None
    for i, line in enumerate(lines):
        if re.search(r"Local\s+Interface|Local\s+Intf", line, re.IGNORECASE):
            header_idx = i
            break

    if header_idx is None:
        return neighbors

    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("-"):
            continue
        tokens = stripped.split()
        if len(tokens) < 4:
            continue
        entry: dict[str, str] = {
            "local_interface": tokens[0],
            "remote_id": tokens[1],
            "chassis_id": tokens[2],
            "port_id": tokens[3],
        }
        if len(tokens) >= 5:
            entry["system_name"] = " ".join(tokens[4:])
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
