# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Extended MyFiles handlers.

Keeps plugins/myfiles.py focused on the legacy flow and bolts on the
Trash / Tags / Versioning / Quotas / Audit / Search / Sharing / Activity
/ Bulk / Smart-Collection handlers here, all gated by
`utils.feature_gate.feature_enabled` so they silently vanish for users
whose plan (or the bot as a whole) hasn't enabled the respective
feature.

Each screen wraps its body with the shared Rename-style two-divider
chrome from tools.mirror_leech.UIChrome. Browsing screens use
`frame_plain` (no signature) — the engine signature is reserved for
messages that actually report file-processing progress.
"""

from __future__ import annotations

import contextlib
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
from tools.mirror_leech.UIChrome import format_bytes, progress_block
from tools.mirror_leech.UIChrome import frame_plain as frame
from utils.feature_gate import feature_enabled
from utils.log import get_logger

logger = get_logger("plugins.myfiles_extras")

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
        await cq.answer("Trash is disabled.", show_alert=True)
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
        body_lines = ["> Trash is empty."]
    rows.append([
        InlineKeyboardButton("🔥 Empty", callback_data="mf_trash_empty"),
        InlineKeyboardButton("← Back", callback_data="myfiles_main"),
    ])
    text = frame(
        f"🗑 **Trash** ({count})",
        "\n".join(body_lines),
    )
    with contextlib.suppress(Exception):
        await cq.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(rows)
        )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_trash_restore_([0-9a-f]{24})$"))
async def trash_restore(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Disabled.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_trash_restore_"))
    if fid is None:
        await cq.answer("Invalid ID.", show_alert=True)
        return
    result = await db.files.update_one(
        {"_id": fid, "user_id": user_id, "is_deleted": True},
        {"$set": {"is_deleted": False},
         "$unset": {"deleted_at": ""}},
    )
    if result.modified_count:
        await db.audit_myfiles(user_id, "restore", file_id=fid)
        await db.log_myfiles_activity(user_id, "restored", file_id=fid)
        await cq.answer("♻️ Restored.")
    else:
        await cq.answer("File not found.", show_alert=True)
    await trash_list(client, cq)


@Client.on_callback_query(filters.regex(r"^mf_trash_purge_([0-9a-f]{24})$"))
async def trash_purge(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Disabled.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_trash_purge_"))
    if fid is None:
        await cq.answer("Invalid ID.", show_alert=True)
        return
    doc = await db.files.find_one({"_id": fid, "user_id": user_id})
    if not doc:
        await cq.answer("File not found.", show_alert=True)
        return
    await db.files.delete_one({"_id": fid})
    await db.myfiles_incr_quota(
        user_id,
        bytes_delta=-int(doc.get("size_bytes", 0) or 0),
        file_delta=-1,
    )
    await db.audit_myfiles(user_id, "purge", file_id=fid)
    await cq.answer("🔥 Permanently deleted.")
    await trash_list(client, cq)


@Client.on_callback_query(filters.regex(r"^mf_trash_empty$"))
async def trash_empty(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Disabled.", show_alert=True)
        return
    # Confirmation step
    if cq.data == "mf_trash_empty":
        text = frame(
            "🔥 **Empty Trash**",
            "> All files will be permanently removed. Are you sure?",
        )
        await cq.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, empty",
                                      callback_data="mf_trash_empty_yes")],
                [InlineKeyboardButton("← Cancel",
                                      callback_data="mf_trash_list")],
            ]),
        )
        await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_trash_empty_yes$"))
async def trash_empty_yes(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_trash", user_id):
        await cq.answer("Disabled.", show_alert=True)
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
    await cq.answer(f"🔥 {res.deleted_count} files removed.")
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
        await cq.answer("Tags disabled.", show_alert=True)
        return
    fid = cq.data.removeprefix("mf_tag_start_")
    _pending[user_id] = {"kind": "tag_edit", "file_id": fid}
    doc = await db.files.find_one({"_id": _oid(fid), "user_id": user_id})
    tags = doc.get("tags", []) if doc else []
    body = (
        "> Send the tags you want to set. Use `+tag` to add,\n"
        "> `-tag` to remove.\n"
        f"> Current tags: `{', '.join(tags) or '—'}`"
    )
    await cq.message.edit_text(
        frame("#️⃣ **Edit Tags**", body),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Cancel",
                                  callback_data=f"myfiles_file_{fid}")],
        ]),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_tag_open_([a-z0-9_\-]+)$"))
async def tag_open(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_tags", user_id):
        await cq.answer("Tags disabled.", show_alert=True)
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
        body_lines = ["> No files carry this tag."]
    rows.append([InlineKeyboardButton(
        "← Tag overview", callback_data="mf_tag_list"
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
        await cq.answer("Tags disabled.", show_alert=True)
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
        body_lines.append(f"> #{row['_id']} — `{row['c']}` file(s)")
        rows.append([InlineKeyboardButton(
            f"#{row['_id']} ({row['c']})",
            callback_data=f"mf_tag_open_{row['_id']}",
        )])
    if not body_lines:
        body_lines = ["> No tags assigned yet."]
    rows.append([InlineKeyboardButton(
        "← Back", callback_data="myfiles_main"
    )])
    await cq.message.edit_text(
        frame("#️⃣ **Tag Overview**", "\n".join(body_lines)),
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
        await cq.answer("Versioning disabled.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_ver_list_"))
    if fid is None:
        await cq.answer("Invalid ID.", show_alert=True)
        return
    current = await db.files.find_one({"_id": fid, "user_id": user_id})
    if not current:
        await cq.answer("File missing.", show_alert=True)
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
                f"♻️ Revert to v{v.get('version_number',1)}",
                callback_data=f"mf_ver_restore_{v['_id']}",
            )])
    rows.append([InlineKeyboardButton(
        "← Back to file",
        callback_data=f"myfiles_file_{fid}",
    )])
    await cq.message.edit_text(
        frame("📜 **Versions**", "\n".join(body_lines) or "> —"),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_ver_restore_([0-9a-f]{24})$"))
async def version_restore(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_versions", user_id):
        await cq.answer("Versioning disabled.", show_alert=True)
        return
    target_id = _oid(cq.data.removeprefix("mf_ver_restore_"))
    if target_id is None:
        await cq.answer("Invalid ID.", show_alert=True)
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
    await cq.answer(f"♻️ v{target.get('version_number',1)} active.")
    await version_list(client, cq)


# ---------------------------------------------------------------------------
# Text-input router — shared with tag/search/share prompts below.
# ---------------------------------------------------------------------------

async def _extras_text_router(client: Client, message: Message) -> None:
    """Legacy text-router signature kept for the unified v2 router below
    to delegate to. Not a Pyrogram handler on its own anymore — the v2
    decorator is the single registered handler."""
    user_id = message.from_user.id
    pending = _pending.get(user_id)
    if not pending:
        return
    kind = pending.get("kind")
    if kind == "tag_edit":
        await _handle_tag_edit(client, message, pending)


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
            "#️⃣ **Tags updated**",
            f"> +: `{', '.join(add) or '—'}`\n"
            f"> –: `{', '.join(rm) or '—'}`",
        )
    )


# ---------------------------------------------------------------------------
# Advanced Search (Phase 5.6)
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^mf_search_start$"))
async def search_start(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_search", user_id):
        await cq.answer("Search disabled.", show_alert=True)
        return
    _pending[user_id] = {"kind": "search_query"}
    body = (
        "> Send your search query. Operators:\n"
        "> `tag:vacation` `-tag:old` `ext:mp4`\n"
        "> `size:>500mb` `size:<1gb`\n"
        "> `before:2026-01` `after:2025-06`\n"
        "> Free text → filename (regex allowed)."
    )
    await cq.message.edit_text(
        frame("🔎 **MyFiles Search**", body),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Cancel", callback_data="myfiles_main")],
        ]),
    )
    await cq.answer()


async def _handle_search_query(client: Client, message: Message, pending: dict) -> None:
    from utils.myfiles_search import build_query
    user_id = message.from_user.id
    if not await feature_enabled("myfiles_search", user_id):
        _drop_pending(user_id)
        return
    _drop_pending(user_id)
    q = build_query(message.text or "", user_id=user_id)
    cursor = db.files.find(q).sort("created_at", -1).limit(20)
    rows: list[list[InlineKeyboardButton]] = []
    lines: list[str] = []
    count = 0
    async for f in cursor:
        count += 1
        lines.append(
            f"> 📄 `{str(f.get('file_name',''))[:42]}` · "
            f"`{format_bytes(float(f.get('size_bytes', 0) or 0))}`"
        )
        rows.append([InlineKeyboardButton(
            f"📄 {str(f.get('file_name',''))[:30]}",
            callback_data=f"myfiles_file_{f['_id']}",
        )])
    if not lines:
        lines = ["> No matches."]
    rows.append([InlineKeyboardButton(
        "🔎 New search", callback_data="mf_search_start",
    )])
    rows.append([InlineKeyboardButton("← Back", callback_data="myfiles_main")])
    await message.reply_text(
        frame(
            f"🔎 **Search Results** ({count})",
            "\n".join(lines),
        ),
        reply_markup=InlineKeyboardMarkup(rows),
    )


# ---------------------------------------------------------------------------
# Granular Sharing (Phase 5.7)
# ---------------------------------------------------------------------------

_EXPIRY_CHOICES = [
    ("1h",  "1 hour",  3600),
    ("1d",  "1 day",   86400),
    ("7d",  "7 days",  7 * 86400),
    ("30d", "30 days", 30 * 86400),
    ("inf", "never",   0),
]
_VIEW_CHOICES = [("1", 1), ("5", 5), ("25", 25), ("inf", 0)]
_ACCESS_CHOICES = [("read", "👁 View"), ("download", "⬇️ Download")]


def _share_cfg_for(user_id: int, fid: str) -> dict:
    state = _pending.get(user_id)
    if state and state.get("kind") == "share_cfg" and state.get("file_id") == fid:
        return state["cfg"]
    cfg = {
        "access": "download",
        "expiry_key": "7d",
        "expiry_seconds": 7 * 86400,
        "max_views": 0,
        "password": None,
    }
    _pending[user_id] = {"kind": "share_cfg", "file_id": fid, "cfg": cfg}
    return cfg


async def _render_share_cfg(cq: CallbackQuery, fid: str) -> None:
    user_id = cq.from_user.id
    cfg = _share_cfg_for(user_id, fid)
    exp_label = next(
        (lab for k, lab, _ in _EXPIRY_CHOICES if k == cfg["expiry_key"]),
        cfg["expiry_key"],
    )
    body = (
        f"> **Access:** {'👁 View' if cfg['access']=='read' else '⬇️ Download'}\n"
        f"> **Expires:** {exp_label}\n"
        f"> **Max views:** "
        f"{cfg['max_views'] if cfg['max_views'] else '∞'}\n"
        f"> **Password:** {'🔒 set' if cfg['password'] else '—'}"
    )
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([
        InlineKeyboardButton(lab, callback_data=f"mf_shcfg_acc_{fid}_{k}")
        for k, lab in _ACCESS_CHOICES
    ])
    rows.append([
        InlineKeyboardButton(lab, callback_data=f"mf_shcfg_exp_{fid}_{k}")
        for k, lab, _ in _EXPIRY_CHOICES
    ])
    rows.append([
        InlineKeyboardButton(
            ("∞" if v == 0 else v_lbl),
            callback_data=f"mf_shcfg_views_{fid}_{v}",
        )
        for v_lbl, v in _VIEW_CHOICES
    ])
    rows.append([
        InlineKeyboardButton("🔒 Set password",
                             callback_data=f"mf_shcfg_pwd_{fid}"),
        InlineKeyboardButton("🧹 Clear password",
                             callback_data=f"mf_shcfg_pwdclr_{fid}"),
    ])
    rows.append([
        InlineKeyboardButton("✅ Generate link",
                             callback_data=f"mf_shcfg_done_{fid}"),
        InlineKeyboardButton("← Back",
                             callback_data=f"myfiles_file_{fid}"),
    ])
    await cq.message.edit_text(
        frame("🔗 **Configure Share Link**", body),
        reply_markup=InlineKeyboardMarkup(rows),
    )


@Client.on_callback_query(filters.regex(r"^mf_share_cfg_([0-9a-f]{24})$"))
async def share_cfg_open(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        await cq.answer("Sharing disabled.", show_alert=True)
        return
    fid = cq.data.removeprefix("mf_share_cfg_")
    _share_cfg_for(user_id, fid)
    await _render_share_cfg(cq, fid)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_shcfg_acc_([0-9a-f]{24})_(read|download)$"))
async def share_cfg_access(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        await cq.answer("Sharing disabled.", show_alert=True)
        return
    _, _, rest = cq.data.partition("mf_shcfg_acc_")
    fid, _, mode = rest.rpartition("_")
    cfg = _share_cfg_for(user_id, fid)
    cfg["access"] = mode
    await _render_share_cfg(cq, fid)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_shcfg_exp_([0-9a-f]{24})_([a-z0-9]+)$"))
async def share_cfg_expiry(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        await cq.answer("Sharing disabled.", show_alert=True)
        return
    rest = cq.data.removeprefix("mf_shcfg_exp_")
    fid, _, key = rest.rpartition("_")
    secs = next((s for k, _, s in _EXPIRY_CHOICES if k == key), None)
    if secs is None:
        await cq.answer("Unknown choice.", show_alert=True)
        return
    cfg = _share_cfg_for(user_id, fid)
    cfg["expiry_key"] = key
    cfg["expiry_seconds"] = secs
    await _render_share_cfg(cq, fid)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_shcfg_views_([0-9a-f]{24})_(\d+)$"))
async def share_cfg_views(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        await cq.answer("Sharing disabled.", show_alert=True)
        return
    rest = cq.data.removeprefix("mf_shcfg_views_")
    fid, _, n = rest.rpartition("_")
    cfg = _share_cfg_for(user_id, fid)
    cfg["max_views"] = int(n)
    await _render_share_cfg(cq, fid)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_shcfg_pwd_([0-9a-f]{24})$"))
async def share_cfg_pwd_prompt(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        await cq.answer("Sharing disabled.", show_alert=True)
        return
    fid = cq.data.removeprefix("mf_shcfg_pwd_")
    _pending[user_id] = {
        "kind": "share_password",
        "file_id": fid,
        "cfg": _share_cfg_for(user_id, fid),
    }
    await cq.message.edit_text(
        frame(
            "🔒 **Set Password**",
            "> Send the password as the next message.\n"
            "> Empty message or `cancel` aborts.",
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Cancel",
                                  callback_data=f"mf_share_cfg_{fid}")],
        ]),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_shcfg_pwdclr_([0-9a-f]{24})$"))
async def share_cfg_pwd_clear(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        await cq.answer("Sharing disabled.", show_alert=True)
        return
    fid = cq.data.removeprefix("mf_shcfg_pwdclr_")
    cfg = _share_cfg_for(user_id, fid)
    cfg["password"] = None
    await _render_share_cfg(cq, fid)
    await cq.answer("🧹 Password removed.")


@Client.on_callback_query(filters.regex(r"^mf_shcfg_done_([0-9a-f]{24})$"))
async def share_cfg_done(client: Client, cq: CallbackQuery) -> None:
    import hashlib

    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        await cq.answer("Sharing disabled.", show_alert=True)
        return
    fid = cq.data.removeprefix("mf_shcfg_done_")
    cfg = _share_cfg_for(user_id, fid)

    token = secrets.token_urlsafe(16)
    expires_at = None
    if cfg.get("expiry_seconds"):
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=int(cfg["expiry_seconds"])
        )
    pwd_hash = None
    if cfg.get("password"):
        pwd_hash = hashlib.sha256(
            cfg["password"].encode("utf-8")
        ).hexdigest()

    doc = {
        "token": token,
        "owner_id": user_id,
        "target_type": "file",
        "target_ids": [fid],
        "access_mode": cfg.get("access", "download"),
        "max_views": int(cfg.get("max_views", 0)),
        "views": 0,
        "password_hash": pwd_hash,
        "expires_at": expires_at,
    }
    share_id = await db.myfiles_create_share(doc)
    if not share_id:
        await cq.answer("Could not generate share link.",
                        show_alert=True)
        return

    _drop_pending(user_id)
    await db.audit_myfiles(user_id, "share_create",
                           file_id=_oid(fid),
                           meta={"token": token,
                                 "max_views": cfg.get("max_views", 0)})
    await db.log_myfiles_activity(user_id, "shared", file_id=_oid(fid))

    me = await client.get_me()
    link = f"https://t.me/{me.username}?start=share_{token}"
    body = (
        f"> ✅ Link generated\n"
        f"> Access: {'👁 View' if cfg['access']=='read' else '⬇️ Download'}\n"
        f"> Expires: {cfg['expiry_key']}\n"
        f"> Max views: "
        f"{cfg['max_views'] if cfg['max_views'] else '∞'}\n\n"
        f"`{link}`"
    )
    await cq.message.edit_text(
        frame("🔗 **Share Link Generated**", body),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Back to file",
                                  callback_data=f"myfiles_file_{fid}")],
        ]),
    )
    await cq.answer()


async def _handle_share_password(client: Client, message: Message, pending: dict) -> None:
    user_id = message.from_user.id
    if not await feature_enabled("myfiles_sharing", user_id):
        _drop_pending(user_id)
        return
    raw = (message.text or "").strip()
    fid = pending.get("file_id")
    cfg = pending.get("cfg", {})
    if raw.lower() in {"", "cancel", "abort"}:
        _drop_pending(user_id)
        await message.reply_text("Cancelled.")
        return
    cfg["password"] = raw[:64]
    _pending[user_id] = {"kind": "share_cfg", "file_id": fid, "cfg": cfg}
    await message.reply_text(
        frame(
            "🔒 **Password Set**",
            "> Reopen the share configurator on the file to generate\n"
            "> the link.",
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Back to share configurator",
                                  callback_data=f"mf_share_cfg_{fid}")],
        ]),
    )


# ---------------------------------------------------------------------------
# Activity Feed (Phase 5.8)
# ---------------------------------------------------------------------------

_EVENT_ICON = {
    "viewed": "👁",
    "downloaded": "⬇️",
    "shared": "🔗",
    "edited": "✏️",
    "restored": "♻️",
    "tagged": "#️⃣",
    "deleted": "🗑",
    "moved": "📂",
}


def _fmt_event_time(dt: datetime.datetime) -> str:
    now = datetime.datetime.utcnow()
    delta = now - dt
    if delta.days >= 7:
        return dt.strftime("%Y-%m-%d")
    if delta.days >= 1:
        return f"{delta.days}d ago"
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{minutes // 60}h ago"


@Client.on_callback_query(filters.regex(r"^mf_activity_list$"))
async def activity_list(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_activity", user_id):
        await cq.answer("Activity disabled.", show_alert=True)
        return
    if db.myfiles_activity is None:
        await cq.answer("Database offline.", show_alert=True)
        return
    cursor = db.myfiles_activity.find({"user_id": user_id}).sort("created_at", -1).limit(50)
    lines: list[str] = []
    count = 0
    async for ev in cursor:
        count += 1
        when = _fmt_event_time(ev.get("created_at") or datetime.datetime.utcnow())
        icon = _EVENT_ICON.get(ev.get("event", ""), "•")
        fid = ev.get("file_id")
        ref = f"`{str(fid)[:10]}`" if fid else ""
        lines.append(f"> {icon} `{ev.get('event','?')}` {ref} · {when}")
    if not lines:
        lines = ["> No activity yet."]
    await cq.message.edit_text(
        frame(f"📊 **Activity** ({count})", "\n".join(lines)),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Back", callback_data="myfiles_main")],
        ]),
    )
    await cq.answer()


# ---------------------------------------------------------------------------
# Extend the text router with the new input kinds.
# ---------------------------------------------------------------------------

async def _dispatch_pending_text(client: Client, message: Message, pending: dict) -> bool:
    """Handle the non-tag input kinds added in this module. Returns True
    when the message was consumed."""
    kind = pending.get("kind")
    if kind == "search_query":
        await _handle_search_query(client, message, pending)
        return True
    if kind == "share_password":
        await _handle_share_password(client, message, pending)
        return True
    return False


# Splice the new dispatcher into the existing text router (which only
# knows about tag_edit). We monkey-patch by replacing the handler's
# closure target — cleanest way without duplicating the handler.
_orig_tag_text_router = _extras_text_router


@Client.on_message(filters.private & filters.text, group=6)
async def _extras_text_router_v2(client: Client, message: Message) -> None:
    user_id = message.from_user.id
    pending = _pending.get(user_id)
    if not pending:
        return
    kind = pending.get("kind")
    if kind == "tag_edit":
        await _handle_tag_edit(client, message, pending)
        return
    if await _dispatch_pending_text(client, message, pending):
        return


# ---------------------------------------------------------------------------
# Bulk Operations (Phase 5.9)
# ---------------------------------------------------------------------------

async def _selected_file_oids(user_id: int) -> list[ObjectId]:
    """Read the multi-select list from the user's MyFiles state."""
    try:
        from plugins.myfiles import get_myfiles_state
    except Exception:
        return []
    state = await get_myfiles_state(user_id)
    ids: list[ObjectId] = []
    for fid in state.get("selected_files", []) or []:
        oid = _oid(str(fid))
        if oid is not None:
            ids.append(oid)
    return ids


