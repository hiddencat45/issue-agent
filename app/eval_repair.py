import argparse
import json
import shutil
import sys
from pathlib import Path

from app.eval_triage import EvalError
from app.propose import default_runner_factory
from app.repair_apply import apply_repair_patch
from app.repair_schema import RepairPatchError, patch_paths, validate_repair_patch
from app.run_pytest import run_pytest
from app.trace import TraceRecorder, write_trace
from app.triage import require_workspace


REQUIRED_CASE_KEYS = {"id", "issue_file", "expected_paths"}
OPTIONAL_CASE_KEYS = {"patch_file", "expect_ok", "workspace"}


def load_repair_cases(cases_dir):
    root = Path(cases_dir)
    manifest = root / "cases.json"
    if not manifest.is_file():
        raise EvalError("缺少 cases.json")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvalError("cases.json 不是合法 JSON") from exc
    if not isinstance(data, dict) or "cases" not in data or not isinstance(data["cases"], list):
        raise EvalError("cases.json 必须包含 cases 数组")
    cases = []
    for item in data["cases"]:
        if not isinstance(item, dict):
            raise EvalError("case 必须是对象")
        keys = set(item)
        if not REQUIRED_CASE_KEYS <= keys or keys - REQUIRED_CASE_KEYS - OPTIONAL_CASE_KEYS:
            raise EvalError(
                "case 字段必须包含 id、issue_file、expected_paths，"
                "可选 patch_file、expect_ok、workspace"
            )
        issue_path = root / item["issue_file"]
        if not issue_path.is_file():
            raise EvalError(f"issue 文件不存在：{item['issue_file']}")
        expected = item["expected_paths"]
        if not isinstance(expected, list) or not expected or not all(
            isinstance(x, str) and x for x in expected
        ):
            raise EvalError("expected_paths 必须是非空字符串数组")
        expect_ok = item.get("expect_ok", True)
        if not isinstance(expect_ok, bool):
            raise EvalError("expect_ok 必须是布尔值")
        patch_file = item.get("patch_file")
        if patch_file is not None:
            relative = Path(patch_file)
            if (
                not isinstance(patch_file, str)
                or not patch_file.strip()
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                raise EvalError("patch_file 必须是案例目录内的相对路径")
            if not (root / relative).is_file():
                raise EvalError(f"patch 文件不存在：{patch_file}")
        workspace_rel = item.get("workspace")
        if workspace_rel is not None:
            relative = Path(workspace_rel)
            if (
                not isinstance(workspace_rel, str)
                or not workspace_rel.strip()
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                raise EvalError("workspace 必须是案例目录内的相对路径")
            if not (root / relative).is_dir():
                raise EvalError(f"workspace 不存在：{workspace_rel}")
        cases.append({
            "id": item["id"],
            "issue_file": item["issue_file"],
            "issue_text": issue_path.read_text(encoding="utf-8"),
            "expected_paths": expected,
            "patch_file": patch_file,
            "expect_ok": expect_ok,
            "workspace": workspace_rel,
        })
    return cases


def evaluate_patch(workspace, patch, *, expected_paths):
    checks = []
    try:
        patch = validate_repair_patch(patch)
    except RepairPatchError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "checks": [],
        }
    paths = patch_paths(patch)
    for expected in expected_paths:
        mentioned = expected in paths
        checks.append({
            "id": f"path:{expected}",
            "ok": mentioned,
            "error": None if mentioned else "补丁未改该文件",
        })
    extra = [path for path in paths if path not in expected_paths]
    checks.append({
        "id": "extra_paths",
        "ok": True,
        "error": None if not extra else "额外修改了：" + ", ".join(extra),
    })
    verify = apply_repair_patch(
        workspace,
        patch,
        allowed_paths=paths,
        dry_run=True,
    )
    checks.append({
        "id": "verify",
        "ok": bool(verify.get("ok")),
        "error": None if verify.get("ok") else (verify.get("error") or "预演失败"),
    })
    return {
        "ok": all(item["ok"] for item in checks),
        "error": None,
        "checks": checks,
        "paths": paths,
    }


def _copy_workspace(src, dest):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            ".pytest_cache",
            ".git",
            ".venv",
            "venv",
        ),
    )


def evaluate_case(fixture, case, patch, work_copy):
    _copy_workspace(fixture, work_copy)
    scored = evaluate_patch(
        work_copy,
        patch,
        expected_paths=case["expected_paths"],
    )
    if not scored["ok"]:
        return {
            "id": case["id"],
            "ok": False,
            "error": scored.get("error"),
            "checks": scored["checks"],
            "applied": False,
            "tests_passed": False,
        }
    apply_result = apply_repair_patch(
        work_copy,
        patch,
        allowed_paths=patch_paths(patch),
        dry_run=False,
    )
    applied = bool(apply_result.get("ok") and apply_result.get("applied"))
    checks = list(scored["checks"])
    checks.append({
        "id": "apply",
        "ok": applied,
        "error": None if applied else (apply_result.get("error") or "写入未成功"),
    })
    tests_passed = False
    if applied:
        pytest_result = run_pytest(work_copy)
        tests_passed = bool(pytest_result.get("passed"))
        checks.append({
            "id": "pytest",
            "ok": tests_passed,
            "error": None if tests_passed else (pytest_result.get("error") or "pytest 未通过"),
        })
    else:
        checks.append({
            "id": "pytest",
            "ok": False,
            "error": "未写入，未运行 pytest",
        })
    return {
        "id": case["id"],
        "ok": all(item["ok"] for item in checks),
        "error": None,
        "checks": checks,
        "applied": applied,
        "tests_passed": tests_passed,
    }


