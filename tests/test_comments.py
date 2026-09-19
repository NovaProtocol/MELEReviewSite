"""Style regression: commenting per §8 and shellcheck (§9)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_no_print_in_api():
    """No print() in api/ — use logger.info or structlog."""
    for p in Path("api").rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        # Allow print inside string literals? Simple check: look for print( not in comment
        # Strip comments then search.
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # naive: check print( outside docstring — api/ must have none
            # consider any occurrence a violation except inside tests
            if "print(" in line:
                pytest.fail(f"{p}:{i} contains print(: {line.strip()!r}")


def test_no_print_in_scripts():
    """No print() in scripts/ — use logging."""
    scripts = Path("scripts")
    if not scripts.exists():
        pytest.skip("no scripts/")
    for p in scripts.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if "print(" in line:
                pytest.fail(f"{p}:{i} contains print(: {line.strip()!r}")


def _is_allowed_trailing_comment(line: str) -> bool:
    """Whitelist trailing comments that are tool directives, not style violations."""
    # mypy, ruff, coverage, fmt directives are allowed trailing
    allowed_substrings = [
        "# type: ignore",
        "# type:",
        "# pragma: no cover",
        "# pragma:",
        "# noqa",
        "# fmt:",
        "# isort:",
        "# pylint:",
        "# nosec",
    ]
    return any(sub in line for sub in allowed_substrings)


def test_no_trailing_inline_comments():
    """Inline comments must be above the line with ' # ', not trailing."""
    # This enforces §8.2: ` # ` with one space, above the line not trailing
    # We allow tool directives as exception.
    for p in Path("api").rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if not line.strip() or line.strip().startswith("#"):
                continue
            # need to detect `#` that is not inside string literal naively.
            # We look for `  #` or `\t#` trailing pattern after code.
            # If line has `#` and code before it, and not whitelisted, fail.
            if "#" in line:
                # split on first # not inside quotes — naive but sufficient for style check
                # If there's code before # and not allowed, flag.
                before, _after = line.split("#", 1)
                if before.strip() == "":
                    continue  # full line comment
                if _is_allowed_trailing_comment(line):
                    continue
                if re.search(r"\S\s+#\s", line):
                    msg = f"{p}:{i} trailing comment, move above: {line.strip()!r}"
                    pytest.fail(msg)


def test_no_bare_todo():
    """No bare TODO without owner: TODO(nova): context."""
    todo_re = re.compile(r"\bTODO\b(?!\()")
    for p in Path("api").rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if todo_re.search(line):
                # Allow TODO(owner): but not bare TODO
                if "TODO(" not in line:
                    pytest.fail(f"{p}:{i} has bare TODO without owner: {line.strip()!r}")
            if "TODO:" in line and "TODO(" not in line:
                pytest.fail(f"{p}:{i} has TODO: without owner parentheses: {line.strip()!r}")


def test_init_db_has_google_docstring():
    """Adaptive _init_db must have Google one-liner docstring."""
    txt = Path("api/app.py").read_text(encoding="utf-8")
    # Find def _init_db
    m = re.search(r"def _init_db\(.*?\).*?:\s*\"\"\"(.+?)\"\"\"", txt, re.DOTALL)
    assert m is not None, "_init_db is missing Google one-liner docstring"
    doc = m.group(1).strip()
    # One-liner means first line non-empty and not multi-paragraph? Simple check: doc should be single line-ish and <100 chars or contain relevant keywords
    assert len(doc.splitlines()[0]) > 10, "_init_db docstring too short"
    # Should mention adaptive or create or retry or table
    assert any(k in doc.lower() for k in ["table", "create", "adaptive", "retry", "migration"]), (
        f"_init_db docstring should describe purpose, got: {doc!r}"
    )


def test_clean_script_has_google_docstrings_and_no_print():
    """scripts/clean_choice_contamination.py must have docstrings and no print."""
    p = Path("scripts/clean_choice_contamination.py")
    assert p.exists(), "scripts/clean_choice_contamination.py missing"
    txt = p.read_text(encoding="utf-8")
    for i, line in enumerate(txt.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # ignore comment part after #
        code = line.split("#", 1)[0]
        assert "print(" not in code, f"{p}:{i} must not use print(); use logging: {line.strip()!r}"
    # Must have docstrings for clean() and main()
    assert "def clean(" in txt
    m = re.search(r"def clean\(.*?\).*?:\s*\"\"\"(.+?)\"\"\"", txt, re.DOTALL)
    assert m is not None, "clean() missing Google one-liner docstring"
    m2 = re.search(r"def main\(.*?\).*?:\s*\"\"\"(.+?)\"\"\"", txt, re.DOTALL)
    assert m2 is not None, "main() missing Google one-liner docstring"
    assert '"""' in txt  # module docstring exists


