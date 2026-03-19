"""
PoE tools for NETGEAR AV switches.

Provides tools to inspect Power-over-Ethernet status on NETGEAR
M4250/M4300/M4350 PoE+ managed switches.
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

def _parse_show_poe(output: str) -> dict:
    """Parse ``show poe`` output (dot-separated key-value format)."""
    data: dict[str, object] = {}

    patterns: list[tuple[str, str]] = [
        (r"Unit[.\s]+(.*)", "unit"),
        (r"Slot[.\s]+(.*)", "slot"),
        (r"Model[.\s]+(\S+.*)", "model"),
        (r"Firmware\s+Version[.\s]+(.*)", "firmware_version"),
        (r"PSE\s+Main\s+Operational\s+Status[.\s]+(.*)", "pse_status"),
        (r"Total\s+Power\s+\(Main\s+AC\)[.\s]+([\d.]+)", "total_power_w"),
        (r"Power\s+Source[.\s]+(.*)", "power_source"),
        (r"Total\s+Power\s+Consumed[.\s]+([\d.]+)", "power_consumed_w"),
        (r"Power\s+Management\s+Mode[.\s]+(.*)", "power_management_mode"),
    ]

    for pat, key in patterns:
        m = re.search(pat, output, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            # Convert numeric values
            if key in ("total_power_w", "power_consumed_w"):
                try:
                    data[key] = float(val)
                except ValueError:
                    data[key] = val
            else:
                data[key] = val

    return data


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register PoE tools on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_show_poe(host: str) -> str:
        """Return Power-over-Ethernet status for a NETGEAR switch.

        Runs ``show poe`` and returns PoE operational status, total power,
        and power consumed.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show poe")
        if output.startswith("ERROR:"):
            return output
        data = _parse_show_poe(output)
        return json.dumps({"host": host, "command": "show poe", **data}, indent=2)
