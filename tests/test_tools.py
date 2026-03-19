"""Tests for MCP tools — Netgear AV switches.

Covers all parsers (unit tests) and all tools (integration via call_tool).
"""

import json

import pytest
from unittest.mock import AsyncMock, patch

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.core import _parse_show_version, _parse_show_switch, _parse_show_hosts
from mcp_server.tools.ports import _parse_interface_counters, _parse_interface_detail, _parse_interface_status
from mcp_server.tools.vlan import _parse_switchport, _parse_vlan_table
from mcp_server.tools.poe import _parse_show_poe
from mcp_server.tools.spantree import _parse_spanning_tree
from mcp_server.tools.routing import _parse_ip_route
from mcp_server.tools.lldp import _parse_lldp_remote


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(result) -> str:
    """Extract text from a FastMCP call_tool result (tuple of list + dict)."""
    return result[0][0].text


@pytest.fixture
def mcp_instance():
    """Create a fresh FastMCP with all tool modules registered."""
    instance = FastMCP("test-netgear")
    from mcp_server.tools.core import register_tools as reg_core
    from mcp_server.tools.ports import register_tools as reg_ports
    from mcp_server.tools.vlan import register_tools as reg_vlan
    from mcp_server.tools.poe import register_tools as reg_poe
    from mcp_server.tools.spantree import register_tools as reg_spantree
    from mcp_server.tools.routing import register_tools as reg_routing
    from mcp_server.tools.lldp import register_tools as reg_lldp
    from mcp_server.tools.cli import register_tools as reg_cli
    reg_core(instance)
    reg_ports(instance)
    reg_vlan(instance)
    reg_poe(instance)
    reg_spantree(instance)
    reg_routing(instance)
    reg_lldp(instance)
    reg_cli(instance)
    return instance


# ═══════════════════════════════════════════════════════════════════════════
# Parser unit tests — pure functions, no MCP needed
# ═══════════════════════════════════════════════════════════════════════════

# ── _parse_show_version ────────────────────────────────────────────────

SHOW_VERSION_OUTPUT = (
    "Machine Model................ M4250-40G8XF-PoE+\n"
    "Serial Number................ ABC123456789\n"
    "Software Version............. 14.0.1.6\n"
    "System Up Time............... 15 days 6 hrs 32 mins\n"
    "Burned In MAC Address........ AA:BB:CC:DD:EE:FF\n"
)


def test_parse_show_version_full():
    """Parse show version with all fields present."""
    data = _parse_show_version(SHOW_VERSION_OUTPUT)
    assert data["model"] == "M4250-40G8XF-PoE+"
    assert data["serial_number"] == "ABC123456789"
    assert data["software_version"] == "14.0.1.6"
    assert data["firmware_version"] == "14.0.1.6"
    assert data["uptime"] == "15 days 6 hrs 32 mins"
    assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"


def test_parse_show_version_empty():
    """Parse show version with empty input returns empty dict."""
    assert _parse_show_version("") == {}


def test_parse_show_version_partial():
    """Parse show version with only model line."""
    data = _parse_show_version("Machine Model................ M4350-24X4V\n")
    assert data["model"] == "M4350-24X4V"
    assert "serial_number" not in data


# ── _parse_show_switch ─────────────────────────────────────────────────

SHOW_SWITCH_OUTPUT = (
    "Machine Type................. M4300-48X\n"
    "Serial Number................ XYZ987654321\n"
    "Software Version............. 13.0.5.1\n"
)


def test_parse_show_switch_dot_format():
    """Parse show switch with dot-separated M4300 format."""
    data = _parse_show_switch(SHOW_SWITCH_OUTPUT)
    assert data["machine_type"] == "M4300-48X"
    assert data["serial_number"] == "XYZ987654321"
    assert data["software_version"] == "13.0.5.1"


def test_parse_show_switch_empty():
    """Parse show switch with empty input returns empty dict."""
    assert _parse_show_switch("") == {}


# ── _parse_show_hosts ──────────────────────────────────────────────────

SHOW_HOSTS_OUTPUT = (
    "Host name.................... SW-AV-01\n"
    "Default domain............... av.local\n"
    "DNS Client Source IPv4 Address 10.9.0.1\n"
    "Name server.................. 8.8.8.8\n"
    "Name server.................. 8.8.4.4\n"
)


