import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app.demo_read_file as demo


def invoke(name, arguments):
    return demo.execute_tool(
        SimpleNamespace(name=name, arguments=arguments)
    )


@pytest.fixture
def handlers(monkeypatch):
    """替换三个文件工具，测试时不执行真实文件操作。"""
    search_result = {
        "query": "notes",
        "matches": ["sub/notes.txt"],
        "scanned_entries": 500,
        "skipped_links": 0,
        "skipped_errors": 0,
        "truncated": True,
        "reasons": ["scan_limit"],
        "limits": {
            "max_depth": 3,
            "max_scanned_entries": 500,
            "max_results": 50,
        },
    }

    search = Mock(return_value=search_result)
    read = Mock(return_value={
        "path": "notes.txt",
        "content": "test",
    })
    listing = Mock(return_value={
        "path": ".",
        "entries": [],
        "truncated": False,
    })

    monkeypatch.setattr(demo, "search_workspace_files", search)
    monkeypatch.setattr(demo, "read_workspace_file", read)
    monkeypatch.setattr(demo, "list_workspace_directory", listing)

    return SimpleNamespace(
        search=search,
        read=read,
        listing=listing,
        search_result=search_result,
    )


def test_tool_definitions():
    names = [tool["name"] for tool in demo.TOOLS]

    assert len(names) == len(set(names)), "工具定义不能重复"
    assert set(names) == {
        "read_workspace_file",
        "list_workspace_directory",
        "search_workspace_files",
    }

    definition = next(
        tool for tool in demo.TOOLS
        if tool["name"] == "search_workspace_files"
    )
    parameters = definition["parameters"]

    assert definition["type"] == "function"
    assert definition["strict"] is True
    assert parameters["type"] == "object"
    assert parameters["required"] == ["query"]
    assert set(parameters["properties"]) == {"query"}
    assert parameters["properties"]["query"]["type"] == "string"
    assert parameters["additionalProperties"] is False


def test_search_dispatch_preserves_incomplete_metadata(handlers):
    result = invoke(
        "search_workspace_files",
        json.dumps({"query": "notes"}),
    )

    handlers.search.assert_called_once_with("notes")
    handlers.read.assert_not_called()
    handlers.listing.assert_not_called()

    assert result == {"ok": True, **handlers.search_result}


def test_invalid_argument_structure_rejected(handlers):
    invalid_arguments = (
        "{}",
        '{"path": "."}',
        '{"query": "notes", "extra": true}',
        "[]",
        "null",
        "{broken",
    )

    for arguments in invalid_arguments:
        result = invoke("search_workspace_files", arguments)
        assert result["ok"] is False, arguments

    handlers.search.assert_not_called()
    handlers.read.assert_not_called()
    handlers.listing.assert_not_called()


def test_handler_failure_is_sanitized(handlers):
    private_details = "private internal details"

    for error_type in (ValueError, TypeError, OSError, RuntimeError):
        handlers.search.reset_mock()
        handlers.search.side_effect = error_type(private_details)

        result = invoke(
            "search_workspace_files",
            '{"query": "notes"}',
        )

        handlers.search.assert_called_once_with("notes")
        assert result["ok"] is False
        assert isinstance(result["error"], str)
        assert result["error"]
        assert private_details not in json.dumps(
            result, ensure_ascii=False
        )

    handlers.read.assert_not_called()
    handlers.listing.assert_not_called()


def test_existing_tools_retain_path_only_dispatch(handlers):
    result = invoke(
        "read_workspace_file",
        '{"path": "notes.txt"}',
    )
    assert result["ok"] is True
    handlers.read.assert_called_once_with("notes.txt")

    result = invoke(
        "list_workspace_directory",
        '{"path": "."}',
    )
    assert result["ok"] is True
    handlers.listing.assert_called_once_with(".")

    for name in (
        "read_workspace_file",
        "list_workspace_directory",
    ):
        for arguments in (
            '{"query": "notes"}',
            '{"path": ".", "extra": true}',
        ):
            result = invoke(name, arguments)
            assert result["ok"] is False, (name, arguments)

    assert handlers.read.call_count == 1
    assert handlers.listing.call_count == 1
    handlers.search.assert_not_called()


def test_unknown_tool_rejected(handlers):
    result = invoke("unknown_tool", "{}")

    assert result["ok"] is False
    handlers.search.assert_not_called()
    handlers.read.assert_not_called()
    handlers.listing.assert_not_called()
