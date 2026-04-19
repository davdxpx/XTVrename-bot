"""Tests for the legacy_misc → CEO personal_settings backfill in
consolidate_nonpublic_settings. Covers the scenario where a non-public
deployment booted once without CEO_ID, had admin writes land in
``legacy_misc`` for PERSONAL_KEYS, and later got a CEO_ID set — the
backfill rescues those writes so admin reads see them.
"""

import os

import pytest
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("BOT_TOKEN", "test")
os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "test")
os.environ.setdefault("MAIN_URI", "mongodb://localhost:27017")

import database_schema as schema  # noqa: E402
from database_shim import SettingsCollectionShim  # noqa: E402


class _FakeDatabase:
    """Minimal stand-in for the Database class — only the attributes the
    consolidate migration touches."""

    def __init__(self, settings_coll, users_coll):
        self.settings = SettingsCollectionShim(
            settings_coll, users_coll, ceo_id=999, public_mode=False
        )
        self.users = users_coll

    def _invalidate_settings_cache(self, user_id=None):  # noqa: ARG002
        pass


async def _setup(ceo_id=999):
    client = AsyncMongoMockClient()
    db = client["test-maindb"]
    settings_coll = db[schema.SETTINGS_COLLECTION]
    users_coll = db[schema.USERS_COLLECTION]
    shim = SettingsCollectionShim(
        settings_coll, users_coll, ceo_id=ceo_id, public_mode=False
    )
    fake_db = _FakeDatabase.__new__(_FakeDatabase)
    fake_db.settings = shim
    fake_db.users = users_coll
    fake_db._invalidate_settings_cache = lambda *a, **kw: None
    return fake_db, settings_coll, users_coll


async def test_backfill_filename_templates_from_legacy_misc(monkeypatch):
    """User had CEO_ID unset, edited filename_templates (landed in
    legacy_misc). Set CEO_ID and boot: backfill moves them into CEO
    personal_settings so admin reads see them."""
    fake_db, settings_coll, users_coll = await _setup(ceo_id=999)

    from config import Config
    monkeypatch.setattr(Config, "PUBLIC_MODE", False, raising=False)
    monkeypatch.setattr(Config, "CEO_ID", 999, raising=False)

    await settings_coll.insert_one(
        {
            "_id": schema.LEGACY_MISC_DOC_ID,
            "filename_templates": {"movies": "CUSTOM.{Title}"},
            "templates": {"title": "{title}"},
            "an_unrelated_legacy_key": "keepme",
        }
    )

    from db_migrations.consolidate_nonpublic_settings import (
        run_consolidate_nonpublic_settings,
    )
    await run_consolidate_nonpublic_settings(fake_db)

    ceo = await users_coll.find_one({"user_id": 999})
    assert ceo is not None
    assert ceo["personal_settings"]["filename_templates"] == {"movies": "CUSTOM.{Title}"}
    assert ceo["personal_settings"]["templates"] == {"title": "{title}"}

    legacy = await settings_coll.find_one({"_id": schema.LEGACY_MISC_DOC_ID})
    # Personal keys removed, unrelated legacy key preserved.
    assert "filename_templates" not in legacy
    assert "templates" not in legacy
    assert legacy["an_unrelated_legacy_key"] == "keepme"

    # Admin reads via the virtual doc now resolve to CEO personal.
    merged = await fake_db.settings.find_one({"_id": "global_settings"})
    assert merged["filename_templates"] == {"movies": "CUSTOM.{Title}"}
    assert merged["templates"] == {"title": "{title}"}


async def test_backfill_legacy_misc_wins_over_stale_ceo_subkey(monkeypatch):
    """Sub-key conflict: legacy_misc is the most recent admin write, so its
    value overwrites the stale CEO sub-key."""
    fake_db, settings_coll, users_coll = await _setup(ceo_id=999)

    from config import Config
    monkeypatch.setattr(Config, "PUBLIC_MODE", False, raising=False)
    monkeypatch.setattr(Config, "CEO_ID", 999, raising=False)

    await users_coll.insert_one(
        {
            "user_id": 999,
            "personal_settings": {
                "filename_templates": {"movies": "STALE", "series": "OK_SERIES"},
            },
        }
    )
    await settings_coll.insert_one(
        {
            "_id": schema.LEGACY_MISC_DOC_ID,
            "filename_templates": {"movies": "FRESH"},
        }
    )

    from db_migrations.consolidate_nonpublic_settings import (
        run_consolidate_nonpublic_settings,
    )
    await run_consolidate_nonpublic_settings(fake_db)

    ceo = await users_coll.find_one({"user_id": 999})
    assert ceo["personal_settings"]["filename_templates"]["movies"] == "FRESH"
    assert ceo["personal_settings"]["filename_templates"]["series"] == "OK_SERIES"


async def test_backfill_no_ceo_id_is_noop(monkeypatch):
    """Without CEO_ID the backfill can't pick a target and must leave
    legacy_misc alone (but the consolidate wrapper still emits the warning)."""
    fake_db, settings_coll, users_coll = await _setup(ceo_id=None)

    from config import Config
    monkeypatch.setattr(Config, "PUBLIC_MODE", False, raising=False)
    monkeypatch.setattr(Config, "CEO_ID", 0, raising=False)

    await settings_coll.insert_one(
        {
            "_id": schema.LEGACY_MISC_DOC_ID,
            "filename_templates": {"movies": "STAYS"},
        }
    )

    from db_migrations.consolidate_nonpublic_settings import (
        run_consolidate_nonpublic_settings,
    )
    await run_consolidate_nonpublic_settings(fake_db)

    legacy = await settings_coll.find_one({"_id": schema.LEGACY_MISC_DOC_ID})
    assert legacy["filename_templates"] == {"movies": "STAYS"}
    assert await users_coll.count_documents({}) == 0


async def test_backfill_public_mode_is_noop(monkeypatch):
    """Public mode never runs the backfill."""
    fake_db, settings_coll, users_coll = await _setup(ceo_id=999)

    from config import Config
    monkeypatch.setattr(Config, "PUBLIC_MODE", True, raising=False)
    monkeypatch.setattr(Config, "CEO_ID", 999, raising=False)

    await settings_coll.insert_one(
        {
            "_id": schema.LEGACY_MISC_DOC_ID,
            "filename_templates": {"movies": "WHATEVER"},
        }
    )

    from db_migrations.consolidate_nonpublic_settings import (
        run_consolidate_nonpublic_settings,
    )
    await run_consolidate_nonpublic_settings(fake_db)

    legacy = await settings_coll.find_one({"_id": schema.LEGACY_MISC_DOC_ID})
    assert legacy["filename_templates"] == {"movies": "WHATEVER"}
    assert await users_coll.count_documents({}) == 0
