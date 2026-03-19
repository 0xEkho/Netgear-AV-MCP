"""
VLAN tools for NETGEAR AV switches.

Provides tools to inspect VLAN configuration (access/trunk mode, native
VLAN, tagged VLANs) on NETGEAR M4250/M4300/M4350 managed switches.
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

def _parse_switchport(output: str) -> list[dict]:
    """Parse ``show interfaces switchport`` output.

    Each port block typically looks like::

        Port: 0/1
        VLAN Membership Mode: Access Mode
        Access Mode VLAN: 1 (default)
        Native VLAN: 1
        Trunking VLANs: 1-4094
    """
    entries: list[dict] = []
    blocks = re.split(r"(?=Port:\s+\S+)", output)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        entry: dict[str, str] = {}

        m = re.search(r"Port:\s+(\S+)", block)
        if m:
            entry["port"] = m.group(1)

        m = re.search(r"VLAN\s+Membership\s+Mode[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["vlan_mode"] = m.group(1).strip()

        m = re.search(r"Access\s+Mode\s+VLAN[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["access_vlan"] = m.group(1).strip()

        m = re.search(r"Native\s+VLAN[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["native_vlan"] = m.group(1).strip()

        m = re.search(r"Trunking\s+VLANs?[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["trunk_vlans"] = m.group(1).strip()

        if entry.get("port"):
            entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register VLAN tools on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_show_vlan(host: str, port_id: str | None = None) -> str:
        """Return VLAN information for a NETGEAR switch.

        Shows per-port VLAN configuration including access/trunk mode,
        native VLAN, and tagged VLANs.

        When *port_id* is provided, only the specified port is returned.

        Args:
            host: IP address of the target NETGEAR switch.
            port_id: Optional port identifier to filter (e.g. ``"0/1"``).
        """
        if port_id:
            cmd = f"show interfaces switchport {port_id}"
        else:
            cmd = "show interfaces switchport"

        output = await execute_command(host, cmd)
        if output.startswith("ERROR:"):
            return output

        entries = _parse_switchport(output)
        return json.dumps(
            {"host": host, "command": cmd, "vlans": entries},
            indent=2,
        )
