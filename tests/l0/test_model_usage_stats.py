"""模型用量账本的纯函数（SPEC-017）。"""

import importlib
import json
from types import SimpleNamespace

from src.model.manager import usage_stats

tracer_mod = importlib.import_module("src.model.manager.usage_tracer")


def _usage(prompt=10, completion=5, total=15, cached=0, reasoning=0):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached) if cached else None,
        completion_tokens_details=(
            SimpleNamespace(reasoning_tokens=reasoning) if reasoning else None
        ),
    )


def test_mask_api_key_hides_short_and_middle():
    assert usage_stats.mask_api_key("") == "UNKNOWN"
    assert usage_stats.mask_api_key("short") == "***"
    assert usage_stats.mask_api_key("sk-1234567890abcdef") == "sk-123***cdef"


def test_extract_usage_fields_reads_details():
    fields = usage_stats.extract_usage_fields(_usage(cached=3, reasoning=2))

    assert fields == {
        "prompt_tokens": 10,
        "cached_tokens": 3,
        "completion_tokens": 5,
        "reasoning_tokens": 2,
        "total_tokens": 15,
    }


def test_extract_usage_fields_tolerates_missing_details():
    fields = usage_stats.extract_usage_fields(_usage())

    assert fields["cached_tokens"] == 0
    assert fields["reasoning_tokens"] == 0


def test_empty_bucket_and_apply_delta():
    bucket = usage_stats.empty_bucket("m", "k***y")
    fields = usage_stats.extract_usage_fields(_usage(cached=3))

    usage_stats.apply_delta(bucket, fields, 0.1234)
    usage_stats.apply_delta(bucket, fields, 0.2)

    assert bucket["calls"] == 2
    assert bucket["prompt_tokens"] == 20
    assert bucket["total_duration_s"] == 0.323


def test_merge_into_disk_accumulates_existing_and_appends_new():
    disk = [
        {
            "model": "m",
            "api_key": "k",
            "calls": 1,
            **{field: 1 for field in usage_stats.SUMMARY_FIELDS},
            "total_duration_s": 1.0,
        }
    ]
    delta = {
        "m|k": {
            "model": "m",
            "api_key": "k",
            "calls": 2,
            **{field: 2 for field in usage_stats.SUMMARY_FIELDS},
            "total_duration_s": 0.5,
        },
        "n|j": {
            "model": "n",
            "api_key": "j",
            "calls": 1,
            **{field: 3 for field in usage_stats.SUMMARY_FIELDS},
            "total_duration_s": 0.5,
        },
    }

    merged = usage_stats.merge_into_disk(disk, delta)

    assert [item["model"] for item in merged] == ["m", "n"]
    assert merged[0]["calls"] == 3
    assert merged[0]["prompt_tokens"] == 3
    assert merged[0]["total_duration_s"] == 1.5
    assert merged[1]["prompt_tokens"] == 3


def test_tracer_record_then_flush_writes_daily_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(tracer_mod, "TRACKER_DIR", str(tmp_path))
    tracer = object.__new__(tracer_mod.ModelUsageTracer)
    tracer._init()
    tracer._flush_interval = 10_000.0

    tracer.record("m", "sk-1234567890abcdef", _usage(cached=2), 0.5)
    tracer.record("m", "sk-1234567890abcdef", _usage(), 0.25)
    tracer.flush()

    files = list((tmp_path / "model_usage").glob("*_summary.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data[0]["calls"] == 2
    assert data[0]["cached_tokens"] == 2
    assert data[0]["total_tokens"] == 30
    assert tracer._pending_deltas == {}


def test_tracer_ignores_missing_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(tracer_mod, "TRACKER_DIR", str(tmp_path))
    tracer = object.__new__(tracer_mod.ModelUsageTracer)
    tracer._init()

    tracer.record("m", "k", None, 1.0)

    assert tracer._pending_deltas == {}
