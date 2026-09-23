from pathlib import Path

from app.repair_schema import RepairPatchError, validate_repair_patch
from app.tools.repository import RepositoryTools


def _error(message):
    return {"ok": False, "error": message}


def _safe_existing_file(root, relative_path):
    relative = Path(relative_path)
    current = root

    for part in relative.parts:
        if part.startswith(".") or part in RepositoryTools.EXCLUDED_DIRS:
            raise RepairPatchError("该路径不允许访问")
        current = current / part
        if current.is_symlink():
            raise RepairPatchError("不允许访问符号链接")

    resolved = current.resolve()
    if not resolved.is_relative_to(root):
        raise RepairPatchError("路径超出仓库范围")
    if not resolved.exists():
        raise RepairPatchError("路径不存在")
    if resolved.is_symlink() or not resolved.is_file():
        raise RepairPatchError("目标必须是普通文件")
    if resolved.suffix.lower() not in RepositoryTools.ALLOWED_SUFFIXES:
        raise RepairPatchError("文件类型不支持")
    if resolved.stat().st_size > RepositoryTools.MAX_FILE_BYTES:
        raise RepairPatchError("文件过大")
    return resolved


def apply_repair_patch(root, patch, *, allowed_paths, dry_run=True):
    """在允许列表内替换已有文件中恰好出现一次的原文。"""
    try:
        patch = validate_repair_patch(patch)
        root = Path(root).resolve()
        if not root.is_dir():
            raise RepairPatchError("工作区不存在或不是目录")

        allowed = {item.replace("\\", "/") for item in allowed_paths}
        if patch["path"] not in allowed:
            raise RepairPatchError("该路径未被 --allow-write 授权")

        target = _safe_existing_file(root, patch["path"])
        original = target.read_text(encoding="utf-8")
        count = original.count(patch["old_text"])
        if count != 1:
            raise RepairPatchError(
                "old_text 必须在文件中恰好出现一次，"
                f"实际出现 {count} 次"
            )

        updated = original.replace(patch["old_text"], patch["new_text"], 1)
        encoded = updated.encode("utf-8")
        if len(encoded) > RepositoryTools.MAX_FILE_BYTES:
            raise RepairPatchError("修改后的文件过大")

        result = {
            "ok": True,
            "path": patch["path"],
            "dry_run": dry_run,
            "applied": not dry_run,
            "rationale": patch["rationale"],
            "bytes_before": len(original.encode("utf-8")),
            "bytes_after": len(encoded),
        }

        if not dry_run:
            target.write_text(updated, encoding="utf-8")

        return result

    except (RepairPatchError, ValueError, OSError, UnicodeError) as exc:
        return _error(str(exc))
