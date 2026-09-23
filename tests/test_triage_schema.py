import json

import pytest

from app.triage_schema import (
    TriageReportError,
    parse_triage_report,
    validate_triage_report,
)


VALID_REPORT = {
    "issue_summary": "分页在非法页码时应报错。",
    "evidence": [
        {
            "path": "text_utils/pagination.py",
            "line": 3,
            "quote": "if page < 1:",
        }
    ],
    "candidate_files": ["text_utils/pagination.py"],
    "uncertainties": ["未确认调用方如何传入 page"],
}


def test_valid_report_roundtrip():
    text = json.dumps(VALID_REPORT, ensure_ascii=False)
    parsed = parse_triage_report(text)
    assert parsed == VALID_REPORT
    assert validate_triage_report(VALID_REPORT) == VALID_REPORT


def test_non_json_text_is_rejected():
    with pytest.raises(TriageReportError, match="合法 JSON"):
        parse_triage_report("不是 JSON")


def test_empty_text_is_rejected():
    with pytest.raises(TriageReportError, match="非空 JSON"):
        parse_triage_report("   ")


def test_extra_field_is_rejected():
    data = dict(VALID_REPORT)
    data["severity"] = "high"
    with pytest.raises(TriageReportError, match="恰好为四格"):
        validate_triage_report(data)


def test_missing_field_is_rejected():
    data = dict(VALID_REPORT)
    del data["uncertainties"]
    with pytest.raises(TriageReportError, match="恰好为四格"):
        validate_triage_report(data)


def test_evidence_line_may_be_null():
    data = json.loads(json.dumps(VALID_REPORT))
    data["evidence"][0]["line"] = None
    assert validate_triage_report(data)["evidence"][0]["line"] is None


def test_invalid_candidate_path_is_rejected():
    data = json.loads(json.dumps(VALID_REPORT))
    data["candidate_files"] = ["../outside.py"]
    with pytest.raises(TriageReportError, match="posix|相对|\\.\\."):
        validate_triage_report(data)


def test_boolean_line_is_rejected():
    data = json.loads(json.dumps(VALID_REPORT))
    data["evidence"][0]["line"] = True
    with pytest.raises(TriageReportError, match="line"):
        validate_triage_report(data)
