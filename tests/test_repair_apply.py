from app.repair_apply import apply_repair_patch


def write_notes(tmp_path):
    path = tmp_path / "notes.py"
    path.write_text('def format_note(text):\n    return text.strip()\n', encoding="utf-8")
    return path


def patch_body():
    return {
        "path": "notes.py",
        "old_text": '    return text.strip()\n',
        "new_text": '    return text\n',
        "rationale": "不再去掉空格",
    }


def test_dry_run_does_not_write(tmp_path):
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")

    result = apply_repair_patch(
        tmp_path,
        patch_body(),
        allowed_paths=["notes.py"],
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["applied"] is False
    assert notes.read_text(encoding="utf-8") == before


def test_apply_writes_when_allowed(tmp_path):
    notes = write_notes(tmp_path)

    result = apply_repair_patch(
        tmp_path,
        patch_body(),
        allowed_paths=["notes.py"],
        dry_run=False,
    )

    assert result["ok"] is True
    assert result["applied"] is True
    text = notes.read_text(encoding="utf-8")
    assert '    return text\n' in text
    assert "strip" not in text


def test_reject_path_not_allowed(tmp_path):
    write_notes(tmp_path)
    result = apply_repair_patch(
        tmp_path,
        patch_body(),
        allowed_paths=["other.py"],
        dry_run=False,
    )
    assert result["ok"] is False
    assert "allow-write" in result["error"]


def test_reject_old_text_mismatch(tmp_path):
    write_notes(tmp_path)
    patch = patch_body()
    patch["old_text"] = "not in file"
    result = apply_repair_patch(
        tmp_path,
        patch,
        allowed_paths=["notes.py"],
        dry_run=False,
    )
    assert result["ok"] is False
    assert "恰好出现一次" in result["error"]
