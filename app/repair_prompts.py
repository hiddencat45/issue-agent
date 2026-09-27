REPAIR_PROPOSE_INSTRUCTIONS = """你是代码仓库的只读补丁提案助手。

任务：根据用户提供的 issue 全文，只使用三个只读工具探测目标仓库，提出一份可以交给人类批准的补丁 JSON。
你不能写文件、不能执行命令、不能声称已经修好。

必须遵守：
1. 只读。最终输出只是提案，不是已经应用的修改。
2. 先搜后读。提出补丁前，必须已经用 read_file 读过要改的每一个文件。
3. 每一处 old_text 必须是读到的原文子串，不得改写、不得凭记忆编造。
4. 每一处 old_text 应包含足够上下文，使其在对应文件中只出现一次。
5. 可以改同一文件的多处，也可以改多个已有文件；不要改无关文件，不要新建或删除文件。
6. 最终回答必须是且只是一个 JSON 对象，不要 Markdown，不要代码围栏，不要额外说明。
7. 如果用户消息里带了 pytest 输出，把它当作只读证据来修正补丁；仍然不要写文件、不要执行命令、不要声称已经修好。

可用工具：
- list_files：列出目录中允许读取的文件。必须提供 path，仓库根用 "."。
- search_code：按字面文本搜索内容。必须提供 query 和 path。
- read_file：按行读取文件。必须提供 path。

最终 JSON 只能包含这两个字段：
{
  "rationale": "为什么这样改",
  "edits": [
    {
      "path": "相对仓库根的 posix 路径",
      "old_text": "该文件中恰好出现一次的原文",
      "new_text": "替换后的文本"
    }
  ]
}

不要输出 severity、diff、命令或其他字段。
如果读到的信息不够提出可验证的补丁，不要编造 old_text。
"""


MAX_PYTEST_FEEDBACK_CHARS = 8_000


def format_pytest_feedback(pytest_result):
    passed = pytest_result.get("passed")
    returncode = pytest_result.get("returncode")
    output = pytest_result.get("output") or ""
    if not output:
        stdout = pytest_result.get("stdout") or ""
        stderr = pytest_result.get("stderr") or ""
        output = "\n".join(part for part in (stdout, stderr) if part)
    if len(output) > MAX_PYTEST_FEEDBACK_CHARS:
        output = output[:MAX_PYTEST_FEEDBACK_CHARS] + "\n...[truncated]"
    return (
        "下面是最近一次 python -m pytest -q 的结果，只作只读上下文。"
        "不要因此直接改仓库，只给出下一版补丁 JSON。\n"
        f"passed: {passed}\n"
        f"returncode: {returncode}\n"
        f"{output}"
    )


def issue_user_message(issue_text, pytest_result=None):
    message = (
        "请对下面的 issue 提出一份只读补丁 JSON。"
        "不要修改仓库，只输出提案。\n\n"
        f"{issue_text}"
    )
    if pytest_result is None:
        return message
    return message + "\n\n" + format_pytest_feedback(pytest_result)
