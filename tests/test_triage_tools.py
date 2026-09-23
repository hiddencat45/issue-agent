import json
from types import SimpleNamespace
from unittest.mock import Mock

from app.triage_tools import TOOLS, execute_tool


def invoke(name, arguments, repository):
    return execute_tool(
        SimpleNamespace(name=name, arguments=arguments),
        repository,
    )


def test_tool_definitions():
    names = [tool["name"] for tool in TOOLS]

    assert len(names) == len(set(names))
    assert names == ["list_files", "search_code", "read_file"]

    by_name = {tool["name"]: tool for tool in TOOLS}

    list_files = by_name["list_files"]
    assert list_files["type"] == "function"
    assert list_files["parameters"]["required"] == ["path"]
    assert set(list_files["parameters"]["properties"]) == {"path", "limit"}
    assert list_files["parameters"]["additionalProperties"] is False
    assert "strict" not in list_files

    search_code = by_name["search_code"]
    assert set(search_code["parameters"]["required"]) == {"query", "path"}
    assert set(search_code["parameters"]["properties"]) == {
        "query",
        "path",
        "limit",
    }

    read_file = by_name["read_file"]
    assert read_file["parameters"]["required"] == ["path"]
    assert set(read_file["parameters"]["properties"]) == {
        "path",
        "start_line",
        "end_line",
    }


def test_unknown_tool_returns_structured_error():
    repository = Mock()

    result = invoke("not_a_tool", '{"path": "."}', repository)

    assert result == {"ok": False, "error": "不支持的工具"}
    repository.assert_not_called()


def test_invalid_json_returns_structured_error():
    repository = Mock()

    result = invoke("list_files", "{broken", repository)

    assert result == {"ok": False, "error": "arguments 不是合法 JSON"}
    repository.list_files.assert_not_called()


def test_key_set_mismatch_is_rejected():
    repository = Mock()
    invalid_arguments = (
        "{}",
        '{"limit": 10}',
        '{"path": ".", "extra": true}',
        "[]",
        "null",
        '"."',
    )

    for arguments in invalid_arguments:
        result = invoke("list_files", arguments, repository)
        assert result == {
            "ok": False,
            "error": "arguments 键集不符",
        }, arguments

    repository.list_files.assert_not_called()


def test_optional_limit_may_be_omitted():
    repository = Mock()
    expected = {"ok": True, "files": ["README.md"], "truncated": False}
    repository.list_files.return_value = expected

    result = invoke("list_files", '{"path": "."}', repository)

    repository.list_files.assert_called_once_with(path=".")
    assert result is expected


def test_optional_limit_may_be_provided():
    repository = Mock()
    expected = {"ok": True, "files": ["a.py"], "truncated": True}
    repository.list_files.return_value = expected

    result = invoke(
        "list_files",
        json.dumps({"path": "src", "limit": 1}),
        repository,
    )

    repository.list_files.assert_called_once_with(path="src", limit=1)
    assert result is expected


def test_search_code_requires_query_and_path():
    repository = Mock()
    expected = {
        "ok": True,
        "matches": [],
        "truncated": False,
        "skipped_files": [],
    }
    repository.search_code.return_value = expected

    result = invoke(
        "search_code",
        json.dumps({"query": "paginate", "path": "."}),
        repository,
    )

    repository.search_code.assert_called_once_with(
        query="paginate",
        path=".",
    )
    assert result is expected


def test_read_file_forwards_optional_lines():
    repository = Mock()
    expected = {"ok": True, "path": "a.py", "total_lines": 3, "lines": []}
    repository.read_file.return_value = expected

    result = invoke(
        "read_file",
        json.dumps({
            "path": "a.py",
            "start_line": 2,
            "end_line": 3,
        }),
        repository,
    )

    repository.read_file.assert_called_once_with(
        path="a.py",
        start_line=2,
        end_line=3,
    )
    assert result is expected


def test_underlying_ok_false_is_passed_through():
    repository = Mock()
    expected = {"ok": False, "error": "路径超出仓库范围"}
    repository.read_file.return_value = expected

    result = invoke("read_file", '{"path": "missing.py"}', repository)

    repository.read_file.assert_called_once_with(path="missing.py")
    assert result is expected
