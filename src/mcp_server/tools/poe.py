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

def _parse_show_power(output: str) -> dict:
    """Parse ``show power`` output.

    Supports two NETGEAR output formats:

    **Dot-separated** (most common on M4250/M4350)::

        Power Budget........................... 740.0 W
        Power Consumption...................... 123.4 W
        Power Remaining........................ 616.6 W

    **Tabular** (found on some firmware)::

        Unit  Power Budget(W)  Power Consumption(W)  Power Remaining(W)
        ----  ---------------  --------------------  ------------------
        1     1440.0           120.5                 1319.5
    """
    data: dict[str, object] = {}

    # Format 1: dot-separated labels (e.g. "Power Budget........ 740.0 W")
    _DOT_FIELDS: list[tuple[str, str]] = [
        (r"Power\s+Budget", "power_budget_w"),
        (r"Power\s+Consumption", "power_consumption_w"),
        (r"Power\s+Remaining", "power_remaining_w"),
    ]
    for pattern, key in _DOT_FIELDS:
        m = re.search(rf"{pattern}[\.\s]+([\d.]+)", output, re.IGNORECASE)
        if m:
            data[key] = float(m.group(1))

    # Unit line
    m_unit = re.search(r"Unit\s*[:\s]+\s*(\d+)", output, re.IGNORECASE)
    if m_unit:
        data["unit"] = m_unit.group(1)

    # Format 2: tabular (fallback if dot-format didn't match any field)
    if not any(k in data for k in ("power_budget_w", "power_consumption_w")):
        m_tab = re.search(
            r"(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
            output,
        )
        if m_tab:
            data["unit"] = m_tab.group(1)
            data["power_budget_w"] = float(m_tab.group(2))
            data["power_consumption_w"] = float(m_tab.group(3))
            data["power_remaining_w"] = float(m_tab.group(4))

    # Per-port table
    ports: list[dict] = []
    lines = output.splitlines()
    in_port_table = False
    for line in lines:
        if re.search(r"Port\s+Admin\s*Mode|Intf\s+Admin\s*Mode", line, re.IGNORECASE):
            in_port_table = True
            continue
        if in_port_table:
            stripped = line.strip()
            if not stripped or stripped.startswith("-"):
                continue
            tokens = stripped.split()
            if len(tokens) >= 4:
                port_entry: dict[str, str] = {
                    "port": tokens[0],
                    "admin_mode": tokens[1],
                    "oper_status": tokens[2],
                    "power_mw": tokens[3],
                }
                if len(tokens) >= 5:
                    port_entry["class"] = tokens[4]
                ports.append(port_entry)

    if ports:
        data["ports"] = ports

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

        Runs ``show power`` and returns power budget, consumption, remaining
        wattage, and per-port PoE status.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show power")
        if output.startswith("ERROR:"):
            return output
        data = _parse_show_power(output)
        return json.dumps({"host": host, "command": "show power", **data}, indent=2)
