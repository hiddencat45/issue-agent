import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from app.repair_apply import apply_repair_patch
from app.repair_schema import RepairPatchError, parse_repair_patch, patch_paths
from app.tools.repository import RepositoryTools
from app.trace import read_trace
from app.trace_schema import TraceError
from app.triage_tools import execute_tool


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="按运行记录重放核对，不调用模型，不写仓库"
    )
    parser.add_argument("--workspace", required=True, help="目标仓库的绝对路径")
    parser.add_argument("--trace-file", required=True, help="记录 JSON 文件")
    return parser.parse_args(argv)


def require_workspace(raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("--workspace 必须是绝对路径")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError("--workspace 不存在或不是目录")
    return resolved


def replay_trace(workspace, trace):
    if trace["kind"] == "repair":
        return _replay_repair(workspace, trace)
    return _replay_tools(workspace, trace)


def _replay_tools(workspace, trace):
    repository = RepositoryTools(workspace)
    mismatches = []
    for index, event in enumerate(trace["events"]):
        call = SimpleNamespace(name=event["name"], arguments=event["arguments"])
        actual = execute_tool(call, repository)
        if actual != event["result"]:
            mismatches.append({
                "index": index,
                "name": event["name"],
                "expected": event["result"],
                "actual": actual,
            })
    return {
        "ok": not mismatches,
        "kind": trace["kind"],
        "mismatches": mismatches,
    }


def _replay_repair(workspace, trace):
    patch = parse_repair_patch(trace["issue_text"])
    recorded = trace["output"]
    if recorded.get("applied"):
        mismatches = []
        for index, edit in enumerate(patch["edits"]):
            target = workspace / edit["path"]
            if not target.is_file():
                actual = {
                    "ok": False,
                    "error": "目标文件不存在",
                    "path": edit["path"],
                }
            else:
                text = target.read_text(encoding="utf-8")
                if edit["new_text"] in text:
                    actual = {
                        "ok": True,
                        "path": edit["path"],
                        "applied": True,
                    }
                else:
                    actual = {
                        "ok": False,
                        "error": "文件中找不到 new_text，写入结果已变化",
                        "path": edit["path"],
                    }
            if not actual.get("ok"):
                mismatches.append({
                    "index": index,
                    "name": "repair_apply",
                    "expected": {
                        "ok": True,
                        "applied": True,
                        "path": edit["path"],
                    },
                    "actual": actual,
                })
        return {
            "ok": not mismatches,
            "kind": "repair",
            "mismatches": mismatches,
        }

    actual = apply_repair_patch(
        workspace,
        patch,
        allowed_paths=patch_paths(patch),
        dry_run=True,
    )
    if actual.get("applied"):
        raise RuntimeError("重放预演不得写入文件")
    mismatches = []
    if actual != recorded:
        mismatches.append({
            "index": 0,
            "name": "repair_apply",
            "expected": recorded,
            "actual": actual,
        })
    return {
        "ok": not mismatches,
        "kind": "repair",
        "mismatches": mismatches,
    }



def main(argv=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        workspace = require_workspace(args.workspace)
        trace = read_trace(args.trace_file)
        result = replay_trace(workspace, trace)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except (ValueError, RepairPatchError, TraceError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
