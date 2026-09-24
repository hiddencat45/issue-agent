import json


class RepairPatchError(ValueError):
    """补丁结构不合法。"""


EDIT_KEYS = ("path", "old_text", "new_text")
SINGLE_PATCH_KEYS = ("path", "old_text", "new_text", "rationale")
MULTI_PATCH_KEYS = ("rationale", "edits")


def parse_repair_patch(text):
    """把模型输出解析为补丁对象；失败时抛出 RepairPatchError，不静默兜底。"""
    if not isinstance(text, str) or not text.strip():
        raise RepairPatchError("补丁必须是非空 JSON 文本")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RepairPatchError("补丁不是合法 JSON") from exc
    return validate_repair_patch(data)


def validate_edit(data):
    if not isinstance(data, dict) or set(data) != set(EDIT_KEYS):
        raise RepairPatchError("每处修改字段必须恰好为 path、old_text、new_text")
    path = data["path"]
    _validate_relative_path(path)
    old_text = data["old_text"]
    if not isinstance(old_text, str) or old_text == "":
        raise RepairPatchError("old_text 必须是非空字符串")
    new_text = data["new_text"]
    if not isinstance(new_text, str):
        raise RepairPatchError("new_text 必须是字符串")
    if old_text == new_text:
        raise RepairPatchError("new_text 与 old_text 相同，没有实际改动")
    return {
        "path": path,
        "old_text": old_text,
        "new_text": new_text,
    }


def validate_repair_patch(data):
    if not isinstance(data, dict):
        raise RepairPatchError("补丁必须是 JSON 对象")

    rationale = data.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise RepairPatchError("rationale 必须是非空字符串")

    if "edits" in data:
        edits = data["edits"]
        if not isinstance(edits, list) or not edits:
            raise RepairPatchError("edits 必须是非空数组")
        normalized = [validate_edit(item) for item in edits]
        allowed = set(MULTI_PATCH_KEYS)
        if len(normalized) == 1:
            allowed = set(MULTI_PATCH_KEYS) | set(EDIT_KEYS)
        if set(data) - allowed:
            raise RepairPatchError(
                "补丁必须是单处四字段，或恰好包含 rationale 与 edits"
            )
        if set(EDIT_KEYS) <= set(data) and (
            data["path"] != normalized[0]["path"]
            or data["old_text"] != normalized[0]["old_text"]
            or data["new_text"] != normalized[0]["new_text"]
        ):
            raise RepairPatchError("兼容字段必须与 edits 中唯一一处一致")
        return _with_single_compat(rationale.strip(), normalized)

    if set(data) != set(SINGLE_PATCH_KEYS):
        raise RepairPatchError(
            "补丁必须是单处四字段，或恰好包含 rationale 与 edits"
        )

    edit = validate_edit({
        "path": data["path"],
        "old_text": data["old_text"],
        "new_text": data["new_text"],
    })
    return _with_single_compat(rationale.strip(), [edit])


def patch_paths(patch):
    patch = validate_repair_patch(patch)
    paths = []
    for edit in patch["edits"]:
        if edit["path"] not in paths:
            paths.append(edit["path"])
    return paths


def _with_single_compat(rationale, edits):
    payload = {
        "rationale": rationale,
        "edits": edits,
    }
    if len(edits) == 1:
        payload["path"] = edits[0]["path"]
        payload["old_text"] = edits[0]["old_text"]
        payload["new_text"] = edits[0]["new_text"]
    return payload


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
