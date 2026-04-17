# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Retention & quota admin panel for the MyFiles Enterprise features.

Covers:
  - Trash / Audit / Activity retention in days
  - Max versions kept per file
  - Default per-plan quotas (free / standard / deluxe)

Entry point: callback `admin_mf_retention`. The admin menu in
plugins/admin/myfiles.py links to this with a new button.
"""

from __future__ import annotations

import asyncio

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import db
from utils.auth import is_admin
from utils.log import get_logger

logger = get_logger("plugins.admin.myfiles_retention")

_pending: dict[int, dict] = {}

_FIELDS = [
    ("myfiles_trash_retention_days",    "🗑 Trash retention (days)"),
    ("myfiles_audit_retention_days",    "🧾 Audit retention (days)"),
    ("myfiles_activity_retention_days", "📊 Activity retention (days)"),
    ("myfiles_max_versions",            "📜 Max versions per file"),
]


async def _render(cq: CallbackQuery) -> None:
    rows: list[list[InlineKeyboardButton]] = []
    body_lines: list[str] = []
    for key, label in _FIELDS:
        val = await db.get_setting(key, None)
        body_lines.append(f"> **{label}:** `{val if val is not None else '—'}`")
        rows.append([InlineKeyboardButton(
            f"✏️ {label}", callback_data=f"admin_mf_ret_edit_{key}"
        )])

    defaults = await db.get_setting("myfiles_default_quotas", {}) or {}
    body_lines.append("")
    body_lines.append("> **Default storage quotas (per plan):**")
    for plan in ("free", "standard", "deluxe"):
        p = defaults.get(plan, {}) or {}
        body_lines.append(
            f"> • `{plan}`: storage `{p.get('storage_bytes', 0)}` B · "
            f"files `{p.get('file_count', 0)}`"
        )
    rows.append([
        InlineKeyboardButton("✏️ Free", callback_data="admin_mf_ret_quota_free"),
        InlineKeyboardButton("✏️ Std", callback_data="admin_mf_ret_quota_standard"),
        InlineKeyboardButton("✏️ Deluxe", callback_data="admin_mf_ret_quota_deluxe"),
    ])
    rows.append([InlineKeyboardButton(
        "← Back", callback_data="admin_myfiles_settings"
    )])

    text = (
        "🗂 **MyFiles — Retention & Quotas**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n".join(body_lines)
        + "\n\n━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 **Engine:** 𝕏TV Core v3.1"
    )
    import contextlib
    with contextlib.suppress(MessageNotModified):
        await cq.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(rows)
        )


@Client.on_callback_query(
    filters.regex(
        r"^(admin_mf_retention$|admin_mf_ret_edit_|admin_mf_ret_quota_)"
    )
)
async def retention_cb(client: Client, cq: CallbackQuery) -> None:
    if not is_admin(cq.from_user.id):
        raise ContinuePropagation
    data = cq.data

    if data == "admin_mf_retention":
        await cq.answer()
        await _render(cq)
        return

    if data.startswith("admin_mf_ret_edit_"):
        key = data.replace("admin_mf_ret_edit_", "")
        if key not in {k for k, _ in _FIELDS}:
            await cq.answer("Unknown field.", show_alert=True)
            return
        _pending[cq.from_user.id] = {"kind": "mf_ret_scalar", "key": key}
        await cq.message.edit_text(
            f"✏️ Send the new **integer** value for `{key}`.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "← Cancel", callback_data="admin_mf_retention"
                )],
            ]),
        )
        await cq.answer()
        return

    if data.startswith("admin_mf_ret_quota_"):
        plan = data.replace("admin_mf_ret_quota_", "")
        if plan not in {"free", "standard", "deluxe"}:
            await cq.answer("Unknown plan.", show_alert=True)
            return
        _pending[cq.from_user.id] = {"kind": "mf_ret_quota", "plan": plan}
        await cq.message.edit_text(
            f"✏️ Send **storage_bytes, file_count** (comma-separated)\n"
            f"for plan `{plan}`. Use `0` for unlimited.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "← Cancel", callback_data="admin_mf_retention"
                )],
            ]),
        )
        await cq.answer()
        return


@Client.on_message(filters.private & filters.text, group=7)
async def _retention_text_router(client: Client, message: Message) -> None:
    user_id = message.from_user.id
    pending = _pending.get(user_id)
    if not pending:
        return
    raw = (message.text or "").strip()

    if pending.get("kind") == "mf_ret_scalar":
        try:
            val = int(raw)
        except ValueError:
            await message.reply_text("⚠️ Integer expected.")
            return
        await db.update_setting(pending["key"], max(1, val))
        _pending.pop(user_id, None)
        await message.reply_text(
            f"✅ `{pending['key']}` = `{val}` saved."
        )
        return

    if pending.get("kind") == "mf_ret_quota":
        try:
            parts = [p.strip() for p in raw.replace(" ", "").split(",")]
            storage = int(parts[0])
            count = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            await message.reply_text(
                "⚠️ Format: `<storage_bytes>,<file_count>`."
            )
            return
        defaults = await db.get_setting("myfiles_default_quotas", {}) or {}
        if not isinstance(defaults, dict):
            defaults = {}
        defaults[pending["plan"]] = {
            "storage_bytes": max(0, storage),
            "file_count": max(0, count),
        }
        await db.update_setting("myfiles_default_quotas", defaults)
        _pending.pop(user_id, None)
        await message.reply_text(
            f"✅ Plan `{pending['plan']}` quotas saved."
        )
        return
