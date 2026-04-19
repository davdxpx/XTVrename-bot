"""Tests for db_migrations.helpers backup_collection and copy_collection."""

import pytest
from mongomock_motor import AsyncMongoMockClient

from db.migrations.helpers import backup_collection, copy_collection


@pytest.fixture
async def db():
    client = AsyncMongoMockClient()
    return client["test-helpers"]


async def test_backup_collection_clones_all_docs(db):
    src = db["users"]
    await src.insert_many([{"user_id": i, "name": f"u{i}"} for i in range(10)])

    result = await backup_collection(db, "users", backup_suffix="_backup_legacy")
    assert result["status"] == "backed_up"
    assert result["count"] == 10

    backup = db["users_backup_legacy"]
    assert await backup.count_documents({}) == 10


async def test_backup_collection_is_idempotent(db):
    src = db["users"]
    await src.insert_many([{"user_id": 1}, {"user_id": 2}])

    first = await backup_collection(db, "users", backup_suffix="_backup_legacy")
    second = await backup_collection(db, "users", backup_suffix="_backup_legacy")
    assert first["status"] == "backed_up"
    assert second["status"] == "already_backed_up"
    assert await db["users_backup_legacy"].count_documents({}) == 2


async def test_backup_collection_missing_source(db):
    result = await backup_collection(db, "nonexistent", backup_suffix="_backup_legacy")
    assert result["status"] == "source_missing"


async def test_copy_collection_copies_all_docs(db):
    src = db["files"]
    await src.insert_many([{"file_name": f"f{i}"} for i in range(7)])

    result = await copy_collection(db, "files", "MediaStudio-files")
    assert result["status"] == "copied"
    assert result["count"] == 7
    assert await db["MediaStudio-files"].count_documents({}) == 7


async def test_copy_collection_is_idempotent(db):
    src = db["folders"]
    await src.insert_many([{"name": "a"}, {"name": "b"}])

    await copy_collection(db, "folders", "MediaStudio-folders")
    second = await copy_collection(db, "folders", "MediaStudio-folders")
    assert second["status"] == "already_copied"
    assert await db["MediaStudio-folders"].count_documents({}) == 2


async def test_copy_collection_missing_source(db):
    result = await copy_collection(db, "nope", "MediaStudio-nope")
    assert result["status"] == "source_missing"
