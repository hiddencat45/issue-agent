from app.repair_apply import apply_repair_patch, restore_files


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


def write_readme(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# notes\n会去掉空格\n", encoding="utf-8")
    return path


def two_file_patch():
    return {
        "rationale": "代码和说明一起改",
        "edits": [
            {
                "path": "notes.py",
                "old_text": "    return text.strip()\n",
                "new_text": "    return text\n",
            },
            {
                "path": "README.md",
                "old_text": "会去掉空格",
                "new_text": "会保留空格",
            },
        ],
    }


def test_same_file_two_hunks(tmp_path):
    notes = tmp_path / "notes.py"
    notes.write_text(
        "def format_note(text):\n    return text.strip()\n\ndef other():\n    return 1\n",
        encoding="utf-8",
    )
    patch = {
        "rationale": "两处都改",
        "edits": [
            {
                "path": "notes.py",
                "old_text": "    return text.strip()\n",
                "new_text": "    return text\n",
            },
            {
                "path": "notes.py",
                "old_text": "    return 1\n",
                "new_text": "    return 2\n",
            },
        ],
    }
    result = apply_repair_patch(
        tmp_path,
        patch,
        allowed_paths=["notes.py"],
        dry_run=False,
    )
    assert result["ok"] is True
    assert result["edits"] == 2
    text = notes.read_text(encoding="utf-8")
    assert "strip" not in text
    assert "return 2" in text


def test_two_files_apply(tmp_path):
    notes = write_notes(tmp_path)
    readme = write_readme(tmp_path)
    result = apply_repair_patch(
        tmp_path,
        two_file_patch(),
        allowed_paths=["notes.py", "README.md"],
        dry_run=False,
    )
    assert result["ok"] is True
    assert result["paths"] == ["notes.py", "README.md"]
    assert "strip" not in notes.read_text(encoding="utf-8")
    assert "会保留空格" in readme.read_text(encoding="utf-8")


def test_missing_allow_write_writes_nothing(tmp_path):
    notes = write_notes(tmp_path)
    readme = write_readme(tmp_path)
    before_notes = notes.read_text(encoding="utf-8")
    before_readme = readme.read_text(encoding="utf-8")
    result = apply_repair_patch(
        tmp_path,
        two_file_patch(),
        allowed_paths=["notes.py"],
        dry_run=False,
    )
    assert result["ok"] is False
    assert "allow-write" in result["error"]
    assert notes.read_text(encoding="utf-8") == before_notes
    assert readme.read_text(encoding="utf-8") == before_readme


def test_second_hunk_mismatch_writes_nothing(tmp_path):
    notes = tmp_path / "notes.py"
    notes.write_text(
        "def format_note(text):\n    return text.strip()\n\ndef other():\n    return 1\n",
        encoding="utf-8",
    )
    before = notes.read_text(encoding="utf-8")
    patch = {
        "rationale": "第二处对不上",
        "edits": [
            {
                "path": "notes.py",
                "old_text": "    return text.strip()\n",
                "new_text": "    return text\n",
            },
            {
                "path": "notes.py",
                "old_text": "    return 99\n",
                "new_text": "    return 2\n",
            },
        ],
    }
    result = apply_repair_patch(
        tmp_path,
        patch,
        allowed_paths=["notes.py"],
        dry_run=False,
    )
    assert result["ok"] is False
    assert "恰好出现一次" in result["error"]
    assert notes.read_text(encoding="utf-8") == before


def test_originals_out_and_restore(tmp_path):
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")
    originals = {}
    result = apply_repair_patch(
        tmp_path,
        patch_body(),
        allowed_paths=["notes.py"],
        dry_run=False,
        originals_out=originals,
    )
    assert result["applied"] is True
    assert "strip" not in notes.read_text(encoding="utf-8")
    assert originals["notes.py"] == before
    restored = restore_files(tmp_path, originals)
    assert restored["ok"] is True
    assert notes.read_text(encoding="utf-8") == before


def test_apply_json_file(tmp_path):
    target = tmp_path / "config.json"
    target.write_text('{"name": "old"}\n', encoding="utf-8")
    result = apply_repair_patch(
        tmp_path,
        {
            "path": "config.json",
            "old_text": '{"name": "old"}',
            "new_text": '{"name": "new"}',
            "rationale": "rename",
        },
        allowed_paths=["config.json"],
        dry_run=False,
    )
    assert result["ok"] is True
    assert '"new"' in target.read_text(encoding="utf-8")


def test_reject_png_patch(tmp_path):
    target = tmp_path / "logo.png"
    target.write_bytes(b"\x89PNG\r\n")
    result = apply_repair_patch(
        tmp_path,
        {
            "path": "logo.png",
            "old_text": "PNG",
            "new_text": "XXX",
            "rationale": "no",
        },
        allowed_paths=["logo.png"],
        dry_run=False,
    )
    assert result["ok"] is False
