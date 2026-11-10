"""Sensor 子进程环境构造与进程控制（SPEC-011）。"""

from __future__ import annotations

import subprocess

import pytest

from src.sensor import processes


def test_build_env_strips_parent_python_vars():
    base = {key: "x" for key in processes.PYTHON_ENV_KEYS}
    base["PATH"] = "/bin"

    env = processes.build_sensor_env(base, {})

    assert not any(key in env for key in processes.PYTHON_ENV_KEYS)
    assert env["PATH"] == "/bin"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_build_env_merges_sensor_config_env():
    env = processes.build_sensor_env({"A": "1"}, {"env": {"A": "2", "B": "3"}})

    assert env["A"] == "2"
    assert env["B"] == "3"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_build_env_does_not_mutate_base():
    base = {"PYTHONPATH": "x"}

    processes.build_sensor_env(base, {"env": {"NEW": "1"}})

    assert base == {"PYTHONPATH": "x"}


def test_sensor_command_uses_uv_run():
    assert processes.sensor_command("C:/sensors/a.py") == [
        "uv",
        "run",
        "C:/sensors/a.py",
    ]


def test_candidate_urls_prefers_package_layout():
    urls = processes.candidate_urls("https://repo/sensors", "clock")

    assert urls == [
        "https://repo/sensors/clock/clock.py",
        "https://repo/sensors/clock.py",
    ]


class _FakeStdin:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeProcess:
    def __init__(self, pid=123):
        self.pid = pid
        self.stdin = _FakeStdin()


def test_close_stdin_handles_missing_and_closed_pipes():
    processes.close_stdin(_FakeProcess())
    processes.close_stdin(type("P", (), {"stdin": None})())


def test_kill_process_tree_uses_taskkill_on_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(processes, "_IS_WINDOWS", True)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    proc = _FakeProcess()

    processes.kill_process_tree(proc)

    assert calls and calls[0][0][0][0] == "taskkill"
    assert proc.stdin.closed is True


def test_kill_process_tree_terminates_on_posix(monkeypatch):
    monkeypatch.setattr(processes, "_IS_WINDOWS", False)

    class _Proc(_FakeProcess):
        terminated = False

        def terminate(self):
            self.terminated = True

    proc = _Proc()
    processes.kill_process_tree(proc)

    assert proc.terminated is True
    assert proc.stdin.closed is True


def test_kill_process_tree_swallows_errors():
    class _Broken:
        stdin = None

        @property
        def pid(self):
            raise RuntimeError("pid unavailable")

    processes.kill_process_tree(_Broken())


@pytest.mark.parametrize("name", ["clock", "feishu"])
def test_download_base_is_official_repo(name):
    urls = processes.candidate_urls(processes.DOWNLOAD_BASE, name)

    assert all(
        url.startswith("https://raw.githubusercontent.com/PurrPod/sensors/")
        for url in urls
    )
