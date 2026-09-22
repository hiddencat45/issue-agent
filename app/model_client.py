import time


def request_response(
    client,
    history,
    *,
    tool_choice,
    tools,
    model,
    instructions,
):
    """向模型发起一次请求，处理流式事件，并返回已完成的响应。

    本模块不读取环境变量、不创建客户端、不持有业务提示词。
    client、model、tools、instructions 等依赖全部由调用方传入。
    """
    started = time.perf_counter()
    completed = None

    with client.responses.create(
        model=model,
        instructions=instructions,
        input=history,
        tools=tools,
        tool_choice=tool_choice,
        include=["reasoning.encrypted_content"],
        store=False,
        stream=True,
    ) as stream:
        for event in stream:
            if event.type == "response.completed":
                completed = event.response
            elif event.type == "response.failed":
                raise RuntimeError(
                    f"响应失败：{event.response.error}"
                )
            elif event.type == "error":
                raise RuntimeError(f"接口错误：{event.message}")

    print(
        f"本轮 API 耗时：{time.perf_counter() - started:.1f} 秒",
        flush=True,
    )

    if completed is None:
        raise RuntimeError("未收到完整响应")

    return completed
