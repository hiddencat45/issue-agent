import argparse
import json
import os
import re
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
from app.repair_schema import RepairPatchError, patch_paths, validate_repair_patch
from app.triage_schema import validate_triage_report


MAX_TITLE_CHARS = 72
MAX_BODY_CHARS = 20_000
DEFAULT_BASE = "main"
DEFAULT_HEAD = "issue-agent"
HEAD_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def github_token(explicit=None):
    load_dotenv(PROJECT_ROOT / ".env")
    if explicit is not None:
        return explicit
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def _clip(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def format_pr_from_report(report, patch, *, issue_number=None):
    if not isinstance(report, dict):
        raise ValueError("report 必须是 JSON 对象")
    report = validate_triage_report(report)
    patch = validate_repair_patch(patch)
    summary = report["issue_summary"].strip()
    title = _clip(summary, MAX_TITLE_CHARS)
    files = patch_paths(patch)
    rationale = str(patch.get("rationale") or "").strip()
    lines = [
        "## 摘要",
        "",
        summary,
        "",
        "## 将改动的文件",
        "",
    ]
    if files:
        lines.extend(["- `" + path + "`" for path in files])
    else:
        lines.append("- (none)")
    lines.extend(["", "## 理由", "", rationale or "(empty)", ""])
    if issue_number:
        lines.extend(["Related: #" + str(issue_number), ""])
    lines.extend(
        [
            "---",
            "由 Issue Agent 预演生成。默认不创建分支、不推送、不写入仓库。",
            "需人工确认 head 分支已存在，并显式 `--open-pr` 后才会真正开 PR。",
            "",
        ]
    )
    body = "\n".join(lines).strip() + "\n"
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n...[truncated]\n"
    return title, body


def load_pr_payload(*, report_file, patch_file, issue_number=None):
    report_path = Path(report_file)
    patch_path = Path(patch_file)
    if not report_path.is_file():
        raise ValueError("--report-file 不存在或不是文件")
    if not patch_path.is_file():
        raise ValueError("--patch-file 不存在或不是文件")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("--report-file 不是合法 JSON") from exc
    try:
        patch = json.loads(patch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("--patch-file 不是合法 JSON") from exc
    return format_pr_from_report(report, patch, issue_number=issue_number)


def validate_ref_name(name, field):
    raw = (name or "").strip()
    if not raw or not HEAD_RE.fullmatch(raw) or ".." in raw:
        raise ValueError(field + " 不是合法分支名")
    return raw


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


def create_github_pr(
    ref,
    title,
    body,
    *,
    head,
    base=DEFAULT_BASE,
    token=None,
    post_json=None,
    dry_run=True,
):
    owner, repo, number = parse_github_issue_ref(ref)
    title_text = (title or "").strip()
    body_text = (body or "").strip()
    if not title_text:
        raise ValueError("PR 标题不能为空")
    if not body_text:
        raise ValueError("PR 正文不能为空")
    head_name = validate_ref_name(head, "--head")
    base_name = validate_ref_name(base, "--base")
    url = f"{API_ROOT}/repos/{owner}/{repo}/pulls"
    result = {
        "ok": True,
        "opened": False,
        "dry_run": dry_run,
        "repository": f"{owner}/{repo}",
        "issue": number,
        "url": url,
        "title": title_text,
        "body": body_text,
        "head": head_name,
        "base": base_name,
    }
    if dry_run:
        return result
    if post_json is not None:
        poster = post_json
        secret = ""
    else:
        secret = github_token(token)
        if not secret:
            raise ValueError("开 PR 需要 GITHUB_TOKEN")
        poster = lambda target, payload, _secret=secret: _post_json(target, _secret, payload)
    response = poster(
        url,
        {
            "title": title_text,
            "body": body_text,
            "head": head_name,
            "base": base_name,
        },
    )
    if not isinstance(response, dict):
        raise ValueError("GitHub 返回的不是合法 JSON")
    result.update({
        "opened": True,
        "dry_run": False,
        "html_url": response.get("html_url") or "",
        "pr_number": response.get("number"),
    })
    if secret and secret in json.dumps(result):
        raise RuntimeError("token leaked")
    return result


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="预演或创建 GitHub PR；默认不创建。不创建分支、不推送、不写仓库"
    )
    parser.add_argument("--github-issue", required=True, help="GitHub issue URL，或 owner/repo#123")
    parser.add_argument("--report-file", required=True, help="分诊 report.json")
    parser.add_argument("--patch-file", required=True, help="补丁 patch.json")
    parser.add_argument("--head", default=DEFAULT_HEAD, help="已存在的 head 分支名；本命令不会创建或推送")
    parser.add_argument("--base", default=DEFAULT_BASE, help="目标分支，默认 main")
    parser.add_argument(
        "--open-pr",
        action="store_true",
        help="真正创建 PR；省略时只预演。不会 git push",
    )
    parser.add_argument("--out", required=False, help="可选：把结果 JSON 写入文件")
    return parser.parse_args(argv)


def main(argv=None, *, poster=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        owner, repo, number = parse_github_issue_ref(args.github_issue)
        title, body = load_pr_payload(
            report_file=args.report_file,
            patch_file=args.patch_file,
            issue_number=number,
        )
        result = create_github_pr(
            args.github_issue,
            title,
            body,
            head=args.head,
            base=args.base,
            post_json=poster,
            dry_run=not args.open_pr,
        )
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        print(payload)
        if args.out:
            Path(args.out).write_text(payload + "\n", encoding="utf-8")
        return 0 if result.get("ok") else 1
    except (
        ValueError,
        GitHubHTTPError,
        RepairPatchError,
        OSError,
        RuntimeError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())