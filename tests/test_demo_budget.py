import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

import app.demo_read_file as demo


def tool_call(number):
    data = {
        "type": "function_call",
        "id": f"fc_{number}",
        "call_id": f"call_{number}",
        "name": "read_workspace_file",
        "arguments": '{"path": "test.txt"}',
    }
    return SimpleNamespace(
        **data,
        model_dump=Mock(return_value=data),
    )


def tool_response(*numbers):
    return SimpleNamespace(
        output=[tool_call(number) for number in numbers],
        output_text="",
    )


def text_response():
    return SimpleNamespace(
        output=[],
        output_text="测试总结：仅报告已确认的信息。",
    )


@pytest.fixture
def setup_run(monkeypatch):
    """隔离环境文件、工作区检查、API 客户端和工具执行。"""
    monkeypatch.setattr(demo, "load_dotenv", Mock())

    workspace = Mock()
    workspace.is_dir.return_value = True
    monkeypatch.setattr(demo, "WORKSPACE", workspace)

    monkeypatch.setenv("OPENAI_API_KEY", "fake-budget-test-key")
    monkeypatch.setenv(
        "OPENAI_BASE_URL",
        "https://example.invalid/v1",
    )

    client_context = MagicMock()
    monkeypatch.setattr(
        demo,
        "OpenAI",
        Mock(return_value=client_context),
    )

    execute = Mock(return_value={"ok": True, "content": "test"})
    monkeypatch.setattr(demo, "execute_tool", execute)

    def prepare(responses):
        pending = iter(responses)
        requests = []

        def fake_request(client, history, tool_choice):
            # 必须保存快照，不能保留之后还会变化的 history 引用。
            requests.append({
                "history": deepcopy(history),
                "tool_choice": tool_choice,
            })
            try:
                return next(pending)
            except StopIteration:
                pytest.fail("发生了超出预期次数的模型请求")

        request = Mock(side_effect=fake_request)
        monkeypatch.setattr(demo, "request_response", request)

        return SimpleNamespace(
            execute=execute,
            request=request,
            requests=requests,
        )

    return prepare


def assert_final_request(run, exploration_rounds):
    choices = [
        request["tool_choice"]
        for request in run.requests
    ]
    assert choices == ["auto"] * exploration_rounds + ["none"]

    history = run.requests[-1]["history"]
    assert history[-1]["role"] == "developer"
    assert "预算已耗尽" in history[-1]["content"]
    assert "不得再调用工具" in history[-1]["content"]
    return history


def assert_matching_outputs(history, expected_count):
    calls = [
        item for item in history
        if item.get("type") == "function_call"
    ]
    outputs = [
        item for item in history
        if item.get("type") == "function_call_output"
    ]

    assert len(calls) == expected_count
    assert len(outputs) == expected_count

    call_ids = [item["call_id"] for item in calls]
    output_ids = [item["call_id"] for item in outputs]

    assert len(set(call_ids)) == expected_count
    assert output_ids == call_ids

    return [json.loads(item["output"]) for item in outputs]


def executed_ids(run):
    return [
        entry.args[0].call_id
        for entry in run.execute.call_args_list
    ]


def test_tool_budget_across_rounds(setup_run):
    run = setup_run([
        tool_response(1, 2, 3),
        tool_response(4, 5, 6),
        text_response(),
    ])

    # 失败的工具调用也必须消耗预算。
    run.execute.return_value = {
        "ok": False,
        "error": "模拟工具失败",
    }

    demo.main()

    assert executed_ids(run) == [
        f"call_{number}" for number in range(1, 7)
    ]

    # 第二轮请求中应已包含第一轮的全部工具结果。
    assert_matching_outputs(
        run.requests[1]["history"],
        expected_count=3,
    )

    history = assert_final_request(run, exploration_rounds=2)
    results = assert_matching_outputs(history, expected_count=6)
    assert all(result == run.execute.return_value for result in results)


def test_extra_batch_calls_rejected_with_matching_outputs(setup_run):
    run = setup_run([
        tool_response(*range(1, 9)),
        text_response(),
    ])

    demo.main()

    assert executed_ids(run) == [
        f"call_{number}" for number in range(1, 7)
    ]

    history = assert_final_request(run, exploration_rounds=1)
    results = assert_matching_outputs(history, expected_count=8)

    assert all(
        result == run.execute.return_value
        for result in results[:6]
    )

    for result in results[6:]:
        assert result["ok"] is False
        assert "预算已耗尽" in result["error"]
        assert "未执行" in result["error"]


def test_round_limit_triggers_final_summary(setup_run, capsys):
    run = setup_run([
        tool_response(1),
        tool_response(2),
        tool_response(3),
        tool_response(4),
        tool_response(5),
        text_response(),
    ])

    demo.main()

    # 工具预算尚余 1 次，但探索轮数已耗尽。
    assert executed_ids(run) == [
        f"call_{number}" for number in range(1, 6)
    ]

    history = assert_final_request(run, exploration_rounds=5)
    assert_matching_outputs(history, expected_count=5)

    output = capsys.readouterr().out
    assert "模型回答（预算耗尽后总结）" in output
    assert "测试总结：仅报告已确认的信息。" in output


def test_final_stage_tool_call_stopped_without_execution(setup_run):
    run = setup_run([
        tool_response(*range(1, 7)),
        tool_response(99),
    ])

    with pytest.raises(
        RuntimeError,
        match="最终总结阶段仍收到工具调用",
    ):
        demo.main()

    assert_final_request(run, exploration_rounds=1)

    # 总结响应里的 call_99 绝不能执行。
    assert executed_ids(run) == [
        f"call_{number}" for number in range(1, 7)
    ]
