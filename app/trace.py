import json
from pathlib import Path

from app.trace_schema import TraceError, validate_trace


class TraceRecorder:
    def __init__(self):
        self.events = []

    def wrap_execute(self, execute_tool_fn):
        def wrapped(call):
            result = execute_tool_fn(call)
            self.events.append({
                "type": "tool_call",
                "name": call.name,
                "arguments": call.arguments,
                "result": result,
            })
            return result

        return wrapped


def write_trace(path, *, kind, issue_text, events, output):
    payload = {
        "schema_version": 1,
        "kind": kind,
        "issue_text": issue_text,
        "events": events,
        "output": output,
    }
    validate_trace(payload)
    target = Path(path)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def read_trace(path):
    target = Path(path)
    if not target.is_file():
        raise TraceError("记录文件不存在")
    text = target.read_text(encoding="utf-8")
    if not text.strip():
        raise TraceError("记录文件不能为空")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TraceError("记录不是合法 JSON") from exc
    return validate_trace(data)
