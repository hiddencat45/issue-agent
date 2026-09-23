import json


TOOLS = [
    {
        "type": "function",
        "name": "list_files",
        "description": (
            "列出目标仓库中允许读取的文本文件，包含子目录。"
            "path 必须是相对仓库根的目录路径，根目录使用 '.'。"
            "limit 可选，默认 100，范围 1 到 500。"
            "truncated 为 true 时表示结果不完整。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对仓库根的目录路径，例如 '.' 或 'src'。",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回的文件数，默认 100，范围 1 到 500。",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_code",
        "description": (
            "在目标仓库中按字面文本搜索文件内容，忽略大小写，不支持正则。"
            "query 是搜索关键词。"
            "path 必须是相对仓库根的目录路径，根目录使用 '.'。"
            "limit 可选，默认 30，范围 1 到 100。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "非空搜索关键词，最多 200 个字符。",
                },
                "path": {
                    "type": "string",
                    "description": "相对仓库根的目录路径，例如 '.'。",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回的匹配条数，默认 30，范围 1 到 100。",
                },
            },
            "required": ["query", "path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "read_file",
        "description": (
            "读取目标仓库中指定文件的连续行，行号从 1 开始。"
            "path 必须是相对仓库根的文件路径。"
            "start_line 与 end_line 可选，默认 1 到 100。"
            "单次最多读取 200 行。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对仓库根的文件路径，例如 'src/example.py'。",
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号，从 1 开始，默认 1。",
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号，不能小于起始行，默认 100。",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]


_SPECS = {
    "list_files": {
        "required": {"path"},
        "optional": {"limit"},
        "method": "list_files",
    },
    "search_code": {
        "required": {"query", "path"},
        "optional": {"limit"},
        "method": "search_code",
    },
    "read_file": {
        "required": {"path"},
        "optional": {"start_line", "end_line"},
        "method": "read_file",
    },
}


def _error(message):
    return {"ok": False, "error": message}


def execute_tool(call, repository):
    """把模型工具调用转发给已有的 RepositoryTools，不创建仓库对象。"""
    spec = _SPECS.get(call.name)

    if spec is None:
        return _error("不支持的工具")

    try:
        args = json.loads(call.arguments)
    except (TypeError, json.JSONDecodeError):
        return _error("arguments 不是合法 JSON")

    if not isinstance(args, dict):
        return _error("arguments 键集不符")

    keys = set(args)
    required = spec["required"]
    allowed = required | spec["optional"]

    if not required <= keys or not keys <= allowed:
        return _error("arguments 键集不符")

    method = getattr(repository, spec["method"])
    return method(**args)