def test_parse_show_hosts_full():
    """Parse show hosts with hostname, domain, DNS servers."""
    data = _parse_show_hosts(SHOW_HOSTS_OUTPUT)
    assert data["hostname"] == "SW-AV-01"
    assert data["default_domain"] == "av.local"
    assert data["dns_client_ipv4"] == "10.9.0.1"
    assert "8.8.8.8" in data["name_servers"]
    assert "8.8.4.4" in data["name_servers"]


def test_parse_show_hosts_empty():
    """Parse show hosts with empty input returns empty dict."""
    assert _parse_show_hosts("") == {}


# ── _parse_interface_counters ──────────────────────────────────────────

SHOW_INTERFACE_COUNTERS_OUTPUT = (
    "Port      InOctets   InUcastPkts  InMcastPkts  InBcastPkts  InDropPkts  InBitRate\n"
    "--------- ---------- ------------ ------------ ------------ ----------- ---------\n"
    "0/1       123456789  1000         200          50           0           100\n"
    "0/2       987654321  5000         300          75           2           500\n"
)


def test_parse_interface_counters_multi_row():
    """Parse interface counters with two port rows."""
    rows = _parse_interface_counters(SHOW_INTERFACE_COUNTERS_OUTPUT)
    assert len(rows) == 2
    assert rows[0]["port"] == "0/1"
    assert rows[0]["in_octets"] == "123456789"
    assert rows[0]["in_ucast_pkts"] == "1000"
    assert rows[1]["port"] == "0/2"
    assert rows[1]["in_octets"] == "987654321"


def test_parse_interface_counters_empty():
    """Parse interface counters with no header returns empty list."""
    assert _parse_interface_counters("No data available\n") == []


def test_parse_interface_counters_header_only():
    """Parse interface counters with header but no data rows."""
    output = (
        "Port      InOctets   InUcastPkts\n"
        "--------- ---------- ------------\n"
    )
    assert _parse_interface_counters(output) == []


# ── _parse_interface_detail ────────────────────────────────────────────

SHOW_INTERFACE_DETAIL_OUTPUT = (
    "Link Status.................. Up\n"
    "Speed........................ 1000 Mbps Full\n"
    "Duplex....................... Full\n"
    "Total Packets Received Without Errors.. 123456\n"
    "Total Packets Transmitted Successfully. 654321\n"
    "Total Packets Received (Octets)........ 12345678\n"
    "Total Packets Transmitted (Octets)..... 87654321\n"
    "Unicast Packets Received..... 100000\n"
    "Multicast Packets Received... 20000\n"
    "Broadcast Packets Received... 3456\n"
)


def test_parse_interface_detail_full():
    """Parse interface detail with all counter fields."""
    data = _parse_interface_detail(SHOW_INTERFACE_DETAIL_OUTPUT)
    assert data["link_status"] == "Up"
    assert data["speed"] == "1000 Mbps Full"
    assert data["duplex"] == "Full"
    assert data["total_packets_received"] == "123456"
    assert data["total_packets_transmitted"] == "654321"
    assert data["total_octets_received"] == "12345678"
    assert data["total_octets_transmitted"] == "87654321"
    assert data["unicast_packets_received"] == "100000"
    assert data["multicast_packets_received"] == "20000"
    assert data["broadcast_packets_received"] == "3456"


def test_parse_interface_detail_empty():
    """Parse interface detail with empty input returns empty dict."""
    assert _parse_interface_detail("") == {}


# ── _parse_switchport ──────────────────────────────────────────────────

SHOW_SWITCHPORT_OUTPUT = (
    "Port: 0/1\n"
    "  VLAN Membership Mode.................. Access\n"
    "  Access Mode VLAN...................... 100\n"
    "  Native VLAN........................... 1\n"
    "  Trunking VLANs........................ ALL\n"
    "\n"
    "Port: 0/2\n"
    "  VLAN Membership Mode.................. Trunk\n"
    "  Access Mode VLAN...................... 1\n"
    "  Native VLAN........................... 1\n"
    "  Trunking VLANs........................ 100,200,300\n"
)


