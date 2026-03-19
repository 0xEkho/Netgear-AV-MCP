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

        Port: 1/0/1
        VLAN Membership Mode: Access Mode
        Access Mode VLAN: 1 (default)
        Native VLAN: 1
        Trunking VLANs: 1-4094
    """
    entries: list[dict] = []
    blocks = re.split(r"(?=^Port:\s+\S+)", output, flags=re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        entry: dict[str, str] = {}

        m = re.search(r"^Port:\s+(\S+)", block, re.MULTILINE)
        if m:
            entry["port"] = m.group(1)

        m = re.search(r"VLAN\s+Membership\s+Mode[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["vlan_mode"] = m.group(1).strip()

        m = re.search(r"Access\s+Mode\s+VLAN[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["access_vlan"] = m.group(1).strip()

        m = re.search(r"^Trunking\s+Mode\s+Native\s+VLAN[:\s.]+(.*)", block, re.IGNORECASE | re.MULTILINE)
        if m:
            entry["native_vlan"] = m.group(1).strip()
        else:
            m = re.search(r"Native\s+VLAN[:\s.]+(.*)", block, re.IGNORECASE)
            if m:
                entry["native_vlan"] = m.group(1).strip()

        m = re.search(r"Trunking\s+Mode\s+VLANs\s+Enabled[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["trunk_vlans"] = m.group(1).strip()
        else:
            m = re.search(r"Trunking\s+VLANs?[:\s.]+(.*)", block, re.IGNORECASE)
            if m:
                entry["trunk_vlans"] = m.group(1).strip()

        # General mode fields (M4300)
        m = re.search(r"General\s+Mode\s+PVID[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["pvid"] = m.group(1).strip()

        m = re.search(r"General\s+Mode\s+Untagged\s+VLANs[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val:
                entry["untagged_vlans"] = val

        m = re.search(r"General\s+Mode\s+Tagged\s+VLANs[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val:
                entry["tagged_vlans"] = val

        m = re.search(r"General\s+Mode\s+Ingress\s+Filtering[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["ingress_filtering"] = m.group(1).strip()

        m = re.search(r"General\s+Mode\s+Acceptable\s+Frame\s+Type[:\s.]+(.*)", block, re.IGNORECASE)
        if m:
            entry["acceptable_frame_type"] = m.group(1).strip()

        if entry.get("port"):
            entries.append(entry)

    return entries


def _parse_vlan_table(output: str) -> list[dict]:
    """Parse ``show vlan`` table output."""
    vlans: list[dict] = []
    lines = output.splitlines()
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-------"):
            in_table = True
            continue
        if in_table and stripped:
            # Handle VLAN with empty name (e.g. VLAN 4093)
            m = re.match(r"(\d+)\s{2,}(\S+.*)", stripped)
            if m and not re.match(r"(\d+)\s+(\S.*\S|\S)\s{2,}(\S+.*)", stripped):
                vlans.append({
                    "vlan_id": int(m.group(1)),
                    "name": "",
                    "type": m.group(2).strip(),
                })
                continue
            m = re.match(r"(\d+)\s+(\S.*\S|\S)\s{2,}(\S+.*)", stripped)
            if m:
                vlans.append({
                    "vlan_id": int(m.group(1)),
                    "name": m.group(2).strip(),
                    "type": m.group(3).strip(),
                })
    return vlans


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

        Without port_id: shows all VLANs configured on the switch.
        With port_id: shows per-port switchport VLAN configuration.

        Args:
            host: IP address of the target NETGEAR switch.
            port_id: Optional port identifier to filter (e.g. ``"1/0/1"``).
        """
        if port_id:
            cmd = f"show interfaces switchport {port_id}"
            output = await execute_command(host, cmd)
            if output.startswith("ERROR:"):
                return output
            entries = _parse_switchport(output)
            return json.dumps(
                {"host": host, "command": cmd, "ports": entries},
                indent=2,
            )
        else:
            cmd = "show vlan"
            output = await execute_command(host, cmd)
            if output.startswith("ERROR:"):
                return output
            vlans = _parse_vlan_table(output)
            return json.dumps(
                {"host": host, "command": cmd, "vlans": vlans},
                indent=2,
            )
