import time


RETRYABLE_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
}

RETRYABLE_STATUS_CODES = {500, 502, 503, 504, 520, 524, 529}

RETRYABLE_TEXT = (
    "stream_read_error",
    "connection error",
    "overloaded",
    "service_unavailable",
    "server_error",
    "error code: 520",
    "status code 520",
    "http 520",
)


def is_retryable(exc):
    name = type(exc).__name__
    if name in RETRYABLE_NAMES:
        return True
    status = getattr(exc, "status_code", None)
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = None
    if status in RETRYABLE_STATUS_CODES:
        return True
    message = str(exc).lower()
    return any(token in message for token in RETRYABLE_TEXT)


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
