import json
from types import SimpleNamespace

from app.repair_apply import apply_repair_patch
from app.tools.repository import RepositoryTools
from app.trace import write_trace
from app.trace_replay import main, replay_trace
from app.triage_tools import execute_tool


def write_notes(tmp_path):
    path = tmp_path / "notes.py"
    path.write_text('def format_note(text):\n    return text.strip()\n', encoding="utf-8")
    return path


def test_replay_tool_call_matches(tmp_path):
    write_notes(tmp_path)
    repository = RepositoryTools(tmp_path)
    call = SimpleNamespace(name="read_file", arguments='{"path": "notes.py"}')
    result = execute_tool(call, repository)
    trace_path = tmp_path / "trace.json"
    write_trace(
        trace_path,
        kind="triage",
        issue_text="读取 notes",
        events=[{
            "type": "tool_call",
            "name": "read_file",
            "arguments": '{"path": "notes.py"}',
            "result": result,
        }],
        output={"issue_summary": "读取 notes"},
    )
    replay = replay_trace(tmp_path.resolve(), json.loads(trace_path.read_text(encoding="utf-8")))
    assert replay["ok"] is True
    assert replay["mismatches"] == []


def test_replay_detects_changed_file(tmp_path):
    notes = write_notes(tmp_path)
    repository = RepositoryTools(tmp_path)
    call = SimpleNamespace(name="read_file", arguments='{"path": "notes.py"}')
    result = execute_tool(call, repository)
    write_trace(
        tmp_path / "trace.json",
        kind="propose",
        issue_text="读取 notes",
        events=[{
            "type": "tool_call",
            "name": "read_file",
            "arguments": '{"path": "notes.py"}',
            "result": result,
        }],
        output={"path": "notes.py"},
    )
    notes.write_text("changed", encoding="utf-8")
    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--trace-file",
        str(tmp_path / "trace.json"),
    ])
    assert code != 0


def test_replay_repair_dry_run_does_not_write(tmp_path):
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")
    patch = {
        "path": "notes.py",
        "old_text": "    return text.strip()" + '\n',
        "new_text": "    return text" + '\n',
        "rationale": "不再去掉空格",
    }
    recorded = apply_repair_patch(
        tmp_path,
        patch,
        allowed_paths=["notes.py"],
        dry_run=True,
    )
    write_trace(
        tmp_path / "trace.json",
        kind="repair",
        issue_text=json.dumps(patch, ensure_ascii=False),
        events=[],
        output=recorded,
    )
    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--trace-file",
        str(tmp_path / "trace.json"),
    ])
    assert code == 0
    assert notes.read_text(encoding="utf-8") == before


def test_replay_applied_repair_checks_new_text(tmp_path):
    notes = write_notes(tmp_path)
    patch = {
        "path": "notes.py",
        "old_text": "    return text.strip()" + '\n',
        "new_text": "    return text" + '\n',
        "rationale": "不再去掉空格",
    }
    recorded = apply_repair_patch(
        tmp_path,
        patch,
        allowed_paths=["notes.py"],
        dry_run=False,
    )
    assert recorded["applied"] is True
    write_trace(
        tmp_path / "trace.json",
        kind="repair",
        issue_text=json.dumps(patch, ensure_ascii=False),
        events=[],
        output=recorded,
    )
    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--trace-file",
        str(tmp_path / "trace.json"),
    ])
    assert code == 0
    notes.write_text('def format_note(text):\n    return text.strip()\n', encoding="utf-8")
    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--trace-file",
        str(tmp_path / "trace.json"),
    ])
    assert code != 0
