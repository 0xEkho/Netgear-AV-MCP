"""Tests for MCP tools — Netgear AV switches."""
import json
import pytest
from unittest.mock import AsyncMock, patch
from mcp.server.fastmcp import FastMCP


def _text(result) -> str:
    """Extract text from a FastMCP call_tool result (tuple of list + dict)."""
    content_list = result[0]
    return content_list[0].text


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


async def test_all_tools_registered(mcp_instance):
    """Verify all expected tools are registered."""
    tools = {t.name: t for t in await mcp_instance.list_tools()}
    expected = [
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
    ]
    for name in expected:
        assert name in tools, f"Tool {name} not registered"


async def test_show_version_returns_json(mcp_instance):
    """Test netgear_show_version returns valid JSON."""
    fake_output = (
        "Machine Model................ M4250-40G8XF-PoE+\n"
        "Serial Number................ ABC123456789\n"
        "Software Version............. 14.0.1.6\n"
        "System Up Time............... 15 days 6 hrs 32 mins\n"
    )
    with patch("mcp_server.tools.core.execute_command", new_callable=AsyncMock, return_value=fake_output):
        result = await mcp_instance.call_tool("netgear_show_version", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["host"] == "10.0.0.1"
        assert data["model"] == "M4250-40G8XF-PoE+"


async def test_show_version_handles_error(mcp_instance):
    """Test netgear_show_version forwards SSH errors."""
    with patch("mcp_server.tools.core.execute_command", new_callable=AsyncMock, return_value="ERROR: ConnectTimeout: could not connect"):
        result = await mcp_instance.call_tool("netgear_show_version", {"host": "10.0.0.1"})
        assert "ERROR:" in _text(result)


async def test_cli_readonly_blocks_write(mcp_instance):
    """Test netgear_cli_readonly blocks non-show commands."""
    result = await mcp_instance.call_tool("netgear_cli_readonly", {"host": "10.0.0.1", "command": "write memory"})
    data = json.loads(_text(result))
    assert "error" in data


async def test_cli_readonly_allows_show(mcp_instance):
    """Test netgear_cli_readonly allows show commands."""
    with patch("mcp_server.tools.cli.execute_command", new_callable=AsyncMock, return_value="some output"):
        result = await mcp_instance.call_tool("netgear_cli_readonly", {"host": "10.0.0.1", "command": "show version"})
        data = json.loads(_text(result))
        assert data["output"] == "some output"


async def test_show_poe_returns_json(mcp_instance):
    """Test netgear_show_poe returns valid JSON with power data."""
    fake_output = (
        "Unit : 1\n"
        "Power Budget........................... 740.0 W\n"
        "Power Consumption...................... 123.4 W\n"
    )
    with patch("mcp_server.tools.poe.execute_command", new_callable=AsyncMock, return_value=fake_output):
        result = await mcp_instance.call_tool("netgear_show_poe", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert data["power_budget_w"] == 740.0


async def test_show_lldp_returns_json(mcp_instance):
    """Test netgear_show_lldp returns valid JSON."""
    fake_output = "some lldp output"
    with patch("mcp_server.tools.lldp.execute_command", new_callable=AsyncMock, return_value=fake_output):
        result = await mcp_instance.call_tool("netgear_show_lldp", {"host": "10.0.0.1"})
        data = json.loads(_text(result))
        assert "host" in data
