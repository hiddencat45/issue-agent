import json
from types import SimpleNamespace

import pytest

from app.trace import TraceRecorder, read_trace, write_trace
from app.trace_schema import TraceError, validate_trace
from app.trace_show import main as show_main


def test_recorder_wraps_execute_without_changing_result():
    recorder = TraceRecorder()
    seen = []

    def execute(call):
        seen.append(call.name)
        return {"ok": True, "path": call.arguments}

    wrapped = recorder.wrap_execute(execute)
    call = SimpleNamespace(name="read_file", arguments='{"path": "a.py"}')
    result = wrapped(call)

    assert result == {"ok": True, "path": '{"path": "a.py"}'}
    assert seen == ["read_file"]
    assert recorder.events == [
        {
            "type": "tool_call",
            "name": "read_file",
            "arguments": '{"path": "a.py"}',
            "result": {"ok": True, "path": '{"path": "a.py"}'},
        }
    ]


def test_write_and_read_roundtrip(tmp_path):
    path = tmp_path / "trace.json"
    payload = write_trace(
        path,
        kind="propose",
        issue_text="不要 strip",
        events=[],
        output={"path": "notes.py", "old_text": "a", "new_text": "b", "rationale": "改"},
    )
    loaded = read_trace(path)
    assert loaded == payload


def test_extra_field_is_rejected():
    data = {
        "schema_version": 1,
        "kind": "propose",
        "issue_text": "issue",
        "events": [],
        "output": {"ok": True},
        "api_key": "secret",
    }
    with pytest.raises(TraceError, match="恰好"):
        validate_trace(data)


def test_show_cli_prints_trace(tmp_path, capsys):
    path = tmp_path / "trace.json"
    write_trace(
        path,
        kind="propose",
        issue_text="不要 strip",
        events=[],
        output={"path": "notes.py"},
    )
    code = show_main(["--trace-file", str(path)])
    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert printed["kind"] == "propose"
    assert "api_key" not in printed
