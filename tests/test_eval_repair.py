import json
from pathlib import Path

from app.eval_repair import evaluate_patch, load_repair_cases, main


VALID_PATCH = {
    "path": "notes.py",
    "old_text": "    return text.strip()\n",
    "new_text": "    return text\n",
    "rationale": "保留首尾空格",
}


def write_fixture(tmp_path):
    repo = tmp_path / "fixture"
    repo.mkdir()
    (repo / "notes.py").write_text(
        "def format_note(text):\n    return text.strip()\n",
        encoding="utf-8",
    )
    (repo / "test_notes.py").write_text(
        "from notes import format_note\n\n"
        "def test_keeps_leading_and_trailing_spaces():\n"
        "    assert format_note(\" a \") == \" a \"\n",
        encoding="utf-8",
    )
    return repo


def write_cases(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "keep_spaces.txt").write_text(
        "format_note 不应再去掉空格\n",
        encoding="utf-8",
    )
    (cases_dir / "cases.json").write_text(json.dumps({
        "cases": [{
            "id": "keep_spaces",
            "issue_file": "keep_spaces.txt",
            "expected_paths": ["notes.py"],
        }]
    }), encoding="utf-8")
    return cases_dir


def test_good_patch_verifies(tmp_path):
    repo = write_fixture(tmp_path)
    scored = evaluate_patch(
        repo,
        VALID_PATCH,
        expected_paths=["notes.py"],
    )
    assert scored["ok"] is True
    assert repo.joinpath("notes.py").read_text(encoding="utf-8").count("strip") == 1


def test_wrong_file_fails(tmp_path):
    repo = write_fixture(tmp_path)
    patch = {
        "path": "README.md",
        "old_text": "hello",
        "new_text": "hi",
        "rationale": "改错文件",
    }
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    scored = evaluate_patch(
        repo,
        patch,
        expected_paths=["notes.py"],
    )
    assert scored["ok"] is False


def test_cli_scores_existing_patch_without_mutating_fixture(tmp_path, capsys):
    repo = write_fixture(tmp_path)
    before = repo.joinpath("notes.py").read_text(encoding="utf-8")
    cases_dir = write_cases(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "keep_spaces.json").write_text(
        json.dumps(VALID_PATCH),
        encoding="utf-8",
    )
    code = main([
        "--workspace",
        str(repo.resolve()),
        "--cases-dir",
        str(cases_dir.resolve()),
        "--out-dir",
        str(out_dir.resolve()),
    ])
    scored = json.loads(capsys.readouterr().out)
    copy_notes = (out_dir / "keep_spaces" / "repo" / "notes.py").read_text(encoding="utf-8")
    assert code == 0
    assert scored["ok"] is True
    assert scored["results"][0]["tests_passed"] is True
    assert repo.joinpath("notes.py").read_text(encoding="utf-8") == before
    assert "strip" not in copy_notes


def test_cli_run_records_error_and_continues(tmp_path, capsys):
    repo = write_fixture(tmp_path)
    cases_dir = write_cases(tmp_path)
    out_dir = tmp_path / "out"

    def fake_run(workspace, cases, dest):
        (dest / "keep_spaces.error.json").write_text(
            json.dumps({"ok": False, "error": "stream_read_error"}),
            encoding="utf-8",
        )
        return {}

    code = main(
        [
            "--workspace",
            str(repo.resolve()),
            "--cases-dir",
            str(cases_dir.resolve()),
            "--out-dir",
            str(out_dir.resolve()),
            "--run",
        ],
        run_cases_fn=fake_run,
    )
    scored = json.loads(capsys.readouterr().out)
    assert code != 0
    assert scored["results"][0]["ok"] is False
    assert scored["results"][0]["error"] == "缺少对应补丁"


def test_load_repair_cases(tmp_path):
    cases_dir = write_cases(tmp_path)
    cases = load_repair_cases(cases_dir)
    assert cases[0]["id"] == "keep_spaces"
    assert "format_note" in cases[0]["issue_text"]


