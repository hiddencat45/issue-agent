import json
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


def _streams(stdout, stderr):
    return {
        "stdout": _truncate(_decode(stdout)),
        "stderr": _truncate(_decode(stderr)),
        "output": _truncate(_combine(stdout, stderr)),
    }


def run_pytest(workspace):
    """在工作区根目录运行 python -m pytest -q。不是任意 Shell，也不接受额外参数。"""
    root = Path(workspace).resolve()
    if not root.is_dir():
        result = {
            "ok": False,
            "passed": False,
            "timed_out": False,
            "command": ["python", "-m", "pytest", "-q"],
            "error": "工作区不存在或不是目录",
        }
        result.update(_streams(None, None))
        return result
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
        result = {
            "ok": False,
            "passed": False,
            "timed_out": True,
            "returncode": None,
            "command": ["python", "-m", "pytest", "-q"],
            "error": f"pytest 超过 {TIMEOUT_SECONDS} 秒",
        }
        result.update(_streams(exc.stdout, exc.stderr))
        return result
    except OSError as exc:
        result = {
            "ok": False,
            "passed": False,
            "timed_out": False,
            "command": ["python", "-m", "pytest", "-q"],
            "error": str(exc),
        }
        result.update(_streams(None, None))
        return result

    passed = completed.returncode == 0
    result = {
        "ok": passed,
        "passed": passed,
        "timed_out": False,
        "returncode": completed.returncode,
        "command": ["python", "-m", "pytest", "-q"],
    }
    result.update(_streams(completed.stdout, completed.stderr))
    if not passed:
        result["error"] = "pytest 未通过"
    return result


def load_pytest_result(raw_path):
    path = Path(raw_path)
    if not path.is_file():
        raise ValueError("--pytest-file 必须存在且是文件")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("--pytest-file 不能为空")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("--pytest-file 不是合法 JSON") from exc
    if not isinstance(data, dict) or "passed" not in data:
        raise ValueError("--pytest-file 必须是 pytest 结果 JSON")
    return data
