"""
Routing tools for NETGEAR AV switches.

Provides tools to inspect the IP routing table on NETGEAR M4250/M4300/M4350
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

def _parse_ip_route(output: str) -> dict:
    """Parse ``show ip route`` output.

    Typical format::

        Route Codes: …
        Default Gateway: 10.9.0.1
          Destination     Gateway        Dist/Metric  …
          10.9.0.0/16     Direct         0/0          …
    """
    data: dict[str, object] = {}

    # Default gateway
    m = re.search(r"Default\s+Gateway[:\s.]+([\d.]+)", output, re.IGNORECASE)
    if m:
        data["default_gateway"] = m.group(1).strip()

    # Route entries — lines starting with a network/mask
    routes: list[dict] = []
    for line in output.splitlines():
        # Match "C 10.9.0.0/16 directly connected, vlan 1" or tabular
        m_route = re.match(
            r"\s*[A-Z*]?\s*([\d.]+/\d+)\s+(.*)",
            line,
        )
        if m_route:
            entry: dict[str, str] = {"destination": m_route.group(1)}
            rest = m_route.group(2).strip()
            if rest:
                entry["detail"] = rest
            # Try to extract gateway IP from the rest
            gw = re.search(r"([\d]+\.[\d]+\.[\d]+\.[\d]+)", rest)
            if gw:
                entry["gateway"] = gw.group(1)
            routes.append(entry)

    if routes:
        data["routes"] = routes

    return data


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register routing tools on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_show_ip_route(host: str) -> str:
        """Return the IP routing table for a NETGEAR switch.

        Runs ``show ip route`` and returns the default gateway and all
        route entries.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show ip route")
        if output.startswith("ERROR:"):
            return output
        data = _parse_ip_route(output)
        return json.dumps(
            {"host": host, "command": "show ip route", **data},
            indent=2,
        )
