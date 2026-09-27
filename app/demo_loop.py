import argparse
import json
import sys
from pathlib import Path

from app.github_comment import format_comment_from_report, post_github_comment
from app.github_pr import create_github_pr, format_pr_from_report
from app.github_issue import GitHubHTTPError, fetch_github_issue, parse_github_issue_ref
from app.issue import require_out_dir, run_workflow
from app.propose import verify_patch
from app.repair_schema import RepairPatchError, validate_repair_patch
from app.trace import TraceRecorder
from app.triage import require_workspace
from app.triage_schema import TriageReportError, validate_triage_report


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE = PROJECT_ROOT / "cases" / "demo" / "workspace"
DEFAULT_ISSUE = PROJECT_ROOT / "cases" / "demo" / "issue.txt"
DEFAULT_FIXTURES = PROJECT_ROOT / "cases" / "demo" / "fixtures"
DEFAULT_COMMENT_REF = "demo/local#1"


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="本地演示闭环：分诊 → 补丁预演 → 评论预览；默认离线，不写入、不发送"
    )
    parser.add_argument("--workspace", help="目标仓库的绝对路径；省略时用内置演示仓库")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--issue-file", help="issue 文本；省略且未给 --github-issue 时用内置演示 issue")
    source.add_argument(
        "--github-issue",
        help="只读拉取 GitHub issue 作为输入；必须同时 --live；评论预演也用该引用，不会发送",
    )
    parser.add_argument("--out-dir", required=True, help="演示产物目录，必须是绝对路径")
    parser.add_argument(
        "--live",
        action="store_true",
        help="调用模型走真实分诊/提案；省略时用离线夹具，不调模型",
    )
    parser.add_argument(
        "--comment-issue",
        help="评论预演引用；默认等于 --github-issue，否则 demo/local#1。不会发送",
    )
    return parser.parse_args(argv)


def load_issue_text(raw_path):
    path = Path(raw_path)
    if not path.is_file():
        raise ValueError("--issue-file 不存在或不是文件")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("--issue-file 不能为空")
    return text


def snapshot_workspace(workspace):
    root = Path(workspace)
    files = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") or part in {"__pycache__", ".venv"} for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        files[relative] = path.read_bytes()
    return files


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_comment_preview(out_dir, report, github_ref):
    comment = format_comment_from_report(report)
    (out_dir / "comment.md").write_text(comment, encoding="utf-8")
    preview = post_github_comment(github_ref, comment, dry_run=True)
    if preview.get("posted") or not preview.get("dry_run"):
        raise RuntimeError("演示不得发送 GitHub 评论")
    _write_json(out_dir / "comment-preview.json", preview)
    return comment, preview


def write_pr_preview(out_dir, report, patch, github_ref):
    _owner, _repo, number = parse_github_issue_ref(github_ref)
    title, body = format_pr_from_report(report, patch, issue_number=number)
    (out_dir / "pr.md").write_text("# " + title + "\n\n" + body, encoding="utf-8")
    preview = create_github_pr(
        github_ref,
        title,
        body,
        head="issue-agent",
        dry_run=True,
    )
    if preview.get("opened") or not preview.get("dry_run"):
        raise RuntimeError("演示不得创建 GitHub PR")
    _write_json(out_dir / "pr-preview.json", preview)
    return preview


def write_walkthrough(out_dir, summary, issue_text):
    live = "是（调用模型）" if summary.get("live") else "否（离线夹具，不调模型）"
    source = summary.get("issue_source") or "file"
    github_ref = summary.get("github_issue") or "（无）"
    text = "\n".join([
        "# Issue Agent 本地演示结果",
        "",
        "- 是否调用模型：" + live,
        "- Issue 来源：" + source,
        "- GitHub 引用：" + str(github_ref),
        "- 是否写入仓库：否",
        "- 是否发送 GitHub 评论：否（仅预演）",
        "- 是否开 PR：否",
        "- 目标仓库是否被改动：是" if not summary.get("workspace_unchanged") else "- 目标仓库是否被改动：否",
        "",
        "## Issue",
        "",
        issue_text.strip(),
        "",
        "## 产物",
        "",
        "- `issue.txt`：本次使用的 issue 原文",
        "- `report.json`：分诊报告",
        "- `patch.json`：补丁",
        "- `verify.json`：补丁预演（对原文，不写入）",
        "- `comment.md`：将要发到 GitHub 的评论预览",
        "- `comment-preview.json`：确认 posted=false",
        "- `pr.md`：将要开的 PR 预览",
        "- `pr-preview.json`：确认 opened=false",
        "",
        "下一步若要真正改代码，请用 `python -m app.issue --allow-write ... --apply`。",
        "下一步若要真正发评论，请用 `python -m app.github_comment --post-comment`。",
        "下一步若要真正开 PR，请先自行推送 head 分支，再用 `python -m app.github_pr --open-pr`。",
        "本命令不会开 PR、不会 git push。",
        "",
    ])
    (out_dir / "WALKTHROUGH.md").write_text(text, encoding="utf-8")


