"""Tests for server.py — security middleware, allowed networks, apply_security."""

import os
import ipaddress

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.server import _build_allowed_networks, _apply_security, _SecurityMiddleware


# ═══════════════════════════════════════════════════════════════════════════
# _build_allowed_networks
# ═══════════════════════════════════════════════════════════════════════════

def test_build_allowed_networks_empty():
    """Empty MCP_ALLOWED_IPS returns empty list."""
    with patch.dict(os.environ, {"MCP_ALLOWED_IPS": ""}, clear=False):
        assert _build_allowed_networks() == []


def test_build_allowed_networks_parses_cidrs():
    """Comma-separated CIDRs are parsed into network objects."""
    with patch.dict(os.environ, {"MCP_ALLOWED_IPS": "10.0.0.0/8, 192.168.1.0/24"}, clear=False):
        nets = _build_allowed_networks()
        assert len(nets) == 2
        assert ipaddress.ip_address("10.1.2.3") in nets[0]
        assert ipaddress.ip_address("192.168.1.100") in nets[1]


def test_build_allowed_networks_ignores_invalid():
    """Invalid CIDRs are silently skipped."""
    with patch.dict(os.environ, {"MCP_ALLOWED_IPS": "10.0.0.0/8, not-a-cidr, 172.16.0.0/12"}, clear=False):
        nets = _build_allowed_networks()
        assert len(nets) == 2


def test_build_allowed_networks_unset():
    """Unset MCP_ALLOWED_IPS returns empty list."""
    env = os.environ.copy()
    env.pop("MCP_ALLOWED_IPS", None)
    with patch.dict(os.environ, env, clear=True):
        assert _build_allowed_networks() == []


# ═══════════════════════════════════════════════════════════════════════════
# _apply_security
# ═══════════════════════════════════════════════════════════════════════════

def test_apply_security_returns_app_when_no_config():
    """Without MCP_API_KEY or MCP_ALLOWED_IPS, the app is returned unwrapped."""
    env = os.environ.copy()
    env.pop("MCP_API_KEY", None)
    env.pop("MCP_ALLOWED_IPS", None)
    sentinel = object()
    with patch.dict(os.environ, env, clear=True):
        result = _apply_security(sentinel)
        assert result is sentinel


def test_apply_security_wraps_when_api_key_set():
    """With MCP_API_KEY set, the returned app is a _SecurityMiddleware."""
    with patch.dict(os.environ, {"MCP_API_KEY": "test-secret", "MCP_ALLOWED_IPS": ""}, clear=False):
        sentinel = object()
        result = _apply_security(sentinel)
        assert isinstance(result, _SecurityMiddleware)


# ═══════════════════════════════════════════════════════════════════════════
# _SecurityMiddleware
# ═══════════════════════════════════════════════════════════════════════════

def _make_middleware(
    api_key: str = "",
    allowed_cidrs: list[str] | None = None,
) -> _SecurityMiddleware:
    """Factory to create a middleware wrapping a dummy ASGI app."""
    inner = AsyncMock()
    nets = []
    for cidr in (allowed_cidrs or []):
        nets.append(ipaddress.ip_network(cidr, strict=False))
    return _SecurityMiddleware(inner, api_key=api_key, allowed_networks=nets)


def _http_scope(
    client_ip: str = "10.0.0.1",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    """Build a minimal ASGI HTTP scope."""
    return {
        "type": "http",
        "client": (client_ip, 12345),
        "headers": headers or [],
    }


async def test_security_middleware_passes_non_http():
    """Non-HTTP scopes (e.g. websocket, lifespan) are forwarded as-is."""
    mw = _make_middleware(api_key="secret", allowed_cidrs=["10.0.0.0/8"])
    scope = {"type": "lifespan"}
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    mw.app.assert_called_once_with(scope, receive, send)


async def test_security_middleware_allows_valid_ip():
    """Request from an allowed IP passes through."""
    mw = _make_middleware(allowed_cidrs=["10.0.0.0/8"])
    scope = _http_scope(client_ip="10.1.2.3")
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    mw.app.assert_called_once()


async def test_security_middleware_blocks_invalid_ip():
    """Request from a disallowed IP gets 403."""
    mw = _make_middleware(allowed_cidrs=["10.0.0.0/8"])
    scope = _http_scope(client_ip="192.168.1.1")
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    mw.app.assert_not_called()
    # Verify 403 was sent
    calls = send.call_args_list
    assert any(
        c.args[0].get("status") == 403
        for c in calls
        if isinstance(c.args[0], dict) and "status" in c.args[0]
    )


async def test_security_middleware_allows_valid_token():
    """Request with correct Bearer token passes through."""
    mw = _make_middleware(api_key="my-secret")
    scope = _http_scope(headers=[(b"authorization", b"Bearer my-secret")])
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    mw.app.assert_called_once()


async def test_security_middleware_blocks_invalid_token():
    """Request with wrong Bearer token gets 401."""
    mw = _make_middleware(api_key="my-secret")
    scope = _http_scope(headers=[(b"authorization", b"Bearer wrong-key")])
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    mw.app.assert_not_called()
    calls = send.call_args_list
    assert any(
        c.args[0].get("status") == 401
        for c in calls
        if isinstance(c.args[0], dict) and "status" in c.args[0]
    )


async def test_security_middleware_blocks_missing_token():
    """Request without Authorization header gets 401."""
    mw = _make_middleware(api_key="my-secret")
    scope = _http_scope(headers=[])
    receive = AsyncMock()
    send = AsyncMock()
    await mw(scope, receive, send)
    mw.app.assert_not_called()
    calls = send.call_args_list
    assert any(
        c.args[0].get("status") == 401
        for c in calls
        if isinstance(c.args[0], dict) and "status" in c.args[0]
    )
