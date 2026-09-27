import json

import pytest

from app.github_comment import (
    format_comment_from_report,
    load_comment_body,
    main,
    post_github_comment,
)
from tests.test_triage_schema import VALID_REPORT


def test_format_comment_from_report_includes_summary_and_quote():
    text = format_comment_from_report(VALID_REPORT)
    assert VALID_REPORT["issue_summary"] in text
    assert "text_utils/pagination.py" in text
    assert "if page < 1:" in text
    assert "Issue Agent" in text
    assert "人工确认" in text


def test_load_comment_body_from_report_file(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(VALID_REPORT, ensure_ascii=False), encoding="utf-8")
    text = load_comment_body(report_file=str(path))
    assert VALID_REPORT["issue_summary"] in text


def test_load_comment_body_requires_one_source(tmp_path):
    with pytest.raises(ValueError, match="comment-file|report-file"):
        load_comment_body()
    path = tmp_path / "both.md"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="comment-file|report-file"):
        load_comment_body(comment_file=str(path), report_file=str(path))


def test_dry_run_does_not_call_poster():
    called = []

    def poster(url, payload):
        called.append((url, payload))
        return {"html_url": "https://example.invalid", "id": 1}

    result = post_github_comment(
        "octo/Hello-World#1",
        "hello",
        token="secret-token",
        post_json=poster,
        dry_run=True,
    )
    assert result["posted"] is False
    assert result["dry_run"] is True
    assert "hello" in result["body"]
    assert called == []
    assert "secret-token" not in json.dumps(result)


def test_dry_run_does_not_need_token():
    result = post_github_comment(
        "octo/Hello-World#1",
        "hello",
        token="",
        dry_run=True,
    )
    assert result["posted"] is False
    assert result["dry_run"] is True


def test_post_comment_uses_injected_poster_and_hides_token():
    called = []

    def poster(url, payload):
        called.append((url, payload))
        return {
            "id": 99,
            "html_url": "https://github.com/octo/Hello-World/issues/1#issuecomment-99",
        }

    result = post_github_comment(
        "octo/Hello-World#1",
        "please review pagination.py",
        token="secret-token",
        post_json=poster,
        dry_run=False,
    )
    assert result["posted"] is True
    assert result["comment_id"] == 99
    assert called[0][0].endswith("/issues/1/comments")
    assert called[0][1] == {"body": "please review pagination.py"}
    assert "secret-token" not in json.dumps(result)


def test_post_without_token_fails():
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        post_github_comment(
            "octo/Hello-World#1",
            "hello",
            token="",
            dry_run=False,
        )


def test_empty_explicit_token_does_not_use_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-secret")
    monkeypatch.setenv("GH_TOKEN", "env-secret")
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        post_github_comment(
            "octo/Hello-World#1",
            "hello",
            token="",
            dry_run=False,
        )


def test_cli_dry_run_default(tmp_path, capsys):
    comment = tmp_path / "comment.md"
    comment.write_text("triage note", encoding="utf-8")
    out = tmp_path / "result.json"
    code = main([
        "--github-issue",
        "octo/Hello-World#1",
        "--comment-file",
        str(comment),
        "--out",
        str(out),
    ], poster=lambda url, payload: (_ for _ in ()).throw(AssertionError("should not post")))
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["posted"] is False
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["posted"] is False


def test_cli_post_comment(tmp_path, capsys):
    comment = tmp_path / "comment.md"
    comment.write_text("triage note", encoding="utf-8")
    seen = {}

    def poster(url, payload):
        seen["url"] = url
        seen["payload"] = payload
        return {"id": 7, "html_url": "https://github.com/octo/Hello-World/issues/1#issuecomment-7"}

    code = main([
        "--github-issue",
        "octo/Hello-World#1",
        "--comment-file",
        str(comment),
        "--post-comment",
    ], poster=poster)
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["posted"] is True
    assert seen["payload"]["body"] == "triage note"


def test_cli_requires_comment_source():
    with pytest.raises(SystemExit):
        main([
            "--github-issue",
            "octo/Hello-World#1",
        ])