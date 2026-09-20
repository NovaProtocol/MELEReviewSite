from __future__ import annotations

import importlib
import os


def _reload_config():
    """Clear cached config and reimport to pick up env changes."""
    # clear lru_cache if exists
    try:
        import api.config as cfg

        if hasattr(cfg.get_config, "cache_clear"):
            cfg.get_config.cache_clear()
    except Exception:
        pass
    # ensure fresh import
    if "api.config" in importlib.sys.modules:
        importlib.reload(importlib.sys.modules["api.config"])
    else:
        importlib.import_module("api.config")
    import api.config as cfg2

    return cfg2


def test_config_requires_secret():
    _orig_db_url = os.environ.get("DATABASE_URL")
    os.environ.pop("SECRET_KEY", None)
    os.environ["MYSQL_PASS"] = "x"
    # ensure DATABASE_URL not masking
    os.environ.pop("DATABASE_URL", None)
    # clear cache and reload
    cfg = _reload_config()
    from pydantic import ValidationError

    try:
        cfg.get_config()
        raise AssertionError("should raise ValidationError for missing SECRET_KEY")
    except ValidationError:
        pass
    except KeyError:
        # legacy path before hardening, bridge to allow TDD fail->pass check
        # but adapted test expects ValidationError, so this is considered fail until hardening
        raise AssertionError("expected ValidationError, got KeyError (not yet hardened)")
    finally:
        # restore for other tests
        os.environ["SECRET_KEY"] = "a" * 32
        if _orig_db_url is not None:
            os.environ["DATABASE_URL"] = _orig_db_url
        else:
            os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/melereview_test.db"
        cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
        if "api.config" in importlib.sys.modules:
            importlib.reload(importlib.sys.modules["api.config"])
        # ensure restored config is cached
        import api.config as _cfg2

        _cfg2.get_config()


def test_config_secret_too_short():
    _orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["SECRET_KEY"] = "short"
    os.environ["MYSQL_PASS"] = "x"
    cfg = _reload_config()
    from pydantic import ValidationError

    try:
        cfg.get_config()
        raise AssertionError("should raise for short SECRET_KEY")
    except ValidationError as e:
        # ensure error mentions SECRET_KEY
        assert "SECRET_KEY" in str(e)
    finally:
        os.environ["SECRET_KEY"] = "b" * 32
        if _orig_db_url is not None:
            os.environ["DATABASE_URL"] = _orig_db_url
        else:
            os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/melereview_test.db"
        cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
        if "api.config" in importlib.sys.modules:
            importlib.reload(importlib.sys.modules["api.config"])
        import api.config as _cfg2

        _cfg2.get_config()


def test_config_db_url_and_alias():
    _orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["SECRET_KEY"] = "c" * 32
    os.environ["MYSQL_PASS"] = "s3cr3t"
    os.environ.pop("DATABASE_URL", None)
    os.environ["MYSQL_HOST"] = "myhost"
    os.environ["MYSQL_PORT"] = "3307"
    os.environ["MYSQL_USER"] = "myuser"
    os.environ["MYSQL_DATABASE"] = "mydb"
    cfg = _reload_config()
    settings = cfg.get_config()
    # db_url computed
    expected = "mysql+aiomysql://myuser:s3cr3t@myhost:3307/mydb"
    assert settings.db_url == expected
    # DATABASE_URL alias stable
    assert expected == settings.DATABASE_URL
    assert settings.db_url == settings.DATABASE_URL
    # cleanup
    for k in ["MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_DATABASE"]:
        os.environ.pop(k, None)
    os.environ["SECRET_KEY"] = "d" * 32
    if _orig_db_url is not None:
        os.environ["DATABASE_URL"] = _orig_db_url
    else:
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/melereview_test.db"
    cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
    if "api.config" in importlib.sys.modules:
        importlib.reload(importlib.sys.modules["api.config"])
    import api.config as _cfg2

    _cfg2.get_config()


def test_config_database_url_override():
    _orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["SECRET_KEY"] = "e" * 32
    os.environ["MYSQL_PASS"] = "x"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/test.db"
    cfg = _reload_config()
    settings = cfg.get_config()
    assert settings.db_url == "sqlite+aiosqlite:////tmp/test.db"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:////tmp/test.db"
    if _orig_db_url is not None:
        os.environ["DATABASE_URL"] = _orig_db_url
    else:
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/melereview_test.db"
    cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
    if "api.config" in importlib.sys.modules:
        importlib.reload(importlib.sys.modules["api.config"])
    import api.config as _cfg2

    _cfg2.get_config()
    # restore SECRET_KEY to test default for downstream tests
    os.environ["SECRET_KEY"] = "test-secret-key-must-be-at-least-32-chars"
    _cfg2.get_config.cache_clear()
    importlib.reload(importlib.sys.modules["api.config"])
    import api.config as _cfg3

    _cfg3.get_config()
