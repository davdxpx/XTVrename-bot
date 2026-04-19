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
from utils.telegram.log import get_logger

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


DUD_DEFAULTS = {
    "dumb_channel_timeout": 3600,
    "dumb_channel_send_delay_s": 2,
    "dumb_channel_retry_on_error": True,
    "dumb_channel_caption_style": "clean",
    "dumb_channel_auto_thumbnail": True,
    "dumb_channel_anonymous_default": False,
    "dumb_channel_forwarding_default": False,
    "dumb_channel_default_movie_id": None,
    "dumb_channel_default_series_id": None,
    "dumb_channel_default_fallback_id": None,
}


def _fmt_seconds(s: int) -> str:
    s = int(s or 0)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m" if m else f"{h}h"


def _on_off(b: bool) -> str:
    return "on" if b else "off"


def _channel_value(value):
    if value in (None, "", 0):
        return "__not set__"
    return f"`{value}`"


async def _render_dumb_user_defaults(callback_query):
    cfg = await db.get_public_config()

    timeout_s = int(cfg.get("dumb_channel_timeout") or DUD_DEFAULTS["dumb_channel_timeout"])
    send_delay_s = int(cfg.get("dumb_channel_send_delay_s") or DUD_DEFAULTS["dumb_channel_send_delay_s"])
    retry = bool(cfg.get("dumb_channel_retry_on_error", DUD_DEFAULTS["dumb_channel_retry_on_error"]))
    caption_style = cfg.get("dumb_channel_caption_style") or DUD_DEFAULTS["dumb_channel_caption_style"]
    auto_thumb = bool(cfg.get("dumb_channel_auto_thumbnail", DUD_DEFAULTS["dumb_channel_auto_thumbnail"]))
    anon_default = bool(cfg.get("dumb_channel_anonymous_default", DUD_DEFAULTS["dumb_channel_anonymous_default"]))
    forward_default = bool(cfg.get("dumb_channel_forwarding_default", DUD_DEFAULTS["dumb_channel_forwarding_default"]))
    movie_id = cfg.get("dumb_channel_default_movie_id")
    series_id = cfg.get("dumb_channel_default_series_id")
    fallback_id = cfg.get("dumb_channel_default_fallback_id")

    timing_lines = [
        "**Timing**",
        f"⏱ Auto-delete timeout: `{_fmt_seconds(timeout_s)}`",
        f"🕒 Send delay: `{send_delay_s}s`",
        f"🔁 Retry on Telegram errors: `{_on_off(retry)}`",
    ]
    routing_lines = [
        "**Routing defaults**",
        f"🎬 Default movie channel: {_channel_value(movie_id)}",
        f"📺 Default series channel: {_channel_value(series_id)}",
        f"📦 Fallback for everything else: {_channel_value(fallback_id)}",
    ]
    behaviour_lines = [
        "**Behaviour defaults**",
        f"🏷 Caption style: `{caption_style}`",
        f"🖼 Auto-thumbnail: `{_on_off(auto_thumb)}`",
        f"👻 Anonymous mode default: `{_on_off(anon_default)}`",
        f"📥 Forwarding allowed by default: `{_on_off(forward_default)}`",
    ]

    text = "\n".join(
        [
            "**📺 Dumb Channel Settings**",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "These defaults apply to every user in public mode",
            "until they change them in their own /settings.",
            "",
            "<blockquote>" + "\n".join(timing_lines) + "</blockquote>",
            "",
            "<blockquote>" + "\n".join(routing_lines) + "</blockquote>",
            "",
            "<blockquote>" + "\n".join(behaviour_lines) + "</blockquote>",
            "",
            "> Tap a row to edit. Changes apply immediately to new users.",
        ]
    )

    buttons = [
        [
            InlineKeyboardButton("⏱ Timeout", callback_data="admin_dud_timeout"),
            InlineKeyboardButton("🕒 Send Delay", callback_data="admin_dud_send_delay"),
        ],
        [
            InlineKeyboardButton(f"🔁 Retry: {_on_off(retry)}", callback_data="admin_dud_retry"),
            InlineKeyboardButton(f"🏷 Caption: {caption_style}", callback_data="admin_dud_caption"),
        ],
        [
            InlineKeyboardButton(f"🖼 Auto-Thumb: {_on_off(auto_thumb)}", callback_data="admin_dud_thumb"),
            InlineKeyboardButton(f"👻 Anon: {_on_off(anon_default)}", callback_data="admin_dud_anon"),
        ],
        [
            InlineKeyboardButton(f"📥 Forward: {_on_off(forward_default)}", callback_data="admin_dud_forward"),
            InlineKeyboardButton("🎬 Movie Default", callback_data="admin_dud_movie"),
        ],
        [
            InlineKeyboardButton("📺 Series Default", callback_data="admin_dud_series"),
            InlineKeyboardButton("📦 Fallback Default", callback_data="admin_dud_fallback"),
        ],
        [InlineKeyboardButton("← Back", callback_data="admin_main")],
    ]

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )


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
        r"^(admin_dumb_channels|admin_dumb_user_defaults|admin_dumb_timeout|"
        r"prompt_admin_dumb_timeout|dumb_menu|dumb_opt_|dumb_ren_|"
        r"dumb_def_(?:std|mov|ser)_|dumb_add|dumb_del_)"
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

    # `admin_dumb_user_defaults` is the new public-mode "Dumb Channel Settings"
    # menu. `admin_dumb_timeout` is kept as a back-compat alias so any stale
    # inline keyboards in flight from a previous deploy still land somewhere
    # sensible instead of going dead.
    if data in ("admin_dumb_user_defaults", "admin_dumb_timeout"):
        await _render_dumb_user_defaults(callback_query)
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

    # `prompt_admin_dumb_timeout` was the "✏️ Change" step from the legacy
    # timeout-only screen. Since that screen no longer exists, redirect any
    # stale callback to the new Settings menu instead of dropping it.
    if data == "prompt_admin_dumb_timeout":
        await _render_dumb_user_defaults(callback_query)
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


