"""End-to-end tests for the mediastudio_layout migration orchestrator."""

import pytest
from mongomock_motor import AsyncMongoMockClient

import database_schema as schema
from db_migrations.mediastudio_layout import run_mediastudio_layout_migration
from database_shim import SettingsCollectionShim


@pytest.fixture
async def seeded_db_non_public():
    """Simulates a non-public-mode production export: CEO personal settings
    intermixed with global config inside `global_settings`, plus a few
    scattered user docs and same-shape data collections."""
    client = AsyncMongoMockClient()
    db = client["test-maindb"]

    await db["user_settings"].insert_many(
        [
            {
                "_id": "global_settings",
                # global
                "bot_name": "OldBot",
                "myfiles_enabled": True,
                "dumb_channel_timeout": 30,
                "global_daily_egress_mb": 500,
                # CEO personal (collision!)
                "thumbnail_file_id": "CEO-THUMB",
                "templates": {"title": "{title}"},
                "preferred_language": "en",
                # unknown legacy field
                "mystery_field": "keep me",
            },
            {
                "_id": "user_42",
                "thumbnail_file_id": "USER42-THUMB",
                "preferred_language": "de",
                "usage": {"date": "2025-01-01", "egress_mb": 123},
            },
            {
                "_id": "xtv_pro_settings",
                "session_string": "SESSION",
                "tunnel_id": 7,
            },
        ]
    )
    await db["users"].insert_many(
        [
            {"user_id": 42, "first_name": "Alice", "is_premium": False},
            {"user_id": 999, "first_name": "CEO", "is_premium": True},
        ]
    )
    await db["files"].insert_many(
        [{"user_id": 42, "file_name": "a.mkv", "status": "permanent"}]
    )
    await db["folders"].insert_many([{"user_id": 42, "name": "Movies"}])
    await db["daily_stats"].insert_many([{"date": "2025-01-01", "egress_mb": 123}])
    await db["pending_payments"].insert_many(
        [{"_id": "pay1", "user_id": 42, "status": "pending"}]
    )
    await db["file_groups"].insert_many(
        [{"group_id": "g1", "user_id": 42, "files": []}]
    )
    return db


async def test_migration_creates_mediastudio_collections(seeded_db_non_public):
    db = seeded_db_non_public
    result = await run_mediastudio_layout_migration(
        db, public_mode=False, ceo_id=999
    )
    assert result["status"] == "completed"
    names = await db.list_collection_names()
    assert schema.SETTINGS_COLLECTION in names
    assert schema.USERS_COLLECTION in names
    assert schema.FILES_COLLECTION in names
    assert schema.FOLDERS_COLLECTION in names


async def test_migration_splits_global_settings_by_concern(seeded_db_non_public):
    db = seeded_db_non_public
    await run_mediastudio_layout_migration(db, public_mode=False, ceo_id=999)

    settings = db[schema.SETTINGS_COLLECTION]
    branding = await settings.find_one({"_id": schema.DOC_BRANDING})
    assert branding["bot_name"] == "OldBot"

    egress = await settings.find_one({"_id": schema.DOC_EGRESS_LIMITS})
    assert egress["dumb_channel_timeout"] == 30
    assert egress["global_daily_egress_mb"] == 500

    myfiles = await settings.find_one({"_id": schema.DOC_MYFILES_CONFIG})
    assert myfiles["myfiles_enabled"] is True


async def test_migration_routes_personal_keys_in_global_to_ceo(seeded_db_non_public):
    db = seeded_db_non_public
    await run_mediastudio_layout_migration(db, public_mode=False, ceo_id=999)

    ceo = await db[schema.USERS_COLLECTION].find_one({"user_id": 999})
    assert ceo is not None
    assert ceo["personal_settings"]["thumbnail_file_id"] == "CEO-THUMB"
    assert ceo["personal_settings"]["templates"] == {"title": "{title}"}
    assert ceo["personal_settings"]["preferred_language"] == "en"


async def test_migration_inlines_user_docs_into_users_collection(seeded_db_non_public):
    db = seeded_db_non_public
    await run_mediastudio_layout_migration(db, public_mode=False, ceo_id=999)

    alice = await db[schema.USERS_COLLECTION].find_one({"user_id": 42})
    assert alice is not None
    assert alice["personal_settings"]["thumbnail_file_id"] == "USER42-THUMB"
    assert alice["personal_settings"]["preferred_language"] == "de"
    assert alice["usage"]["egress_mb"] == 123
    # Original users-collection data is preserved (we copied first)
    assert alice.get("first_name") == "Alice"


async def test_migration_preserves_xtv_pro_settings(seeded_db_non_public):
    db = seeded_db_non_public
    await run_mediastudio_layout_migration(db, public_mode=False, ceo_id=999)
    xtv = await db[schema.SETTINGS_COLLECTION].find_one({"_id": schema.DOC_XTV_PRO})
    assert xtv["session_string"] == "SESSION"
    assert xtv["tunnel_id"] == 7


async def test_migration_preserves_unknown_fields_in_legacy_misc(seeded_db_non_public):
    db = seeded_db_non_public
    await run_mediastudio_layout_migration(db, public_mode=False, ceo_id=999)
    misc = await db[schema.SETTINGS_COLLECTION].find_one(
        {"_id": schema.LEGACY_MISC_DOC_ID}
    )
    assert misc["mystery_field"] == "keep me"


async def test_migration_creates_backups(seeded_db_non_public):
    db = seeded_db_non_public
    await run_mediastudio_layout_migration(db, public_mode=False, ceo_id=999)
    names = await db.list_collection_names()
    for legacy in ("user_settings", "users", "files", "folders"):
        assert f"{legacy}{schema.BACKUP_SUFFIX}" in names


async def test_migration_is_idempotent(seeded_db_non_public):
    db = seeded_db_non_public
    first = await run_mediastudio_layout_migration(
        db, public_mode=False, ceo_id=999
    )
    second = await run_mediastudio_layout_migration(
        db, public_mode=False, ceo_id=999
    )
    assert first["status"] == "completed"
    assert second["status"] == "already_done"
    # Data unchanged on the second run.
    branding = await db[schema.SETTINGS_COLLECTION].find_one(
        {"_id": schema.DOC_BRANDING}
    )
    assert branding["bot_name"] == "OldBot"


async def test_shim_reads_back_migrated_data(seeded_db_non_public):
    """After migration, legacy `db.settings.find_one({"_id":"global_settings"})`
    style access through the shim must still return the original fields."""
    db = seeded_db_non_public
    await run_mediastudio_layout_migration(db, public_mode=False, ceo_id=999)

    shim = SettingsCollectionShim(
        db[schema.SETTINGS_COLLECTION], db[schema.USERS_COLLECTION]
    )
    merged = await shim.find_one({"_id": "global_settings"})
    assert merged["bot_name"] == "OldBot"
    assert merged["dumb_channel_timeout"] == 30
    assert merged["myfiles_enabled"] is True

    ceo_personal = await shim.find_one({"_id": "user_999"})
    assert ceo_personal["thumbnail_file_id"] == "CEO-THUMB"

    alice_personal = await shim.find_one({"_id": "user_42"})
    assert alice_personal["preferred_language"] == "de"


async def test_dry_run_does_not_mutate(seeded_db_non_public):
    db = seeded_db_non_public
    result = await run_mediastudio_layout_migration(
        db, public_mode=False, ceo_id=999, dry_run=True
    )
    assert result["status"] == "dry_run"
    names = await db.list_collection_names()
    assert schema.SETTINGS_COLLECTION not in names  # dry-run wrote nothing
    assert schema.USERS_COLLECTION not in names
