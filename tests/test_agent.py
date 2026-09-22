import json
from types import SimpleNamespace

from app.agent import run_agent


class FakeItem:
    def __init__(self, **data):
        self.__dict__.update(data)

    def model_dump(self, exclude_none=True):
        return {
            key: value
            for key, value in vars(self).items()
            if not exclude_none or value is not None
        }


def test_direct_answer_without_tools():
    history = [{"role": "user", "content": "你好"}]
    requested_choices = []

    message = FakeItem(
        type="message",
        role="assistant",
        content=[
            {"type": "output_text", "text": "你好。"}
        ],
    )

    def request(history_arg, *, tool_choice):
        assert history_arg is history
        requested_choices.append(tool_choice)
        return SimpleNamespace(
            output=[message],
            output_text="你好。",
        )

    def execute(call):
        raise AssertionError("直接回答不应执行工具")

    answer = run_agent(
        history,
        request_response=request,
        execute_tool=execute,
    )

    assert answer == "你好。"
    assert requested_choices == ["auto"]
    assert history[-1] == message.model_dump()


def test_failed_tool_counts_and_extra_call_is_blocked():
    history = [{"role": "user", "content": "读取项目说明"}]
    requested_choices = []
    executed_ids = []

    calls = [
        FakeItem(
            type="function_call",
            name="read_workspace_file",
            arguments='{"path": "README.md"}',
            call_id=call_id,
        )
        for call_id in ("call_1", "call_2")
    ]

    def request(history_arg, *, tool_choice):
        assert history_arg is history
        requested_choices.append(tool_choice)

        if len(requested_choices) == 1:
            assert tool_choice == "auto"
            return SimpleNamespace(
                output=calls,
                output_text="",
            )

        assert len(requested_choices) == 2
        assert tool_choice == "none"
        assert history_arg[-1]["role"] == "developer"
        assert "预算已耗尽" in history_arg[-1]["content"]

        outputs = [
            item
            for item in history_arg
            if item.get("type") == "function_call_output"
        ]

        assert [item["call_id"] for item in outputs] == [
            "call_1",
            "call_2",
        ]

        first_result = json.loads(outputs[0]["output"])
        second_result = json.loads(outputs[1]["output"])

        assert first_result == {
            "ok": False,
            "error": "模拟读取失败",
        }
        assert second_result["ok"] is False
        assert "此调用未执行" in second_result["error"]

        return SimpleNamespace(
            output=[],
            output_text="读取失败，预算已耗尽，无法判断用途。",
        )

    def execute(call):
        executed_ids.append(call.call_id)
        return {"ok": False, "error": "模拟读取失败"}

    answer = run_agent(
        history,
        request_response=request,
        execute_tool=execute,
        max_tool_calls=1,
    )

    assert executed_ids == ["call_1"]
    assert requested_choices == ["auto", "none"]
    assert answer == "读取失败，预算已耗尽，无法判断用途。"
