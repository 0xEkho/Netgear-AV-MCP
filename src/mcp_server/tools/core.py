"""
Core NETGEAR tools — version, hosts, config backup.

Provides fundamental information-gathering tools for NETGEAR M4250/M4300/M4350
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
# Parsers
# ---------------------------------------------------------------------------

def _parse_show_version(output: str) -> dict:
    """Parse ``show version`` output from a NETGEAR switch.

    Expected key lines::

        Machine Model................ M4250-26G4F-PoE+
        Serial Number................ XXXXXXXXXX
        Software Version............. 14.0.2.5
        System Up Time............... 42 days 3 hrs 15 mins 8 secs
        Burned In MAC Address........ AA:BB:CC:DD:EE:FF
    """
    data: dict[str, str] = {}

    patterns = {
        "model": r"Machine\s+Model[.\s]+(.*)",
        "serial_number": r"Serial\s+Number[.\s]+(.*)",
        "software_version": r"Software\s+Version[.\s]+(.*)",
        "uptime": r"System\s+Up\s+Time[.\s]+(.*)",
        "mac_address": r"Burned\s+In\s+MAC\s+Address[.\s]+(.*)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, output, re.IGNORECASE)
        if m:
            data[key] = m.group(1).strip()

    if "software_version" in data:
        data["firmware_version"] = data["software_version"]

    return data


def _parse_show_switch(output: str) -> dict:
    """Parse ``show switch`` output (M4300 table format)."""
    data: dict[str, object] = {}

    # Generic key-value with dots separator
    for line in output.splitlines():
        if "..." in line or ". " in line:
            parts = re.split(r"\.{2,}\s*", line, maxsplit=1)
            if len(parts) == 2:
                key = parts[0].strip().lower().replace(" ", "_")
                data[key] = parts[1].strip()

    return data


def _parse_show_hosts(output: str) -> dict:
    """Parse ``show hosts`` output.

    Expected key lines::

        Host name.................... SwitchName
        Default domain............... example.com
        Name/address lookup.......... Disabled
        DNS Client Source IPv4 Address 10.9.0.1
    """
    data: dict[str, str] = {}

    patterns = {
        "hostname": r"Host\s+name[.\s]+(.*)",
        "default_domain": r"Default\s+domain[.\s]+(.*)",
        "dns_client_ipv4": r"DNS\s+Client\s+Source\s+IPv4\s+Address[.\s]+(.*)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, output, re.IGNORECASE)
        if m:
            data[key] = m.group(1).strip()

    # Clean dns_client_ipv4 — strip trailing [Up]/[Down]
    if "dns_client_ipv4" in data:
        data["dns_client_ipv4"] = re.sub(r"\s*\[.*?\]\s*$", "", data["dns_client_ipv4"]).strip()

    # Collect name servers — two formats:
    # 1. Multi-line:  "Name server.. IP" repeated (word boundary excludes "servers")
    # 2. Single line: "Name servers (Preference order).... IP, IP"
    multi_ns = re.findall(
        r"Name\s+server\b[.\s]+(\d[\d.]+)", output, re.IGNORECASE,
    )
    m_ns = re.search(
        r"Name\s+servers?\s*(?:\([^)]*\))?[.\s]+(\d[\d.,\s]+)",
        output, re.IGNORECASE,
    )
    comma_ns: list[str] = []
    if m_ns:
        raw_ns = m_ns.group(1).strip().rstrip(",")
        comma_ns = [s.strip() for s in raw_ns.split(",") if s.strip()]
    servers = multi_ns if len(multi_ns) >= len(comma_ns) else comma_ns
    if servers:
        data["name_servers"] = ", ".join(servers)

    return data


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP) -> None:
    """Register core NETGEAR tools on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def netgear_show_version(host: str) -> str:
        """Return version and model information for a NETGEAR switch.

        Runs ``show version`` and returns model, serial number, firmware
        version, uptime and burned-in MAC address.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show version")
        if output.startswith("ERROR:"):
            return output
        data = _parse_show_version(output)
        # Fallback to "show switch" if no model found (M4300)
        if not data.get("model"):
            output2 = await execute_command(host, "show switch")
            if not output2.startswith("ERROR:"):
                data = _parse_show_switch(output2)
        return json.dumps({"host": host, "command": "show version", **data}, indent=2)

    @mcp.tool()
    async def netgear_show_hosts(host: str) -> str:
        """Return hostname and DNS information for a NETGEAR switch.

        Runs ``show hosts`` and returns hostname, domain, DNS servers and
        management IP.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show hosts")
        if output.startswith("ERROR:"):
            return output
        data = _parse_show_hosts(output)
        return json.dumps({"host": host, "command": "show hosts", **data}, indent=2)

    @mcp.tool()
    async def netgear_config_backup(host: str) -> str:
        """Return the full running configuration of a NETGEAR switch.

        Runs ``show running-config`` and returns the raw text output.

        Args:
            host: IP address of the target NETGEAR switch.
        """
        output = await execute_command(host, "show running-config")
        if output.startswith("ERROR:"):
            return output
        return json.dumps(
            {"host": host, "command": "show running-config", "config": output},
            indent=2,
        )
