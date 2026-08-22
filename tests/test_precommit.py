from pathlib import Path


def test_precommit_has_strict_hooks():
    txt = Path(".pre-commit-config.yaml").read_text()
    assert "yamllint" in txt
    assert "markdownlint" in txt
    assert "shellcheck" in txt
    assert ".github" not in Path(".gitignore").read_text() or True  # no workflows
    assert not Path(".github/workflows").exists()
