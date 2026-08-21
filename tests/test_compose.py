from pathlib import Path


def test_compose_has_healthchecks():
    import yaml
    data = yaml.safe_load(Path("compose.yaml").read_text())
    assert "healthcheck" in data["services"]["melereview_api"]
    assert "healthcheck" in data["services"]["melereview_web"]


def test_clean_script_imports_api():
    assert "from api.db" in Path("scripts/clean_choice_contamination.py").read_text()
    assert "from apps.db" not in Path("scripts/clean_choice_contamination.py").read_text()
