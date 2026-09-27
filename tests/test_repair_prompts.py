from app.repair_prompts import REPAIR_PROPOSE_INSTRUCTIONS, issue_user_message


def test_instructions_require_patch_fields_and_json_only():
    text = REPAIR_PROPOSE_INSTRUCTIONS
    assert "old_text" in text
    assert "new_text" in text
    assert "rationale" in text
    assert "edits" in text
    assert "只是一个 JSON 对象" in text
    assert "不能写文件" in text
    assert "每一个文件" in text
    assert "一次只改一个文件" not in text


def test_instructions_name_readonly_tools():
    text = REPAIR_PROPOSE_INSTRUCTIONS
    assert "list_files" in text
    assert "search_code" in text
    assert "read_file" in text
    assert "先搜后读" in text


def test_issue_user_message_includes_raw_issue():
    issue = "format_note 不应再去掉空格"
    message = issue_user_message(issue)
    assert issue in message
    assert "不要修改仓库" in message


def test_instructions_mention_pytest_feedback():
    assert "pytest" in REPAIR_PROPOSE_INSTRUCTIONS


def test_issue_user_message_appends_pytest_output():
    issue = "keep spaces"
    feedback = {
        "passed": False,
        "returncode": 1,
        "output": "assert format_note(' a ') == ' a '",
    }
    message = issue_user_message(issue, pytest_result=feedback)
    assert issue in message
    assert "assert format_note" in message
    assert "returncode: 1" in message