def resolve_case_workspace(default_workspace, cases_dir, case):
    relative = case.get("workspace")
    if not relative:
        return Path(default_workspace).resolve()
    root = Path(cases_dir).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise EvalError("workspace 必须在案例目录内")
    if not path.is_dir():
        raise EvalError(f"workspace 不存在：{relative}")
    return path


def evaluate_cases(fixture, cases, patches, out_dir, cases_dir=None):
    results = []
    for case in cases:
        patch = patches.get(case["id"])
        if patch is None:
            results.append({
                "id": case["id"],
                "ok": False,
                "error": "缺少对应补丁",
                "checks": [],
                "applied": False,
                "tests_passed": False,
            })
            continue
        work_copy = Path(out_dir) / case["id"] / "repo"
        case_root = resolve_case_workspace(fixture, cases_dir, case)
        try:
            result = evaluate_case(case_root, case, patch, work_copy)
        except (RepairPatchError, OSError, UnicodeError) as exc:
            result = {
                "id": case["id"],
                "ok": False,
                "error": str(exc),
                "checks": [],
                "applied": False,
                "tests_passed": False,
            }
        results.append(_with_expectation(case, result))
    return {
        "ok": all(item["ok"] for item in results),
        "results": results,
    }


def _with_expectation(case, result):
    expect_ok = case.get("expect_ok", True)
    actual_ok = bool(result.get("ok"))
    matched = actual_ok is expect_ok
    payload = dict(result)
    payload["actual_ok"] = actual_ok
    payload["expect_ok"] = expect_ok
    payload["ok"] = matched
    if not matched and not payload.get("error"):
        payload["error"] = "结果与 expect_ok 不符"
    return payload


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="核对修复补丁：路径、预演、写入副本后 pytest"
    )
    parser.add_argument("--workspace", required=True, help="有缺陷的目标仓库模板，绝对路径")
    parser.add_argument("--cases-dir", required=True, help="含 cases.json 的目录")
    parser.add_argument("--out-dir", required=True, help="补丁、副本与评分输出目录")
    parser.add_argument(
        "--run",
        action="store_true",
        help="先对每个 case 调用提案（会使用模型）；省略则只评分已有补丁",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_patches(out_dir, cases, cases_dir=None):
    patches = {}
    root = Path(cases_dir) if cases_dir is not None else None
    for case in cases:
        canned = case.get("patch_file")
        if canned:
            if root is None:
                continue
            path = root / canned
            if path.is_file():
                patches[case["id"]] = json.loads(path.read_text(encoding="utf-8"))
            continue
        path = Path(out_dir) / f"{case['id']}.json"
        if not path.is_file():
            continue
        patches[case["id"]] = json.loads(path.read_text(encoding="utf-8"))
    return patches


def run_cases(workspace, cases, out_dir, *, propose_factory=None, cases_dir=None):
    patches = {}
    for case in cases:
        if case.get("patch_file"):
            continue
        recorder = TraceRecorder()
        factory = propose_factory or (
            lambda item, rec=recorder: default_runner_factory(item, recorder=rec)
        )
        try:
            case_root = resolve_case_workspace(workspace, cases_dir, case)
            patch = factory(case_root)(case["issue_text"])
        except Exception as exc:
            _write_json(
                Path(out_dir) / f"{case['id']}.error.json",
                {"ok": False, "error": str(exc)},
            )
            continue
        patches[case["id"]] = patch
        _write_json(Path(out_dir) / f"{case['id']}.json", patch)
        write_trace(
            Path(out_dir) / f"{case['id']}-trace.json",
            kind="propose",
            issue_text=case["issue_text"],
            events=recorder.events,
            output=patch,
        )
    return patches


def main(argv=None, *, run_cases_fn=None, propose_factory=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        workspace = require_workspace(args.workspace)
        cases_dir = Path(args.cases_dir)
        if not cases_dir.is_absolute():
            raise ValueError("--cases-dir 必须是绝对路径")
        out_dir = require_out_dir(args.out_dir)
        cases = load_repair_cases(cases_dir)
        if args.case_id:
            wanted = set(args.case_id)
            known = {case["id"] for case in cases}
            missing = wanted - known
            if missing:
                raise EvalError("未知 case-id：" + ", ".join(sorted(missing)))
            cases = [case for case in cases if case["id"] in wanted]
        patches = load_patches(out_dir, cases, cases_dir)
        if args.run:
            to_run = [case for case in cases if not case.get("patch_file")]
            runner = run_cases_fn or (
                lambda ws, items, dest: run_cases(
                    ws,
                    items,
                    dest,
                    propose_factory=propose_factory,
                    cases_dir=cases_dir,
                )
            )
            patches.update(runner(workspace, to_run, out_dir))
        scored = evaluate_cases(
            workspace, cases, patches, out_dir, cases_dir=cases_dir
        )
        _write_json(out_dir / "score.json", scored)
        print(json.dumps(scored, ensure_ascii=False, indent=2))
        return 0 if scored["ok"] else 1
    except (
        ValueError,
        EvalError,
        RepairPatchError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        RuntimeError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
