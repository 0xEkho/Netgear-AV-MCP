"""
MCP Server for NETGEAR AV switches (M4250 / M4300 / M4350).

This module initialises the FastMCP server, applies optional bearer-token
and IP-allowlist security, dynamically loads tool modules, and exposes
``main()`` as the CLI entry-point.

Transports supported (selected via ``MCP_TRANSPORT`` env var):
  - ``streamable-http`` (default)
  - ``sse``
  - ``stdio``
"""

from __future__ import annotations

import importlib
import ipaddress
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

# ── Load .env FIRST ─────────────────────────────────────────────────────
load_dotenv()

from mcp.server.fastmcp import FastMCP  # noqa: E402

# ── Logging — stderr only (never stdout for STDIO transport) ────────────
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ── FastMCP instance ────────────────────────────────────────────────────
mcp = FastMCP(
    os.getenv("MCP_SERVER_NAME", "netgear-av-mcp"),
    host=os.getenv("MCP_HOST", "0.0.0.0"),  # noqa: S104
    port=int(os.getenv("MCP_PORT", "8082")),
)


# ── Security: Bearer token + IP allowlist (ASGI middleware) ─────────────

class _SecurityMiddleware:
    """Pure ASGI middleware — bearer-token & IP-allowlist checks.

    Streaming-safe: never buffers the response body.

    Args:
        app: Inner ASGI application to wrap.
        api_key: Expected Bearer token value; empty string disables the check.
        allowed_networks: Permitted client IP networks; empty list disables.
    """

    def __init__(
        self,
        app: Any,
        api_key: str,
        allowed_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
    ) -> None:
        self.app = app
        self.api_key = api_key
        self.allowed_networks = allowed_networks

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ── IP allowlist ────────────────────────────────────────────
        if self.allowed_networks:
            client = scope.get("client")
            client_host: str | None = client[0] if client else None
            if not client_host:
                await self._respond(send, 403, "Forbidden: no client IP")
                return
            try:
                client_ip = ipaddress.ip_address(client_host)
                if not any(client_ip in net for net in self.allowed_networks):
                    logger.warning("Rejected request from %s", client_host)
                    await self._respond(send, 403, "Forbidden: IP not allowed")
                    return
            except ValueError:
                await self._respond(send, 403, "Forbidden: invalid client IP")
                return

        # ── Bearer token ────────────────────────────────────────────
        if self.api_key:
            headers: dict[bytes, bytes] = dict(scope.get("headers", []))
            auth_bytes = headers.get(b"authorization", b"")
            auth_header = auth_bytes.decode("latin-1", errors="replace")
            if not auth_header.startswith("Bearer "):
                await self._respond(send, 401, "Unauthorized: missing Bearer token")
                return
            token = auth_header[len("Bearer "):].strip()
            if token != self.api_key:
                logger.warning("Rejected request: invalid API key")
                await self._respond(send, 401, "Unauthorized: invalid API key")
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _respond(send: Any, status: int, body: str) -> None:
        encoded = body.encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(encoded)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": encoded, "more_body": False})


def _build_allowed_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse ``MCP_ALLOWED_IPS`` into a list of network objects."""
    raw = os.getenv("MCP_ALLOWED_IPS", "").strip()
    if not raw:
        return []
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in raw.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("Invalid CIDR in MCP_ALLOWED_IPS: %r — ignored", cidr)
    return nets


def _apply_security(app: Any) -> Any:
    """Wrap *app* with :class:`_SecurityMiddleware` when auth is configured."""
    api_key = os.getenv("MCP_API_KEY", "").strip()
    allowed_networks = _build_allowed_networks()
    if not api_key and not allowed_networks:
        logger.debug("No MCP_API_KEY / MCP_ALLOWED_IPS — security middleware skipped")
        return app
    logger.info(
        "Security middleware enabled: api_key=%s, allowed_networks=%d",
        "yes" if api_key else "no",
        len(allowed_networks),
    )
    return _SecurityMiddleware(app, api_key, allowed_networks)


# ── Dynamic tool registration ──────────────────────────────────────────

_TOOL_MODULES: list[str] = [
    "mcp_server.tools.core",
    "mcp_server.tools.ports",
    "mcp_server.tools.vlan",
    "mcp_server.tools.poe",
    "mcp_server.tools.spantree",
    "mcp_server.tools.routing",
    "mcp_server.tools.lldp",
    "mcp_server.tools.cli",
]


def _register_tool_modules() -> None:
    """Import each tool module and call its ``register_tools(mcp)`` function.

    Modules that fail to import are logged and skipped (graceful
    degradation).
    """
    for module_path in _TOOL_MODULES:
        short = module_path.rsplit(".", 1)[-1]
        try:
            mod = importlib.import_module(module_path)
            register_fn = getattr(mod, "register_tools", None)
            if register_fn is None:
                logger.warning("Module %s has no register_tools(), skipping", short)
                continue
            register_fn(mcp)
            logger.info("Registered tool module: %s", short)
        except Exception:
            logger.exception("Failed to load tool module: %s", short)


# ── Entry-point ─────────────────────────────────────────────────────────


def main() -> None:
    """Start the NETGEAR AV MCP server.

    The transport is selected via the ``MCP_TRANSPORT`` environment variable
    (default: ``streamable-http``).  Supported values: ``stdio``, ``sse``,
    ``streamable-http``.
    """
    _register_tool_modules()

    transport = os.getenv("MCP_TRANSPORT", "streamable-http").strip().lower()
    logger.info("Starting NETGEAR AV MCP server (transport=%s)", transport)

    if transport == "stdio":
        mcp.run(transport="stdio")
        return

    if transport not in ("sse", "streamable-http"):
        logger.error(
            "Unknown MCP_TRANSPORT=%r — expected stdio, sse or streamable-http",
            transport,
        )
        sys.exit(1)

    # HTTP transports: build Starlette app, apply security, serve via uvicorn.
    import anyio
    import uvicorn

    async def _serve() -> None:
        if transport == "sse":
            mcp_app = mcp.sse_app()
        else:
            mcp_app = mcp.streamable_http_app()

        secured_app = _apply_security(mcp_app)

        config = uvicorn.Config(
            secured_app,
            host=mcp.settings.host,
            port=mcp.settings.port,
            log_level=os.getenv("LOG_LEVEL", "info").lower(),
        )
        server = uvicorn.Server(config)
        logger.info(
            "Uvicorn listening on %s:%d (transport=%s)",
            mcp.settings.host,
            mcp.settings.port,
            transport,
        )
        await server.serve()

    anyio.run(_serve)


if __name__ == "__main__":
    main()
