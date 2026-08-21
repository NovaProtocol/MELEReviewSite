import tomllib
from pathlib import Path


def test_pyproject_exists_and_has_ruff_mypy():
    p = Path("pyproject.toml")
    assert p.exists()
    data = tomllib.loads(p.read_text())
    assert "tool" in data and "ruff" in data["tool"]
    assert "tool" in data and "mypy" in data["tool"]
    assert data["project"]["requires-python"] == ">=3.14"


def test_pre_commit_exists():
    assert Path(".pre-commit-config.yaml").exists()
