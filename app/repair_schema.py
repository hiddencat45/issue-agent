class RepairPatchError(ValueError):
    """补丁结构不合法。"""


PATCH_KEYS = ("path", "old_text", "new_text", "rationale")


def validate_repair_patch(data):
    if not isinstance(data, dict):
        raise RepairPatchError("补丁必须是 JSON 对象")

    if set(data) != set(PATCH_KEYS):
        raise RepairPatchError("补丁字段必须恰好为 path、old_text、new_text、rationale")

    path = data["path"]
    _validate_relative_path(path)

    old_text = data["old_text"]
    if not isinstance(old_text, str) or old_text == "":
        raise RepairPatchError("old_text 必须是非空字符串")

    new_text = data["new_text"]
    if not isinstance(new_text, str):
        raise RepairPatchError("new_text 必须是字符串")

    rationale = data["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise RepairPatchError("rationale 必须是非空字符串")

    if old_text == new_text:
        raise RepairPatchError("new_text 与 old_text 相同，没有实际改动")

    return {
        "path": path,
        "old_text": old_text,
        "new_text": new_text,
        "rationale": rationale.strip(),
    }


def _validate_relative_path(path):
    if not isinstance(path, str) or not path.strip():
        raise RepairPatchError("path 必须是非空相对路径")

    if "\\" in path:
        raise RepairPatchError("path 必须使用 posix 相对路径")

    if path.startswith("/"):
        raise RepairPatchError("path 必须是相对仓库根的文件路径")

    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise RepairPatchError("path 不允许空段、'.' 或 '..'")

    if any(part.startswith(".") for part in parts):
        raise RepairPatchError("path 不允许隐藏路径")
