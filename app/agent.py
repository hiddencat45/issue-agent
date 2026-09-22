import json


def run_agent(
    history,
    *,
    request_response,
    execute_tool,
    max_exploration_rounds=5,
    max_tool_calls=6,
):
    """运行探索与总结循环，原地更新 history，并返回最终回答。

    request_response(history, tool_choice=...) 负责请求模型。
    execute_tool(call) 负责执行工具，并返回可 JSON 序列化的结果。

    本模块不初始化客户端、不读取环境变量、不直接访问文件。
    """
    tool_calls_used = 0

    # 探索阶段：由模型自主选择是否调用工具。
    for turn in range(max_exploration_rounds):
        print(
            f"\n开始探索第 {turn + 1}/"
            f"{max_exploration_rounds} 轮请求……"
            f"已执行工具 {tool_calls_used}/{max_tool_calls} 次",
            flush=True,
        )

        response = request_response(history, tool_choice="auto")

        history.extend(
            item.model_dump(exclude_none=True)
            for item in response.output
        )

        calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        if not calls:
            if not response.output_text:
                raise RuntimeError("未收到文本回答")

            print("\n模型回答：")
            print(response.output_text)
            return response.output_text

        for call in calls:
            # 同一轮可能返回多个调用，逐个检查预算。
            if tool_calls_used >= max_tool_calls:
                result = {
                    "ok": False,
                    "error": "工具调用预算已耗尽，此调用未执行。",
                }
                print(
                    f"预算拦截：{call.name}，未执行",
                    flush=True,
                )
            else:
                # 失败的工具调用也计入预算。
                tool_calls_used += 1
                print(
                    f"工具请求 [{tool_calls_used}/"
                    f"{max_tool_calls}]："
                    f"{call.name} {call.arguments}",
                    flush=True,
                )
                result = execute_tool(call)

            # 即使被预算拦截，也为每个调用返回对应结果。
            history.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(
                        result, ensure_ascii=False
                    ),
                }
            )

        if tool_calls_used >= max_tool_calls:
            break

    # 工具次数或探索轮数耗尽，额外进行一次只总结请求。
    print(
        "\n探索预算已耗尽，开始最终总结请求"
        "（禁止调用工具）……",
        flush=True,
    )

    history.append(
        {
            "role": "developer",
            "content": (
                "探索预算已耗尽，不得再调用工具。"
                "请根据已有工具结果回答原任务。"
                "如果信息不足，明确列出未完成部分及原因，"
                "不要猜测未读取的文件内容。"
            ),
        }
    )

    response = request_response(history, tool_choice="none")

    if any(
        item.type == "function_call"
        for item in response.output
    ):
        raise RuntimeError(
            "最终总结阶段仍收到工具调用；已停止，不执行"
        )

    if not response.output_text:
        raise RuntimeError("最终总结阶段未收到文本回答")

    print("\n模型回答（预算耗尽后总结）：")
    print(response.output_text)
    return response.output_text
