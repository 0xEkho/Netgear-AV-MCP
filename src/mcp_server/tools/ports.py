"""
Port / interface tools for NETGEAR AV switches.

Provides tools to inspect interface counters and per-port statistics on
NETGEAR M4250/M4300/M4350 managed switches.
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
# Parsers
# ---------------------------------------------------------------------------

def _parse_interface_counters(output: str) -> list[dict]:
    """Parse ``show interface counters`` tabular output.

    The table typically has columns:
    Interface | InOctets | InUcastPkts | InMcastPkts | InBcastPkts | …
    """
    rows: list[dict] = []
    lines = output.splitlines()

    header_idx: int | None = None
    for i, line in enumerate(lines):
        if re.search(r"InOctets|In Octets|InUcastPkts", line, re.IGNORECASE):
            header_idx = i
            break

    if header_idx is None:
        return rows

    # Determine column positions from the dashes separator line (if present)
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("-"):
            continue
        tokens = stripped.split()
        if len(tokens) < 3:
            continue
        row: dict[str, str] = {"port": tokens[0]}
        keys = [
            "in_octets", "in_ucast_pkts", "in_mcast_pkts",
            "in_bcast_pkts", "in_drop_pkts", "in_bit_rate_mbps",
        ]
        for j, key in enumerate(keys):
            idx = j + 1
            if idx < len(tokens):
                row[key] = tokens[idx]
        rows.append(row)

    return rows


def _parse_interface_status(output: str) -> dict:
    """Parse ``show interfaces status <port>`` output."""
    data: dict[str, str] = {}
    lines = output.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("-") or stripped.lower().startswith("port"):
            continue
        # Skip header lines containing "Link" and "Physical"
        if "Physical" in stripped and "Link" in stripped:
            continue
        tokens = stripped.split()
        if not tokens:
            continue
        # First token is port
        data["port"] = tokens[0]
        # Find "Up" or "Down" in the tokens
        for i, t in enumerate(tokens[1:], 1):
            if t in ("Up", "Down"):
                data["link_state"] = t
                if i + 1 < len(tokens):
                    data["physical_mode"] = tokens[i + 1]
                # Check for speed/duplex
                if t == "Up" and i + 2 < len(tokens):
                    rest = " ".join(tokens[i + 2:])
                    speed_m = re.match(r"(\d+)\s+(Full|Half)", rest)
                    if speed_m:
                        data["speed"] = speed_m.group(1)
                        data["duplex"] = speed_m.group(2)
                break
        break  # Only first data line
    return data


def _parse_interface_detail(output: str) -> dict:
    """Parse ``show interface ethernet <port>`` output.

    Extracts key counters from a per-port detail view.
    Handles M4300 dot-format counters.
    """
    data: dict[str, str] = {}

    patterns = {
        "link_status": r"Link\s+Status[.\s]+(.*)",
        "duplex": r"Duplex[.\s]+(.*)",
        "total_packets_received": r"Total\s+Packets\s+Received\s+Without\s+Errors[.\s]+(.*)",
        "total_packets_transmitted": r"Total\s+Packets\s+Transmitted\s+Successfully[.\s]+(.*)",
        "total_octets_received": r"Total\s+Packets\s+Received\s+\(Octets\)[.\s]+(.*)",
        "total_octets_transmitted": r"Total\s+Packets\s+Transmitted\s+\(Octets\)[.\s]+(.*)",
        "unicast_packets_received": r"Unicast\s+Packets\s+Received[.\s]+(.*)",
        "multicast_packets_received": r"Multicast\s+Packets\s+Received[.\s]+(.*)",
        "broadcast_packets_received": r"Broadcast\s+Packets\s+Received[.\s]+(.*)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, output, re.IGNORECASE)
        if m:
            data[key] = m.group(1).strip()

    # Speed on its own line (avoid matching inside "Packets Received … Octets" lines)
    m = re.search(r"^Speed[.\s]+(.*)", output, re.IGNORECASE | re.MULTILINE)
    if m:
        data["speed"] = m.group(1).strip()

    return data


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register port/interface tools on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_show_interfaces(host: str) -> str:
        """Return interface counters for all ports on a NETGEAR switch.

        Runs ``show interface counters`` and returns per-port traffic
        statistics as a JSON list.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show interface counters")
        if output.startswith("ERROR:"):
            return output
        rows = _parse_interface_counters(output)
        return json.dumps(
            {"host": host, "command": "show interface counters", "interfaces": rows},
            indent=2,
        )

    @mcp.tool()
    async def netgear_show_interface_port(host: str, port: str) -> str:
        """Return detailed statistics for a specific port on a NETGEAR switch.

        Runs ``show interfaces status <port>`` for link state and
        ``show interface ethernet <port>`` for counters.

        Args:
            host: IP address of the target NETGEAR switch.
            port: Port identifier (e.g. ``"1/0/1"``, ``"1/0/48"``).
        """
        # Get link status
        cmd_status = f"show interfaces status {port}"
        output_status = await execute_command(host, cmd_status)
        status_data: dict = {}
        if not output_status.startswith("ERROR:"):
            status_data = _parse_interface_status(output_status)

        # Get counters
        cmd_counters = f"show interface ethernet {port}"
        output_counters = await execute_command(host, cmd_counters)
        counter_data: dict = {}
        if not output_counters.startswith("ERROR:"):
            counter_data = _parse_interface_detail(output_counters)

        data = {**status_data, **counter_data}
        if not data.get("port"):
            data["port"] = port
        return json.dumps({"host": host, "command": cmd_status, "port": port, **data}, indent=2)
