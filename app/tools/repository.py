import os
from pathlib import Path


class RepositoryTools:
    # 第一版只读取明确允许的文本类型。
    ALLOWED_SUFFIXES = {
        ".py",
        ".md",
        ".toml",
        ".txt",
        ".json",
        ".yml",
        ".yaml",
        ".ini",
        ".cfg",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".rs",
        ".go",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".html",
        ".css",
        ".sh",
        ".ps1",
    }

    EXCLUDED_DIRS = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "logs",
    }

    MAX_FILE_BYTES = 200_000

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

        if not self.root.is_dir():
            raise ValueError(f"仓库目录不存在：{self.root}")

    def _safe_path(self, relative_path: str) -> Path:
        """校验相对路径，禁止越界、隐藏路径和符号链接。"""
        relative = Path(relative_path)

        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("只允许仓库内的相对路径，不允许使用 ..")

        current = self.root

        for part in relative.parts:
            if part.startswith(".") or part in self.EXCLUDED_DIRS:
                raise ValueError("该路径不允许访问")

            current = current / part

            if current.is_symlink():
                raise ValueError("不允许访问符号链接")

        resolved = current.resolve()

        if not resolved.is_relative_to(self.root):
            raise ValueError("路径超出仓库范围")

        if not resolved.exists():
            raise ValueError("路径不存在")

        return resolved

    def _readable_file(self, path: Path) -> bool:
        """判断文件是否属于允许读取的范围。"""
        return (
            path.is_file()
            and not path.is_symlink()
            and not path.name.startswith(".")
            and path.suffix.lower() in self.ALLOWED_SUFFIXES
            and path.stat().st_size <= self.MAX_FILE_BYTES
        )

    def _iter_files(self, directory: Path):
        """遍历允许读取的文件，不进入排除目录。"""
        for current, dirs, files in os.walk(directory, followlinks=False):
            current_path = Path(current)

            dirs[:] = sorted(
                name
                for name in dirs
                if not name.startswith(".")
                and name not in self.EXCLUDED_DIRS
                and not (current_path / name).is_symlink()
            )

            for name in sorted(files):
                file_path = current_path / name

                if self._readable_file(file_path):
                    yield file_path

    @staticmethod
    def _error(message: str) -> dict:
        return {"ok": False, "error": message}

    def list_files(self, path: str = ".", limit: int = 100) -> dict:
        """列出目录中的可读文件，包含子目录。"""
        try:
            if not 1 <= limit <= 500:
                raise ValueError("limit 必须在 1 到 500 之间")

            directory = self._safe_path(path)

            if not directory.is_dir():
                raise ValueError("path 必须是目录")

            files = []
            truncated = False

            for file_path in self._iter_files(directory):
                if len(files) >= limit:
                    truncated = True
                    break

                files.append(file_path.relative_to(self.root).as_posix())

            return {
                "ok": True,
                "files": files,
                "truncated": truncated,
            }

        except (ValueError, OSError) as exc:
            return self._error(str(exc))

    def search_code(
        self,
        query: str,
        path: str = ".",
        limit: int = 30,
    ) -> dict:
        """按字面文本搜索，忽略大小写；第一版不支持正则表达式。"""
        try:
            if not query.strip():
                raise ValueError("搜索关键词不能为空")

            if len(query) > 200:
                raise ValueError("搜索关键词过长")

            if not 1 <= limit <= 100:
                raise ValueError("limit 必须在 1 到 100 之间")

            directory = self._safe_path(path)

            if not directory.is_dir():
                raise ValueError("path 必须是目录")

            matches = []
            skipped_files = []
            query_lower = query.lower()

            for file_path in self._iter_files(directory):
                relative = file_path.relative_to(self.root).as_posix()

                try:
                    text = file_path.read_text(encoding="utf-8")
                except (UnicodeError, OSError):
                    skipped_files.append(relative)
                    continue

                for line_number, line in enumerate(text.splitlines(), 1):
                    if query_lower not in line.lower():
                        continue

                    if len(matches) >= limit:
                        return {
                            "ok": True,
                            "matches": matches,
                            "truncated": True,
                            "skipped_files": skipped_files,
                        }

                    matches.append({
                        "path": relative,
                        "line": line_number,
                        "text": line[:500],
                        "text_truncated": len(line) > 500,
                    })

            return {
                "ok": True,
                "matches": matches,
                "truncated": False,
                "skipped_files": skipped_files,
            }

        except (ValueError, OSError) as exc:
            return self._error(str(exc))

    def read_file(
        self,
        path: str,
        start_line: int = 1,
        end_line: int = 100,
    ) -> dict:
        """读取指定文件的连续行，行号从 1 开始。"""
        try:
            if start_line < 1 or end_line < start_line:
                raise ValueError("行号必须从 1 开始，结束行不能小于开始行")

            if end_line - start_line + 1 > 200:
                raise ValueError("单次最多读取 200 行")

            file_path = self._safe_path(path)

            if not self._readable_file(file_path):
                raise ValueError("文件类型不支持、文件过大或不是普通文件")

            lines = file_path.read_text(encoding="utf-8").splitlines()

            if lines and start_line > len(lines):
                raise ValueError("开始行超出文件范围")

            selected = [
                {
                    "line": index + 1,
                    "text": lines[index][:500],
                    "text_truncated": len(lines[index]) > 500,
                }
                for index in range(
                    start_line - 1,
                    min(end_line, len(lines)),
                )
            ]

            return {
                "ok": True,
                "path": file_path.relative_to(self.root).as_posix(),
                "total_lines": len(lines),
                "lines": selected,
            }

        except (ValueError, OSError, UnicodeError) as exc:
            return self._error(str(exc))
