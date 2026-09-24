import time


def is_retryable(exc):
    name = type(exc).__name__
    message = str(exc).lower()
    if name in {"APIConnectionError", "APITimeoutError"}:
        return True
    if "stream_read_error" in message:
        return True
    if "connection error" in message:
        return True
    return False


def call_with_retry(fn, *, attempts=2, delay_seconds=1.0, on_retry=None):
    if attempts < 1:
        raise ValueError("attempts 必须大于等于 1")
    last_error = None
    for index in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if index >= attempts - 1 or not is_retryable(exc):
                raise
            if on_retry is not None:
                on_retry(index + 1, attempts - 1, exc)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
    raise last_error
