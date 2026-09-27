import argparse
import json
import sys
from pathlib import Path

from app import propose
from app import triage
from app.github_issue import GitHubHTTPError, add_issue_source_args, load_issue_text_from_args
from app.repair_apply import apply_repair_patch, restore_files
from app.repair_schema import RepairPatchError
from app.run_pytest import run_pytest
from app.trace import TraceRecorder, write_trace
from app.trace_schema import TraceError
from app.triage_schema import TriageReportError


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="开发者工作流：分诊 → 提案 → 预演；加 --apply 才写入"
    )
    parser.add_argument("--workspace", required=True, help="目标仓库的绝对路径")
    add_issue_source_args(parser)
    parser.add_argument("--out-dir", required=True, help="报告、补丁和记录的输出目录")
    parser.add_argument(
        "--allow-write",
        action="append",
        default=[],
        help="允许写入的相对路径，可重复；仅 --apply 时需要",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="预演通过后真正写入；省略时不改目标仓库",
    )
    parser.add_argument(
        "--rollback-on-fail",
        action="store_true",
        help="pytest 失败后，把本轮写入的文件恢复成写入前；必须同时提供 --pytest",
    )
    parser.add_argument(
        "--pytest",
        action="store_true",
        help="写入成功后在目标仓库运行 python -m pytest -q；必须同时提供 --apply",
    )
    return parser.parse_args(argv)


def require_out_dir(raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("--out-dir 必须是绝对路径")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError("--out-dir 不是目录")
    return path.resolve()


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_workflow(
    workspace,
    issue_text,
    out_dir,
    *,
    make_triage,
    make_propose,
    triage_recorder,
    propose_recorder,
    allow_write,
    apply,
    run_tests=False,
    rollback_on_fail=False,
):
    report = make_triage(workspace)(issue_text)
    _write_json(out_dir / "report.json", report)
    write_trace(
        out_dir / "triage-trace.json",
        kind="triage",
        issue_text=issue_text,
        events=triage_recorder.events,
        output=report,
    )

    patch = make_propose(workspace)(issue_text)
    _write_json(out_dir / "patch.json", patch)
    write_trace(
        out_dir / "propose-trace.json",
        kind="propose",
        issue_text=issue_text,
        events=propose_recorder.events,
        output=patch,
    )

    verify = propose.verify_patch(workspace, patch)
    _write_json(out_dir / "verify.json", verify)
    write_trace(
        out_dir / "verify-trace.json",
        kind="repair",
        issue_text=json.dumps(patch, ensure_ascii=False),
        events=[],
        output=verify,
    )

    applied = False
    if apply:
        if not allow_write:
            raise ValueError("使用 --apply 时至少提供一个 --allow-write")
        originals = {}
        apply_result = apply_repair_patch(
            workspace,
            patch,
            allowed_paths=allow_write,
            dry_run=False,
            originals_out=originals,
        )
        _write_json(out_dir / "apply.json", apply_result)
        write_trace(
            out_dir / "repair-trace.json",
            kind="repair",
            issue_text=json.dumps(patch, ensure_ascii=False),
            events=[],
            output=apply_result,
        )
        if not apply_result.get("ok") or not apply_result.get("applied"):
            raise ValueError(apply_result.get("error") or "写入未成功")
        applied = True

    tests_passed = None
    if run_tests:
        if not applied:
            raise ValueError("使用 --pytest 时必须同时提供 --apply")
        pytest_result = run_pytest(workspace)
        _write_json(out_dir / "pytest.json", pytest_result)
        tests_passed = bool(pytest_result.get("passed"))
        pytest_returncode = pytest_result.get("returncode")

    rolled_back = False
    rollback_result = None
    if rollback_on_fail:
        if not run_tests:
            raise ValueError("使用 --rollback-on-fail 时必须同时提供 --pytest")
        if applied and tests_passed is False:
            rollback_result = restore_files(workspace, originals)
            _write_json(out_dir / "rollback.json", rollback_result)
            rolled_back = bool(rollback_result.get("ok"))

    summary = {
        "ok": True if tests_passed is None else tests_passed,
        "report": "report.json",
        "patch": "patch.json",
        "verify": "verify.json",
        "applied": applied,
    }
    if tests_passed is not None:
        summary["pytest"] = "pytest.json"
        summary["tests_passed"] = tests_passed
        summary["pytest_returncode"] = pytest_returncode
    if rollback_on_fail:
        summary["rolled_back"] = rolled_back
        if rollback_result is not None:
            summary["rollback"] = "rollback.json"
    _write_json(out_dir / "summary.json", summary)
    return summary


def main(argv=None, *, triage_factory=None, propose_factory=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        if args.rollback_on_fail and not args.pytest:
            raise ValueError("使用 --rollback-on-fail 时必须同时提供 --pytest")
        if args.pytest and not args.apply:
            raise ValueError("使用 --pytest 时必须同时提供 --apply")
        workspace = triage.require_workspace(args.workspace)
        issue_text = load_issue_text_from_args(args)
        out_dir = require_out_dir(args.out_dir)

        triage_recorder = TraceRecorder()
        propose_recorder = TraceRecorder()

        def make_triage(item):
            if triage_factory is not None:
                return triage_factory(item)
            return triage.default_runner_factory(
                item, recorder=triage_recorder
            )

        def make_propose(item):
            if propose_factory is not None:
                return propose_factory(item)
            return propose.default_runner_factory(
                item, recorder=propose_recorder
            )

        summary = run_workflow(
            workspace,
            issue_text,
            out_dir,
            make_triage=make_triage,
            make_propose=make_propose,
            triage_recorder=triage_recorder,
            propose_recorder=propose_recorder,
            allow_write=args.allow_write,
            apply=args.apply,
            run_tests=args.pytest,
            rollback_on_fail=args.rollback_on_fail,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("ok") else 1

    except (
        ValueError, GitHubHTTPError,
        TriageReportError,
        RepairPatchError,
        TraceError,
        FileNotFoundError,
        OSError,
        KeyError,
        RuntimeError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