def test_parse_switchport_multi_port():
    """Parse switchport with two port blocks (access + trunk)."""
    entries = _parse_switchport(SHOW_SWITCHPORT_OUTPUT)
    assert len(entries) == 2
    assert entries[0]["port"] == "0/1"
    assert entries[0]["access_vlan"] == "100"
    assert entries[0]["trunk_vlans"] == "ALL"
    assert entries[1]["port"] == "0/2"
    assert entries[1]["vlan_mode"] == "Trunk"
    assert entries[1]["trunk_vlans"] == "100,200,300"


def test_parse_switchport_empty():
    """Parse switchport with empty input returns empty list."""
    assert _parse_switchport("") == []


def test_parse_switchport_block_without_port():
    """Parse switchport ignores blocks without Port: header."""
    output = "  VLAN Membership Mode.................. Access\n"
    entries = _parse_switchport(output)
    assert entries == []


# ── _parse_show_poe ────────────────────────────────────────────────────

SHOW_POE_OUTPUT = (
    "Unit........................................... 1\n"
    "Slot........................................... 0\n"
    "Model.......................................... M4300-28G-PoE+\n"
    "Firmware Version............................... 4.1.0.12\n"
    "PSE Main Operational Status.................... OFF\n"
    "Total Power (Main AC).......................... 720.0 Watts\n"
    "Power Source................................... Main AC\n"
    "Total Power Consumed........................... 0.0 Watts\n"
    "Power Management Mode.......................... Dynamic\n"
    "Traps.......................................... Enable\n"
)


def test_parse_show_poe_full():
    """Parse show poe with all fields present."""
    data = _parse_show_poe(SHOW_POE_OUTPUT)
    assert data["unit"] == "1"
    assert data["slot"] == "0"
    assert data["model"] == "M4300-28G-PoE+"
    assert data["firmware_version"] == "4.1.0.12"
    assert data["pse_status"] == "OFF"
    assert data["total_power_w"] == 720.0
    assert data["power_source"] == "Main AC"
    assert data["power_consumed_w"] == 0.0
    assert data["power_management_mode"] == "Dynamic"


def test_parse_show_poe_empty():
    """Parse show poe with empty input returns empty dict."""
    assert _parse_show_poe("") == {}


# ── _parse_spanning_tree ───────────────────────────────────────────────

STP_NOT_ROOT_OUTPUT = (
    "Bridge Priority.............. 32768\n"
    "Bridge Identifier............ 8000.AABBCCDDEEFF\n"
    "Designated Root.............. 8000.112233445566\n"
    "Root Port.................... 0/49\n"
    "Time Since Topology Change... 5 days 12 hrs 30 mins\n"
)

STP_ROOT_OUTPUT = (
    "Bridge Priority.............. 32768\n"
    "Bridge Identifier............ 8000.AABBCCDDEEFF\n"
    "Designated Root.............. 8000.AABBCCDDEEFF\n"
    "Root Port.................... None\n"
    "Time Since Topology Change... 10 days 0 hrs 0 mins\n"
)


def test_parse_spanning_tree_not_root():
    """Parse spanning-tree where switch is NOT root bridge."""
    data = _parse_spanning_tree(STP_NOT_ROOT_OUTPUT)
    assert data["bridge_priority"] == "32768"
    assert data["bridge_id"] == "8000.AABBCCDDEEFF"
    assert data["root_bridge_id"] == "8000.112233445566"
    assert data["root_port"] == "0/49"
    assert data["is_root"] == "False"


def test_parse_spanning_tree_is_root():
    """Parse spanning-tree where switch IS the root bridge."""
    data = _parse_spanning_tree(STP_ROOT_OUTPUT)
    assert data["is_root"] == "True"
    assert data["root_port"] == "None"
    assert data["time_since_topology_change"] == "10 days 0 hrs 0 mins"


def test_parse_spanning_tree_empty():
    """Parse spanning-tree with empty input returns empty dict."""
    assert _parse_spanning_tree("") == {}


# ── _parse_ip_route ────────────────────────────────────────────────────

