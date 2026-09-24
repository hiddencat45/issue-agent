import subprocess
import sys
from pathlib import Path


TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 20_000
PYTEST_ARGS = ["-m", "pytest", "-q"]


def _truncate(text):
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + "\n...[truncated]"


def _decode(payload):
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return payload.decode("utf-8", errors="replace")


def _combine(stdout, stderr):
    parts = [part for part in (_decode(stdout), _decode(stderr)) if part]
    return "".join(parts) if len(parts) <= 1 else parts[0] + "\n" + parts[1]


def run_pytest(workspace):
    """在工作区根目录运行 python -m pytest -q。不是任意 Shell，也不接受额外参数。"""
    root = Path(workspace).resolve()
    if not root.is_dir():
        return {
            "ok": False,
            "passed": False,
            "timed_out": False,
            "command": ["python", "-m", "pytest", "-q"],
            "error": "工作区不存在或不是目录",
        }
    try:
        completed = subprocess.run(
            [sys.executable, *PYTEST_ARGS],
            cwd=root,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "passed": False,
            "timed_out": True,
            "returncode": None,
            "command": ["python", "-m", "pytest", "-q"],
            "output": _truncate(_combine(exc.stdout, exc.stderr)),
            "error": f"pytest 超过 {TIMEOUT_SECONDS} 秒",
        }
    except OSError as exc:
        return {
            "ok": False,
            "passed": False,
            "timed_out": False,
            "command": ["python", "-m", "pytest", "-q"],
            "error": str(exc),
        }

    passed = completed.returncode == 0
    result = {
        "ok": passed,
        "passed": passed,
        "timed_out": False,
        "returncode": completed.returncode,
        "command": ["python", "-m", "pytest", "-q"],
        "output": _truncate(_combine(completed.stdout, completed.stderr)),
    }
    if not passed:
        result["error"] = "pytest 未通过"
    return result
