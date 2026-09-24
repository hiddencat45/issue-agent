import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.agent import run_agent
from app import model_client
from app.api_retry import call_with_retry
from app.triage_prompts import TRIAGE_INSTRUCTIONS, issue_user_message
from app.triage_schema import TriageReportError, parse_triage_report
from app.triage_tools import TOOLS, execute_tool
from app.trace import TraceRecorder, write_trace
from app.tools.repository import RepositoryTools


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv):
    parser = argparse.ArgumentParser(description="只读 Issue 分诊")
    parser.add_argument("--workspace", required=True, help="目标仓库的绝对路径")
    parser.add_argument("--issue-file", required=True, help="包含 issue 全文的文件")
    parser.add_argument("--out", required=False, help="可选，将报告写入该文件")
    parser.add_argument(
        "--trace-out",
        required=False,
        help="可选，将本次工具调用与报告写入运行记录",
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
                instructions=TRIAGE_INSTRUCTIONS,
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


def collect_report(
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
    return parse_triage_report(answer)


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
            return collect_report(
                issue_text,
                request_response=make_request_response(client),
                execute_tool_fn=execute,
            )

    return runner


def emit_report(report, out_path=None):
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if out_path:
        Path(out_path).write_text(payload + "\n", encoding="utf-8")


def main(argv=None, *, runner_factory=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        workspace = require_workspace(args.workspace)
        issue_text = load_issue_text(args.issue_file)
        recorder = TraceRecorder()
        factory = runner_factory or (
            lambda item: default_runner_factory(item, recorder=recorder)
        )
        report = factory(workspace)(issue_text)
        if args.trace_out:
            write_trace(
                args.trace_out,
                kind="triage",
                issue_text=issue_text,
                events=recorder.events,
                output=report,
            )
        emit_report(report, args.out)
        return 0

    except (ValueError, TriageReportError, FileNotFoundError, OSError, KeyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