def test_unknown_case_id_exits_nonzero(tmp_path, capsys):
    repo = write_fixture(tmp_path)
    cases_dir = write_cases(tmp_path)
    code = main([
        "--workspace",
        str(repo.resolve()),
        "--cases-dir",
        str(cases_dir.resolve()),
        "--out-dir",
        str((tmp_path / "out").resolve()),
        "--case-id",
        "no_such",
    ])
    err = capsys.readouterr().err
    assert code != 0
    assert "未知 case-id" in err


def test_extra_readme_is_allowed(tmp_path):
    repo = write_fixture(tmp_path)
    (repo / "README.md").write_text("format_note 会去掉首尾空格。\n", encoding="utf-8")
    patch = {
        "rationale": "代码和说明一起改",
        "edits": [
            {
                "path": "notes.py",
                "old_text": "    return text.strip()\n",
                "new_text": "    return text\n",
            },
            {
                "path": "README.md",
                "old_text": "format_note 会去掉首尾空格。",
                "new_text": "format_note 会保留首尾空格。",
            },
        ],
    }
    scored = evaluate_patch(repo, patch, expected_paths=["notes.py"])
    assert scored["ok"] is True


def test_repo_fixture_scores_good_and_bad(tmp_path, capsys):
    root = Path(__file__).resolve().parent.parent
    workspace = root / "cases" / "repair" / "workspace"
    cases_dir = root / "cases" / "repair"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    before = (workspace / "notes.py").read_text(encoding="utf-8")
    (out_dir / "keep_spaces.json").write_text(
        json.dumps(VALID_PATCH),
        encoding="utf-8",
    )
    code = main([
        "--workspace",
        str(workspace.resolve()),
        "--cases-dir",
        str(cases_dir.resolve()),
        "--out-dir",
        str(out_dir.resolve()),
    ])
    scored = json.loads(capsys.readouterr().out)
    by_id = {item["id"]: item for item in scored["results"]}
    assert code == 0
    assert scored["ok"] is True
    assert by_id["keep_spaces"]["actual_ok"] is True
    assert by_id["keep_spaces"]["tests_passed"] is True
    assert by_id["wrong_file"]["actual_ok"] is False
    assert by_id["wrong_file"]["ok"] is True
    assert by_id["mismatch"]["actual_ok"] is False
    assert by_id["mismatch"]["ok"] is True
    assert (workspace / "notes.py").read_text(encoding="utf-8") == before


def test_run_skips_canned_patches(tmp_path, capsys):
    repo = write_fixture(tmp_path)
    (repo / "README.md").write_text("format_note 会去掉首尾空格。\n", encoding="utf-8")
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "keep_spaces.txt").write_text("format_note 不应再去掉空格\n", encoding="utf-8")
    (cases_dir / "patches").mkdir()
    (cases_dir / "patches" / "wrong_file.json").write_text(
        json.dumps({
            "path": "README.md",
            "old_text": "format_note 会去掉首尾空格。",
            "new_text": "format_note 会保留首尾空格。",
            "rationale": "只改说明",
        }),
        encoding="utf-8",
    )
    (cases_dir / "cases.json").write_text(json.dumps({
        "cases": [
            {
                "id": "keep_spaces",
                "issue_file": "keep_spaces.txt",
                "expected_paths": ["notes.py"],
            },
            {
                "id": "wrong_file",
                "issue_file": "keep_spaces.txt",
                "expected_paths": ["notes.py"],
                "patch_file": "patches/wrong_file.json",
                "expect_ok": False,
            },
        ]
    }), encoding="utf-8")
    seen = []

    def fake_run(workspace, cases, dest):
        seen.extend(case["id"] for case in cases)
        (dest / "keep_spaces.json").write_text(
            json.dumps(VALID_PATCH),
            encoding="utf-8",
        )
        return {"keep_spaces": VALID_PATCH}

    code = main(
        [
            "--workspace",
            str(repo.resolve()),
            "--cases-dir",
            str(cases_dir.resolve()),
            "--out-dir",
            str((tmp_path / "out").resolve()),
            "--run",
        ],
        run_cases_fn=fake_run,
    )
    scored = json.loads(capsys.readouterr().out)
    assert code == 0
    assert seen == ["keep_spaces"]
    by_id = {item["id"]: item for item in scored["results"]}
    assert by_id["keep_spaces"]["actual_ok"] is True
    assert by_id["wrong_file"]["actual_ok"] is False
