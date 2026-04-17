# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""MyFiles Enterprise features.

Keeps plugins/myfiles.py focused on the legacy flow and bolts on the
Trash / Tags / Versioning / Quotas / Audit / Search / Sharing / Activity
/ Bulk / Smart-Collection handlers here, all gated by
`utils.feature_gate.feature_enabled` so they silently vanish for users
whose plan (or the bot as a whole) hasn't enabled the respective
feature.

Each screen wraps its body with the shared Rename-style chrome from
tools.mirror_leech.UIChrome.frame so MyFiles matches the rest of the bot.
"""

from __future__ import annotations

import datetime
import secrets
from typing import Any

from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from database import db
from tools.mirror_leech.UIChrome import frame, progress_block, format_bytes
from utils.feature_gate import feature_enabled
from utils.log import get_logger

logger = get_logger("plugins.myfiles_enterprise")

# Pending text-input states keyed by user id: {"kind": "tag_add"|"search"|
# "share_pwd"|..., "file_id": str | None, "meta": dict}
_pending: dict[int, dict] = {}


def _drop_pending(user_id: int) -> None:
    _pending.pop(user_id, None)


def _oid(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Quota header (used inline by the legacy myfiles menu via import)
# ---------------------------------------------------------------------------

async def render_quota_header(user_id: int) -> str | None:
    """Return a one-line quota header for the MyFiles main screen, or
    None when the feature is disabled for this user."""
    if not await feature_enabled("myfiles_quotas", user_id):
        return None
    doc = await db.myfiles_get_quota(user_id)
    used = int(doc.get("storage_used_bytes", 0))
    quota = int(doc.get("storage_quota_bytes", 0))
    if quota <= 0:
        # Inherit plan default
        defaults = (await db.get_setting("myfiles_default_quotas", {})) or {}
        plan = "free"
        if Config.PUBLIC_MODE and hasattr(db, "get_user"):
            user = await db.get_user(user_id)
            if user and user.get("is_premium"):
                plan = user.get("premium_plan") or "standard"
        plan_q = (defaults.get(plan) or {}).get("storage_bytes")
        if plan_q:
            quota = int(plan_q)
    if quota <= 0:
        pct = 0.0
        cap = "∞"
    else:
        pct = min(1.0, used / quota) if quota else 0.0
        cap = format_bytes(float(quota))
    bar = progress_block(pct).splitlines()[-1]  # grab just the bar
    return f"> 💾 `{format_bytes(float(used))}` / `{cap}`\n> {bar}"


# ---------------------------------------------------------------------------
# Trash / Recycle Bin
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^mf_trash_list$"))
async def trash_list(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Papierkorb ist deaktiviert.", show_alert=True)
        return
    cursor = db.files.find(
        {"user_id": user_id, "is_deleted": True}
    ).sort("deleted_at", -1).limit(50)
    rows: list[list[InlineKeyboardButton]] = []
    body_lines: list[str] = []
    count = 0
    async for f in cursor:
        count += 1
        body_lines.append(
            f"> 🗑 `{str(f.get('file_name',''))[:40]}`"
        )
        rows.append([
            InlineKeyboardButton(
                f"♻️ {str(f.get('file_name',''))[:20]}",
                callback_data=f"mf_trash_restore_{f['_id']}",
            ),
            InlineKeyboardButton(
                "🔥", callback_data=f"mf_trash_purge_{f['_id']}"
            ),
        ])
    if count == 0:
        body_lines = ["> Papierkorb ist leer."]
    rows.append([
        InlineKeyboardButton("🔥 Leeren", callback_data="mf_trash_empty"),
        InlineKeyboardButton("← Zurück", callback_data="myfiles_main"),
    ])
    text = frame(
        f"🗑 **Papierkorb** ({count})",
        "\n".join(body_lines),
    )
    try:
        await cq.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(rows)
        )
    except Exception:
        pass
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_trash_restore_([0-9a-f]{24})$"))
async def trash_restore(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Deaktiviert.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_trash_restore_"))
    if fid is None:
        await cq.answer("Ungültige ID.", show_alert=True)
        return
    result = await db.files.update_one(
        {"_id": fid, "user_id": user_id, "is_deleted": True},
        {"$set": {"is_deleted": False},
         "$unset": {"deleted_at": ""}},
    )
    if result.modified_count:
        await db.audit_myfiles(user_id, "restore", file_id=fid)
        await db.log_myfiles_activity(user_id, "restored", file_id=fid)
        await cq.answer("♻️ Wiederhergestellt.")
    else:
        await cq.answer("Datei nicht gefunden.", show_alert=True)
    await trash_list(client, cq)


@Client.on_callback_query(filters.regex(r"^mf_trash_purge_([0-9a-f]{24})$"))
async def trash_purge(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Deaktiviert.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_trash_purge_"))
    if fid is None:
        await cq.answer("Ungültige ID.", show_alert=True)
        return
    doc = await db.files.find_one({"_id": fid, "user_id": user_id})
    if not doc:
        await cq.answer("Datei nicht gefunden.", show_alert=True)
        return
    await db.files.delete_one({"_id": fid})
    await db.myfiles_incr_quota(
        user_id,
        bytes_delta=-int(doc.get("size_bytes", 0) or 0),
        file_delta=-1,
    )
    await db.audit_myfiles(user_id, "purge", file_id=fid)
    await cq.answer("🔥 Endgültig gelöscht.")
    await trash_list(client, cq)


@Client.on_callback_query(filters.regex(r"^mf_trash_empty$"))
async def trash_empty(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Deaktiviert.", show_alert=True)
        return
    # Confirmation step
    if cq.data == "mf_trash_empty":
        text = frame(
            "🔥 **Papierkorb leeren**",
            "> Alle Dateien werden endgültig entfernt. Sicher?",
        )
        await cq.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ja, leeren",
                                      callback_data="mf_trash_empty_yes")],
                [InlineKeyboardButton("← Abbrechen",
                                      callback_data="mf_trash_list")],
            ]),
        )
        await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_trash_empty_yes$"))
async def trash_empty_yes(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Deaktiviert.", show_alert=True)
        return
    aggregate = await db.files.aggregate([
        {"$match": {"user_id": user_id, "is_deleted": True}},
        {"$group": {
            "_id": None,
            "bytes": {"$sum": {"$ifNull": ["$size_bytes", 0]}},
            "count": {"$sum": 1},
        }},
    ]).to_list(length=1)
    bytes_delta = int((aggregate[0]["bytes"] if aggregate else 0) or 0)
    file_delta = int((aggregate[0]["count"] if aggregate else 0) or 0)
    res = await db.files.delete_many({"user_id": user_id, "is_deleted": True})
    if file_delta:
        await db.myfiles_incr_quota(
            user_id, bytes_delta=-bytes_delta, file_delta=-file_delta
        )
    await db.audit_myfiles(
        user_id, "bulk_purge", meta={"count": res.deleted_count}
    )
    await cq.answer(f"🔥 {res.deleted_count} Dateien entfernt.")
    await trash_list(client, cq)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def _sanitize_tag(raw: str) -> str | None:
    t = raw.strip().lstrip("#").lower()
    if not t or any(c.isspace() for c in t) or len(t) > 24:
        return None
    return t


@Client.on_callback_query(filters.regex(r"^mf_tag_start_([0-9a-f]{24})$"))
async def tag_start(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_tags", user_id):
        await cq.answer("Tags deaktiviert.", show_alert=True)
        return
    fid = cq.data.removeprefix("mf_tag_start_")
    _pending[user_id] = {"kind": "tag_edit", "file_id": fid}
    doc = await db.files.find_one({"_id": _oid(fid), "user_id": user_id})
    tags = doc.get("tags", []) if doc else []
    body = (
        "> Sende die Tags die du setzen willst, jeweils mit `+tag` zum\n"
        "> Hinzufügen oder `-tag` zum Entfernen.\n"
        f"> Aktuelle Tags: `{', '.join(tags) or '—'}`"
    )
    await cq.message.edit_text(
        frame("#️⃣ **Tags bearbeiten**", body),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Abbrechen",
                                  callback_data=f"myfiles_file_{fid}")],
        ]),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_tag_open_([a-z0-9_\-]+)$"))
async def tag_open(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_tags", user_id):
        await cq.answer("Tags deaktiviert.", show_alert=True)
        return
    tag = cq.data.removeprefix("mf_tag_open_")
    cursor = db.files.find({
        "user_id": user_id,
        "tags": tag,
        "is_deleted": {"$ne": True},
    }).sort("created_at", -1).limit(20)
    rows: list[list[InlineKeyboardButton]] = []
    body_lines: list[str] = []
    async for f in cursor:
        body_lines.append(f"> 📄 `{str(f.get('file_name',''))[:40]}`")
        rows.append([InlineKeyboardButton(
            f"📄 {str(f.get('file_name',''))[:30]}",
            callback_data=f"myfiles_file_{f['_id']}",
        )])
    if not body_lines:
        body_lines = ["> Keine Dateien mit diesem Tag."]
    rows.append([InlineKeyboardButton(
        "← Tag-Übersicht", callback_data="mf_tag_list"
    )])
    await cq.message.edit_text(
        frame(f"#️⃣ **Tag `{tag}`**", "\n".join(body_lines)),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_tag_list$"))
async def tag_list(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_tags", user_id):
        await cq.answer("Tags deaktiviert.", show_alert=True)
        return
    pipeline = [
        {"$match": {"user_id": user_id, "is_deleted": {"$ne": True}}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "c": {"$sum": 1}}},
        {"$sort": {"c": -1}},
        {"$limit": 40},
    ]
    rows: list[list[InlineKeyboardButton]] = []
    body_lines: list[str] = []
    async for row in db.files.aggregate(pipeline):
        body_lines.append(f"> #{row['_id']} — `{row['c']}` Datei(en)")
        rows.append([InlineKeyboardButton(
            f"#{row['_id']} ({row['c']})",
            callback_data=f"mf_tag_open_{row['_id']}",
        )])
    if not body_lines:
        body_lines = ["> Noch keine Tags vergeben."]
    rows.append([InlineKeyboardButton(
        "← Zurück", callback_data="myfiles_main"
    )])
    await cq.message.edit_text(
        frame("#️⃣ **Tag-Übersicht**", "\n".join(body_lines)),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await cq.answer()


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^mf_ver_list_([0-9a-f]{24})$"))
async def version_list(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_versions", user_id):
        await cq.answer("Versioning deaktiviert.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_ver_list_"))
    if fid is None:
        await cq.answer("Ungültige ID.", show_alert=True)
        return
    current = await db.files.find_one({"_id": fid, "user_id": user_id})
    if not current:
        await cq.answer("Datei fehlt.", show_alert=True)
        return
    root = current.get("version_of") or fid
    cursor = db.files.find({
        "user_id": user_id,
        "$or": [{"_id": root}, {"version_of": root}],
    }).sort("version_number", -1).limit(20)
    rows: list[list[InlineKeyboardButton]] = []
    body_lines: list[str] = []
    async for v in cursor:
        marker = "✅" if v.get("is_current_version") else "•"
        body_lines.append(
            f"> {marker} v{v.get('version_number',1)} — "
            f"`{str(v.get('file_name',''))[:36]}`"
        )
        if not v.get("is_current_version"):
            rows.append([InlineKeyboardButton(
                f"♻️ Zurück auf v{v.get('version_number',1)}",
                callback_data=f"mf_ver_restore_{v['_id']}",
            )])
    rows.append([InlineKeyboardButton(
        "← Zurück zur Datei",
        callback_data=f"myfiles_file_{fid}",
    )])
    await cq.message.edit_text(
        frame("📜 **Versionen**", "\n".join(body_lines) or "> —"),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_ver_restore_([0-9a-f]{24})$"))
async def version_restore(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_versions", user_id):
        await cq.answer("Versioning deaktiviert.", show_alert=True)
        return
    target_id = _oid(cq.data.removeprefix("mf_ver_restore_"))
    if target_id is None:
        await cq.answer("Ungültige ID.", show_alert=True)
        return
    target = await db.files.find_one({"_id": target_id, "user_id": user_id})
    if not target:
        await cq.answer("Version fehlt.", show_alert=True)
        return
    root = target.get("version_of") or target_id
    await db.files.update_many(
        {"user_id": user_id, "$or": [{"_id": root}, {"version_of": root}]},
        {"$set": {"is_current_version": False}},
    )
    await db.files.update_one(
        {"_id": target_id}, {"$set": {"is_current_version": True}}
    )
    await db.audit_myfiles(user_id, "version_restore", file_id=target_id)
    await db.log_myfiles_activity(user_id, "restored", file_id=target_id)
    await cq.answer(f"♻️ v{target.get('version_number',1)} aktiv.")
    await version_list(client, cq)


# ---------------------------------------------------------------------------
# Text-input router — shared with tag/search/share prompts below.
# ---------------------------------------------------------------------------

@Client.on_message(filters.private & filters.text, group=6)
async def _enterprise_text_router(client: Client, message: Message) -> None:
    user_id = message.from_user.id
    pending = _pending.get(user_id)
    if not pending:
        return
    kind = pending.get("kind")
    if kind == "tag_edit":
        await _handle_tag_edit(client, message, pending)
    # Phase 5.6 search + 5.7 sharing text input wire in the follow-up
    # commits reuse the same _pending slot.


async def _handle_tag_edit(client: Client, message: Message, pending: dict) -> None:
    user_id = message.from_user.id
    if not await feature_enabled("myfiles_tags", user_id):
        _drop_pending(user_id)
        return
    fid = _oid(pending.get("file_id", ""))
    if fid is None:
        _drop_pending(user_id)
        return
    add: list[str] = []
    rm: list[str] = []
    for token in (message.text or "").split():
        if token.startswith("+"):
            t = _sanitize_tag(token[1:])
            if t:
                add.append(t)
        elif token.startswith("-"):
            t = _sanitize_tag(token[1:])
            if t:
                rm.append(t)
    if add:
        await db.files.update_one(
            {"_id": fid, "user_id": user_id},
            {"$addToSet": {"tags": {"$each": add[:20]}}},
        )
    if rm:
        await db.files.update_one(
            {"_id": fid, "user_id": user_id},
            {"$pull": {"tags": {"$in": rm}}},
        )
    if add or rm:
        await db.audit_myfiles(
            user_id, "tag_edit", file_id=fid,
            meta={"add": add, "remove": rm},
        )
        await db.log_myfiles_activity(user_id, "tagged", file_id=fid)
    _drop_pending(user_id)
    await message.reply_text(
        frame(
            "#️⃣ **Tags aktualisiert**",
            f"> +: `{', '.join(add) or '—'}`\n"
            f"> –: `{', '.join(rm) or '—'}`",
        )
    )


__all__ = [
    "render_quota_header",
]
