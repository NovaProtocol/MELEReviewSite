from __future__ import annotations

import os
import importlib


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
    os.environ.pop("SECRET_KEY", None)
    os.environ["MYSQL_PASS"] = "x"
    # ensure DATABASE_URL not masking
    os.environ.pop("DATABASE_URL", None)
    # clear cache and reload
    cfg = _reload_config()
    from pydantic import ValidationError

    try:
        cfg.get_config()
        assert False, "should raise ValidationError for missing SECRET_KEY"
    except ValidationError:
        pass
    except KeyError:
        # legacy path before hardening — bridge to allow TDD fail->pass check
        # but adapted test expects ValidationError, so this is considered fail until hardening
        assert False, "expected ValidationError, got KeyError (not yet hardened)"
    finally:
        # restore for other tests
        os.environ["SECRET_KEY"] = "a" * 32
        cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
        if "api.config" in importlib.sys.modules:
            importlib.reload(importlib.sys.modules["api.config"])


def test_config_secret_too_short():
    os.environ["SECRET_KEY"] = "short"
    os.environ["MYSQL_PASS"] = "x"
    cfg = _reload_config()
    from pydantic import ValidationError

    try:
        cfg.get_config()
        assert False, "should raise for short SECRET_KEY"
    except ValidationError as e:
        # ensure error mentions SECRET_KEY
        assert "SECRET_KEY" in str(e)
    finally:
        os.environ["SECRET_KEY"] = "b" * 32
        cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
        if "api.config" in importlib.sys.modules:
            importlib.reload(importlib.sys.modules["api.config"])


def test_config_db_url_and_alias():
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
    assert settings.DATABASE_URL == expected
    assert settings.db_url == settings.DATABASE_URL
    # cleanup
    for k in ["MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_DATABASE"]:
        os.environ.pop(k, None)
    os.environ["SECRET_KEY"] = "d" * 32
    cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
    if "api.config" in importlib.sys.modules:
        importlib.reload(importlib.sys.modules["api.config"])


def test_config_database_url_override():
    os.environ["SECRET_KEY"] = "e" * 32
    os.environ["MYSQL_PASS"] = "x"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/test.db"
    cfg = _reload_config()
    settings = cfg.get_config()
    assert settings.db_url == "sqlite+aiosqlite:////tmp/test.db"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:////tmp/test.db"
    os.environ.pop("DATABASE_URL", None)
    cfg.get_config.cache_clear() if hasattr(cfg.get_config, "cache_clear") else None
    if "api.config" in importlib.sys.modules:
        importlib.reload(importlib.sys.modules["api.config"])
