from app.repair_prompts import REPAIR_PROPOSE_INSTRUCTIONS, issue_user_message


def test_instructions_require_patch_fields_and_json_only():
    text = REPAIR_PROPOSE_INSTRUCTIONS
    assert "old_text" in text
    assert "new_text" in text
    assert "rationale" in text
    assert "只是一个 JSON 对象" in text
    assert "不能写文件" in text


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
