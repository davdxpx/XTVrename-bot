# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""DB Schema Health admin panel.

Surfaces:
  - current schema version / migration timestamps
  - collection document counts (MediaStudio-* + any legacy backups)
  - the shim's recent unknown-key write log (helps spot drift)
  - an operator "drop legacy backup collections" action (double-confirmed)
  - a dry-run trigger to re-run the mediastudio_layout migration planner
"""

from __future__ import annotations

import contextlib
import datetime as _dt

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import Config
from db import db
from db.migrations.mediastudio_layout import (
    MIGRATION_ID,
    run_mediastudio_layout_migration,
)
from plugins.admin.core import is_admin
from utils.log import get_logger

logger = get_logger("plugins.admin.db_health")


def _fmt_ts(ts) -> str:
    if not ts:
        return "—"
    try:
        return _dt.datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)


async def _collection_counts() -> list[tuple[str, int]]:
    if db.db is None:
        return []
    names = await db.db.list_collection_names()
    rows: list[tuple[str, int]] = []
    for name in sorted(names):
        if not (
            name.startswith("MediaStudio-")
            or name.endswith(db.schema.BACKUP_SUFFIX)
        ):
            continue
        try:
            count = await db.db[name].count_documents({})
        except Exception:
            count = -1
        rows.append((name, count))
    return rows


async def _render_health(callback_query: CallbackQuery):
    if db.settings is None:
        await callback_query.answer("DB not connected.", show_alert=True)
        return

    migrations_doc = (
        await db.settings.real.find_one({"_id": db.schema.DOC_SCHEMA_MIGRATIONS}) or {}
    )
    entry = migrations_doc.get(MIGRATION_ID) or {}

    unknown_writes = db.settings.recent_unknown_writes()
    counts = await _collection_counts()

    lines = [
        "🩺 **DB Schema Health**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"• Bot version: `{Config.VERSION}`",
        f"• MyFiles engine: `{Config.MYFILES_VERSION}`",
        f"• Layout migration: `{MIGRATION_ID}`",
        f"  started: {_fmt_ts(entry.get('started_at'))}",
        f"  completed: {_fmt_ts(entry.get('completed_at'))}",
        "",
        "**Collections**",
    ]
    if counts:
        for name, count in counts:
            marker = "📦" if name.startswith("MediaStudio-") else "🧳"
            lines.append(f"{marker} `{name}` — {count}")
    else:
        lines.append("__no MediaStudio collections yet__")

    lines.append("")
    lines.append("**Recent unknown-key writes**")
    if not unknown_writes:
        lines.append("__none — routing table is holding up ✅__")
    else:
        for entry in unknown_writes[-10:]:
            lines.append(
                f"• `{entry['key']}` on `{entry['doc_id']}` ({entry['op']})"
            )

    lines.append("")
    lines.append(
        f"__Last refreshed: {_dt.datetime.utcnow().strftime('%H:%M:%S UTC')}__"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Re-run migration (dry-run)", callback_data="admin_db_health_dry_run")],
            [InlineKeyboardButton("🗑 Drop legacy backup collections", callback_data="admin_db_health_drop_backups")],
            [InlineKeyboardButton("↻ Refresh", callback_data="admin_db_health")],
            [InlineKeyboardButton("← Back", callback_data="admin_system_health")],
        ]
    )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "\n".join(lines), reply_markup=keyboard
        )


async def _render_drop_confirm(callback_query: CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Yes — drop them all", callback_data="admin_db_health_drop_backups_confirm")],
            [InlineKeyboardButton("🚫 Cancel", callback_data="admin_db_health")],
        ]
    )
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "⚠️ **Drop legacy backup collections?**\n\n"
            "This permanently deletes every `*" + db.schema.BACKUP_SUFFIX + "` "
            "collection in the DB. They were created by the mediastudio_layout "
            "migration as a safety net. Only drop them once you've verified the "
            "new layout works in production.\n\n"
            "This action cannot be undone from within the bot.",
            reply_markup=keyboard,
        )


async def _run_drop_backups(callback_query: CallbackQuery):
    if db.db is None:
        await callback_query.answer("DB not connected.", show_alert=True)
        return
    dropped: list[str] = []
    names = await db.db.list_collection_names()
    suffix = db.schema.BACKUP_SUFFIX
    for name in names:
        if name.endswith(suffix):
            try:
                await db.db[name].drop()
                dropped.append(name)
            except Exception as exc:
                logger.warning("Failed to drop %s: %s", name, exc)
    await callback_query.answer(
        f"Dropped {len(dropped)} legacy backup collection(s).", show_alert=True
    )
    logger.info("Operator dropped legacy backups: %s", dropped)
    await _render_health(callback_query)


async def _run_dry_run(callback_query: CallbackQuery):
    if db.db is None:
        await callback_query.answer("DB not connected.", show_alert=True)
        return
    try:
        result = await run_mediastudio_layout_migration(
            db.db,
            public_mode=Config.PUBLIC_MODE,
            ceo_id=Config.CEO_ID,
            dry_run=True,
        )
    except Exception as exc:
        logger.exception("Dry-run failed")
        await callback_query.answer(f"Dry-run failed: {exc}", show_alert=True)
        return
    await callback_query.answer(
        f"Dry-run status: {result.get('status')}", show_alert=True
    )


# --- Handler registration ---------------------------------------------------

@Client.on_callback_query(filters.regex(r"^admin_db_health(?:_(?:dry_run|drop_backups(?:_confirm)?))?$"))
async def db_health_callback(client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("Not authorised.", show_alert=True)
        return

    data = callback_query.data
    if data == "admin_db_health":
        await _render_health(callback_query)
        # Always ack so Telegram drops the loading spinner, even when the
        # message content happened to be identical (MessageNotModified was
        # swallowed in _render_health).
        with contextlib.suppress(Exception):
            await callback_query.answer("Refreshed.")
    elif data == "admin_db_health_dry_run":
        await _run_dry_run(callback_query)
    elif data == "admin_db_health_drop_backups":
        await _render_drop_confirm(callback_query)
        with contextlib.suppress(Exception):
            await callback_query.answer()
    elif data == "admin_db_health_drop_backups_confirm":
        await _run_drop_backups(callback_query)
