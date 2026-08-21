# Task 3: Config Hardening (pydantic-settings, validation, secure defaults)

## Brief
Harden `api/config.py` to use `pydantic-settings`, add validation, keep backwards compat for `get_config().DATABASE_URL`. Update `api/db.py` pool settings, document `SECRET_KEY >=32`.

## Changes

### `api/config.py`
- Rewrote from `dataclass Config` to `pydantic-settings BaseSettings` `Settings`
- Fields: `DEBUG` (bool default_factory reading `DEPLOYMENT_TYPE`), `MYSQL_HOST`, `MYSQL_PORT: int`, `MYSQL_USER`, `MYSQL_PASS` (required), `MYSQL_DATABASE`, `SECRET_KEY` with `Field(min_length=32)`, `DATABASE_URL_OVERRIDE` with `validation_alias="DATABASE_URL"`
- `model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)`
- Properties: `db_url` (computed `mysql+aiomysql://...` or override), `DATABASE_URL` alias for backwards compat (`return self.db_url`), `is_debug`
- `@lru_cache def get_config() -> Settings`
- Alias `Config = Settings` for legacy imports

### `api/db.py`
- `_get_engine()` now uses `config.db_url` instead of `config.DATABASE_URL`
- Added `pool_recycle=3600`, `echo=config.is_debug` alongside existing `pool_pre_ping=True, pool_size=5`

### `tests/test_config.py` (new, TDD)
- `test_config_requires_secret`: pops `SECRET_KEY`, expects `pydantic.ValidationError` (adapted from brief `KeyError`)
- `test_config_secret_too_short`: asserts `ValidationError` mentions `SECRET_KEY` when <32 chars
- `test_config_db_url_and_alias`: verifies computed `db_url == DATABASE_URL == "mysql+aiomysql://myuser:s3cr3t@myhost:3307/mydb"`
- `test_config_database_url_override`: verifies `DATABASE_URL` env override returns same via both accessors

### `.env.example`
- Documented `SECRET_KEY >=32` with generation hint: `# SECRET_KEY must be at least 32 characters (generate with: openssl rand -hex 32)` and example value `changeme-must-be-at-least-32-characters-long`

### `api/requirements.txt`
- Added `pydantic-settings>=2,<3`

### `pyproject.toml`
- Added `pydantic-settings>=2` to `[project.optional-dependencies].dev`

### `tests/conftest.py`
- Updated `SECRET_KEY` default from `test-secret` (11) to `test-secret-key-must-be-at-least-32-chars` to satisfy new validation

## TDD Verification

- **Before** (legacy `Config`): `pytest tests/test_config.py -v` → 4 FAILED
  - `test_config_requires_secret` → `AssertionError: expected ValidationError, got KeyError`
  - `test_config_secret_too_short` → `AssertionError: should raise for short SECRET_KEY`
  - `test_config_db_url_and_alias` → `AttributeError: 'Config' object has no attribute 'db_url'`
  - `test_config_database_url_override` → `AttributeError: 'Config' object has no attribute 'db_url'`
- **After** (`Settings`): `pytest tests/test_config.py -v` → 4 passed (0.05s)

## Test Results

```
pytest tests/test_config.py tests/test_tooling.py tests/test_ci_exists.py -v → 7 passed
pytest tests/test_api.py -v → 16 passed
pytest -q → 35 passed (16 api + 8 web + 4 questions_js + 4 config + 2 tooling + 1 ci)
```

- Full suite: 35 passed, 0 failed
- `ruff check api/config.py api/db.py` → 0 errors on config, 1 pre-existing on db line length
- `mypy api/config.py` → no errors

## Commit
`feat: harden config with pydantic-settings validation`

## Files Changed
| File | Change |
|------|--------|
| `api/config.py` | rewrite to Settings, validation, cache, aliases |
| `api/db.py` | use db_url, pool_recycle=3600, echo=is_debug |
| `tests/test_config.py` | new TDD tests (4) |
| `.env.example` | SECRET_KEY >=32 docs |
| `api/requirements.txt` | + pydantic-settings |
| `pyproject.toml` | + pydantic-settings to dev |
| `tests/conftest.py` | longer test SECRET_KEY |
