"""Port selection shared by the Python API entry point and its tests."""

from __future__ import annotations

import socket

DEFAULT_API_PORT = 8000
DEFAULT_SCAN_ATTEMPTS = 50


def parse_port(value: object | None) -> int | None:
    """Parse a configured port, returning ``None`` when it is not configured."""

    if value is None or str(value).strip() == "":
        return None

    raw = str(value).strip()
    if not raw.isdecimal():
        raise ValueError(
            f'Invalid API port "{value}". Use an integer between 1 and 65535.'
        )

    port = int(raw)
    if not 1 <= port <= 65535:
        raise ValueError(
            f'Invalid API port "{value}". Use an integer between 1 and 65535.'
        )
    return port


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Return whether the API can bind ``host:port`` at this moment."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def resolve_api_port(
    requested: object | None,
    *,
    host: str = "0.0.0.0",
    start: int = DEFAULT_API_PORT,
    attempts: int = DEFAULT_SCAN_ATTEMPTS,
) -> int:
    """Resolve an explicit port or the first available port from the default range.

    An explicit port is strict: it never silently falls back. With no explicit
    value, the default port is tried first and then subsequent ports are used.
    """

    explicit = requested is not None and str(requested).strip() != ""
    if explicit:
        port = parse_port(requested)
        assert port is not None
        if not is_port_available(port, host):
            raise ValueError(f"API port {port} is unavailable.")
        return port

    if not 1 <= start <= 65535:
        raise ValueError("API port scan start must be between 1 and 65535.")
    if attempts < 1:
        raise ValueError("API port scan attempts must be a positive integer.")

    for offset in range(attempts):
        port = start + offset
        if port > 65535:
            break
        if is_port_available(port, host):
            return port

    end = min(65535, start + attempts - 1)
    raise ValueError(f"No available API port found between {start} and {end}.")
