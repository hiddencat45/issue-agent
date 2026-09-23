import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.triage import collect_report, main
from app.triage_schema import TriageReportError
from tests.test_triage_schema import VALID_REPORT


class FakeItem:
    def __init__(self, **data):
        self.__dict__.update(data)

    def model_dump(self, exclude_none=True):
        return {
            key: value
            for key, value in vars(self).items()
            if not exclude_none or value is not None
        }


def write_issue(tmp_path, text="paginate 在 page=0 时应报错"):
    path = tmp_path / "issue.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_workspace_exits_nonzero(tmp_path):
    issue = write_issue(tmp_path)
    code = main([
        "--workspace",
        str(tmp_path / "missing"),
        "--issue-file",
        str(issue),
    ])
    assert code != 0


def test_relative_workspace_exits_nonzero(tmp_path):
    issue = write_issue(tmp_path)
    code = main([
        "--workspace",
        "relative-dir",
        "--issue-file",
        str(issue),
    ])
    assert code != 0


def test_empty_issue_file_exits_nonzero(tmp_path):
    issue = write_issue(tmp_path, "  \n")
    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--issue-file",
        str(issue),
    ])
    assert code != 0


def test_cli_prints_valid_report(tmp_path, capsys):
    issue = write_issue(tmp_path)
    out = tmp_path / "report.json"

    def factory(workspace):
        assert workspace == tmp_path.resolve()

        def runner(issue_text):
            assert "paginate" in issue_text
            return VALID_REPORT

        return runner

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--out",
            str(out),
        ],
        runner_factory=factory,
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == VALID_REPORT
    assert json.loads(out.read_text(encoding="utf-8")) == VALID_REPORT


def test_non_json_agent_output_exits_nonzero(tmp_path):
    issue = write_issue(tmp_path)

    def factory(workspace):
        def runner(issue_text):
            raise TriageReportError("报告不是合法 JSON")

        return runner

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
        ],
        runner_factory=factory,
    )
    assert code != 0


def test_collect_report_requires_read_file():
    calls = []
    answer = json.dumps(VALID_REPORT, ensure_ascii=False)

    def request(history, *, tool_choice):
        if not calls:
            item = FakeItem(
                type="function_call",
                name="read_file",
                arguments='{"path": "text_utils/pagination.py"}',
                call_id="call-1",
            )
            return SimpleNamespace(output=[item], output_text="")

        message = FakeItem(type="message", role="assistant", content=[])
        return SimpleNamespace(output=[message], output_text=answer)

    def execute(call):
        calls.append(call.name)
        return {"ok": True, "path": "text_utils/pagination.py", "total_lines": 1, "lines": []}

    report = collect_report(
        "分页问题",
        request_response=request,
        execute_tool_fn=execute,
    )

    assert calls == ["read_file"]
    assert report["issue_summary"] == VALID_REPORT["issue_summary"]


def test_trace_out_writes_record(tmp_path, capsys):
    issue = write_issue(tmp_path)
    trace_path = tmp_path / "trace.json"

    def factory(workspace):
        def runner(issue_text):
            return VALID_REPORT
        return runner

    code = main(
        [
            "--workspace",
            str(tmp_path.resolve()),
            "--issue-file",
            str(issue),
            "--trace-out",
            str(trace_path),
        ],
        runner_factory=factory,
    )
    printed = json.loads(capsys.readouterr().out)
    record = json.loads(trace_path.read_text(encoding="utf-8"))
    assert code == 0
    assert printed == VALID_REPORT
    assert record["kind"] == "triage"
    assert record["output"] == VALID_REPORT
    assert "paginate" in record["issue_text"]
    assert record["events"] == []
