import json


REPORT_KEYS = (
    "issue_summary",
    "evidence",
    "candidate_files",
    "uncertainties",
)

EVIDENCE_KEYS = ("path", "line", "quote")


class TriageReportError(ValueError):
    """四格报告结构不合法。"""


def parse_triage_report(text):
    """把模型输出解析为四格报告；失败时抛出 TriageReportError，不静默兜底。"""
    if not isinstance(text, str) or not text.strip():
        raise TriageReportError("报告必须是非空 JSON 文本")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TriageReportError("报告不是合法 JSON") from exc

    return validate_triage_report(data)


def validate_triage_report(data):
    if not isinstance(data, dict):
        raise TriageReportError("报告必须是 JSON 对象")

    if set(data) != set(REPORT_KEYS):
        raise TriageReportError("报告字段必须恰好为四格")

    summary = data["issue_summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise TriageReportError("issue_summary 必须是非空字符串")

    evidence = data["evidence"]
    if not isinstance(evidence, list):
        raise TriageReportError("evidence 必须是数组")

    for item in evidence:
        _validate_evidence_item(item)

    candidate_files = data["candidate_files"]
    if not isinstance(candidate_files, list):
        raise TriageReportError("candidate_files 必须是数组")

    for path in candidate_files:
        _validate_relative_path(path, "candidate_files")

    uncertainties = data["uncertainties"]
    if not isinstance(uncertainties, list):
        raise TriageReportError("uncertainties 必须是数组")

    for item in uncertainties:
        if not isinstance(item, str) or not item.strip():
            raise TriageReportError("uncertainties 每项必须是非空字符串")

    return {
        "issue_summary": summary,
        "evidence": evidence,
        "candidate_files": candidate_files,
        "uncertainties": uncertainties,
    }


def _validate_evidence_item(item):
    if not isinstance(item, dict) or set(item) != set(EVIDENCE_KEYS):
        raise TriageReportError("evidence 项字段必须为 path、line、quote")

    _validate_relative_path(item["path"], "evidence.path")

    line = item["line"]
    if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
        raise TriageReportError("evidence.line 必须是正整数或 null")

    quote = item["quote"]
    if not isinstance(quote, str) or not quote:
        raise TriageReportError("evidence.quote 必须是原文非空字符串")


def _validate_relative_path(path, field):
    if not isinstance(path, str) or not path.strip():
        raise TriageReportError(f"{field} 必须是非空相对路径")

    if "\\" in path:
        raise TriageReportError(f"{field} 必须使用 posix 相对路径")

    if path.startswith("/") or path == "." or path.startswith("./"):
        raise TriageReportError(f"{field} 必须是相对仓库根的文件路径")

    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise TriageReportError(f"{field} 不允许空段、'.' 或 '..'")
