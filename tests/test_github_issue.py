import json

import pytest

from app.github_issue import (
    fetch_github_issue,
    format_github_issue,
    load_issue_text_from_args,
    parse_github_issue_ref,
)
from app.issue import main as issue_main
from app.triage import main as triage_main
from tests.test_issue_cli import factories, write_notes


def test_parse_url_and_shorthand():
    assert parse_github_issue_ref("https://github.com/octo/Hello-World/issues/12") == (
        "octo",
        "Hello-World",
        12,
    )
    assert parse_github_issue_ref("https://github.com/octo/Hello-World/pull/3") == (
        "octo",
        "Hello-World",
        3,
    )
    assert parse_github_issue_ref("octo/Hello-World#9") == ("octo", "Hello-World", 9)


def test_parse_rejects_non_github():
    with pytest.raises(ValueError):
        parse_github_issue_ref("https://evil.example/octo/Hello-World/issues/1")


def test_format_includes_title_body_and_comments():
    text = format_github_issue(
        {
            "title": "page=0",
            "number": 1,
            "html_url": "https://github.com/octo/Hello-World/issues/1",
            "state": "open",
            "repository": "octo/Hello-World",
            "body": "paginate should reject 0",
        },
        [{"user": {"login": "alice"}, "body": "please check pagination.py"}],
    )
    assert "# page=0" in text
    assert "paginate should reject 0" in text
    assert "@alice" in text
    assert "pagination.py" in text


def test_fetch_uses_injected_get_json_and_hides_token():
    calls = []

    def get_json(url):
        calls.append(url)
        if url.endswith("/issues/1"):
            return {
                "title": "bug",
                "number": 1,
                "html_url": "https://github.com/octo/Hello-World/issues/1",
                "state": "open",
                "body": "boom",
            }
        return [{"user": {"login": "bob"}, "body": "ack"}]

    text = fetch_github_issue("octo/Hello-World#1", token="secret-token", get_json=get_json)
    assert "boom" in text
    assert "@bob" in text
    assert "secret-token" not in text
    assert any(url.endswith("/issues/1") for url in calls)
    assert any("comments" in url for url in calls)


def test_load_args_github_issue():
    args = type("A", (), {"github_issue": "octo/Hello-World#1", "issue_file": None})()
    text = load_issue_text_from_args(args, fetch=lambda ref: "fetched:" + ref)
    assert text == "fetched:octo/Hello-World#1"


def test_cli_requires_issue_source(tmp_path):
    with pytest.raises(SystemExit):
        triage_main(["--workspace", str(tmp_path.resolve())])


def test_cli_rejects_both_issue_sources(tmp_path):
    issue = tmp_path / "issue.txt"
    issue.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        triage_main([
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--github-issue",
            "octo/Hello-World#1",
        ])


def test_issue_cli_github_issue_is_read_only(tmp_path, capsys, monkeypatch):
    notes = write_notes(tmp_path)
    before = notes.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"
    triage_factory, propose_factory = factories()

    def fake_fetch(ref):
        assert ref == "octo/Hello-World#1"
        return "format_note should keep spaces"

    monkeypatch.setattr("app.github_issue.fetch_github_issue", fake_fetch)
    code = issue_main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--github-issue",
            "octo/Hello-World#1",
            "--out-dir",
            str(out_dir.resolve()),
        ],
        triage_factory=triage_factory,
        propose_factory=propose_factory,
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0
    assert summary["applied"] is False
    assert notes.read_text(encoding="utf-8") == before
    assert (out_dir / "report.json").is_file()