def load_offline_fixtures(fixture_dir):
    fixture_dir = Path(fixture_dir)
    report_path = fixture_dir / "report.json"
    patch_path = fixture_dir / "patch.json"
    if not report_path.is_file() or not patch_path.is_file():
        raise ValueError("离线夹具缺少 report.json 或 patch.json")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("离线夹具 report.json 不是合法 JSON") from exc
    try:
        patch = json.loads(patch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("离线夹具 patch.json 不是合法 JSON") from exc
    return validate_triage_report(report), validate_repair_patch(patch)


def finish_summary(out_dir, summary, *, live, issue_text, github_ref, issue_source):
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    write_comment_preview(out_dir, report, github_ref)
    patch = json.loads((out_dir / "patch.json").read_text(encoding="utf-8"))
    write_pr_preview(out_dir, report, patch, github_ref)
    (out_dir / "issue.txt").write_text(issue_text, encoding="utf-8")
    summary = dict(summary)
    summary["ok"] = True
    summary["live"] = live
    summary["applied"] = False
    summary["posted"] = False
    summary["opened"] = False
    summary["dry_run"] = True
    summary["issue_source"] = issue_source
    summary["github_issue"] = github_ref
    summary["issue"] = "issue.txt"
    summary["comment"] = "comment.md"
    summary["comment_preview"] = "comment-preview.json"
    summary["pr"] = "pr.md"
    summary["pr_preview"] = "pr-preview.json"
    summary["walkthrough"] = "WALKTHROUGH.md"
    _write_json(out_dir / "summary.json", summary)
    write_walkthrough(out_dir, summary, issue_text)
    return summary


def run_offline(workspace, issue_text, out_dir, *, github_ref, issue_source, fixture_dir=DEFAULT_FIXTURES):
    before = snapshot_workspace(workspace)
    report, patch = load_offline_fixtures(fixture_dir)
    verify = verify_patch(workspace, patch)
    _write_json(out_dir / "report.json", report)
    _write_json(out_dir / "patch.json", patch)
    _write_json(out_dir / "verify.json", verify)
    after = snapshot_workspace(workspace)
    if before != after:
        raise RuntimeError("演示不得修改目标仓库")
    summary = {
        "ok": True,
        "report": "report.json",
        "patch": "patch.json",
        "verify": "verify.json",
        "applied": False,
        "workspace_unchanged": True,
        "verify_ok": bool(verify.get("ok")),
    }
    return finish_summary(
        out_dir,
        summary,
        live=False,
        issue_text=issue_text,
        github_ref=github_ref,
        issue_source=issue_source,
    )


def run_live(
    workspace,
    issue_text,
    out_dir,
    *,
    github_ref,
    issue_source,
    make_triage,
    make_propose,
    triage_recorder,
    propose_recorder,
):
    before = snapshot_workspace(workspace)
    summary = run_workflow(
        workspace,
        issue_text,
        out_dir,
        make_triage=make_triage,
        make_propose=make_propose,
        triage_recorder=triage_recorder,
        propose_recorder=propose_recorder,
        allow_write=[],
        apply=False,
        run_tests=False,
        rollback_on_fail=False,
    )
    after = snapshot_workspace(workspace)
    if before != after:
        raise RuntimeError("演示不得修改目标仓库")
    summary = dict(summary)
    summary["workspace_unchanged"] = True
    return finish_summary(
        out_dir,
        summary,
        live=True,
        issue_text=issue_text,
        github_ref=github_ref,
        issue_source=issue_source,
    )


def resolve_issue_text(args, *, fetch=None):
    if args.github_issue:
        if not args.live:
            raise ValueError("使用 --github-issue 时必须同时提供 --live；离线夹具只适用于内置演示仓库")
        loader = fetch or fetch_github_issue
        text = loader(args.github_issue)
        if not (text or "").strip():
            raise ValueError("GitHub issue 为空")
        return text, "github"
    path = args.issue_file or str(DEFAULT_ISSUE)
    return load_issue_text(path), "file"


def main(argv=None, *, triage_factory=None, propose_factory=None, fetch=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        workspace = require_workspace(args.workspace or str(DEFAULT_WORKSPACE.resolve()))
        out_dir = require_out_dir(args.out_dir)
        issue_text, issue_source = resolve_issue_text(args, fetch=fetch)
        github_ref = args.comment_issue or args.github_issue or DEFAULT_COMMENT_REF

        if args.live:
            triage_recorder = TraceRecorder()
            propose_recorder = TraceRecorder()

            def make_triage(item):
                if triage_factory is not None:
                    return triage_factory(item)
                from app import triage
                return triage.default_runner_factory(item, recorder=triage_recorder)

            def make_propose(item):
                if propose_factory is not None:
                    return propose_factory(item)
                from app import propose
                return propose.default_runner_factory(item, recorder=propose_recorder)

            summary = run_live(
                workspace,
                issue_text,
                out_dir,
                github_ref=github_ref,
                issue_source=issue_source,
                make_triage=make_triage,
                make_propose=make_propose,
                triage_recorder=triage_recorder,
                propose_recorder=propose_recorder,
            )
        else:
            if triage_factory is not None or propose_factory is not None:
                raise ValueError("离线演示不调用模型工厂；若要注入工厂请加 --live")
            if fetch is not None:
                raise ValueError("离线演示不拉取 GitHub issue")
            summary = run_offline(
                workspace,
                issue_text,
                out_dir,
                github_ref=github_ref,
                issue_source=issue_source,
            )

        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("ok") else 1

    except (
        ValueError,
        GitHubHTTPError,
        TriageReportError,
        RepairPatchError,
        FileNotFoundError,
        OSError,
        KeyError,
        RuntimeError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())