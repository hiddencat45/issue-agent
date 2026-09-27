from pathlib import Path

from app.repair_schema import RepairPatchError, patch_paths, validate_repair_patch
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


def apply_repair_patch(root, patch, *, allowed_paths, dry_run=True, originals_out=None):
    """在允许列表内替换已有文件中恰好出现一次的原文。多处修改先全部算完再写。"""
    try:
        patch = validate_repair_patch(patch)
        root = Path(root).resolve()
        if not root.is_dir():
            raise RepairPatchError("工作区不存在或不是目录")

        allowed = {item.replace("\\", "/") for item in allowed_paths}
        paths = patch_paths(patch)
        missing = [path for path in paths if path not in allowed]
        if missing:
            raise RepairPatchError(
                "该路径未被 --allow-write 授权：" + ", ".join(missing)
            )

        originals = {}
        buffers = {}
        targets = {}
        for path in paths:
            target = _safe_existing_file(root, path)
            text = target.read_text(encoding="utf-8")
            originals[path] = text
            buffers[path] = text
            targets[path] = target
        if originals_out is not None:
            originals_out.clear()
            originals_out.update(originals)

        for edit in patch["edits"]:
            path = edit["path"]
            count = buffers[path].count(edit["old_text"])
            if count != 1:
                raise RepairPatchError(
                    f"{path} 中 old_text 必须恰好出现一次，实际出现 {count} 次"
                )
            buffers[path] = buffers[path].replace(
                edit["old_text"],
                edit["new_text"],
                1,
            )
            encoded = buffers[path].encode("utf-8")
            if len(encoded) > RepositoryTools.MAX_FILE_BYTES:
                raise RepairPatchError(f"{path} 修改后的文件过大")

        files = {
            path: {
                "bytes_before": len(originals[path].encode("utf-8")),
                "bytes_after": len(buffers[path].encode("utf-8")),
            }
            for path in paths
        }
        result = {
            "ok": True,
            "dry_run": dry_run,
            "applied": not dry_run,
            "rationale": patch["rationale"],
            "paths": paths,
            "edits": len(patch["edits"]),
            "files": files,
        }
        if len(paths) == 1:
            path = paths[0]
            result["path"] = path
            result["bytes_before"] = files[path]["bytes_before"]
            result["bytes_after"] = files[path]["bytes_after"]

        if not dry_run:
            for path in paths:
                targets[path].write_text(buffers[path], encoding="utf-8")

        return result

    except (RepairPatchError, ValueError, OSError, UnicodeError) as exc:
        return _error(str(exc))


def restore_files(root, originals):
    """Write snapshotted texts back. Does not create or delete files."""
    root = Path(root).resolve()
    restored = []
    try:
        if not root.is_dir():
            raise RepairPatchError("工作区不存在或不是目录")
        if not originals:
            raise RepairPatchError("没有可回滚的原文")
        for path, text in originals.items():
            target = _safe_existing_file(root, path)
            target.write_text(text, encoding="utf-8")
            restored.append(path)
        return {"ok": True, "restored": restored}
    except (RepairPatchError, ValueError, OSError, UnicodeError) as exc:
        return {"ok": False, "error": str(exc), "restored": restored}
