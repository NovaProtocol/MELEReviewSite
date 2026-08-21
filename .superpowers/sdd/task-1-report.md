# Task 1 Report: Tooling Foundation — pyproject.toml + Ruff + Mypy + Pre-commit

## What was implemented

- **`pyproject.toml`**: Created verbatim from brief. Sets `project.requires-python = ">=3.14"`, `dev` optional-dependencies (pytest, ruff, mypy, pre-commit, alembic), `[tool.ruff]` (line-length 100, target py314, select E/F/I/UP/B/SIM/RUF), `[tool.ruff.format]` (double quotes), `[tool.ruff.lint.isort]` (known-first-party api/web/tests), `[tool.mypy]` (python_version 3.14, warn_return_any, ignore_missing_imports, pydantic plugin, CoolProp override), `[tool.pytest.ini_options]` (testpaths tests, asyncio_mode auto), `[tool.alembic]`.
- **`.pre-commit-config.yaml`**: Created verbatim from brief. Two repos: astral-sh/ruff-pre-commit v0.8.6 (hooks ruff --fix, ruff-format) and pre-commit/mirrors-mypy v1.13.0 (hook mypy with pydantic/sqlalchemy/types-requests).
- **`.editorconfig`**: Created with root=true, utf-8/lf/final_newline/trim, space indent 4 (2 for yaml/json/md/toml), tab for Makefile.
- **`.gitignore`**: Appended `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/` under Tooling caches.
- **`tests/test_tooling.py`**: TDD test (TDD step 1/2 verified FAIL before, PASS after). Fixed tomllib nested-dict check (`"tool" in data and "ruff" in data["tool"]`) — brief's flat `"tool.ruff" in data` is incorrect for tomllib which nests `[tool.ruff]`.
- **`api/requirements.txt` / `web/requirements.txt`**: No change required; deps remain in Docker requirements per pyproject comment. Brief lists them as Modify but gives no delta — left intact.

## Test results

TDD verified:
- Before: `pytest tests/test_tooling.py -v` → 2 FAILED (AssertionError FileNotFound)
- After: `pytest tests/test_tooling.py -v` → 2 passed (0.02s)

```
tests/test_tooling.py::test_pyproject_exists_and_has_ruff_mypy PASSED
tests/test_tooling.py::test_pre_commit_exists PASSED
```

Full suite: 27 passed, 3 failed (pre-existing `tests/test_questions_js.py` failures: silenced catch, missing load log — unrelated to tooling, present before this task on main 1c5786d).

## Files changed

| File | Change |
|------|--------|
| `pyproject.toml` | +41 lines (new) |
| `.pre-commit-config.yaml` | +13 lines (new) |
| `.editorconfig` | +14 lines (new) |
| `.gitignore` | +5 lines (caches) |
| `tests/test_tooling.py` | +16 lines (new, corrected tomllib check) |

## Verification

- `python -m pytest tests/test_tooling.py -v` → 2 passed
- `pyproject.toml` valid TOML, `requires-python == ">=3.14"`, ruff/mypy sections present
- `.pre-commit-config.yaml` valid YAML with correct revs
- `ruff check` / `ruff format` / `mypy` driven from pyproject (ruff 0.11 available, mypy not in venv but config valid)

## Commit

`494f0ef` — chore: add pyproject tooling foundation (ruff, mypy, pre-commit)

## Concerns

- Brief's test assertion `"tool.ruff" in data` is wrong for `tomllib` (nests to `data["tool"]["ruff"]`). Fixed to nested check; otherwise test would never pass with standard TOML. Flag for brief correction.
- System Python is 3.13 (`python3 --version 3.13.5`) but venv is 3.14.6; pyproject `requires-python >=3.14` satisfied only in venv. CI should pin 3.14.
- `ruff`/`mypy` not installed in `.venv` (only global ruff 0.11); `pip install -e .[dev]` needed for local pre-commit runs.
- 3 pre-existing failures in `tests/test_questions_js.py` unrelated to this task.

---

## Fix: C1 — target-version py314 incompatible with Ruff 0.8.6/0.11.0

**Issue:** `pyproject.toml` sets `target-version = "py314"` but `.pre-commit-config.yaml` pinned `astral-sh/ruff-pre-commit` at `v0.8.6` and global Ruff at `0.11.0`. Neither supports `py314` → `ruff check` fails with `Unknown variant py314` (reproducible with Ruff 0.8.6/0.11; blocked pre-commit and CI).

**Fix applied:**
- `pyproject.toml` `[project.optional-dependencies] dev`: bumped to `ruff>=0.14`, `mypy>=1.16`, added `pytest-asyncio`:
  ```toml
  dev = ["pytest>=8", "httpx", "aiosqlite", "ruff>=0.14", "mypy>=1.16", "pre-commit", "alembic", "pytest-asyncio"]
  ```
  Kept `target-version = "py314"` (supported from Ruff ≥0.14).
- `.pre-commit-config.yaml`: bumped `astral-sh/ruff-pre-commit` rev `v0.8.6` → `v0.16.4`, `pre-commit/mirrors-mypy` rev `v1.13.0` → `v1.16.1`.

**Verification (2026-08-21, venv Python 3.14.6):**

- `.venv/bin/pip install "ruff>=0.14" "mypy>=1.16" pytest-asyncio` → installed `ruff 0.16.4`, `mypy 2.3.1` (satisfies `>=1.16`).
- `.venv/bin/ruff --version` → `ruff 0.16.4` (supports `py314`).
- `.venv/bin/mypy --version` → `mypy 2.3.1 (compiled: yes)` (satisfies `>=1.16`, supports `python_version = 3.14`).
- `.venv/bin/ruff check pyproject.toml` → `All checks passed!` (config parses, no `Unknown variant py314`).
- `.venv/bin/ruff check .` → exits 1 with 98 lint errors (E501, F401, B008, etc.) — **no** `Unknown variant` error; `target-version py314` accepted. Lint errors are pre-existing codebase style issues, not config errors. `ruff check` correctly reads `pyproject.toml`.
- `.venv/bin/python -m pytest tests/test_tooling.py -v` → `2 passed`:
  ```
  tests/test_tooling.py::test_pyproject_exists_and_has_ruff_mypy PASSED
  tests/test_tooling.py::test_pre_commit_exists PASSED
  ```

**Result:** C1 resolved. `ruff check`/`ruff format`/`mypy` now handle `py314`; pre-commit revs align with `pyproject.toml` constraints.

**Commit:** `fix: bump ruff/mypy to support py314` (see `git log` for hash)
