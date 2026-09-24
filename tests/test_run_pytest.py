import subprocess
from pathlib import Path

from app.run_pytest import run_pytest


def test_passing_workspace(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = run_pytest(tmp_path)
    assert result["passed"] is True
    assert result["ok"] is True
    assert result["timed_out"] is False
    assert result["command"] == ["python", "-m", "pytest", "-q"]
    assert result["returncode"] == 0


def test_failing_workspace(tmp_path):
    (tmp_path / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    result = run_pytest(tmp_path)
    assert result["passed"] is False
    assert result["ok"] is False
    assert result["returncode"] != 0
    assert "pytest 未通过" in result["error"]


def test_does_not_use_shell(tmp_path, monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_pytest(tmp_path)
    assert seen["kwargs"]["shell"] is False
    assert seen["kwargs"]["cwd"] == Path(tmp_path).resolve()
    assert seen["command"][1:] == ["-m", "pytest", "-q"]
    assert result["passed"] is True
