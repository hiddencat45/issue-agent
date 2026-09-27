import json
from pathlib import Path

from app.demo_loop import DEFAULT_WORKSPACE, main


DEMO_ROOT = Path(__file__).resolve().parent.parent / "cases" / "demo"


def load_fixture(name):
    return json.loads((DEMO_ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def factories():
    report = load_fixture("report.json")
    patch = load_fixture("patch.json")

    def triage_factory(workspace):
        def runner(issue_text):
            return report
        return runner

    def propose_factory(workspace):
        def runner(issue_text):
            return patch
        return runner

    return triage_factory, propose_factory


def test_offline_demo_does_not_write_or_post(tmp_path, capsys):
    notes = DEFAULT_WORKSPACE / "notes.py"
    before = notes.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"

    code = main([
        "--out-dir",
        str(out_dir.resolve()),
    ])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["ok"] is True
    assert summary["live"] is False
    assert summary["applied"] is False
    assert summary["posted"] is False
    assert summary["dry_run"] is True
    assert summary["workspace_unchanged"] is True
    assert summary["issue_source"] == "file"
    assert summary["github_issue"] == "demo/local#1"
    assert notes.read_text(encoding="utf-8") == before
    assert "strip" in before

    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert "format_note" in report["issue_summary"]
    verify = json.loads((out_dir / "verify.json").read_text(encoding="utf-8"))
    assert verify["ok"] is True
    assert verify["applied"] is False
    comment = (out_dir / "comment.md").read_text(encoding="utf-8")
    assert "notes.py" in comment
    assert "人工确认" in comment
    preview = json.loads((out_dir / "comment-preview.json").read_text(encoding="utf-8"))
    assert preview["posted"] is False
    assert preview["dry_run"] is True
    walkthrough = (out_dir / "WALKTHROUGH.md").read_text(encoding="utf-8")
    assert "不调模型" in walkthrough
    assert "否" in walkthrough
    assert (out_dir / "issue.txt").is_file()


def test_offline_rejects_injected_factories(tmp_path, capsys):
    triage_factory, propose_factory = factories()
    code = main(
        ["--out-dir", str((tmp_path / "out").resolve())],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    err = capsys.readouterr().err
    assert code != 0
    assert "--live" in err


def test_live_demo_with_factories_still_read_only(tmp_path, capsys):
    notes = DEFAULT_WORKSPACE / "notes.py"
    before = notes.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--out-dir",
            str(out_dir.resolve()),
            "--live",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["live"] is True
    assert summary["applied"] is False
    assert summary["posted"] is False
    assert notes.read_text(encoding="utf-8") == before
    assert (out_dir / "triage-trace.json").is_file()
    assert (out_dir / "propose-trace.json").is_file()
    preview = json.loads((out_dir / "comment-preview.json").read_text(encoding="utf-8"))
    assert preview["posted"] is False


def test_relative_out_dir_is_rejected(tmp_path, capsys):
    code = main(["--out-dir", "relative-out"])
    err = capsys.readouterr().err
    assert code != 0
    assert "绝对路径" in err


def test_custom_workspace_must_match_patch(tmp_path, capsys):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes.py").write_text("def format_note(text):\n    return text\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    code = main([
        "--workspace",
        str(workspace.resolve()),
        "--out-dir",
        str(out_dir.resolve()),
    ])
    err = capsys.readouterr().err
    assert code != 0
    assert "old_text" in err or "出现" in err
    assert (workspace / "notes.py").read_text(encoding="utf-8") == "def format_note(text):\n    return text\n"


def test_github_issue_requires_live(tmp_path, capsys):
    code = main([
        "--out-dir",
        str((tmp_path / "out").resolve()),
        "--github-issue",
        "octo/Hello-World#1",
    ])
    err = capsys.readouterr().err
    assert code != 0
    assert "--live" in err


def test_github_issue_live_fetch_is_read_only(tmp_path, capsys):
    notes = DEFAULT_WORKSPACE / "notes.py"
    before = notes.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()
    seen = {}

    def fake_fetch(ref):
        seen["ref"] = ref
        return "format_note 会去掉字符串首尾空格。请改成保留首尾空格，不要 strip。"

    code = main(
        [
            "--out-dir",
            str(out_dir.resolve()),
            "--live",
            "--github-issue",
            "octo/Hello-World#9",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
        fetch=fake_fetch,
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert seen["ref"] == "octo/Hello-World#9"
    assert summary["issue_source"] == "github"
    assert summary["github_issue"] == "octo/Hello-World#9"
    assert summary["applied"] is False
    assert summary["posted"] is False
    assert notes.read_text(encoding="utf-8") == before
    issue_text = (out_dir / "issue.txt").read_text(encoding="utf-8")
    assert "strip" in issue_text
    preview = json.loads((out_dir / "comment-preview.json").read_text(encoding="utf-8"))
    assert preview["posted"] is False
    assert preview["repository"] == "octo/Hello-World"
    assert preview["issue"] == 9


def test_issue_file_and_github_issue_are_mutex(tmp_path):
    issue = tmp_path / "issue.txt"
    issue.write_text("x", encoding="utf-8")
    try:
        main([
            "--out-dir",
            str((tmp_path / "out").resolve()),
            "--issue-file",
            str(issue),
            "--github-issue",
            "octo/Hello-World#1",
        ])
    except SystemExit:
        return
    raise AssertionError("expected argparse to reject both sources")