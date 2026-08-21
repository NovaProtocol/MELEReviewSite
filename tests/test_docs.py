from pathlib import Path


def test_readme_mentions_alembic():
    assert "alembic" in Path("README.md").read_text().lower()


def test_readme_mentions_solution_blocks():
    text = Path("README.md").read_text().lower()
    assert "solution" in text and "block" in text


def test_adr_exists():
    assert Path("docs/adr/001-plain-pin.md").exists()