@Client.on_callback_query(filters.regex(r"^mf_bulk_tag_start$"))
async def bulk_tag_start(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_bulk", user_id):
        await cq.answer("Bulk ops disabled.", show_alert=True)
        return
    ids = await _selected_file_oids(user_id)
    if not ids:
        await cq.answer("Nothing selected.", show_alert=True)
        return
    _pending[user_id] = {"kind": "bulk_tag", "oids": [str(i) for i in ids]}
    await cq.message.edit_text(
        frame(
            "#️⃣ **Bulk Tag**",
            f"> Applies tags to **{len(ids)}** file(s).\n"
            "> Same syntax as the single-file editor: `+foo -bar`.",
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Cancel", callback_data="myfiles_main")],
        ]),
    )
    await cq.answer()


async def _handle_bulk_tag(client: Client, message: Message, pending: dict) -> None:
    user_id = message.from_user.id
    if not await feature_enabled("myfiles_bulk", user_id):
        _drop_pending(user_id)
        return
    oids = [ObjectId(s) for s in pending.get("oids", [])]
    _drop_pending(user_id)
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
        await db.files.update_many(
            {"_id": {"$in": oids}, "user_id": user_id},
            {"$addToSet": {"tags": {"$each": add[:20]}}},
        )
    if rm:
        await db.files.update_many(
            {"_id": {"$in": oids}, "user_id": user_id},
            {"$pull": {"tags": {"$in": rm}}},
        )
    await db.audit_myfiles(
        user_id, "bulk_tag", meta={"count": len(oids), "add": add, "remove": rm}
    )
    await message.reply_text(
        frame(
            "#️⃣ **Bulk Tag Complete**",
            f"> Updated: **{len(oids)}** file(s)\n"
            f"> +: `{', '.join(add) or '—'}`\n"
            f"> –: `{', '.join(rm) or '—'}`",
        )
    )


