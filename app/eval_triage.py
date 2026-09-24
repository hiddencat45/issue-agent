import json
from pathlib import Path

from app.triage_schema import TriageReportError, validate_triage_report


class EvalError(ValueError):
    """评测输入不合法。"""


def load_cases(cases_dir):
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
        if set(item) != {"id", "issue_file", "expected_files"}:
            raise EvalError("case 字段必须恰好为 id、issue_file、expected_files")
        issue_path = root / item["issue_file"]
        if not issue_path.is_file():
            raise EvalError(f"issue 文件不存在：{item['issue_file']}")
        expected = item["expected_files"]
        if not isinstance(expected, list) or not expected or not all(isinstance(x, str) and x for x in expected):
            raise EvalError("expected_files 必须是非空字符串数组")
        cases.append({
            "id": item["id"],
            "issue_file": item["issue_file"],
            "issue_text": issue_path.read_text(encoding="utf-8"),
            "expected_files": expected,
        })
    return cases


def _safe_file(workspace, relative):
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise EvalError("证据路径必须是仓库内相对路径")
    target = (Path(workspace) / relative_path).resolve()
    if not target.is_relative_to(Path(workspace).resolve()):
        raise EvalError("证据路径超出仓库范围")
    return target


def check_quote(workspace, item):
    try:
        target = _safe_file(workspace, item["path"])
    except EvalError as exc:
        return False, str(exc)
    if not target.is_file():
        return False, "证据文件不存在"
    text = target.read_text(encoding="utf-8")
    quote = item["quote"]
    if quote not in text:
        return False, "quote 不是文件中的原文子串"
    line = item.get("line")
    if line is None:
        return True, ""
    lines = text.splitlines()
    if line < 1 or line > len(lines):
        return False, "行号超出文件范围"
    if quote not in lines[line - 1]:
        return False, "quote 与声称的行号不一致"
    return True, ""


def evaluate_report(workspace, report, *, expected_files):
    report = validate_triage_report(report)
    checks = []
    for path in expected_files:
        mentioned = path in report["candidate_files"] or any(
            item["path"] == path for item in report["evidence"]
        )
        checks.append({
            "id": f"mentions:{path}",
            "ok": mentioned,
            "error": None if mentioned else "未在 candidate_files 或 evidence 中提到该文件",
        })
    if not report["evidence"]:
        checks.append({
            "id": "evidence_nonempty",
            "ok": False,
            "error": "没有证据",
        })
    for index, item in enumerate(report["evidence"]):
        ok, error = check_quote(workspace, item)
        checks.append({
            "id": f"quote:{index}",
            "ok": ok,
            "error": error or None,
        })
    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def evaluate_cases(workspace, cases, reports):
    results = []
    for case in cases:
        report = reports.get(case["id"])
        if report is None:
            results.append({
                "id": case["id"],
                "ok": False,
                "error": "缺少对应报告",
                "checks": [],
            })
            continue
        try:
            scored = evaluate_report(
                workspace,
                report,
                expected_files=case["expected_files"],
            )
        except (TriageReportError, EvalError, OSError, UnicodeError) as exc:
            results.append({
                "id": case["id"],
                "ok": False,
                "error": str(exc),
                "checks": [],
            })
            continue
        results.append({
            "id": case["id"],
            "ok": scored["ok"],
            "error": None,
            "checks": scored["checks"],
        })
    return {
        "ok": all(item["ok"] for item in results),
        "results": results,
    }
