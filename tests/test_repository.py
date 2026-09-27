import pytest

from app.tools.repository import RepositoryTools


@pytest.fixture
def tools(tmp_path):
    """为每个测试创建临时仓库，不依赖真实 target-repo。"""
    src = tmp_path / "src"
    src.mkdir()

    (src / "example.py").write_text(
        "def greet(name):\n"
        "    return f'Hello {name}'\n",
        encoding="utf-8",
    )

    (tmp_path / "README.md").write_text(
        "# Demo repository\n",
        encoding="utf-8",
    )

    (tmp_path / ".env").write_text(
        "API_KEY=fake-test-key\n",
        encoding="utf-8",
    )

    hidden_dir = tmp_path / ".git"
    hidden_dir.mkdir()
    (hidden_dir / "internal.py").write_text(
        "hidden = True\n",
        encoding="utf-8",
    )

    return RepositoryTools(tmp_path)


def test_list_files(tools):
    result = tools.list_files()

    assert result["ok"] is True
    assert set(result["files"]) == {
        "src/example.py",
        "README.md",
    }


def test_list_files_limit(tools):
    result = tools.list_files(limit=1)

    assert len(result["files"]) == 1
    assert result["truncated"] is True


def test_search_code(tools):
    result = tools.search_code("def greet")

    assert result["ok"] is True
    assert result["matches"][0]["path"] == "src/example.py"
    assert result["matches"][0]["line"] == 1


def test_search_no_match(tools):
    result = tools.search_code("not_existing_keyword")

    assert result["ok"] is True
    assert result["matches"] == []


def test_search_empty_query(tools):
    result = tools.search_code(" ")

    assert result["ok"] is False


def test_read_file(tools):
    result = tools.read_file(
        "src/example.py",
        start_line=2,
        end_line=2,
    )

    assert result["ok"] is True
    assert result["lines"][0]["line"] == 2
    assert "return" in result["lines"][0]["text"]


def test_reject_parent_path(tools):
    result = tools.read_file("../outside.py")

    assert result["ok"] is False


def test_reject_env_file(tools):
    result = tools.read_file(".env")

    assert result["ok"] is False


def test_missing_file(tools):
    result = tools.read_file("missing.py")

    assert result["ok"] is False


def test_invalid_line_range(tools):
    result = tools.read_file(
        "src/example.py",
        start_line=3,
        end_line=1,
    )

    assert result["ok"] is False


def test_allows_json_and_rejects_png(tools, tmp_path):
    (tmp_path / "config.json").write_text('{"ok": true}\n', encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")
    listed = tools.list_files()
    assert listed["ok"] is True
    assert "config.json" in listed["files"]
    assert "logo.png" not in listed["files"]
    read_json = tools.read_file("config.json")
    assert read_json["ok"] is True
    assert '{"ok": true}' in read_json["lines"][0]["text"]
    read_png = tools.read_file("logo.png")
    assert read_png["ok"] is False