@Client.on_callback_query(filters.regex(r"^mf_bulk_pin$"))
async def bulk_pin(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_bulk", user_id):
        await cq.answer("Bulk ops disabled.", show_alert=True)
        return
    ids = await _selected_file_oids(user_id)
    if not ids:
        await cq.answer("Nothing selected.", show_alert=True)
        return
    res = await db.files.update_many(
        {"_id": {"$in": ids}, "user_id": user_id},
        {"$set": {"pinned": True}},
    )
    await db.audit_myfiles(user_id, "bulk_pin", meta={"count": res.modified_count})
    await cq.answer(f"📌 Pinned {res.modified_count}.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^mf_bulk_unpin$"))
async def bulk_unpin(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_bulk", user_id):
        await cq.answer("Bulk ops disabled.", show_alert=True)
        return
    ids = await _selected_file_oids(user_id)
    if not ids:
        await cq.answer("Nothing selected.", show_alert=True)
        return
    res = await db.files.update_many(
        {"_id": {"$in": ids}, "user_id": user_id},
        {"$set": {"pinned": False}},
    )
    await cq.answer(f"📌 Unpinned {res.modified_count}.", show_alert=True)


# ---------------------------------------------------------------------------
# Smart Collections (Phase 5.11)
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^mf_smart_list$"))
async def smart_list(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_smart", user_id):
        await cq.answer("Smart Collections disabled.", show_alert=True)
        return
    cursor = db.folders.find({
        "user_id": user_id,
        "type": "smart",
        "is_deleted": {"$ne": True},
    }).sort("created_at", -1)
    rows: list[list[InlineKeyboardButton]] = []
    body_lines: list[str] = []
    async for folder in cursor:
        body_lines.append(
            f"> 🧠 {folder.get('icon','')} **{folder.get('name','Smart')}** — "
            f"`{folder.get('description','')[:40]}`"
        )
        rows.append([InlineKeyboardButton(
            f"🧠 {folder.get('name','Smart')}",
            callback_data=f"mf_smart_open_{folder['_id']}",
        )])
    if not body_lines:
        body_lines = [
            "> No Smart Collections yet.\n"
            "> Tap **Create** to add your first rule."
        ]
    rows.append([InlineKeyboardButton(
        "➕ Create", callback_data="mf_smart_create_start"
    )])
    rows.append([InlineKeyboardButton(
        "← Back", callback_data="myfiles_main"
    )])
    await cq.message.edit_text(
        frame("🧠 **Smart Collections**", "\n".join(body_lines)),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_smart_create_start$"))
async def smart_create_start(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_smart", user_id):
        await cq.answer("Smart Collections disabled.", show_alert=True)
        return
    _pending[user_id] = {"kind": "smart_create"}
    body = (
        "> Send two lines:\n"
        "> 1. **Name** of the collection\n"
        "> 2. **Rule** — same syntax as the search DSL\n"
        "> (`tag:vacation`, `size:>500mb`, `ext:mp4`, …)\n\n"
        "> Example:\n"
        "> ```\n"
        "> Large Videos\n"
        "> ext:mp4 size:>500mb\n"
        "> ```"
    )
    await cq.message.edit_text(
        frame("🧠 **New Smart Collection**", body),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← Cancel", callback_data="mf_smart_list")],
        ]),
    )
    await cq.answer()


async def _handle_smart_create(client: Client, message: Message, pending: dict) -> None:
    user_id = message.from_user.id
    if not await feature_enabled("myfiles_smart", user_id):
        _drop_pending(user_id)
        return
    lines = [line.strip() for line in (message.text or "").splitlines() if line.strip()]
    if len(lines) < 2:
        await message.reply_text(
            "⚠️ Please send both **name** and **rule** (two lines)."
        )
        return
    name, rule = lines[0][:60], lines[1][:200]
    _drop_pending(user_id)
    doc = {
        "user_id": user_id,
        "name": name,
        "type": "smart",
        "description": rule,
        "smart_rule_text": rule,
        "icon": "🧠",
        "is_deleted": False,
        "parent_folder_id": None,
        "created_at": datetime.datetime.utcnow(),
    }
    res = await db.folders.insert_one(doc)
    await db.audit_myfiles(
        user_id, "smart_create",
        folder_id=res.inserted_id, meta={"rule": rule},
    )
    await message.reply_text(
        frame(
            "🧠 **Smart Collection Created**",
            f"> **Name:** `{name}`\n"
            f"> **Rule:** `{rule}`",
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧠 Open",
                                  callback_data=f"mf_smart_open_{res.inserted_id}")],
            [InlineKeyboardButton("← Overview",
                                  callback_data="mf_smart_list")],
        ]),
    )


