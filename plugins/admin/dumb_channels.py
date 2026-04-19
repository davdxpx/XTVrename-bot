# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Dumb Channels admin domain.

Handles all callbacks that manage globally-shared "dumb" channels used for
auto-forwarding uploads: list/paginate, open per-channel settings, rename,
add, delete, set as default for Standard/Movie/Series, and edit the global
forward-wait timeout.

Text-input handlers for `awaiting_dumb_*` states are registered with the
shared ``text_dispatcher`` and routed here at runtime.
"""

import contextlib
import math

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin
from utils.log import get_logger

logger = get_logger("plugins.admin.dumb_channels")


# --- Render helpers ----------------------------------------------------------
# Replace the recursive self-calls the legacy dispatcher used (it rewrote
# `callback_query.data` and re-invoked itself). After the carve-out there is
# no central dispatcher to re-enter, so the rendering logic is factored out
# into these helpers and shared between the handler and the post-action
# "refresh" paths (e.g. after set-default / delete).

async def _render_dumb_menu(callback_query, page: int = 1):
    channels = await db.get_dumb_channels()

    text = (
        "📺 **Manage Dumb Channels**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "> Configure globally shared channels for auto-forwarding files.\n\n"
    )

    if not channels:
        text += "❌ __No Dumb Channels configured yet.__\n\n"

    buttons = [[InlineKeyboardButton("➕ Add New Dumb Channel", callback_data="dumbv2_start:global")]]

    if channels:
        ch_items = list(channels.items())
        total_channels = len(ch_items)
        items_per_page = 10
        total_pages = math.ceil(total_channels / items_per_page) if total_channels > 0 else 1
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_channels = ch_items[start_idx:end_idx]

        buttons.append([InlineKeyboardButton("─── Your Channels ───", callback_data="noop")])
        for ch_id, ch_name in current_channels:
            buttons.append([
                InlineKeyboardButton(f"📺 {ch_name}", callback_data=f"dumb_opt_{ch_id}")
            ])

        if total_pages > 1:
            nav = []
            if page > 1:
                nav.append(InlineKeyboardButton("⬅️", callback_data=f"dumb_menu_{page-1}"))
            nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav.append(InlineKeyboardButton("➡️", callback_data=f"dumb_menu_{page+1}"))
            buttons.append(nav)

    buttons.append([InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def _render_dumb_opt(callback_query, ch_id: str):
    channels = await db.get_dumb_channels()
    if ch_id not in channels:
        await callback_query.answer("Channel not found.", show_alert=True)
        return

    ch_name = channels[ch_id]
    default_ch = await db.get_default_dumb_channel()
    movie_ch = await db.get_movie_dumb_channel()
    series_ch = await db.get_series_dumb_channel()

    is_def = "✅" if str(ch_id) == default_ch else "❌"
    is_mov = "✅" if str(ch_id) == movie_ch else "❌"
    is_ser = "✅" if str(ch_id) == series_ch else "❌"

    text = (
        f"⚙️ **Channel Settings**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"> **Name:** `{ch_name}`\n"
        f"> **ID:** `{ch_id}`\n\n"
        f"**Current Status:**\n"
        f"> 🔸 Standard Default: `{is_def}`\n"
        f"> 🎬 Movie Default: `{is_mov}`\n"
        f"> 📺 Series Default: `{is_ser}`\n\n"
        f"Select an action below to manage this global channel."
    )

    buttons = [
        [InlineKeyboardButton("✏️ Rename Channel", callback_data=f"dumb_ren_{ch_id}")],
        [InlineKeyboardButton("🔸 Set Standard Default", callback_data=f"dumb_def_std_{ch_id}")],
        [InlineKeyboardButton("🎬 Set Movie Default", callback_data=f"dumb_def_mov_{ch_id}")],
        [InlineKeyboardButton("📺 Set Series Default", callback_data=f"dumb_def_ser_{ch_id}")],
        [InlineKeyboardButton("🗑 Delete Channel", callback_data=f"dumb_del_{ch_id}")],
        [InlineKeyboardButton("← Back to Dumb Channels", callback_data="dumb_menu")]
    ]

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# --- Callback dispatch -------------------------------------------------------
# Matches: admin_dumb_channels, admin_dumb_timeout, prompt_admin_dumb_timeout,
# dumb_menu[_N], dumb_opt_, dumb_ren_, dumb_def_{std,mov,ser}_, dumb_add,
# dumb_del_. Explicitly does NOT match `dumb_user_*` (handled elsewhere) or
# `dumbv2_*` (handled in plugins/dumb_channel.py).

@Client.on_callback_query(
    filters.regex(
        r"^(admin_dumb_channels|admin_dumb_timeout|prompt_admin_dumb_timeout|"
        r"dumb_menu|dumb_opt_|dumb_ren_|dumb_def_(?:std|mov|ser)_|dumb_add|dumb_del_)"
    )
)
async def dumb_channels_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    data = callback_query.data

    # --- Top-level entry points ------------------------------------------------
    if data == "admin_dumb_channels" or data.startswith("dumb_menu"):
        page = 1
        if data.startswith("dumb_menu") and "_" in data.replace("dumb_menu", ""):
            parts = data.split("_")
            if len(parts) >= 3:
                with contextlib.suppress(ValueError, IndexError):
                    page = int(parts[2])
        await _render_dumb_menu(callback_query, page=page)
        return

    # --- Per-channel settings --------------------------------------------------
    if data.startswith("dumb_opt_"):
        ch_id = data.replace("dumb_opt_", "")
        await _render_dumb_opt(callback_query, ch_id)
        return

    if data.startswith("dumb_ren_"):
        ch_id = data.replace("dumb_ren_", "")
        admin_sessions[user_id] = {
            "state": f"awaiting_dumb_rename_{ch_id}",
            "msg_id": callback_query.message.id,
        }
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "✏️ **Rename Channel**\n\n"
                "Please enter the new name for this global channel:\n\n"
                "__(Send `disable` to cancel)__",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data=f"dumb_opt_{ch_id}")]]
                ),
            )
        return

    if data.startswith("dumb_def_std_"):
        ch_id = data.replace("dumb_def_std_", "")
        await db.set_default_dumb_channel(ch_id)
        await callback_query.answer("Standard Default channel set.", show_alert=True)
        await _render_dumb_opt(callback_query, ch_id)
        return

    if data.startswith("dumb_def_mov_"):
        ch_id = data.replace("dumb_def_mov_", "")
        await db.set_movie_dumb_channel(ch_id)
        await callback_query.answer("Movie Default channel set.", show_alert=True)
        await _render_dumb_opt(callback_query, ch_id)
        return

    if data.startswith("dumb_def_ser_"):
        ch_id = data.replace("dumb_def_ser_", "")
        await db.set_series_dumb_channel(ch_id)
        await callback_query.answer("Series Default channel set.", show_alert=True)
        await _render_dumb_opt(callback_query, ch_id)
        return

    # --- Add / delete ----------------------------------------------------------
    if data == "dumb_add":
        admin_sessions[user_id] = {
            "state": "awaiting_dumb_add",
            "msg_id": callback_query.message.id,
        }
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "➕ **Add Dumb Channel**\n\n"
                "Please add me as an Administrator in the desired channel.\n"
                "Then, forward any message from that channel to me, OR send the Channel ID (e.g. `-100...`) or Public Username.\n\n"
                "__(Send `disable` to cancel)__",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]]
                ),
            )
        return

    if data.startswith("dumb_del_"):
        ch_id = data.replace("dumb_del_", "")
        await db.remove_dumb_channel(ch_id)
        await callback_query.answer("Channel removed.", show_alert=True)
        await _render_dumb_menu(callback_query, page=1)
        return

    # --- Global timeout --------------------------------------------------------
    if data == "admin_dumb_timeout":
        current_val = await db.get_dumb_channel_timeout()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"⏱ **Edit Dumb Channel Timeout**\n\n"
                f"This is the max time (in seconds) the bot will wait for earlier files before uploading to the Dumb Channel.\n\n"
                f"Current: `{current_val}` seconds\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("✏️ Change", callback_data="prompt_admin_dumb_timeout")],
                        [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
                    ]
                ),
            )
        return

    if data == "prompt_admin_dumb_timeout":
        admin_sessions[user_id] = {
            "state": "awaiting_dumb_timeout",
            "msg_id": callback_query.message.id,
        }
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "⏱ **Send the new timeout in seconds (e.g., 3600 for 1 hour):**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]
                ),
            )
        return


# ---------------------------------------------------------------------------
# Text-input state handler (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def handle_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_dumb_timeout, awaiting_dumb_rename_*, awaiting_dumb_add."""
    user_id = message.from_user.id

    if state == "awaiting_dumb_timeout":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_dumb_timeout")]]
                ),
            )
            return
        await db.update_dumb_channel_timeout(int(val))
        await edit_or_reply(client, message, msg_id,
            f"✅ Dumb channel timeout updated to `{val}` seconds.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Dumb Channel Timeout", callback_data="admin_dumb_timeout")]]
            ),
        )
        admin_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_dumb_rename_") and not Config.PUBLIC_MODE:
        ch_id = state.replace("awaiting_dumb_rename_", "")
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            admin_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Channel Settings", callback_data=f"dumb_opt_{ch_id}")]]
                ),
            )
            return

        channels = await db.get_dumb_channels()
        if ch_id in channels:
            channels[ch_id] = val
            doc_id = "global_settings"
            await db.settings.update_one({"_id": doc_id}, {"$set": {"dumb_channels": channels}}, upsert=True)
            await edit_or_reply(client, message, msg_id, f"✅ Channel renamed to **{val}**.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Channel Settings", callback_data=f"dumb_opt_{ch_id}")]]
                ),
            )
        admin_sessions.pop(user_id, None)
        return

    if state == "awaiting_dumb_add" and not Config.PUBLIC_MODE:
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            admin_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Dumb Channels", callback_data="dumb_menu")]]
                ),
            )
            return

        ch_id = None
        ch_name = "Custom Channel"
        if message.forward_from_chat:
            ch_id = message.forward_from_chat.id
            ch_name = message.forward_from_chat.title
        elif val:
            try:
                chat = await client.get_chat(val)
                ch_id = chat.id
                ch_name = chat.title or "Channel"
            except Exception as e:
                await edit_or_reply(client, message, msg_id,
                    f"❌ Error finding channel: {e}\nTry forwarding a message instead.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]]
                    ),
                )
                return

        if ch_id:
            invite_link = None
            try:
                invite_link = await client.export_chat_invite_link(ch_id)
            except Exception as e:
                logger.warning(f"Could not export invite link for {ch_id}: {e}")

            await db.add_dumb_channel(ch_id, ch_name, invite_link=invite_link)
            await edit_or_reply(client, message, msg_id,
                f"✅ Added Dumb Channel: **{ch_name}** (`{ch_id}`)",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Dumb Channels", callback_data="dumb_menu")]]
                ),
            )
            admin_sessions.pop(user_id, None)
        return


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_dumb_", handle_text)
