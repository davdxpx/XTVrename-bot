"""End-to-end roundtrip through the Database class: admin handler's exact
write + read pattern for filename_templates in non-public mode.
"""

import os
import sys

import pytest
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("BOT_TOKEN", "test")
os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "test")
os.environ.setdefault("MAIN_URI", "mongodb://localhost:27017")


@pytest.fixture
def db_nonpublic(monkeypatch):
    """Patch Config.PUBLIC_MODE off and replace Motor client with a mock."""
    # Clear cached module so Config picks up env
    for mod in list(sys.modules):
        if mod.startswith(("config", "database", "database_shim", "database_schema")):
            sys.modules.pop(mod, None)

    from config import Config  # noqa: E402

    monkeypatch.setattr(Config, "PUBLIC_MODE", False, raising=False)

    from motor import motor_asyncio  # noqa: E402

    monkeypatch.setattr(
        motor_asyncio,
        "AsyncIOMotorClient",
        lambda *a, **kw: AsyncMongoMockClient(),
    )

    from database import Database  # noqa: E402

    return Database


async def _roundtrip(ceo_id: int | None, monkeypatch):
    for mod in list(sys.modules):
        if mod.startswith(("config", "database", "database_shim", "database_schema")):
            sys.modules.pop(mod, None)

    from config import Config  # noqa: E402

    monkeypatch.setattr(Config, "PUBLIC_MODE", False, raising=False)
    monkeypatch.setattr(Config, "CEO_ID", ceo_id or 0, raising=False)

    from motor import motor_asyncio  # noqa: E402

    mock_client = AsyncMongoMockClient()
    monkeypatch.setattr(motor_asyncio, "AsyncIOMotorClient", lambda *a, **kw: mock_client)

    from database import Database  # noqa: E402

    db = Database()
    # Verify mode
    assert not Config.PUBLIC_MODE

    # 1) Initial read (fresh install): should bootstrap defaults via insert_one.
    settings = await db.get_settings()
    assert settings is not None
    assert "filename_templates" in settings
    assert settings["filename_templates"]["movies"] == Config.DEFAULT_FILENAME_TEMPLATES["movies"]

    # 2) Admin edits movies filename template:
    await db.update_filename_template("movies", "CUSTOM.{Title}.{Year}")

    # 3) Admin UI reloads and displays current value:
    templates = await db.get_filename_templates()
    assert templates["movies"] == "CUSTOM.{Title}.{Year}", (
        f"Roundtrip failed for ceo_id={ceo_id}: got {templates}"
    )
    # Other defaults must still resolve (callers use .get(k, DEFAULT[k])).
    return db


async def test_roundtrip_with_ceo_id(monkeypatch):
    await _roundtrip(ceo_id=123, monkeypatch=monkeypatch)


async def test_roundtrip_without_ceo_id(monkeypatch):
    await _roundtrip(ceo_id=None, monkeypatch=monkeypatch)


async def test_roundtrip_ceo_id_zero(monkeypatch):
    await _roundtrip(ceo_id=0, monkeypatch=monkeypatch)
