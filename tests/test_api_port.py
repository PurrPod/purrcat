from __future__ import annotations

import importlib.util
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.api_port import (
    DEFAULT_API_PORT,
    RUNTIME_STATE_FILENAME,
    clear_runtime_state,
    parse_port,
    read_runtime_port,
    resolve_api_port,
    runtime_state_path,
    runtime_state_port,
    write_runtime_state,
)

ROOT = Path(__file__).resolve().parent.parent


def _load_relay_module():
    """scripts/acp_relay.py 是独立部署到 ~/.purrcat/bin 的脚本（不在包内），按路径加载。"""
    spec = importlib.util.spec_from_file_location(
        "acp_relay_under_test", ROOT / "scripts" / "acp_relay.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


class RuntimeStateTests(unittest.TestCase):
    """运行时端口状态文件：写入原子性、读取容错、值边界。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # 故意放在不存在的子目录里，顺带覆盖目录自动创建
        self.state_path = os.path.join(self._tmp.name, "nested", RUNTIME_STATE_FILENAME)

    def _write_raw(self, content: str) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def _write_json(self, payload: object) -> None:
        self._write_raw(json.dumps(payload))

    def test_state_path_defaults_to_purrcat_dir(self) -> None:
        from src.utils.config import PURRCAT_DIR

        path = runtime_state_path()
        self.assertEqual(os.path.dirname(path), PURRCAT_DIR)
        self.assertEqual(os.path.basename(path), RUNTIME_STATE_FILENAME)

    def test_write_then_read_roundtrip(self) -> None:
        self.assertTrue(write_runtime_state(8001, self.state_path))
        self.assertEqual(read_runtime_port(self.state_path), 8001)
        with open(self.state_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(payload["pid"], os.getpid())

    def test_write_creates_missing_directories(self) -> None:
        self.assertFalse(os.path.isdir(os.path.dirname(self.state_path)))
        self.assertTrue(write_runtime_state(8000, self.state_path))
        self.assertTrue(os.path.isfile(self.state_path))

    def test_write_overwrites_previous_value(self) -> None:
        self.assertTrue(write_runtime_state(8000, self.state_path))
        self.assertTrue(write_runtime_state(8050, self.state_path))
        self.assertEqual(read_runtime_port(self.state_path), 8050)

    def test_write_leaves_no_temp_file(self) -> None:
        self.assertTrue(write_runtime_state(8002, self.state_path))
        self.assertFalse(os.path.exists(f"{self.state_path}.tmp"))

    def test_write_rejects_unusable_ports(self) -> None:
        for value in (0, -1, 65536, None, "", "  ", "abc", 8000.5, True):
            with self.subTest(value=value):
                self.assertFalse(write_runtime_state(value, self.state_path))
                self.assertFalse(os.path.exists(self.state_path))

    def test_write_returns_false_when_target_is_not_writable(self) -> None:
        blocker = os.path.join(self._tmp.name, "blocker")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")
        # 父路径是个普通文件：makedirs 必然失败，只允许返回 False 不能抛出
        self.assertFalse(
            write_runtime_state(8000, os.path.join(blocker, "runtime.json"))
        )

    def test_read_missing_file_returns_none(self) -> None:
        self.assertIsNone(read_runtime_port(self.state_path))

    def test_read_tolerates_corrupt_payloads(self) -> None:
        for content in ("", "   ", "not json", "[1, 2]", '"8000"', "null", "8000"):
            with self.subTest(content=content):
                self._write_raw(content)
                self.assertIsNone(read_runtime_port(self.state_path))

    def test_read_rejects_unusable_port_values(self) -> None:
        for value in (0, -1, 65536, True, False, 1.0, None, "", "abc", "0", "65536"):
            with self.subTest(value=value):
                self._write_json({"api_port": value})
                self.assertIsNone(read_runtime_port(self.state_path))

    def test_read_accepts_boundary_and_string_ports(self) -> None:
        for value, expected in (
            (1, 1),
            (65535, 65535),
            ("8001", 8001),
            (" 8001 ", 8001),
        ):
            with self.subTest(value=value):
                self._write_json({"api_port": value})
                self.assertEqual(read_runtime_port(self.state_path), expected)

    def test_runtime_state_port_ignores_non_dict_payloads(self) -> None:
        for state in (None, [], "8000", 8000, {"pid": 1}):
            with self.subTest(state=state):
                self.assertIsNone(runtime_state_port(state))

    def test_runtime_state_port_boundaries(self) -> None:
        self.assertEqual(runtime_state_port({"api_port": 1}), 1)
        self.assertEqual(runtime_state_port({"api_port": 65535}), 65535)
        for value in (0, -1, 65536, True, False, 1.0, None, ""):
            with self.subTest(value=value):
                self.assertIsNone(runtime_state_port({"api_port": value}))

    def test_clear_removes_state_and_is_idempotent(self) -> None:
        self.assertTrue(write_runtime_state(8001, self.state_path))
        clear_runtime_state(self.state_path)
        self.assertFalse(os.path.exists(self.state_path))
        self.assertIsNone(read_runtime_port(self.state_path))
        clear_runtime_state(self.state_path)  # 文件已不存在：不得抛异常

    def test_clear_missing_file_is_silent(self) -> None:
        clear_runtime_state(self.state_path)


class AcpRelayPortTests(unittest.TestCase):
    """ACP relay 的端口发现：优先级与非法来源的边界。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.relay = _load_relay_module()

    def test_default_backend_port_matches_backend_default(self) -> None:
        self.assertEqual(self.relay.DEFAULT_BACKEND_PORT, DEFAULT_API_PORT)

    def test_valid_port_accepts_only_usable_ports(self) -> None:
        for value in (1, 65535, "8000", " 8001 "):
            with self.subTest(value=value):
                self.assertIsNotNone(self.relay._valid_port(value))
        for value in (
            0,
            -1,
            65536,
            "0",
            "65536",
            "abc",
            "",
            "  ",
            True,
            False,
            1.0,
            None,
            "8000a",
        ):
            with self.subTest(value=value):
                self.assertIsNone(self.relay._valid_port(value))

    def test_all_sources_missing_falls_back_to_default(self) -> None:
        self.assertEqual(self.relay.pick_backend_port(), DEFAULT_API_PORT)

    def test_explicit_env_wins_over_everything(self) -> None:
        self.assertEqual(self.relay.pick_backend_port("9000", 8001, 8000), 9000)

    def test_runtime_wins_over_settings_after_fallback(self) -> None:
        # 核心场景：默认端口被占，后端实际跑在 8001，settings 仍是期望值 8000
        self.assertEqual(self.relay.pick_backend_port(None, 8001, 8000), 8001)

    def test_invalid_env_falls_back_to_runtime(self) -> None:
        for env_port in ("", "  ", "99999", "0", "abc"):
            with self.subTest(env_port=env_port):
                self.assertEqual(
                    self.relay.pick_backend_port(env_port, 8001, 8000), 8001
                )

    def test_invalid_runtime_falls_back_to_settings(self) -> None:
        for runtime_port in (None, "", "abc", 0, 65536, True, 1.0, {"port": 8001}):
            with self.subTest(runtime_port=runtime_port):
                self.assertEqual(
                    self.relay.pick_backend_port(None, runtime_port, 8000), 8000
                )

    def test_invalid_settings_falls_back_to_default(self) -> None:
        for settings_port in (None, "", "abc", 0, 65536, True, 1.0):
            with self.subTest(settings_port=settings_port):
                self.assertEqual(
                    self.relay.pick_backend_port(None, None, settings_port),
                    DEFAULT_API_PORT,
                )

    def test_priority_is_by_source_not_by_port_size(self) -> None:
        # runtime 里的 8000 同样胜过 settings 里的 9000：先看来源，不比数值
        self.assertEqual(self.relay.pick_backend_port(None, 8000, 9000), 8000)

    def test_runtime_file_reading_edge_cases(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            home_path = Path(home)
            runtime_file = home_path / "runtime.json"
            self.assertIsNone(self.relay._read_runtime_port(home_path))  # 文件缺失
            runtime_file.write_text("", encoding="utf-8")
            self.assertIsNone(self.relay._read_runtime_port(home_path))  # 空文件
            runtime_file.write_text("{ not json", encoding="utf-8")
            self.assertIsNone(self.relay._read_runtime_port(home_path))  # 损坏
            runtime_file.write_text('["8001"]', encoding="utf-8")
            self.assertIsNone(self.relay._read_runtime_port(home_path))  # 非对象
            runtime_file.write_text('{"pid": 1}', encoding="utf-8")
            self.assertIsNone(self.relay._read_runtime_port(home_path))  # 缺字段
            runtime_file.write_text('{"api_port": 8001}', encoding="utf-8")
            self.assertEqual(
                self.relay.pick_backend_port(
                    None, self.relay._read_runtime_port(home_path), 8000
                ),
                8001,
            )

    def _fake_home(
        self, home: str, *, runtime: str | None = None, settings: str | None = None
    ) -> None:
        config_dir = Path(home) / ".purrcat"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "acp_token").write_text("tok\n", encoding="utf-8")
        if runtime is not None:
            (config_dir / "runtime.json").write_text(runtime, encoding="utf-8")
        if settings is not None:
            (config_dir / "settings.json").write_text(settings, encoding="utf-8")

    def _discover_with_home(self, home: str):
        with mock.patch.dict(
            os.environ, {"HOME": home, "USERPROFILE": home}, clear=False
        ):
            os.environ.pop("PURRCAT_ACP_PORT", None)
            os.environ.pop("PURRCAT_ACP_TOKEN", None)
            return self.relay.discover()

    def test_discover_prefers_runtime_over_settings(self) -> None:
        # 端口 fallback 后的真实场景：后端在 8007，settings 里的期望值仍是 8000
        with tempfile.TemporaryDirectory() as home:
            self._fake_home(
                home,
                runtime='{"api_port": 8007, "pid": 1}',
                settings='{"acp_port": 8000}',
            )
            base, token = self._discover_with_home(home)
            self.assertEqual(base, "http://127.0.0.1:8007")
            self.assertEqual(token, "tok")

    def test_discover_falls_back_to_settings_without_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self._fake_home(home, settings='{"acp_port": 8005}')
            base, _ = self._discover_with_home(home)
            self.assertEqual(base, "http://127.0.0.1:8005")

    def test_discover_falls_back_to_default_when_everything_is_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self._fake_home(home, runtime="not json", settings='{"acp_port": "abc"}')
            base, _ = self._discover_with_home(home)
            self.assertEqual(base, f"http://127.0.0.1:{DEFAULT_API_PORT}")

    def test_discover_env_overrides_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self._fake_home(
                home, runtime='{"api_port": 8007}', settings='{"acp_port": 8000}'
            )
            with mock.patch.dict(
                os.environ, {"HOME": home, "USERPROFILE": home}, clear=False
            ):
                os.environ["PURRCAT_ACP_PORT"] = "9000"
                os.environ.pop("PURRCAT_ACP_TOKEN", None)
                base, _ = self.relay.discover()
            self.assertEqual(base, "http://127.0.0.1:9000")


if __name__ == "__main__":
    unittest.main()
