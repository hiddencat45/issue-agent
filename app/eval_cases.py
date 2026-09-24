import argparse
import json
import sys
from pathlib import Path

from app.eval_triage import EvalError, evaluate_cases, load_cases
from app.trace import TraceRecorder, write_trace
from app.triage import default_runner_factory, require_workspace
from app.triage_schema import TriageReportError


def parse_args(argv):
    parser = argparse.ArgumentParser(description="核对分诊报告：相关文件与原文证据")
    parser.add_argument("--workspace", required=True, help="目标仓库的绝对路径")
    parser.add_argument("--cases-dir", required=True, help="含 cases.json 的目录")
    parser.add_argument("--out-dir", required=True, help="报告与评分输出目录")
    parser.add_argument(
        "--run",
        action="store_true",
        help="先对每个 case 调用分诊（会使用模型）；省略则只评分已有报告",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="只跑指定案例 id，可重复",
    )
    return parser.parse_args(argv)


def require_out_dir(raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("--out-dir 必须是绝对路径")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_reports(out_dir, cases):
    reports = {}
    for case in cases:
        path = out_dir / f"{case['id']}.json"
        if not path.is_file():
            continue
        reports[case["id"]] = json.loads(path.read_text(encoding="utf-8"))
    return reports


def run_cases(workspace, cases, out_dir):
    reports = {}
    for case in cases:
        recorder = TraceRecorder()
        runner = default_runner_factory(workspace, recorder=recorder)
        try:
            report = runner(case["issue_text"])
        except Exception as exc:
            _write_json(
                out_dir / f"{case['id']}.error.json",
                {"ok": False, "error": str(exc)},
            )
            continue
        reports[case["id"]] = report
        _write_json(out_dir / f"{case['id']}.json", report)
        write_trace(
            out_dir / f"{case['id']}-trace.json",
            kind="triage",
            issue_text=case["issue_text"],
            events=recorder.events,
            output=report,
        )
    return reports


def main(argv=None, *, run_cases_fn=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        workspace = require_workspace(args.workspace)
        cases_dir = Path(args.cases_dir)
        if not cases_dir.is_absolute():
            raise ValueError("--cases-dir 必须是绝对路径")
        out_dir = require_out_dir(args.out_dir)
        cases = load_cases(cases_dir)
        if args.case_id:
            wanted = set(args.case_id)
            known = {case["id"] for case in cases}
            missing = wanted - known
            if missing:
                raise EvalError("未知 case-id：" + ", ".join(sorted(missing)))
            cases = [case for case in cases if case["id"] in wanted]
        if args.run:
            runner = run_cases_fn or run_cases
            reports = runner(workspace, cases, out_dir)
        else:
            reports = load_reports(out_dir, cases)
        scored = evaluate_cases(workspace, cases, reports)
        _write_json(out_dir / "score.json", scored)
        print(json.dumps(scored, ensure_ascii=False, indent=2))
        return 0 if scored["ok"] else 1
    except (ValueError, EvalError, TriageReportError, OSError, json.JSONDecodeError, KeyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
