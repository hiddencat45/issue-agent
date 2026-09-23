import argparse
import json
import sys

from app.trace import read_trace
from app.trace_schema import TraceError


def parse_args(argv):
    parser = argparse.ArgumentParser(description="查看一次运行记录，不调用模型，不写仓库")
    parser.add_argument("--trace-file", required=True, help="记录 JSON 文件")
    return parser.parse_args(argv)


def main(argv=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        payload = read_trace(args.trace_file)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except (TraceError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
