"""Tests for SSH credential resolution."""
import os
import pytest
from unittest.mock import patch


class TestGetZone:
    """Tests for _get_zone() function."""

    def test_zone_detection_10_9_x_x(self):
        """10.9.0.1 → zone 9"""
        from mcp_server.ssh.auth import _get_zone
        assert _get_zone("10.9.0.1") == 9

    def test_zone_detection_10_1_x_x(self):
        """10.1.0.1 → zone 1"""
        from mcp_server.ssh.auth import _get_zone
        assert _get_zone("10.1.0.1") == 1

    def test_no_zone_192_168(self):
        """192.168.1.1 → None (not 10.x)"""
        from mcp_server.ssh.auth import _get_zone
        assert _get_zone("192.168.1.1") is None

    def test_no_zone_invalid_ip(self):
        """Invalid IP → None"""
        from mcp_server.ssh.auth import _get_zone
        assert _get_zone("not-an-ip") is None

    def test_no_zone_ipv6(self):
        """IPv6 → None"""
        from mcp_server.ssh.auth import _get_zone
        assert _get_zone("::1") is None


class TestGetCredentials:
    """Tests for get_credentials() function."""

    def test_global_credentials(self):
        """Returns global creds when no zone match."""
        from mcp_server.ssh.auth import get_credentials
        with patch.dict(os.environ, {
            "NETGEAR_GLOBAL_USERNAME": "admin",
            "NETGEAR_GLOBAL_PASSWORD": "pass123",
        }, clear=False):
            user, pwd = get_credentials("192.168.1.1")
            assert user == "admin"
            assert pwd == "pass123"

    def test_zone_credentials_override(self):
        """Zone creds override global for 10.9.x.x."""
        from mcp_server.ssh.auth import get_credentials
        with patch.dict(os.environ, {
            "NETGEAR_GLOBAL_USERNAME": "admin",
            "NETGEAR_GLOBAL_PASSWORD": "global",
            "NETGEAR_ZONE9_USERNAME": "zone9user",
            "NETGEAR_ZONE9_PASSWORD": "zone9pass",
        }, clear=False):
            user, pwd = get_credentials("10.9.0.1")
            assert user == "zone9user"
            assert pwd == "zone9pass"

    def test_zone_fallback_to_global(self):
        """Falls back to global when zone creds not set."""
        from mcp_server.ssh.auth import get_credentials
        env = {
            "NETGEAR_GLOBAL_USERNAME": "admin",
            "NETGEAR_GLOBAL_PASSWORD": "global",
        }
        # Remove zone vars if present
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("NETGEAR_ZONE9_USERNAME", None)
            os.environ.pop("NETGEAR_ZONE9_PASSWORD", None)
            user, pwd = get_credentials("10.9.1.1")
            assert user == "admin"
            assert pwd == "global"

    def test_empty_credentials(self):
        """Returns empty strings when nothing configured."""
        from mcp_server.ssh.auth import get_credentials
        with patch.dict(os.environ, {}, clear=True):
            user, pwd = get_credentials("192.168.1.1")
            assert user == ""
            assert pwd == ""