SHOW_IP_ROUTE_OUTPUT = (
    "Default Gateway: 10.9.0.1\n"
    "\n"
    "C  10.9.0.0/16 directly connected, vlan 1\n"
    "S  0.0.0.0/0 via 10.9.0.1\n"
)


def test_parse_ip_route_default_gateway():
    """Parse ip route extracts default gateway."""
    data = _parse_ip_route(SHOW_IP_ROUTE_OUTPUT)
    assert data["default_gateway"] == "10.9.0.1"


def test_parse_ip_route_routes():
    """Parse ip route extracts route entries with destination and gateway."""
    data = _parse_ip_route(SHOW_IP_ROUTE_OUTPUT)
    routes = data["routes"]
    assert len(routes) == 2
    assert routes[0]["destination"] == "10.9.0.0/16"
    assert routes[1]["destination"] == "0.0.0.0/0"
    assert routes[1]["gateway"] == "10.9.0.1"


def test_parse_ip_route_empty():
    """Parse ip route with empty input returns empty dict."""
    assert _parse_ip_route("") == {}


# ── _parse_lldp_remote ────────────────────────────────────────────────

SHOW_LLDP_OUTPUT = (
    "Local\n"
    "Interface  RemID   Chassis ID            Port ID             System Name         OUI          OUI Subtype\n"
    "--------- -------  --------------------  ------------------  ------------------  -----------  -----------\n"
    "1/0/25     2       AA:BB:CC:DD:EE:01     port1               SWITCH-NEIGHBOR     0x00120f     0x03\n"
    "1/0/26     1       AA:BB:CC:DD:EE:01     uplink              SWITCH-NEIGHBOR     0x00120f     0x03\n"
)


def test_parse_lldp_remote_full():
    """Parse LLDP table with system_name present."""
    neighbors = _parse_lldp_remote(SHOW_LLDP_OUTPUT)
    assert len(neighbors) == 2
    assert neighbors[0]["local_interface"] == "1/0/25"
    assert neighbors[0]["remote_id"] == "2"
    assert neighbors[0]["chassis_id"] == "AA:BB:CC:DD:EE:01"
    assert neighbors[0]["port_id"] == "port1"
    assert neighbors[0]["system_name"] == "SWITCH-NEIGHBOR"


def test_parse_lldp_remote_second_entry():
    """Parse LLDP second neighbor entry."""
    neighbors = _parse_lldp_remote(SHOW_LLDP_OUTPUT)
    assert neighbors[1]["local_interface"] == "1/0/26"
    assert neighbors[1]["port_id"] == "uplink"
    assert neighbors[1]["system_name"] == "SWITCH-NEIGHBOR"


def test_parse_lldp_remote_empty():
    """Parse LLDP with no header returns empty list."""
    assert _parse_lldp_remote("No LLDP neighbors found\n") == []


# ═══════════════════════════════════════════════════════════════════════════
# Tool integration tests — via mcp.call_tool with mocked execute_command
# ═══════════════════════════════════════════════════════════════════════════

async def test_all_tools_registered(mcp_instance):
    """Verify all 11 expected tools are registered."""
    tools = {t.name for t in await mcp_instance.list_tools()}
    expected = {
        "netgear_show_version",
        "netgear_show_hosts",
        "netgear_config_backup",
        "netgear_show_interfaces",
        "netgear_show_interface_port",
        "netgear_show_vlan",
        "netgear_show_poe",
        "netgear_show_spanning_tree",
        "netgear_show_ip_route",
        "netgear_show_lldp",
        "netgear_cli_readonly",
    }
    assert tools == expected


# ── netgear_show_version ───────────────────────────────────────────────

