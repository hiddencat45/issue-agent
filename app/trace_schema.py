TRACE_KEYS = (
    "schema_version",
    "kind",
    "issue_text",
    "events",
    "output",
)

ALLOWED_KINDS = {"propose", "triage", "repair"}
TOOL_CALL_KEYS = ("type", "name", "arguments", "result")


class TraceError(ValueError):
    """运行记录结构不合法。"""


def validate_trace(data):
    if not isinstance(data, dict):
        raise TraceError("记录必须是 JSON 对象")
    if set(data) != set(TRACE_KEYS):
        raise TraceError("记录字段必须恰好为规定字段")
    if data["schema_version"] != 1:
        raise TraceError("不支持的 schema_version")
    if data["kind"] not in ALLOWED_KINDS:
        raise TraceError("kind 不支持")
    if not isinstance(data["issue_text"], str) or not data["issue_text"].strip():
        raise TraceError("issue_text 必须是非空字符串")
    events = data["events"]
    if not isinstance(events, list):
        raise TraceError("events 必须是数组")
    for event in events:
        _validate_event(event)
    if not isinstance(data["output"], dict):
        raise TraceError("output 必须是对象")
    return data


def _validate_event(event):
    if not isinstance(event, dict) or set(event) != set(TOOL_CALL_KEYS):
        raise TraceError("工具事件字段必须为 type、name、arguments、result")
    if event["type"] != "tool_call":
        raise TraceError("当前只支持 tool_call 事件")
    if not isinstance(event["name"], str) or not event["name"]:
        raise TraceError("工具名必须是非空字符串")
    if not isinstance(event["arguments"], str):
        raise TraceError("arguments 必须是模型给出的原始字符串")
    if not isinstance(event["result"], dict):
        raise TraceError("result 必须是对象")
