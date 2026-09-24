from __future__ import annotations

import socket
import unittest

from src.api_port import (
    DEFAULT_API_PORT,
    parse_port,
    resolve_api_port,
)


class ApiPortTests(unittest.TestCase):
    def test_default_and_empty_values(self) -> None:
        self.assertEqual(DEFAULT_API_PORT, 8000)
        self.assertIsNone(parse_port(None))
        self.assertIsNone(parse_port("  "))

    def test_invalid_ports_are_rejected(self) -> None:
        for value in ("abc", 0, 65536):
            with self.assertRaises(ValueError):
                parse_port(value)

    def test_explicit_available_port_is_preserved(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("0.0.0.0", 0))
            port = server.getsockname()[1]
        self.assertEqual(resolve_api_port(str(port)), port)

    def test_explicit_occupied_port_does_not_fallback(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("0.0.0.0", 0))
            server.listen()
            port = server.getsockname()[1]
            with self.assertRaisesRegex(ValueError, rf"API port {port} is unavailable"):
                resolve_api_port(port)

    def test_scan_falls_back_when_start_is_occupied(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("0.0.0.0", 0))
            server.listen()
            start = server.getsockname()[1]
            self.assertGreater(resolve_api_port(None, start=start, attempts=5), start)


if __name__ == "__main__":
    unittest.main()
