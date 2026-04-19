"""Reproduces the template-persistence bug reported against PR #346.

Setup: non-public deployment whose CEO_ID is unset (0 / None) at runtime.
Expectation: writing a filename_template via the virtual global_settings doc
must round-trip — the same value must come back on the next find_one, regardless
of whether `_ceo_personal_routing_enabled()` returns True or False.
"""

import pytest
from mongomock_motor import AsyncMongoMockClient

import database_schema as schema
from database_shim import SettingsCollectionShim


@pytest.fixture
async def shim_no_ceo():
    client = AsyncMongoMockClient()
    db = client["test-maindb"]
    settings_coll = db[schema.SETTINGS_COLLECTION]
    users_coll = db[schema.USERS_COLLECTION]
    return (
        SettingsCollectionShim(
            settings_coll, users_coll, ceo_id=None, public_mode=False
        ),
        settings_coll,
        users_coll,
    )


async def test_nonpublic_no_ceo_template_roundtrip(shim_no_ceo):
    """Non-public + missing CEO_ID: write then read filename_templates.movies
    through the virtual global_settings doc. Must not silently drop the value."""
    s, _, _ = shim_no_ceo
    await s.update_one(
        {"_id": "global_settings"},
        {"$set": {"filename_templates.movies": "MyMovies.{Title}"}},
        upsert=True,
    )
    merged = await s.find_one({"_id": "global_settings"})
    assert merged is not None, "merge returned None after a write"
    assert merged.get("filename_templates") == {"movies": "MyMovies.{Title}"}


async def test_nonpublic_ceo_migrated_then_runtime_has_no_ceo_id(shim_no_ceo):
    """A concrete regression of what the user reports: migration ran while
    CEO_ID was configured and moved filename_templates into
    MediaStudio-users.<ceo>.personal_settings. After a redeploy the CEO_ID
    env var is missing — the shim can't find CEO personal data and writes
    land in legacy_misc. The new writes should become visible on read."""
    s, _, users_coll = shim_no_ceo
    # Pretend the previous deployment (with CEO_ID=123) migrated templates
    # into the user doc.
    await users_coll.insert_one(
        {
            "user_id": 123,
            "personal_settings": {
                "filename_templates": {
                    "movies": "MIGRATED.{Title}",
                    "series": "MIGRATED.{Title}",
                },
            },
        }
    )
    # Now the admin edits the movies template through the panel:
    await s.update_one(
        {"_id": "global_settings"},
        {"$set": {"filename_templates.movies": "NEW.{Title}"}},
        upsert=True,
    )
    # And reads it back:
    merged = await s.find_one({"_id": "global_settings"})
    assert merged is not None
    # NEW must win, because that's what the admin just set. The migrated
    # personal_settings is inaccessible without CEO_ID and should not be used.
    assert merged["filename_templates"]["movies"] == "NEW.{Title}"


async def test_nonpublic_no_ceo_bootstrap_then_update(shim_no_ceo):
    """Replay the Database.get_settings fresh-install path: insert defaults
    via virtual global_settings, then update one filename template, then read."""
    s, _, _ = shim_no_ceo
    defaults = {
        "_id": "global_settings",
        "thumbnail_file_id": None,
        "thumbnail_mode": "none",
        "templates": {"title": "@X - {title}"},
        "filename_templates": {"movies": "DEFAULT.{Title}", "series": "DEFAULT.{Title}"},
        "channel": "@X",
    }
    await s.insert_one(defaults)
    await s.update_one(
        {"_id": "global_settings"},
        {"$set": {"filename_templates.movies": "CUSTOM.{Title}"}},
        upsert=True,
    )
    merged = await s.find_one({"_id": "global_settings"})
    assert merged is not None
    # The full dict must preserve the series default AND the custom movies value.
    assert merged["filename_templates"]["movies"] == "CUSTOM.{Title}"
    assert merged["filename_templates"]["series"] == "DEFAULT.{Title}"


@pytest.fixture
async def shim_with_ceo():
    client = AsyncMongoMockClient()
    db = client["test-maindb"]
    settings_coll = db[schema.SETTINGS_COLLECTION]
    users_coll = db[schema.USERS_COLLECTION]
    return (
        SettingsCollectionShim(
            settings_coll, users_coll, ceo_id=999, public_mode=False
        ),
        settings_coll,
        users_coll,
    )


async def test_nonpublic_empty_dict_filename_templates_merge_is_preserved(shim_with_ceo):
    """Regression: a stored `filename_templates: {}` (empty dict) must NOT
    hide keys set via dotted writes on another doc. get_settings callers
    do `settings.get("filename_templates", DEFAULTS)` and an empty dict is
    truthy enough to bypass the fallback, so an empty stored value silently
    makes the admin UI show "using default"."""
    s, settings_coll, users_coll = shim_with_ceo
    # Simulate a weird state where legacy_misc has an empty filename_templates
    # dict (perhaps from an old migration) and the CEO personal_settings has
    # the real values.
    await settings_coll.insert_one(
        {"_id": schema.LEGACY_MISC_DOC_ID, "filename_templates": {}}
    )
    await users_coll.insert_one(
        {
            "user_id": 999,
            "personal_settings": {
                "filename_templates": {"movies": "CUSTOM.{Title}"},
            },
        }
    )
    merged = await s.find_one({"_id": "global_settings"})
    assert merged["filename_templates"] == {"movies": "CUSTOM.{Title}"}


async def test_nonpublic_with_ceo_bootstrap_then_update_fn_template(shim_with_ceo):
    """Bootstrap: insert defaults via virtual global_settings; filename_templates
    (as a whole dict) should land in CEO personal_settings. Then updating a
    single field should still round-trip via the CEO overlay."""
    s, settings_coll, users_coll = shim_with_ceo
    defaults = {
        "_id": "global_settings",
        "templates": {"title": "@X - {title}"},
        "filename_templates": {"movies": "DEFAULT.{Title}", "series": "DEFAULT.{Title}"},
        "channel": "@X",
    }
    await s.insert_one(defaults)

    ceo = await users_coll.find_one({"user_id": 999})
    assert ceo is not None, "CEO user doc not created by bootstrap insert"
    assert ceo["personal_settings"]["filename_templates"] == {
        "movies": "DEFAULT.{Title}",
        "series": "DEFAULT.{Title}",
    }

    # Now admin edits the movies template through the panel.
    await s.update_one(
        {"_id": "global_settings"},
        {"$set": {"filename_templates.movies": "CUSTOM.{Title}"}},
        upsert=True,
    )
    ceo = await users_coll.find_one({"user_id": 999})
    assert ceo["personal_settings"]["filename_templates"]["movies"] == "CUSTOM.{Title}"
    assert ceo["personal_settings"]["filename_templates"]["series"] == "DEFAULT.{Title}"

    merged = await s.find_one({"_id": "global_settings"})
    assert merged is not None
    assert merged["filename_templates"]["movies"] == "CUSTOM.{Title}"
    assert merged["filename_templates"]["series"] == "DEFAULT.{Title}"
