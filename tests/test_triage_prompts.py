from app.triage_prompts import TRIAGE_INSTRUCTIONS, issue_user_message


def test_instructions_require_four_fields_and_json_only():
    text = TRIAGE_INSTRUCTIONS

    assert "issue_summary" in text
    assert "evidence" in text
    assert "candidate_files" in text
    assert "uncertainties" in text
    assert "只是一个 JSON 对象" in text
    assert "severity" in text
    assert "可能/大概" in text


def test_instructions_name_the_three_tools():
    text = TRIAGE_INSTRUCTIONS

    assert "list_files" in text
    assert "search_code" in text
    assert "read_file" in text
    assert "先搜后读" in text
    assert "read_file" in text


def test_issue_user_message_includes_raw_issue():
    issue = "paginate 在 page=0 时没有报错"
    message = issue_user_message(issue)

    assert issue in message
    assert "四格 JSON" in message
    assert message.strip() != issue


def test_instructions_require_one_quote_per_line():
    text = TRIAGE_INSTRUCTIONS
    assert "一条证据只对应文件中的一行" in text
    assert "不得包含换行" in text
    assert "拆成多条 evidence" in text


def test_instructions_cap_search_and_require_read():
    text = TRIAGE_INSTRUCTIONS
    assert "search_code 本轮最多 2 次" in text
    assert "不能把 search_code 的匹配行直接当 quote" in text
    assert "至少留 2 次给 read_file" in text


def test_user_message_asks_to_read_after_search():
    message = issue_user_message("x")
    assert "read_file" in message
    assert "先搜索定位" in message
