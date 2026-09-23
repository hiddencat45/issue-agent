import argparse
import json
import sys
from pathlib import Path

from app.repair_apply import apply_repair_patch
from app.repair_schema import RepairPatchError
from app.trace import write_trace


def parse_args(argv):
    parser = argparse.ArgumentParser(description="受控修复：预演或应用一份补丁")
    parser.add_argument("--workspace", required=True, help="目标仓库的绝对路径")
    parser.add_argument("--patch-file", required=True, help="补丁 JSON 文件")
    parser.add_argument(
        "--allow-write",
        action="append",
        default=[],
        help="允许写入的相对路径，可重复",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写入文件；省略时只预演",
    )
    parser.add_argument(
        "--trace-out",
        required=False,
        help="可选，将本次预演或写入结果写入运行记录",
    )
    return parser.parse_args(argv)


def require_workspace(raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("--workspace 必须是绝对路径")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError("--workspace 不存在或不是目录")
    return resolved


def load_patch(raw_path):
    path = Path(raw_path)
    if not path.is_file():
        raise ValueError("--patch-file 不存在或不是文件")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("--patch-file 不能为空")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("补丁不是合法 JSON") from exc
    return data


def main(argv=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        if not args.allow_write:
            raise ValueError("至少提供一个 --allow-write")

        workspace = require_workspace(args.workspace)
        patch = load_patch(args.patch_file)
        result = apply_repair_patch(
            workspace,
            patch,
            allowed_paths=args.allow_write,
            dry_run=not args.apply,
        )
        if args.trace_out:
            write_trace(
                args.trace_out,
                kind="repair",
                issue_text=json.dumps(patch, ensure_ascii=False),
                events=[],
                output=result,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    except (ValueError, RepairPatchError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
