import json

from app.eval_cases import main
from app.eval_triage import evaluate_report, load_cases


def write_workspace(tmp_path):
    target = tmp_path / "repo" / "text_utils"
    target.mkdir(parents=True)
    (target / "pagination.py").write_text(
        "def paginate(items, page, page_size):\n"
        "    if page < 1:\n"
        "        raise ValueError(\"page 必须大于等于 1\")\n",
        encoding="utf-8",
    )
    return tmp_path / "repo"


def test_quote_must_be_original(tmp_path):
    workspace = write_workspace(tmp_path)
    good = {
        "issue_summary": "page=0 应报错",
        "evidence": [{
            "path": "text_utils/pagination.py",
            "line": 2,
            "quote": "    if page < 1:",
        }],
        "candidate_files": ["text_utils/pagination.py"],
        "uncertainties": [],
    }
    bad = json.loads(json.dumps(good))
    bad["evidence"][0]["quote"] = "大概会抛异常"

    assert evaluate_report(workspace, good, expected_files=["text_utils/pagination.py"])["ok"] is True
    scored = evaluate_report(workspace, bad, expected_files=["text_utils/pagination.py"])
    assert scored["ok"] is False
    assert any(not item["ok"] and "原文" in (item["error"] or "") for item in scored["checks"])


def test_missing_expected_file_fails(tmp_path):
    workspace = write_workspace(tmp_path)
    report = {
        "issue_summary": "page=0 应报错",
        "evidence": [{
            "path": "README.md",
            "line": None,
            "quote": "hello",
        }],
        "candidate_files": ["README.md"],
        "uncertainties": [],
    }
    (workspace / "README.md").write_text("hello\n", encoding="utf-8")
    scored = evaluate_report(
        workspace,
        report,
        expected_files=["text_utils/pagination.py"],
    )
    assert scored["ok"] is False


def test_eval_cli_scores_existing_reports(tmp_path, capsys):
    workspace = write_workspace(tmp_path)
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "page_zero.txt").write_text("page=0 会怎样？\n", encoding="utf-8")
    (cases_dir / "cases.json").write_text(json.dumps({
        "cases": [{
            "id": "page_zero",
            "issue_file": "page_zero.txt",
            "expected_files": ["text_utils/pagination.py"],
        }]
    }), encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "page_zero.json").write_text(json.dumps({
        "issue_summary": "page=0 应报错",
        "evidence": [{
            "path": "text_utils/pagination.py",
            "line": 2,
            "quote": "    if page < 1:",
        }],
        "candidate_files": ["text_utils/pagination.py"],
        "uncertainties": [],
    }), encoding="utf-8")

    code = main([
        "--workspace",
        str(workspace.resolve()),
        "--cases-dir",
        str(cases_dir.resolve()),
        "--out-dir",
        str(out_dir.resolve()),
    ])
    scored = json.loads(capsys.readouterr().out)
    assert code == 0
    assert scored["ok"] is True
    assert load_cases(cases_dir)[0]["id"] == "page_zero"


def test_run_records_error_and_continues(tmp_path, capsys):
    workspace = write_workspace(tmp_path)
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "a.txt").write_text("a\n", encoding="utf-8")
    (cases_dir / "b.txt").write_text("b\n", encoding="utf-8")
    (cases_dir / "cases.json").write_text(json.dumps({
        "cases": [
            {"id": "a", "issue_file": "a.txt", "expected_files": ["text_utils/pagination.py"]},
            {"id": "b", "issue_file": "b.txt", "expected_files": ["text_utils/pagination.py"]},
        ]
    }), encoding="utf-8")
    out_dir = tmp_path / "out"
    good = {
        "issue_summary": "page=0 应报错",
        "evidence": [{
            "path": "text_utils/pagination.py",
            "line": 2,
            "quote": "    if page < 1:",
        }],
        "candidate_files": ["text_utils/pagination.py"],
        "uncertainties": [],
    }

    def fake_run(workspace_arg, cases, out_dir_arg):
        from pathlib import Path as P
        (P(out_dir_arg) / "a.json").write_text(json.dumps(good), encoding="utf-8")
        (P(out_dir_arg) / "b.error.json").write_text(
            json.dumps({"ok": False, "error": "stream_read_error"}),
            encoding="utf-8",
        )
        return {"a": good}

    code = main(
        [
            "--workspace",
            str(workspace.resolve()),
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
    by_id = {item["id"]: item for item in scored["results"]}
    assert by_id["a"]["ok"] is True
    assert by_id["b"]["ok"] is False
