import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from app.api_retry import call_with_retry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = "https://api.github.com"
MAX_COMMENTS = 20
MAX_FIELD_CHARS = 20_000
MAX_TOTAL_CHARS = 80_000
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class GitHubHTTPError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def add_issue_source_args(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--issue-file",
        help="包含 issue 全文的文件",
    )
    group.add_argument(
        "--github-issue",
        help="GitHub issue URL，或 owner/repo#123",
    )


def load_issue_file(raw_path):
    path = Path(raw_path)
    if not path.is_file():
        raise ValueError("--issue-file 不存在或不是文件")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("--issue-file 不能为空")
    return text


def load_issue_text_from_args(args, *, fetch=None):
    ref = getattr(args, "github_issue", None)
    if ref:
        loader = fetch or fetch_github_issue
        return loader(ref)
    return load_issue_file(args.issue_file)


def parse_github_issue_ref(ref):
    raw = (ref or "").strip()
    if not raw:
        raise ValueError("--github-issue 不能为空")

    shorthand = re.fullmatch(
        r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:#|/issues/|/pull/)(\d+)",
        raw,
    )
    if shorthand:
        return shorthand.group(1), shorthand.group(2), int(shorthand.group(3))

    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "https":
        raise ValueError("--github-issue 只支持 https://github.com/owner/repo/issues/123 或 owner/repo#123")
    host = (parsed.hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        raise ValueError("--github-issue 只支持 https://github.com/owner/repo/issues/123 或 owner/repo#123")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2] not in {"issues", "pull"}:
        raise ValueError("--github-issue 只支持 https://github.com/owner/repo/issues/123 或 owner/repo#123")
    owner, repo, _kind, number = parts
    if not NAME_RE.fullmatch(owner) or not NAME_RE.fullmatch(repo):
        raise ValueError("--github-issue 只支持 https://github.com/owner/repo/issues/123 或 owner/repo#123")
    if not number.isdigit() or int(number) < 1:
        raise ValueError("--github-issue 只支持 https://github.com/owner/repo/issues/123 或 owner/repo#123")
    return owner, repo, int(number)


def _clip(text, limit=MAX_FIELD_CHARS):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def format_github_issue(issue, comments=None):
    owner_repo = issue.get("repository") or ""
    html_url = issue.get("html_url") or ""
    number = issue.get("number")
    title = issue.get("title") or ""
    state = issue.get("state") or ""
    body = _clip(issue.get("body") or "")
    lines = [
        f"# {title}".rstrip(),
        "",
        f"Repository: {owner_repo}",
        f"Issue: {number}",
        f"URL: {html_url}",
        f"State: {state}",
        "",
        body,
    ]
    items = comments or []
    if items:
        lines.extend(["", "## Comments"])
        for item in items[:MAX_COMMENTS]:
            user = ((item.get("user") or {}).get("login")) or "unknown"
            lines.extend(["", f"### @{user}", _clip(item.get("body") or "")])
        if len(items) > MAX_COMMENTS:
            lines.append("\n...[truncated]")
    text = "\n".join(lines).strip() + "\n"
    if len(text) > MAX_TOTAL_CHARS:
        text = text[:MAX_TOTAL_CHARS] + "\n...[truncated]\n"
    return text


def _default_get_json(url, token):
    if not url.startswith(API_ROOT + "/"):
        raise ValueError("只允许请求 api.github.com")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "issue-agent",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)

    def once():
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            raise GitHubHTTPError(exc.code, f"GitHub API HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise GitHubHTTPError(0, "connection error") from None
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("GitHub 返回的不是合法 JSON") from exc

    return call_with_retry(once, attempts=2, delay_seconds=1.0)


def fetch_github_issue(ref, *, token=None, get_json=None):
    load_dotenv(PROJECT_ROOT / ".env")
    owner, repo, number = parse_github_issue_ref(ref)
    secret = token
    if secret is None:
        secret = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    getter = get_json or (lambda url: _default_get_json(url, secret))
    issue = getter(f"{API_ROOT}/repos/{owner}/{repo}/issues/{number}")
    if not isinstance(issue, dict):
        raise ValueError("GitHub 返回的不是合法 JSON")
    issue = dict(issue)
    issue["repository"] = f"{owner}/{repo}"
    comments = getter(
        f"{API_ROOT}/repos/{owner}/{repo}/issues/{number}/comments?per_page={MAX_COMMENTS}"
    )
    if not isinstance(comments, list):
        comments = []
    text = format_github_issue(issue, comments)
    if not text.strip():
        raise ValueError("GitHub issue 为空")
    return text


def parse_args(argv):
    parser = argparse.ArgumentParser(description="只读拉取 GitHub issue，不发评论、不改仓库")
    parser.add_argument("--github-issue", required=True, help="GitHub issue URL，或 owner/repo#123")
    parser.add_argument("--out", required=False, help="可选：把拉取结果写入文件")
    return parser.parse_args(argv)


def main(argv=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        text = fetch_github_issue(args.github_issue)
        print(text, end="")
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        return 0
    except (ValueError, GitHubHTTPError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
