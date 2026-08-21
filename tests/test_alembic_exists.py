from pathlib import Path


def test_alembic_exists():
    assert Path("alembic.ini").exists()
    assert Path("alembic/env.py").exists()
