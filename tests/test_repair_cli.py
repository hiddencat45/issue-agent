import json

from app.repair import main


def write_workspace(tmp_path):
    (tmp_path / "notes.py").write_text('def format_note(text):\n    return text.strip()\n', encoding="utf-8")
    patch = tmp_path / "patch.json"
    patch.write_text(
        json.dumps({
            "path": "notes.py",
            "old_text": '    return text.strip()\n',
            "new_text": '    return text\n',
            "rationale": "不再去掉空格",
        }),
        encoding="utf-8",
    )
    return patch


def test_missing_allow_write_exits_nonzero(tmp_path):
    patch = write_workspace(tmp_path)
    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--patch-file",
        str(patch),
    ])
    assert code != 0


def test_relative_workspace_exits_nonzero(tmp_path):
    patch = write_workspace(tmp_path)
    code = main([
        "--workspace",
        "relative-dir",
        "--patch-file",
        str(patch),
        "--allow-write",
        "notes.py",
    ])
    assert code != 0


def test_dry_run_cli_does_not_write(tmp_path, capsys):
    patch = write_workspace(tmp_path)
    notes = tmp_path / "notes.py"
    before = notes.read_text(encoding="utf-8")

    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--patch-file",
        str(patch),
        "--allow-write",
        "notes.py",
    ])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["ok"] is True
    assert result["applied"] is False
    assert notes.read_text(encoding="utf-8") == before


def test_apply_cli_writes(tmp_path, capsys):
    patch = write_workspace(tmp_path)

    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--patch-file",
        str(patch),
        "--allow-write",
        "notes.py",
        "--apply",
    ])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["applied"] is True
    assert "strip" not in (tmp_path / "notes.py").read_text(encoding="utf-8")


def test_trace_out_records_dry_run(tmp_path, capsys):
    patch = write_workspace(tmp_path)
    notes = tmp_path / "notes.py"
    before = notes.read_text(encoding="utf-8")
    trace_path = tmp_path / "trace.json"

    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--patch-file",
        str(patch),
        "--allow-write",
        "notes.py",
        "--trace-out",
        str(trace_path),
    ])
    result = json.loads(capsys.readouterr().out)
    record = json.loads(trace_path.read_text(encoding="utf-8"))
    assert code == 0
    assert result["applied"] is False
    assert notes.read_text(encoding="utf-8") == before
    assert record["kind"] == "repair"
    assert record["output"]["applied"] is False
    assert record["events"] == []
