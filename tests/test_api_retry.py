import pytest

from app.api_retry import call_with_retry, is_retryable


class FakeConnectionError(Exception):
    def __str__(self):
        return "Connection error."


def test_retries_connection_error_then_succeeds():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise FakeConnectionError()
        return "ok"

    seen = []

    def on_retry(tried, remaining, exc):
        seen.append((tried, remaining, str(exc)))

    assert call_with_retry(fn, attempts=2, delay_seconds=0, on_retry=on_retry) == "ok"
    assert calls["n"] == 2
    assert seen == [(1, 1, "Connection error.")]


def test_does_not_retry_value_error():
    def fn():
        raise ValueError("arguments 键集不符")

    with pytest.raises(ValueError, match="键集不符"):
        call_with_retry(fn, attempts=3, delay_seconds=0)


def test_stream_read_error_is_retryable():
    assert is_retryable(RuntimeError("stream_read_error")) is True
    assert is_retryable(ValueError("报告不是合法 JSON")) is False
