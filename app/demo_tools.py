import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.tools.repository import RepositoryTools


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def show(title: str, result: dict):
    print(f"\n=== {title} ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    target_path = Path(
        os.getenv("TARGET_REPO_PATH", "../target-repo")
    ).expanduser()

    if not target_path.is_absolute():
        target_path = PROJECT_ROOT / target_path

    tools = RepositoryTools(target_path)

    show("1. 查看仓库", tools.list_files())

    show(
        "2. 搜索分页函数",
        tools.search_code("def paginate"),
    )

    show(
        "3. 读取分页代码",
        tools.read_file(
            "text_utils/pagination.py",
            start_line=1,
            end_line=50,
        ),
    )

    show(
        "4. 验证越界拒绝",
        tools.read_file("../issue-agent/.env"),
    )


if __name__ == "__main__":
    main()