@Client.on_callback_query(filters.regex(r"^mf_smart_open_([0-9a-f]{24})$"))
async def smart_open(client: Client, cq: CallbackQuery) -> None:
    from utils.myfiles_search import build_query
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_smart", user_id):
        await cq.answer("Smart Collections disabled.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_smart_open_"))
    if fid is None:
        await cq.answer("Invalid ID.", show_alert=True)
        return
    folder = await db.folders.find_one({
        "_id": fid, "user_id": user_id, "type": "smart"
    })
    if not folder:
        await cq.answer("Collection missing.", show_alert=True)
        return
    rule = folder.get("smart_rule_text") or folder.get("description", "")
    q = build_query(rule, user_id=user_id)
    cursor = db.files.find(q).sort("created_at", -1).limit(30)
    rows: list[list[InlineKeyboardButton]] = []
    body: list[str] = [f"> **Rule:** `{rule}`", ""]
    count = 0
    async for f in cursor:
        count += 1
        body.append(
            f"> 📄 `{str(f.get('file_name',''))[:40]}`"
        )
        rows.append([InlineKeyboardButton(
            f"📄 {str(f.get('file_name',''))[:30]}",
            callback_data=f"myfiles_file_{f['_id']}",
        )])
    if count == 0:
        body.append("> — No matching files. —")
    rows.append([
        InlineKeyboardButton("🔥 Delete",
                             callback_data=f"mf_smart_del_{fid}"),
        InlineKeyboardButton("← Back",
                             callback_data="mf_smart_list"),
    ])
    await cq.message.edit_text(
        frame(
            f"🧠 **{folder.get('name','Smart')}** ({count})",
            "\n".join(body),
        ),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^mf_smart_del_([0-9a-f]{24})$"))
async def smart_delete(client: Client, cq: CallbackQuery) -> None:
    user_id = cq.from_user.id
    if not await feature_enabled("myfiles_smart", user_id):
        await cq.answer("Smart Collections disabled.", show_alert=True)
        return
    fid = _oid(cq.data.removeprefix("mf_smart_del_"))
    if fid is None:
        await cq.answer("Invalid ID.", show_alert=True)
        return
    await db.folders.delete_one({
        "_id": fid, "user_id": user_id, "type": "smart"
    })
    await db.audit_myfiles(user_id, "smart_delete", folder_id=fid)
    await cq.answer("🔥 Deleted.")
    cq.data = "mf_smart_list"
    await smart_list(client, cq)


# ---------------------------------------------------------------------------
# Extend the text dispatcher with the new input kinds.
# ---------------------------------------------------------------------------

_prev_dispatch = _dispatch_pending_text


async def _dispatch_pending_text(client: Client, message: Message, pending: dict) -> bool:  # type: ignore[no-redef]
    kind = pending.get("kind")
    if kind == "bulk_tag":
        await _handle_bulk_tag(client, message, pending)
        return True
    if kind == "smart_create":
        await _handle_smart_create(client, message, pending)
        return True
    return await _prev_dispatch(client, message, pending)


__all__ = [
    "render_quota_header",
]
