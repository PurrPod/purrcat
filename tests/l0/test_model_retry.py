"""LLM 重试策略的纯函数（SPEC-017）。"""

import pytest

from src.model.core import retry


@pytest.mark.parametrize(
    "model_name, expected",
    [
        ("gpt-4o", "gpt-4o"),
        ("openai:gpt-4o", "gpt-4o"),
        ("a:b:c", "b"),
        (":leading", "leading"),
    ],
)
def test_strip_model_prefix(model_name, expected):
    assert retry.strip_model_prefix(model_name) == expected


@pytest.mark.parametrize(
    "message",
    [
        "rate limit exceeded",
        "HTTP 429",
        "too many requests",
        "upstream 502",
        "503 unavailable",
    ],
)
def test_retryable_by_message(message):
    assert retry.is_retryable_error(Exception(message)) is True


@pytest.mark.parametrize(
    "message",
    ["invalid api key", "400 bad request", "403 forbidden", "model not found"],
)
def test_not_retryable_by_message(message):
    assert retry.is_retryable_error(Exception(message)) is False


def test_retryable_by_exception_type(monkeypatch):
    class _Conn(Exception):
        pass

    monkeypatch.setattr(retry, "APIConnectionError", _Conn)

    assert retry.is_retryable_error(_Conn("boom")) is True


def test_backoff_is_exponential_with_explicit_jitter():
    assert retry.backoff_seconds(0, jitter=1.0) == 2.0
    assert retry.backoff_seconds(1, jitter=1.0) == 4.0
    assert retry.backoff_seconds(3, jitter=1.0) == 16.0


def test_backoff_jitter_range():
    for _ in range(20):
        value = retry.backoff_seconds(0)
        assert 1.6 <= value <= 2.4


def test_max_retries_constant_is_stable():
    assert retry.MAX_RETRIES == 8
