import pytest

from app.repair_schema import RepairPatchError, parse_repair_patch, validate_repair_patch


def test_valid_patch_is_accepted():
    patch = {
        "path": "notes.py",
        "old_text": "return text.strip()",
        "new_text": "return text.rstrip()",
        "rationale": "只去掉右侧空格",
    }
    assert validate_repair_patch(patch)["path"] == "notes.py"


def test_extra_field_is_rejected():
    data = {
        "path": "notes.py",
        "old_text": "a",
        "new_text": "b",
        "rationale": "改",
        "shell": "rm -rf /",
    }
    with pytest.raises(RepairPatchError, match="恰好"):
        validate_repair_patch(data)


def test_parent_path_is_rejected():
    data = {
        "path": "../secrets.py",
        "old_text": "a",
        "new_text": "b",
        "rationale": "越界",
    }
    with pytest.raises(RepairPatchError, match=r"\.\."):
        validate_repair_patch(data)


def test_identical_text_is_rejected():
    data = {
        "path": "notes.py",
        "old_text": "same",
        "new_text": "same",
        "rationale": "空改动",
    }
    with pytest.raises(RepairPatchError, match="没有实际改动"):
        validate_repair_patch(data)


def test_parse_valid_json_text():
    raw = (
        '{"path": "notes.py", "old_text": "a",'
        ' "new_text": "b", "rationale": "改"}'
    )
    parsed = parse_repair_patch(raw)
    assert parsed["path"] == "notes.py"


def test_parse_non_json_is_rejected():
    import pytest
    with pytest.raises(RepairPatchError, match="合法 JSON"):
        parse_repair_patch("不是 JSON")
