from pathlib import Path


def test_calculator_js_no_silent_catch():
    for p in Path("web/static/js/calculators").glob("*.js"):
        txt = p.read_text()
        assert "/* ignore */" not in txt, f"{p} has silent catch"
        assert "/* ignore malformed */" not in txt


def test_calculator_js_exists():
    files = list(Path("web/static/js/calculators").glob("*.js"))
    assert len(files) >= 6, f"expected >=6 got {len(files)}"


def test_calculator_js_has_logic():
    for p in Path("web/static/js/calculators").glob("*.js"):
        if p.name == "thermo_inline.js":
            continue
        txt = p.read_text()
        assert len(txt.strip()) > 20
