import json
from types import SimpleNamespace

from app.propose import collect_patch, main
from app.repair_schema import RepairPatchError


VALID_PATCH = {
    "path": "notes.py",
    "old_text": "    return text.strip()",
    "new_text": "    return text",
    "rationale": "按 issue 要求保留首尾空格",
}


class FakeItem:
    def __init__(self, **data):
        self.__dict__.update(data)

    def model_dump(self, exclude_none=True):
        return {
            key: value
            for key, value in vars(self).items()
            if not exclude_none or value is not None
        }


def write_issue(tmp_path, text="format_note 不应再去掉空格"):
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


def test_empty_issue_file_exits_nonzero(tmp_path):
    issue = write_issue(tmp_path, "  \n")
    code = main([
        "--workspace",
        str(tmp_path.resolve()),
        "--issue-file",
        str(issue),
    ])
    assert code != 0


def test_cli_prints_valid_patch(tmp_path, capsys):
    issue = write_issue(tmp_path)
    out = tmp_path / "patch.json"

    def factory(workspace):
        assert workspace == tmp_path.resolve()

        def runner(issue_text):
            assert "format_note" in issue_text
            return VALID_PATCH

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
    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert printed == VALID_PATCH
    assert json.loads(out.read_text(encoding="utf-8")) == VALID_PATCH


def test_non_json_agent_output_exits_nonzero(tmp_path):
    issue = write_issue(tmp_path)

    def factory(workspace):
        def runner(issue_text):
            raise RepairPatchError("补丁不是合法 JSON")
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


def test_collect_patch_requires_read_file():
    calls = []
    answer = json.dumps(VALID_PATCH, ensure_ascii=False)

    def request(history, *, tool_choice):
        if not calls:
            item = FakeItem(
                type="function_call",
                name="read_file",
                arguments='{"path": "notes.py"}',
                call_id="call-1",
            )
            return SimpleNamespace(output=[item], output_text="")
        message = FakeItem(type="message", role="assistant", content=[])
        return SimpleNamespace(output=[message], output_text=answer)

    def execute(call):
        calls.append(call.name)
        return {"ok": True, "path": "notes.py", "total_lines": 1, "lines": []}

    patch = collect_patch(
        "不要去掉空格",
        request_response=request,
        execute_tool_fn=execute,
    )
    assert calls == ["read_file"]
    assert patch == VALID_PATCH