_DUD_TOGGLES = {
    "retry":   ("dumb_channel_retry_on_error",   DUD_DEFAULTS["dumb_channel_retry_on_error"]),
    "thumb":   ("dumb_channel_auto_thumbnail",   DUD_DEFAULTS["dumb_channel_auto_thumbnail"]),
    "anon":    ("dumb_channel_anonymous_default",DUD_DEFAULTS["dumb_channel_anonymous_default"]),
    "forward": ("dumb_channel_forwarding_default",DUD_DEFAULTS["dumb_channel_forwarding_default"]),
}

_DUD_TEXT_PROMPTS = {
    "timeout": (
        "awaiting_dud_timeout",
        "⏱ **Auto-delete timeout**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the new value in seconds (e.g., `3600` for 1 hour).\n\n"
        "__(Send `disable` to cancel)__",
    ),
    "send_delay": (
        "awaiting_dud_send_delay",
        "🕒 **Send delay**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the new delay in seconds between uploads (e.g., `2`).\n\n"
        "__(Send `disable` to cancel)__",
    ),
    "movie": (
        "awaiting_dud_movie",
        "🎬 **Default movie channel**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send `@username` or numeric ID (`-100…`) of the channel.\n"
        "Send `none` to clear, or `disable` to cancel.",
    ),
    "series": (
        "awaiting_dud_series",
        "📺 **Default series channel**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send `@username` or numeric ID (`-100…`) of the channel.\n"
        "Send `none` to clear, or `disable` to cancel.",
    ),
    "fallback": (
        "awaiting_dud_fallback",
        "📦 **Fallback channel**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send `@username` or numeric ID (`-100…`) of the channel.\n"
        "Send `none` to clear, or `disable` to cancel.",
    ),
}


@Client.on_callback_query(
    filters.regex(
        r"^admin_dud_(timeout|send_delay|retry|caption|thumb|anon|forward|movie|series|fallback)$"
    )
)
async def admin_dud_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    action = callback_query.matches[0].group(1)
    cfg = await db.get_public_config()

    if action in _DUD_TOGGLES:
        key, default = _DUD_TOGGLES[action]
        new_val = not bool(cfg.get(key, default))
        await db.update_public_config(key, new_val)
        await _render_dumb_user_defaults(callback_query)
        return

    if action == "caption":
        cur = cfg.get("dumb_channel_caption_style") or DUD_DEFAULTS["dumb_channel_caption_style"]
        new_val = "verbose" if cur == "clean" else "clean"
        await db.update_public_config("dumb_channel_caption_style", new_val)
        await _render_dumb_user_defaults(callback_query)
        return

    state, prompt = _DUD_TEXT_PROMPTS[action]
    admin_sessions[user_id] = {"state": state, "msg_id": callback_query.message.id}
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            prompt,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_dumb_user_defaults")]]
            ),
        )


_DUD_CHANNEL_KEYS = {
    "awaiting_dud_movie":    "dumb_channel_default_movie_id",
    "awaiting_dud_series":   "dumb_channel_default_series_id",
    "awaiting_dud_fallback": "dumb_channel_default_fallback_id",
}


async def handle_dud_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_dud_* text inputs from the Dumb Channel Settings menu."""
    user_id = message.from_user.id
    val = (message.text or "").strip()

    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="admin_dumb_user_defaults")]]
    )

    if val.lower() == "disable":
        admin_sessions.pop(user_id, None)
        await edit_or_reply(client, message, msg_id, "Cancelled.", reply_markup=back_kb)
        return

    if state in ("awaiting_dud_timeout", "awaiting_dud_send_delay"):
        if not val.isdigit() or int(val) < 0:
            await edit_or_reply(
                client, message, msg_id,
                "❌ Invalid number. Send a non-negative integer or `disable` to cancel.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_dumb_user_defaults")]]
                ),
            )
            return
        n = int(val)
        if state == "awaiting_dud_timeout":
            await db.update_dumb_channel_timeout(n)
            label = f"timeout updated to `{_fmt_seconds(n)}`"
        else:
            await db.update_public_config("dumb_channel_send_delay_s", n)
            label = f"send delay updated to `{n}s`"
        await edit_or_reply(client, message, msg_id, f"✅ Dumb channel {label}.", reply_markup=back_kb)
        admin_sessions.pop(user_id, None)
        return

    if state in _DUD_CHANNEL_KEYS:
        key = _DUD_CHANNEL_KEYS[state]
        if val.lower() == "none":
            await db.update_public_config(key, None)
            await edit_or_reply(client, message, msg_id, "✅ Channel cleared.", reply_markup=back_kb)
            admin_sessions.pop(user_id, None)
            return
        try:
            chat = await client.get_chat(val if not val.lstrip("-").isdigit() else int(val))
            stored = chat.id
        except Exception as e:
            await edit_or_reply(
                client, message, msg_id,
                f"❌ Could not resolve `{val}`: {e}\nSend `@username`, numeric ID, `none`, or `disable`.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_dumb_user_defaults")]]
                ),
            )
            return
        await db.update_public_config(key, stored)
        title = chat.title or chat.username or str(stored)
        await edit_or_reply(client, message, msg_id, f"✅ Saved channel **{title}** (`{stored}`).", reply_markup=back_kb)
        admin_sessions.pop(user_id, None)
        return


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_dumb_", handle_text)
_register("awaiting_dud_", handle_dud_text)
