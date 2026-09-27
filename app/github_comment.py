import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from app.api_retry import call_with_retry
from app.github_issue import (
    API_ROOT,
    GitHubHTTPError,
    PROJECT_ROOT,
    parse_github_issue_ref,
)


MAX_COMMENT_CHARS = 20_000


def github_token(explicit=None):
    load_dotenv(PROJECT_ROOT / ".env")
    if explicit is not None:
        return explicit
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def format_comment_from_report(report):
    if not isinstance(report, dict):
        raise ValueError("report 必须是 JSON 对象")
    summary = str(report.get("issue_summary") or "").strip() or "(empty)"
    files = report.get("candidate_files") or []
    evidence = report.get("evidence") or []
    unknowns = report.get("uncertainties") or []
    lines = [
        "## Issue Agent 分诊",
        "",
        "**摘要：** " + summary,
        "",
        "**相关文件：**",
    ]
    if files:
        lines.extend(["- `" + str(path) + "`" for path in files])
    else:
        lines.append("- (none)")
    lines.extend(["", "**证据：**"])
    if evidence:
        for item in evidence:
            path = item.get("path") or ""
            line = item.get("line")
            quote = item.get("quote") or ""
            loc = path if line is None else f"{path}:{line}"
            lines.append(f"- `{loc}` {quote}")
    else:
        lines.append("- (none)")
    lines.extend(["", "**不确定：**"])
    if unknowns:
        lines.extend(["- " + str(item) for item in unknowns])
    else:
        lines.append("- (none)")
    lines.extend(["", "---", "由 Issue Agent 生成，需人工确认后再改代码。"])
    text = "\n".join(lines).strip() + "\n"
    if len(text) > MAX_COMMENT_CHARS:
        text = text[:MAX_COMMENT_CHARS] + "\n...[truncated]\n"
    return text


def load_comment_body(*, comment_file=None, report_file=None):
    if bool(comment_file) == bool(report_file):
        raise ValueError("必须提供 --comment-file 或 --report-file 之一")
    if comment_file:
        path = Path(comment_file)
        if not path.is_file():
            raise ValueError("--comment-file 不存在或不是文件")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError("--comment-file 不能为空")
        if len(text) > MAX_COMMENT_CHARS:
            text = text[:MAX_COMMENT_CHARS] + "\n...[truncated]\n"
        return text
    path = Path(report_file)
    if not path.is_file():
        raise ValueError("--report-file 不存在或不是文件")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("--report-file 不是合法 JSON") from exc
    return format_comment_from_report(report)


def _post_json(url, token, payload):
    if not url.startswith(API_ROOT + "/"):
        raise ValueError("只允许请求 api.github.com")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "issue-agent",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
    }
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)

    def once():
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            raise GitHubHTTPError(exc.code, f"GitHub API HTTP {exc.code}") from None
        except urllib.error.URLError:
            raise GitHubHTTPError(0, "connection error") from None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("GitHub 返回的不是合法 JSON") from exc

    return call_with_retry(once, attempts=2, delay_seconds=1.0)


def post_github_comment(ref, body, *, token=None, post_json=None, dry_run=True):
    owner, repo, number = parse_github_issue_ref(ref)
    text = (body or "").strip()
    if not text:
        raise ValueError("评论内容不能为空")
    url = f"{API_ROOT}/repos/{owner}/{repo}/issues/{number}/comments"
    result = {
        "ok": True,
        "posted": False,
        "dry_run": dry_run,
        "repository": f"{owner}/{repo}",
        "issue": number,
        "url": url,
        "body": text,
    }
    if dry_run:
        return result
    if post_json is not None:
        poster = post_json
        secret = ""
    else:
        secret = github_token(token)
        if not secret:
            raise ValueError("发送评论需要 GITHUB_TOKEN")
        poster = lambda target, payload, _secret=secret: _post_json(target, _secret, payload)
    response = poster(url, {"body": text})
    if not isinstance(response, dict):
        raise ValueError("GitHub 返回的不是合法 JSON")
    html_url = response.get("html_url") or ""
    result.update({
        "posted": True,
        "dry_run": False,
        "html_url": html_url,
        "comment_id": response.get("id"),
    })
    if secret and secret in json.dumps(result):
        raise RuntimeError("token leaked")
    return result


def parse_args(argv):
    parser = argparse.ArgumentParser(description="预演或发送 GitHub 评论；默认不发送，不开 PR")
    parser.add_argument("--github-issue", required=True, help="GitHub issue URL，或 owner/repo#123")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--comment-file", help="要发送的 Markdown 文件")
    source.add_argument("--report-file", help="分诊 report.json，自动生成评论")
    parser.add_argument(
        "--post-comment",
        action="store_true",
        help="真正发送；省略时只预演",
    )
    parser.add_argument("--out", required=False, help="可选：把结果 JSON 写入文件")
    return parser.parse_args(argv)


def main(argv=None, *, poster=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        body = load_comment_body(
            comment_file=args.comment_file,
            report_file=args.report_file,
        )
        result = post_github_comment(
            args.github_issue,
            body,
            post_json=poster,
            dry_run=not args.post_comment,
        )
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        print(payload)
        if args.out:
            Path(args.out).write_text(payload + "\n", encoding="utf-8")
        return 0 if result.get("ok") else 1
    except (ValueError, GitHubHTTPError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
