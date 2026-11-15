from __future__ import annotations

import re
from pathlib import Path

from app.bootstrap import SEED_FILE, _split_statements

SEED = Path(SEED_FILE)


def _statements() -> list[str]:
    return _split_statements(SEED.read_text(encoding="utf-8"))


def test_seed_is_guarded_against_duplicates():
    for statement in _statements():
        assert "NOT EXISTS" in statement, statement[:80]


def test_seeded_taxonomy_matches_the_required_lists(admin_client):
    all_subjects = admin_client.get("/api/subjects").json()
    subjects = {
        s["name"]: [t["name"] for t in s["topics"]]
        for s in all_subjects
        if s["name"]
        in {
            "Mathematics",
            "Power & Industrial Plant Engineering",
            "Machine Design & Shop Practice",
        }
    }

    assert set(subjects) == {
        "Mathematics",
        "Power & Industrial Plant Engineering",
        "Machine Design & Shop Practice",
    }
    assert subjects["Mathematics"] == [
        "algebra",
        "plane and spherical trigonometry",
        "geometry",
        "analytic geometry",
        "differential calculus",
        "integral calculus",
        "differential equation",
        "advance math",
        "probability and statistics",
        "physics and mechanics",
        "strength of materials",
        "economics",
    ]
    assert subjects["Power & Industrial Plant Engineering"] == [
        "thermodynamics",
        "fluid mechanics",
        "internal combustion engine",
        "fuels and combustion",
        "diesel power plant",
        "gas turbine power plant",
        "steam power plant",
        "steam generators",
        "steam prime movers",
        "gas and feedwater loop",
        "geothermal power plant",
        "hydroelectric power plant",
        "non conventional power plant",
        "nuclear power plant",
        "machine foundation",
        "variable load problems",
        "chimney",
        "piping system",
        "heat transfer",
        "compressors",
        "pumps",
        "fans and blowers",
        "refrigeration",
        "air conditioning",
    ]
    assert subjects["Machine Design & Shop Practice"] == [
        "kinematics",
        "stresses",
        "shafting",
        "keys",
        "splines",
        "coupling",
        "threaded members",
        "pressure vessels",
        "rivets and welded joints",
        "bearing",
        "springs",
        "flywheel",
        "brakes",
        "clutch",
        "belts",
        "wire ropes",
        "power chain",
        "gears",
        "engineering materials",
        "fits, tolerance limits & roughness",
        "seals, packing, gasket & shields",
        "machine shop",
    ]


def test_reseeding_adds_nothing(admin_client):
    """Startup ran the seed; running it again must be a no-op.

    Counted by name rather than by total, because other tests in the session add
    subjects of their own and the total is not a fixed number.
    """
    before = admin_client.get("/api/subjects").json()
    names_before = sorted(s["name"] for s in before)
    topics_before = sum(len(s["topics"]) for s in before)

    import asyncio

    from app.bootstrap import seed_taxonomy
    from app.db import _get_engine

    asyncio.run(seed_taxonomy(_get_engine()))

    after = admin_client.get("/api/subjects").json()
    assert sorted(s["name"] for s in after) == names_before
    assert sum(len(s["topics"]) for s in after) == topics_before


def test_taxonomy_lives_in_the_database_not_in_code():
    """No Python module may hold the topic list."""
    for path in Path("app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "advance math" not in source, path
        assert "fans and blowers" not in source, path
    assert "advance math" in SEED.read_text(encoding="utf-8")


def test_mysql_seed_is_portable_to_both_dialects():
    """The statements avoid dialect-only syntax so SQLite can run them too."""
    banned = ("AUTO_INCREMENT", "ENGINE=", "ON DUPLICATE KEY", "`", "NOW()")
    for statement in _statements():
        for token in banned:
            assert token not in statement, (token, statement[:60])
    assert not re.search(r"\bDELETE\b|\bDROP\b", SEED.read_text(encoding="utf-8"))
