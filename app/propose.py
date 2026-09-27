import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.agent import run_agent
from app import model_client
from app.api_retry import call_with_retry
from app.repair_apply import apply_repair_patch
from app.repair_prompts import (
    REPAIR_PROPOSE_INSTRUCTIONS,
    format_pytest_feedback,
    issue_user_message,
)
from app.run_pytest import load_pytest_result
from app.repair_schema import RepairPatchError, parse_repair_patch, patch_paths
from app.trace import TraceRecorder, write_trace
from app.triage_tools import TOOLS, execute_tool
from app.tools.repository import RepositoryTools
from app.github_issue import GitHubHTTPError, add_issue_source_args, load_issue_text_from_args


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv):
    parser = argparse.ArgumentParser(description="只读提出受控修复补丁")
    parser.add_argument("--workspace", required=True, help="目标仓库的绝对路径")
    add_issue_source_args(parser)
    parser.add_argument("--out", required=False, help="可选，将补丁写入该文件")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="对提案做一次预演，确认 old_text 能对上；绝不写入",
    )
    parser.add_argument(
        "--pytest-file",
        required=False,
        help="可选：上一次 pytest.json，作为只读上下文再提一版补丁",
    )
    parser.add_argument(
        "--trace-out",
        required=False,
        help="可选，将本次工具调用与补丁写入运行记录",
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


def load_issue_text(raw_path):
    path = Path(raw_path)
    if not path.is_file():
        raise ValueError("--issue-file 不存在或不是文件")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("--issue-file 不能为空")
    return text


def make_request_response(client):
    def request(history, *, tool_choice):
        def once():
            return model_client.request_response(
                client,
                history,
                tool_choice=tool_choice,
                tools=TOOLS,
                model=os.environ["OPENAI_MODEL"],
                instructions=REPAIR_PROPOSE_INSTRUCTIONS,
            )

        def on_retry(tried, remaining, exc):
            print(
                f"模型请求失败，正在重试（{tried}/{tried + remaining}）：{exc}",
                flush=True,
            )

        return call_with_retry(
            once,
            attempts=2,
            delay_seconds=1.0,
            on_retry=on_retry,
        )

    return request


def make_execute_tool(repository):
    def bound(call):
        return execute_tool(call, repository)

    return bound


def collect_patch(
    issue_text,
    *,
    request_response,
    execute_tool_fn,
    run_agent_fn=run_agent,
):
    history = [
        {
            "role": "user",
            "content": issue_user_message(issue_text),
        }
    ]
    answer = run_agent_fn(
        history,
        request_response=request_response,
        execute_tool=execute_tool_fn,
        max_exploration_rounds=5,
        max_tool_calls=6,
    )
    return parse_repair_patch(answer)


def default_runner_factory(workspace, recorder=None):
    load_dotenv(PROJECT_ROOT / ".env")
    from openai import OpenAI

    repository = RepositoryTools(workspace)
    execute = make_execute_tool(repository)
    if recorder is not None:
        execute = recorder.wrap_execute(execute)

    def runner(issue_text):
        with OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ["OPENAI_BASE_URL"],
            timeout=180.0,
            max_retries=0,
        ) as client:
            return collect_patch(
                issue_text,
                request_response=make_request_response(client),
                execute_tool_fn=execute,
            )

    return runner


def emit_patch(patch, out_path=None):
    payload = json.dumps(patch, ensure_ascii=False, indent=2)
    print(payload)
    if out_path:
        Path(out_path).write_text(payload + "\n", encoding="utf-8")


def verify_patch(workspace, patch):
    result = apply_repair_patch(
        workspace,
        patch,
        allowed_paths=patch_paths(patch),
        dry_run=True,
    )
    if not result.get("ok"):
        raise ValueError(result.get("error") or "补丁预演失败")
    if result.get("applied"):
        raise RuntimeError("预演阶段不得写入文件")
    return result


def main(argv=None, *, runner_factory=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        workspace = require_workspace(args.workspace)
        issue_text = load_issue_text_from_args(args)
        if args.pytest_file:
            issue_text = (
                issue_text
                + "\n\n"
                + format_pytest_feedback(load_pytest_result(args.pytest_file))
            )
        recorder = TraceRecorder()
        factory = runner_factory or (
            lambda item: default_runner_factory(item, recorder=recorder)
        )
        patch = factory(workspace)(issue_text)
        if args.verify:
            verify_patch(workspace, patch)
        if args.trace_out:
            write_trace(
                args.trace_out,
                kind="propose",
                issue_text=issue_text,
                events=recorder.events,
                output=patch,
            )
        emit_patch(patch, args.out)
        return 0

    except (ValueError, GitHubHTTPError, RepairPatchError, FileNotFoundError, OSError, KeyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
