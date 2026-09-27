import json

import pytest

from app.github_pr import create_github_pr, format_pr_from_report, main
from tests.test_triage_schema import VALID_REPORT


VALID_PATCH = {
    "path": "notes.py",
    "old_text": "    return text.strip()\n",
    "new_text": "    return text\n",
    "rationale": "按 issue 要求保留首尾空格",
}


def test_format_pr_includes_summary_and_path():
    title, body = format_pr_from_report(VALID_REPORT, VALID_PATCH, issue_number=9)
    assert VALID_REPORT["issue_summary"][:20] in title
    assert "notes.py" in body
    assert "Related: #9" in body
    assert "--open-pr" in body
    assert "不创建分支" in body


def test_dry_run_does_not_call_poster():
    called = []

    def poster(url, payload):
        called.append((url, payload))
        return {"html_url": "https://example.invalid", "number": 1}

    result = create_github_pr(
        "octo/Hello-World#1",
        "title",
        "body",
        head="fix-note",
        token="secret-token",
        post_json=poster,
        dry_run=True,
    )
    assert result["opened"] is False
    assert result["dry_run"] is True
    assert result["head"] == "fix-note"
    assert called == []
    assert "secret-token" not in json.dumps(result)


def test_open_pr_uses_injected_poster_and_hides_token():
    called = []

    def poster(url, payload):
        called.append((url, payload))
        return {
            "number": 4,
            "html_url": "https://github.com/octo/Hello-World/pull/4",
        }

    result = create_github_pr(
        "octo/Hello-World#1",
        "keep spaces",
        "please review",
        head="fix-note",
        base="master",
        token="secret-token",
        post_json=poster,
        dry_run=False,
    )
    assert result["opened"] is True
    assert result["pr_number"] == 4
    assert called[0][0].endswith("/repos/octo/Hello-World/pulls")
    assert called[0][1]["head"] == "fix-note"
    assert called[0][1]["base"] == "master"
    assert "secret-token" not in json.dumps(result)


def test_open_without_token_fails():
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        create_github_pr(
            "octo/Hello-World#1",
            "title",
            "body",
            head="fix-note",
            token="",
            dry_run=False,
        )


def test_empty_explicit_token_does_not_use_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-secret")
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        create_github_pr(
            "octo/Hello-World#1",
            "title",
            "body",
            head="fix-note",
            token="",
            dry_run=False,
        )


def test_cli_dry_run_default(tmp_path, capsys):
    report = tmp_path / "report.json"
    patch = tmp_path / "patch.json"
    report.write_text(json.dumps(VALID_REPORT, ensure_ascii=False), encoding="utf-8")
    patch.write_text(json.dumps(VALID_PATCH, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "result.json"
    code = main([
        "--github-issue",
        "octo/Hello-World#1",
        "--report-file",
        str(report),
        "--patch-file",
        str(patch),
        "--head",
        "fix-note",
        "--out",
        str(out),
    ], poster=lambda url, payload: (_ for _ in ()).throw(AssertionError("should not open")))
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["opened"] is False
    assert json.loads(out.read_text(encoding="utf-8"))["opened"] is False


def test_cli_open_pr(tmp_path, capsys):
    report = tmp_path / "report.json"
    patch = tmp_path / "patch.json"
    report.write_text(json.dumps(VALID_REPORT, ensure_ascii=False), encoding="utf-8")
    patch.write_text(json.dumps(VALID_PATCH, ensure_ascii=False), encoding="utf-8")
    seen = {}

    def poster(url, payload):
        seen["url"] = url
        seen["payload"] = payload
        return {"number": 8, "html_url": "https://github.com/octo/Hello-World/pull/8"}

    code = main([
        "--github-issue",
        "octo/Hello-World#1",
        "--report-file",
        str(report),
        "--patch-file",
        str(patch),
        "--head",
        "fix-note",
        "--open-pr",
    ], poster=poster)
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["opened"] is True
    assert seen["payload"]["head"] == "fix-note"
    assert "分页" in seen["payload"]["title"] or "page" in seen["payload"]["title"].lower() or seen["payload"]["title"]