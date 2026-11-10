"""磁盘维护的观测指标与回收决策（SPEC-015）。"""

from __future__ import annotations

import datetime

import pytest

from src.utils import disk_metrics, disk_probe, disk_tasks


def test_parse_size_accepts_docker_units():
    assert disk_metrics.parse_size("1.5 GB") == 1_500_000_000
    assert disk_metrics.parse_size("2KiB") == 2048
    assert disk_metrics.parse_size("1 TB") == 1000**4
    assert disk_metrics.parse_size("") == 0
    assert disk_metrics.parse_size("oops") == 0


def test_human_size_keeps_binary_scale():
    assert disk_metrics.human_size(0) == "0 B"
    assert disk_metrics.human_size(1023) == "1023 B"
    assert disk_metrics.human_size(1024) == "1.0 KB"
    assert disk_metrics.human_size(1024**3) == "1.0 GB"


def test_parse_rfc3339_handles_nanoseconds_and_offsets():
    expected = datetime.datetime(
        2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc
    ).timestamp()
    assert disk_metrics.parse_rfc3339("2026-01-02T03:04:05Z") == expected
    assert disk_metrics.parse_rfc3339("2026-01-02T03:04:05.123456789Z") == (
        pytest.approx(expected + 0.123456)
    )
    assert disk_metrics.parse_rfc3339("not-a-date") is None


def test_evaluate_disk_usage_reports_dead_space():
    usage = disk_metrics.evaluate_disk_usage(10 * 1024**3, 5 * 1024**3)

    assert usage is not None
    assert usage.dead == 5 * 1024**3
    assert usage.ratio == 0.5
    assert usage.needs_compact is True
    assert usage.detail == (
        "实际占盘 10.0 GB · 有效数据约 5.0 GB · 空洞约 5.0 GB（50%）"
    )


def test_evaluate_disk_usage_clamps_live_to_allocated():
    usage = disk_metrics.evaluate_disk_usage(1024**3, 2 * 1024**3)

    assert usage is not None
    assert usage.live == 1024**3
    assert usage.dead == 0
    assert usage.ratio == 0.0
    assert usage.needs_compact is False


def test_compact_requires_both_ratio_and_absolute_threshold():
    low_ratio = disk_metrics.evaluate_disk_usage(10 * 1024**3, int(7.1 * 1024**3))
    small_disk = disk_metrics.evaluate_disk_usage(2 * 1024**3, int(1.6 * 1024**3))
    over_line = disk_metrics.evaluate_disk_usage(10 * 1024**3, 7 * 1024**3)

    assert low_ratio is not None and low_ratio.needs_compact is False
    assert small_disk is not None and small_disk.needs_compact is False
    assert over_line is not None and over_line.needs_compact is True


def test_evaluate_disk_usage_returns_none_without_live_estimate():
    assert disk_metrics.evaluate_disk_usage(1024**3, None) is None
    assert disk_metrics.unknown_live_detail(1024**3) == (
        "数据盘实际占盘 1.0 GB，Docker 未运行，暂时无法估算有效数据"
    )


def test_sandbox_record_rounds_age_days():
    record = disk_metrics.sandbox_record("img:latest", 0.0, 86400 * 2 + 43200)

    assert record == {"image": "img:latest", "created_at": 0.0, "age_days": 2.5}


def test_find_vhdx_prefers_largest_candidate(tmp_path, monkeypatch):
    root = tmp_path / "Docker" / "wsl"
    (root / "data").mkdir(parents=True)
    small = root / "small.vhdx"
    large = root / "data" / "large.vhdx"
    small.write_bytes(b"x" * 10)
    large.write_bytes(b"x" * 100)

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(disk_probe, "get_global_settings", lambda: {})
    disk_probe.reset_vhdx_cache()

    assert disk_probe.find_vhdx() == str(large)

    disk_probe.reset_vhdx_cache()
    monkeypatch.setattr(
        disk_probe, "get_global_settings", lambda: {"docker_vhdx_path": str(small)}
    )
    assert disk_probe.find_vhdx() == str(small)
    disk_probe.reset_vhdx_cache()


def test_task_registry_rejects_concurrent_run():
    assert disk_tasks.begin("compact", "[00:00:00] 开始压缩") is True
    assert disk_tasks.begin("prune", "[00:00:00] 开始清理") is False
    assert disk_tasks.get_task()["log"] == ["[00:00:00] 开始压缩"]

    disk_tasks.finish("success")

    snapshot = disk_tasks.get_task()
    assert snapshot["state"] == "success"
    assert snapshot["finished_at"] is not None
