"""
Spanning-tree tools for NETGEAR AV switches.

Provides tools to inspect STP status on NETGEAR M4250/M4300/M4350
managed switches.
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

def _parse_spanning_tree(output: str) -> dict:
    """Parse ``show spanning-tree`` output.

    Looks for key-value pairs like::

        Bridge Priority.............. 32768
        Bridge Identifier............ 80:00:AA:BB:CC:DD:EE:FF
        Designated Root.............. 80:00:11:22:33:44:55:66
        Root Port.................... 0/49
        Time Since Topology Change... 5 days 12 hrs 30 mins
    """
    data: dict[str, str] = {}

    patterns = {
        "bridge_priority": r"Bridge\s+Priority[.\s]+(.*)",
        "bridge_id": r"Bridge\s+Identifier[.\s]+(.*)",
        "root_bridge_id": r"Designated\s+Root[.\s]+(.*)",
        "root_port": r"Root\s+Port\s*(?:Identifier)?[.\s]+(\S+)",
        "time_since_topology_change": r"Time\s+Since\s+Topology\s+Change[.\s]+(.*)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, output, re.IGNORECASE)
        if m:
            data[key] = m.group(1).strip()

    # Determine if this switch is root bridge
    bridge = data.get("bridge_id", "").lower()
    root = data.get("root_bridge_id", "").lower()
    if bridge and root:
        data["is_root"] = str(bridge == root)

    return data


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register spanning-tree tools on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_show_spanning_tree(host: str) -> str:
        """Return spanning-tree status for a NETGEAR switch.

        Runs ``show spanning-tree`` and returns bridge priority, bridge
        identifier, root bridge, root port, and topology-change timer.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show spanning-tree")
        if output.startswith("ERROR:"):
            return output
        data = _parse_spanning_tree(output)
        return json.dumps(
            {"host": host, "command": "show spanning-tree", **data},
            indent=2,
        )
