from pathlib import Path


def test_solution_blocks_js_exists():
    assert Path("web/static/js/solution_blocks.js").exists()
    src = Path("web/static/js/questions.js").read_text()
    assert (
        "solution_blocks" in src.lower()
        or "renderblocks" in src.lower()
        or "createblocks" in src.lower()
    )
