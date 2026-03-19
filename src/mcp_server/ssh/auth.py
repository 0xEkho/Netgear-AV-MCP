"""
Credential resolution for NETGEAR AV switches.

Looks up SSH credentials from environment variables using a zone-based
fallback strategy:

1. ``NETGEAR_ZONE{X}_USERNAME`` / ``NETGEAR_ZONE{X}_PASSWORD`` — where *X*
   is the second octet of a ``10.X.0.0/16`` address.
2. ``NETGEAR_GLOBAL_USERNAME`` / ``NETGEAR_GLOBAL_PASSWORD`` — default
   fallback for any host.

All values are read via :func:`os.getenv`; they must be defined in the
process environment (typically loaded from ``.env`` by ``python-dotenv``).
"""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(stream=sys.stderr)
logger = logging.getLogger(__name__)

_DEFAULT_USERNAME = ""
_DEFAULT_PASSWORD = ""


def _get_zone(host: str) -> int | None:
    """Extract the zone number from a ``10.X.0.0/16`` address.

    The zone is the second octet of the IP address when the first octet is
    ``10``.

    Args:
        host: IPv4 address string (e.g. ``"10.9.0.1"``).

    Returns:
        The second octet as an integer, or ``None`` if *host* is not in the
        ``10.0.0.0/8`` range or is unparseable.
    """
    try:
        parts = host.strip().split(".")
        if len(parts) != 4:
            return None
        if parts[0] != "10":
            return None
        zone = int(parts[1])
        return zone
    except (ValueError, IndexError):
        return None


def get_credentials(host: str) -> tuple[str, str]:
    """Return ``(username, password)`` for a NETGEAR switch.

    Resolution order:

    1. Zone-specific: ``NETGEAR_ZONE{X}_USERNAME`` / ``NETGEAR_ZONE{X}_PASSWORD``
    2. Global: ``NETGEAR_GLOBAL_USERNAME`` / ``NETGEAR_GLOBAL_PASSWORD``
    3. Hard-coded defaults (``admin`` / empty string).

    Args:
        host: IP address of the target switch.

    Returns:
        A ``(username, password)`` tuple.
    """
    zone = _get_zone(host)

    # 1 — Zone-specific credentials
    if zone is not None:
        zone_user = os.getenv(f"NETGEAR_ZONE{zone}_USERNAME")
        zone_pass = os.getenv(f"NETGEAR_ZONE{zone}_PASSWORD")
        if zone_user and zone_pass:
            logger.debug("Using zone %d credentials for %s", zone, host)
            return zone_user, zone_pass

    # 2 — Global credentials
    global_user = os.getenv("NETGEAR_GLOBAL_USERNAME")
    global_pass = os.getenv("NETGEAR_GLOBAL_PASSWORD")
    if global_user and global_pass:
        logger.debug("Using global credentials for %s", host)
        return global_user, global_pass

    # 3 — Defaults
    logger.debug("Using default credentials for %s", host)
    return _DEFAULT_USERNAME, _DEFAULT_PASSWORD
