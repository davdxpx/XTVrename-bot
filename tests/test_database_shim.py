"""Unit tests for SettingsCollectionShim."""

import logging

import pytest
from mongomock_motor import AsyncMongoMockClient

import database_schema as schema
from database_shim import SettingsCollectionShim


@pytest.fixture
async def shim():
    client = AsyncMongoMockClient()
    db = client["test-maindb"]
    settings_coll = db[schema.SETTINGS_COLLECTION]
    users_coll = db[schema.USERS_COLLECTION]
    return SettingsCollectionShim(settings_coll, users_coll), settings_coll, users_coll


# A.06 — merge read --------------------------------------------------------


async def test_find_one_global_settings_merges_split_docs(shim):
    s, settings_coll, _ = shim
    await settings_coll.insert_one({"_id": schema.DOC_BRANDING, "bot_name": "TestBot"})
    await settings_coll.insert_one(
        {
            "_id": schema.DOC_PAYMENTS,
            "base_currency": "EUR",
            "stars_payment_enabled": True,
        }
    )
    await settings_coll.insert_one(
        {"_id": schema.DOC_PREMIUM_PLANS, "premium_system_enabled": True}
    )

    merged = await s.find_one({"_id": "global_settings"})
    assert merged is not None
    assert merged["_id"] == "global_settings"
    assert merged["bot_name"] == "TestBot"
    assert merged["base_currency"] == "EUR"
    assert merged["stars_payment_enabled"] is True
    assert merged["premium_system_enabled"] is True


async def test_find_one_public_mode_config_uses_same_merge(shim):
    s, settings_coll, _ = shim
    await settings_coll.insert_one({"_id": schema.DOC_BRANDING, "bot_name": "PublicBot"})

    merged = await s.find_one({"_id": "public_mode_config"})
    assert merged is not None
    assert merged["bot_name"] == "PublicBot"


# A.07 — routed update -----------------------------------------------------


async def test_update_one_routes_known_key_to_correct_doc(shim):
    s, settings_coll, _ = shim
    result = await s.update_one(
        {"_id": "global_settings"}, {"$set": {"base_currency": "EUR"}}, upsert=True
    )
    assert result is not None
    doc = await settings_coll.find_one({"_id": schema.DOC_PAYMENTS})
    assert doc is not None
    assert doc["base_currency"] == "EUR"
    # The other docs stay untouched.
    assert await settings_coll.find_one({"_id": schema.DOC_BRANDING}) is None


async def test_update_one_with_multiple_keys_fans_out(shim):
    s, settings_coll, _ = shim
    await s.update_one(
        {"_id": "global_settings"},
        {
            "$set": {
                "bot_name": "Fanout",
                "base_currency": "USD",
                "premium_system_enabled": False,
            }
        },
        upsert=True,
    )
    assert (await settings_coll.find_one({"_id": schema.DOC_BRANDING}))["bot_name"] == "Fanout"
    assert (
        await settings_coll.find_one({"_id": schema.DOC_PAYMENTS})
    )["base_currency"] == "USD"
    assert (
        await settings_coll.find_one({"_id": schema.DOC_PREMIUM_PLANS})
    )["premium_system_enabled"] is False


# A.08 — unknown-key fallback ---------------------------------------------


async def test_unknown_key_lands_in_legacy_misc_and_warns(shim, caplog):
    s, settings_coll, _ = shim
    with caplog.at_level(logging.WARNING, logger="database.shim"):
        await s.update_one(
            {"_id": "global_settings"},
            {"$set": {"brand_new_key_xyz": 42}},
            upsert=True,
        )
    doc = await settings_coll.find_one({"_id": schema.LEGACY_MISC_DOC_ID})
    assert doc is not None
    assert doc["brand_new_key_xyz"] == 42
    # warning captured
    assert any("brand_new_key_xyz" in rec.message for rec in caplog.records)
    # recent-unknown log populated
    assert any(e["key"] == "brand_new_key_xyz" for e in s.recent_unknown_writes())


# A.09 — per-user find rewrites to MediaStudio-users -----------------------


async def test_find_one_user_doc_reads_from_users_collection(shim):
    s, _, users_coll = shim
    await users_coll.insert_one(
        {
            "user_id": 42,
            "personal_settings": {
                "thumbnail_mode": "auto",
                "preferred_language": "de",
            },
        }
    )
    doc = await s.find_one({"_id": "user_42"})
    assert doc is not None
    assert doc["_id"] == "user_42"
    assert doc["thumbnail_mode"] == "auto"
    assert doc["preferred_language"] == "de"


async def test_find_one_unknown_user_returns_none(shim):
    s, _, _ = shim
    assert await s.find_one({"_id": "user_99999"}) is None


# A.10 — per-user update writes into personal_settings ---------------------


async def test_update_one_user_doc_writes_under_personal_settings(shim):
    s, _, users_coll = shim
    await s.update_one(
        {"_id": "user_42"},
        {"$set": {"thumbnail_file_id": "ABC"}},
        upsert=True,
    )
    user = await users_coll.find_one({"user_id": 42})
    assert user is not None
    assert user["personal_settings"]["thumbnail_file_id"] == "ABC"


async def test_update_one_user_doc_handles_multiple_keys(shim):
    s, _, users_coll = shim
    await s.update_one(
        {"_id": "user_7"},
        {"$set": {"preferred_language": "en", "display_show_poster": True}},
        upsert=True,
    )
    user = await users_coll.find_one({"user_id": 7})
    assert user["personal_settings"]["preferred_language"] == "en"
    assert user["personal_settings"]["display_show_poster"] is True


async def test_update_one_user_unset_removes_field(shim):
    s, _, users_coll = shim
    await s.update_one(
        {"_id": "user_7"}, {"$set": {"preferred_language": "en"}}, upsert=True
    )
    await s.update_one({"_id": "user_7"}, {"$unset": {"preferred_language": ""}})
    user = await users_coll.find_one({"user_id": 7})
    assert "preferred_language" not in user["personal_settings"]


# Extra coverage: legacy whole-doc routing ---------------------------------


async def test_find_one_xtv_pro_settings_reads_real_doc(shim):
    s, settings_coll, _ = shim
    await settings_coll.insert_one(
        {"_id": schema.DOC_XTV_PRO, "session_string": "deadbeef"}
    )
    doc = await s.find_one({"_id": "xtv_pro_settings"})
    assert doc is not None
    assert doc["_id"] == "xtv_pro_settings"  # legacy alias preserved
    assert doc["session_string"] == "deadbeef"


async def test_insert_one_virtual_doc_routes_fields(shim):
    s, settings_coll, _ = shim
    await s.insert_one(
        {
            "_id": "public_mode_config",
            "bot_name": "InitBot",
            "base_currency": "USD",
        }
    )
    assert (
        await settings_coll.find_one({"_id": schema.DOC_BRANDING})
    )["bot_name"] == "InitBot"
    assert (
        await settings_coll.find_one({"_id": schema.DOC_PAYMENTS})
    )["base_currency"] == "USD"