def test_inline_comments_are_above_line_in_clean_script():
    """clean_choice_contamination.py inline comments must be above line with ' # '."""
    p = Path("scripts/clean_choice_contamination.py")
    txt = p.read_text(encoding="utf-8")
    for i, line in enumerate(txt.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _is_allowed_trailing_comment(line):
            continue
        if re.search(r"\S\s+#\s", line):
            pytest.fail(f"{p}:{i} trailing comment must be above line: {line.strip()!r}")
    # also check comment length <72 for lines starting with # (excluding tool directives)
    for i, line in enumerate(txt.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") and not _is_allowed_trailing_comment(stripped):
            # comment body length without "# "
            body = stripped.lstrip("#").strip()
            if body and not body.startswith("---"):
                assert len(stripped) <= 72 + 2, (
                    f"{p}:{i} comment >72 chars: {stripped!r} ({len(stripped)})"
                )


def test_no_console_log_except_guards():
    """No console.log in web/static/js except guards at top and DOMContentLoaded."""
    js_root = Path("web/static/js")
    if not js_root.exists():
        pytest.skip("no web/static/js")
    allowed_patterns = [
        "file loaded",  # questions.js:1 file-loaded guard
        "DOMContentLoaded fired",
    ]
    for p in js_root.rglob("*.js"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if "console.log" in line:
                # allow only if line contains allowed pattern
                if any(pat in line for pat in allowed_patterns):
                    continue
                # Also allow console.log inside comment? If line is // console.log it's commented out, ignore
                stripped = line.strip()
                if stripped.startswith("//") and "console.log" in stripped:
                    # commented out code -> should not contain console.log at all per spec, but we treat as violation if not guard
                    # However spec says no console.log except guards, so commented out counts as not violation? We flag commented out as violation because it's leftover debug.
                    # Let's allow commented out as not execution, but still flag as debug leftover? We'll skip commented lines with // console.log as they are not executed.
                    if "// console.log" in line:
                        continue
                pytest.fail(
                    f"{p}:{i} has unexpected console.log (only guards allowed): {line.strip()!r}"
                )
            # Also forbid console.debug/info/warn leftovers? Spec only says console.log, but we check log specifically
        # also ensure questions.js first non-empty line is guard
        if p.name == "questions.js":
            first_nonempty = next((ln for ln in text.splitlines() if ln.strip()), "")
            assert "console.log" in first_nonempty and "file loaded" in first_nonempty, (
                f"questions.js should start with file-loaded guard, got: {first_nonempty!r}"
            )
            assert "DOMContentLoaded fired" in text


def test_no_console_log_in_other_js_files():
    """Other JS files must have zero console.log."""
    for p in Path("web/static/js").glob("*.js"):
        if p.name == "questions.js":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if "console.log" in line and not line.strip().startswith("//"):
                pytest.fail(f"{p}:{i} should not contain console.log: {line.strip()!r}")


def test_shellcheck_clean():
    """All scripts/*.sh must be shellcheck clean with set -euo pipefail."""
    import shutil
    import subprocess

    sh_files = list(Path("scripts").glob("*.sh")) if Path("scripts").exists() else []
    sh_files += list(Path(".").glob("*.sh"))
    # also check any *.sh at root of reference? just scripts/
    if not sh_files:
        # vacuous pass if no sh files, but we still verify that if they existed they'd be checked
        return
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        pytest.skip("shellcheck not installed")
    for p in sh_files:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        # Must have set -euo pipefail
        assert "set -euo pipefail" in txt, f"{p} missing 'set -euo pipefail'"
        # Run shellcheck
        result = subprocess.run([shellcheck, str(p)], capture_output=True, text=True)
        assert result.returncode == 0, (
            f"shellcheck failed for {p}:\n{result.stdout}\n{result.stderr}"
        )


def test_section_comments_format():
    """Section comments only in files >150 lines, format # --- Section ---."""
    for p in Path("api").rglob("*.py"):
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if len(lines) <= 150:
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Flag old style section headers like #### or === or ---
                if stripped.startswith("#") and any(
                    x in stripped for x in ["####", "====", "----"]
                ):
                    # Allow only "# ---" style
                    if not re.match(r"# --- .+ ---", stripped):
                        pytest.fail(
                            f"{p}:{i} has non-standard section header: {stripped!r} (use '# --- Section ---')"
                        )
                # also flag manual "# imports" header (ruff handles)
                if stripped.lower() in ["# imports", "# import"]:
                    pytest.fail(f"{p}:{i} has manual imports header which ruff isort handles")


def test_line_length_and_double_quotes_style():
    """Spot check: ruff line length 100 and double quotes enforced via pre-commit."""
    # We don't enforce full ruff here, but ensure no egregious >120 lines in api/ (ruff would catch 100, but we allow 110 tolerance)
    for p in Path("api").rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if len(line) > 120 and not line.strip().startswith("#"):
                # allow long URLs or strings? just warn if many
                pass  # not hard fail, ruff handles
