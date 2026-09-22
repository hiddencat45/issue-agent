import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def main():
    configured_path = Path(
        os.getenv("TARGET_REPO_PATH", "../target-repo")
    ).expanduser()

    if not configured_path.is_absolute():
        configured_path = PROJECT_ROOT / configured_path

    target_repo = configured_path.resolve()

    if not target_repo.is_dir():
        raise FileNotFoundError(
            f"目标仓库不存在或不是目录：{target_repo}"
        )

    print("Issue Agent 初始化成功")
    print(f"目标仓库：{target_repo}")


if __name__ == "__main__":
    main()