async def test_show_version_returns_json(mcp_instance):
    """Tool returns parsed JSON with model, serial, version, uptime."""
    with patch("mcp_server.tools.core.execute_command", new_callable=AsyncMock, return_value=SHOW_VERSION_OUTPUT):
        result = await mcp_instance.call_tool("netgear_show_version", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["host"] == "10.0.0.1"
        assert data["model"] == "M4250-40G8XF-PoE+"
        assert data["serial_number"] == "ABC123456789"
        assert data["software_version"] == "14.0.1.6"


async def test_show_version_handles_error(mcp_instance):
    """Tool forwards SSH errors as-is."""
    with patch("mcp_server.tools.core.execute_command", new_callable=AsyncMock, return_value="ERROR: ConnectTimeout: could not connect"):
        result = await mcp_instance.call_tool("netgear_show_version", {"host": "10.0.0.1"})
        assert "ERROR:" in _text(result)


async def test_show_version_fallback_show_switch(mcp_instance):
    """Tool falls back to show switch when show version returns no model."""
    async def _side_effect(host: str, cmd: str) -> str:
        if cmd == "show version":
            return "Some text without model info"
        return SHOW_SWITCH_OUTPUT

    with patch("mcp_server.tools.core.execute_command", new_callable=AsyncMock, side_effect=_side_effect):
        result = await mcp_instance.call_tool("netgear_show_version", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["machine_type"] == "M4300-48X"


# ── netgear_show_hosts ─────────────────────────────────────────────────

async def test_show_hosts_returns_json(mcp_instance):
    """Tool returns parsed JSON with hostname, domain, DNS servers."""
    with patch("mcp_server.tools.core.execute_command", new_callable=AsyncMock, return_value=SHOW_HOSTS_OUTPUT):
        result = await mcp_instance.call_tool("netgear_show_hosts", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["hostname"] == "SW-AV-01"
        assert data["default_domain"] == "av.local"
        assert "8.8.8.8" in data["name_servers"]


# ── netgear_config_backup ─────────────────────────────────────────────

async def test_config_backup_returns_config(mcp_instance):
    """Tool returns raw running-config in JSON."""
    fake_config = "hostname SW-AV-01\nvlan 100\n name AV-VLAN\n!"
    with patch("mcp_server.tools.core.execute_command", new_callable=AsyncMock, return_value=fake_config):
        result = await mcp_instance.call_tool("netgear_config_backup", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["command"] == "show running-config"
        assert "hostname SW-AV-01" in data["config"]


# ── netgear_show_interfaces ───────────────────────────────────────────

async def test_show_interfaces_returns_json(mcp_instance):
    """Tool returns per-port counters as JSON list."""
    with patch("mcp_server.tools.ports.execute_command", new_callable=AsyncMock, return_value=SHOW_INTERFACE_COUNTERS_OUTPUT):
        result = await mcp_instance.call_tool("netgear_show_interfaces", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert len(data["interfaces"]) == 2
        assert data["interfaces"][0]["port"] == "0/1"


# ── netgear_show_interface_port ────────────────────────────────────────

async def test_show_interface_port_returns_json(mcp_instance):
    """Tool returns detailed port stats as JSON."""
    async def _side_effect(host: str, cmd: str) -> str:
        if "interfaces status" in cmd:
            return "1/0/1                                    Up    Auto    1000 Full    Copper    Inactive\n"
        return SHOW_INTERFACE_DETAIL_OUTPUT

    with patch("mcp_server.tools.ports.execute_command", new_callable=AsyncMock, side_effect=_side_effect):
        result = await mcp_instance.call_tool("netgear_show_interface_port", {"host": "10.0.0.1", "port": "1/0/1"})
        data = json.loads(_text(result))
        assert data["link_state"] == "Up"
        assert data["total_packets_received"] == "123456"


# ── netgear_show_vlan ─────────────────────────────────────────────────

async def test_show_vlan_returns_json(mcp_instance):
    """Tool returns VLAN table as JSON list when no port_id given."""
    show_vlan_output = (
        "VLAN ID VLAN Name                        VLAN Type\n"
        "------- -------------------------------- -------------------\n"
        "1       default                          Default\n"
        "129     Production                       Static\n"
    )
    with patch("mcp_server.tools.vlan.execute_command", new_callable=AsyncMock, return_value=show_vlan_output):
        result = await mcp_instance.call_tool("netgear_show_vlan", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["command"] == "show vlan"
        assert len(data["vlans"]) == 2
        assert data["vlans"][0]["vlan_id"] == 1
        assert data["vlans"][0]["name"] == "default"
        assert data["vlans"][1]["name"] == "Production"


async def test_show_vlan_with_port_id(mcp_instance):
    """Tool uses per-port command when port_id is given."""
    single_port_output = (
        "Port: 1/0/5\n"
        "  VLAN Membership Mode.................. Access\n"
        "  Access Mode VLAN...................... 200\n"
    )
    with patch("mcp_server.tools.vlan.execute_command", new_callable=AsyncMock, return_value=single_port_output) as mock_exec:
        result = await mcp_instance.call_tool("netgear_show_vlan", {"host": "10.0.0.1", "port_id": "1/0/5"})
        data = json.loads(_text(result))
        assert data["ports"][0]["access_vlan"] == "200"
        mock_exec.assert_called_once_with("10.0.0.1", "show interfaces switchport 1/0/5")


# ── netgear_show_poe ──────────────────────────────────────────────────

async def test_show_poe_returns_json(mcp_instance):
    """Tool returns PoE data from show poe format."""
    with patch("mcp_server.tools.poe.execute_command", new_callable=AsyncMock, return_value=SHOW_POE_OUTPUT):
        result = await mcp_instance.call_tool("netgear_show_poe", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["command"] == "show poe"
        assert data["total_power_w"] == 720.0
        assert data["pse_status"] == "OFF"
        assert data["model"] == "M4300-28G-PoE+"


# ── netgear_show_spanning_tree ─────────────────────────────────────────

async def test_show_spanning_tree_returns_json(mcp_instance):
    """Tool returns spanning-tree info as JSON."""
    with patch("mcp_server.tools.spantree.execute_command", new_callable=AsyncMock, return_value=STP_NOT_ROOT_OUTPUT):
        result = await mcp_instance.call_tool("netgear_show_spanning_tree", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["bridge_priority"] == "32768"
        assert data["is_root"] == "False"


# ── netgear_show_ip_route ─────────────────────────────────────────────

async def test_show_ip_route_returns_json(mcp_instance):
    """Tool returns IP route table as JSON."""
    with patch("mcp_server.tools.routing.execute_command", new_callable=AsyncMock, return_value=SHOW_IP_ROUTE_OUTPUT):
        result = await mcp_instance.call_tool("netgear_show_ip_route", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["default_gateway"] == "10.9.0.1"
        assert len(data["routes"]) == 2


# ── netgear_show_lldp ─────────────────────────────────────────────────

async def test_show_lldp_returns_json(mcp_instance):
    """Tool returns LLDP neighbor list as JSON."""
    with patch("mcp_server.tools.lldp.execute_command", new_callable=AsyncMock, return_value=SHOW_LLDP_OUTPUT):
        result = await mcp_instance.call_tool("netgear_show_lldp", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert len(data["neighbors"]) == 2
        assert data["neighbors"][0]["system_name"] == "SWITCH-NEIGHBOR"


# ── netgear_cli_readonly ──────────────────────────────────────────────

async def test_cli_readonly_blocks_write(mcp_instance):
    """Tool rejects write commands."""
    result = await mcp_instance.call_tool("netgear_cli_readonly", {"host": "10.0.0.1", "command": "write memory"})
    data = json.loads(_text(result))
    assert "error" in data
    assert "read-only" in data["error"].lower()


async def test_cli_readonly_blocks_configure(mcp_instance):
    """Tool rejects configure commands."""
    result = await mcp_instance.call_tool("netgear_cli_readonly", {"host": "10.0.0.1", "command": "configure terminal"})
    data = json.loads(_text(result))
    assert "error" in data


async def test_cli_readonly_allows_show(mcp_instance):
    """Tool allows show commands and returns output."""
    with patch("mcp_server.tools.cli.execute_command", new_callable=AsyncMock, return_value="some output"):
        result = await mcp_instance.call_tool("netgear_cli_readonly", {"host": "10.0.0.1", "command": "show version"})
        data = json.loads(_text(result))
        assert data["output"] == "some output"


async def test_cli_readonly_handles_ssh_error(mcp_instance):
    """Tool returns ERROR string when SSH fails."""
    with patch("mcp_server.tools.cli.execute_command", new_callable=AsyncMock, return_value="ERROR: TimeoutError: timed out"):
        result = await mcp_instance.call_tool("netgear_cli_readonly", {"host": "10.0.0.1", "command": "show version"})
        assert "ERROR:" in _text(result)
