import json

from app.issue import main
from tests.test_triage_schema import VALID_REPORT


VALID_PATCH = {
    "path": "notes.py",
    "old_text": '    return text.strip()\n',
    "new_text": '    return text\n',
    "rationale": "按 issue 要求保留首尾空格",
}


def write_issue(tmp_path, text="format_note 不应再去掉空格"):
    path = tmp_path / "issue.txt"
    path.write_text(text, encoding="utf-8")
    return path


def write_notes(tmp_path):
    path = tmp_path / "notes.py"
    path.write_text('def format_note(text):\n    return text.strip()\n', encoding="utf-8")
    return path


def factories():
    def triage_factory(workspace):
        def runner(issue_text):
            return VALID_REPORT
        return runner

    def propose_factory(workspace):
        def runner(issue_text):
            return VALID_PATCH
        return runner

    return triage_factory, propose_factory


def test_workflow_writes_artifacts_without_apply(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["ok"] is True
    assert summary["applied"] is False
    assert notes.read_text(encoding="utf-8") == before
    assert json.loads((out_dir / "report.json").read_text(encoding="utf-8")) == VALID_REPORT
    assert json.loads((out_dir / "patch.json").read_text(encoding="utf-8")) == VALID_PATCH
    assert json.loads((out_dir / "verify.json").read_text(encoding="utf-8"))["applied"] is False
    assert (out_dir / "triage-trace.json").is_file()
    assert (out_dir / "propose-trace.json").is_file()
    assert not (out_dir / "apply.json").exists()


def test_apply_without_allow_write_fails(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--apply",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    err = capsys.readouterr().err
    assert code != 0
    assert "allow-write" in err
    assert notes.read_text(encoding="utf-8") == before


def test_apply_writes_when_allowed(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["applied"] is True
    assert "strip" not in notes.read_text(encoding="utf-8")
    assert json.loads((out_dir / "apply.json").read_text(encoding="utf-8"))["applied"] is True


def write_workspace_test(tmp_path, body="def test_ok():\n    assert True\n"):
    path = tmp_path / "test_sample.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_pytest_requires_apply(tmp_path, capsys):
    issue = write_issue(tmp_path)
    write_notes(tmp_path)
    write_workspace_test(tmp_path, "def test_bad():\n    assert False\n")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--pytest",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    err = capsys.readouterr().err
    assert code != 0
    assert "--apply" in err
    assert not (out_dir / "pytest.json").exists()
    assert not (out_dir / "report.json").exists()


def test_apply_without_pytest_skips_tests(tmp_path, capsys):
    issue = write_issue(tmp_path)
    write_notes(tmp_path)
    write_workspace_test(tmp_path)
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["applied"] is True
    assert "tests_passed" not in summary
    assert not (out_dir / "pytest.json").exists()


def test_pytest_after_apply_records_pass(tmp_path, capsys):
    issue = write_issue(tmp_path)
    write_notes(tmp_path)
    write_workspace_test(tmp_path)
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
            "--pytest",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    pytest_result = json.loads((out_dir / "pytest.json").read_text(encoding="utf-8"))
    assert code == 0
    assert summary["applied"] is True
    assert summary["tests_passed"] is True
    assert pytest_result["passed"] is True
    assert "strip" not in (tmp_path / "notes.py").read_text(encoding="utf-8")


def test_pytest_failure_keeps_written_files(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    write_workspace_test(tmp_path, "def test_bad():\n    assert False\n")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
            "--pytest",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert code != 0
    assert summary["applied"] is True
    assert summary["tests_passed"] is False
    assert "strip" not in notes.read_text(encoding="utf-8")


def test_pytest_failure_saves_output(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    write_workspace_test(tmp_path, "def test_bad():\n    assert False\n")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
            "--pytest",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    pytest_result = json.loads((out_dir / "pytest.json").read_text(encoding="utf-8"))
    assert code != 0
    assert summary["applied"] is True
    assert summary["tests_passed"] is False
    assert summary["pytest_returncode"] == pytest_result["returncode"]
    assert pytest_result["passed"] is False
    assert pytest_result["output"]
    assert "strip" not in notes.read_text(encoding="utf-8")
    assert not (out_dir / "patch-retry.json").exists()


def test_rollback_on_fail_restores_files(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")
    write_workspace_test(tmp_path, "def test_bad():\n    assert False\n")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
            "--pytest",
            "--rollback-on-fail",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    pytest_result = json.loads((out_dir / "pytest.json").read_text(encoding="utf-8"))
    rollback = json.loads((out_dir / "rollback.json").read_text(encoding="utf-8"))
    assert code != 0
    assert summary["applied"] is True
    assert summary["tests_passed"] is False
    assert summary["rolled_back"] is True
    assert pytest_result["passed"] is False
    assert pytest_result["output"]
    assert rollback["ok"] is True
    assert notes.read_text(encoding="utf-8") == before


def test_rollback_on_fail_requires_pytest(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()
    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
            "--rollback-on-fail",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    err = capsys.readouterr().err
    assert code != 0
    assert "--pytest" in err
    assert notes.read_text(encoding="utf-8") == before


def test_rollback_on_fail_keeps_files_when_tests_pass(tmp_path, capsys):
    issue = write_issue(tmp_path)
    notes = write_notes(tmp_path)
    write_workspace_test(tmp_path)
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()
    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out-dir",
            str(out_dir.resolve()),
            "--allow-write",
            "notes.py",
            "--apply",
            "--pytest",
            "--rollback-on-fail",
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["tests_passed"] is True
    assert summary["rolled_back"] is False
    assert not (out_dir / "rollback.json").exists()
    assert "strip" not in notes.read_text(encoding="utf-8")
