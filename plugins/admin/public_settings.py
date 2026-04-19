# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Public Settings admin domain.

Houses the Public Mode Settings menu and the prompt setup for its
text-input fields. Surfaces fields from the public_mode_config document:
branding (bot/community/support), per-user daily limits, and premium
toggles + trial duration. Force-Sub and Payment Methods stay in their
own dedicated submenus and are reached via shortcut buttons here.

Mode: PUBLIC-ONLY. Every non-trivial action returns early when
``Config.PUBLIC_MODE`` is False.
"""

import contextlib

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━"


def _on_off(b: bool) -> str:
    return "on" if b else "off"


def _format_mb(mb) -> str:
    mb = int(mb or 0)
    if mb <= 0:
        return "_unlimited_"
    if mb >= 1024:
        gb = mb / 1024
        return f"`{gb:.2f} GB`"
    return f"`{mb} MB`"


def _format_count(n) -> str:
    n = int(n or 0)
    return "_unlimited_" if n <= 0 else f"`{n}`"


def _value_or_dim(value, fallback: str = "_not set_") -> str:
    if value in (None, "", 0):
        return fallback
    return f"`{value}`"


# --- Renderer ---------------------------------------------------------------
async def _render_public_settings(callback_query: CallbackQuery):
    cfg = await db.get_public_config()

    bot_name = cfg.get("bot_name") or "Not set"
    community = cfg.get("community_name") or "Not set"
    support = cfg.get("support_contact") or "Not set"
    force_sub = cfg.get("force_sub_channel")
    egress_mb = cfg.get("daily_egress_mb", 0)
    file_count = cfg.get("daily_file_count", 0)
    prem_sys = bool(cfg.get("premium_system_enabled", False))
    prem_trial = bool(cfg.get("premium_trial_enabled", False))
    prem_trial_days = int(cfg.get("premium_trial_days", 1) or 1)
    prem_deluxe = bool(cfg.get("premium_deluxe_enabled", False))

    branding_lines = [
        "**Branding**",
        f"🤖 Bot name: `{bot_name}`",
        f"🏷 Community: `{community}`",
        f"💬 Support contact: `{support}`",
    ]
    limits_lines = [
        "**Limits per user / day**",
        f"📦 Egress cap: {_format_mb(egress_mb)}",
        f"📁 File count cap: {_format_count(file_count)}",
    ]
    access_lines = [
        "**Access**",
        f"🔒 Force-sub channel: {_value_or_dim(force_sub)}",
    ]
    trial_str = f"`{prem_trial_days} day{'s' if prem_trial_days != 1 else ''}`"
    premium_lines = [
        "**Premium**",
        f"💎 Premium system: `{_on_off(prem_sys)}`",
        f"🎁 Trial: `{_on_off(prem_trial)}` · {trial_str}",
        f"👑 Deluxe tier: `{_on_off(prem_deluxe)}`",
    ]

    text = "\n".join(
        [
            "**🌍 Public Mode Settings**",
            SEPARATOR,
            "",
            "<blockquote>" + "\n".join(branding_lines) + "</blockquote>",
            "",
            "<blockquote>" + "\n".join(limits_lines) + "</blockquote>",
            "",
            "<blockquote>" + "\n".join(access_lines) + "</blockquote>",
            "",
            "<blockquote>" + "\n".join(premium_lines) + "</blockquote>",
            "",
            "> Tap a row to edit. Force-Sub and Payments open their full editors.",
        ]
    )

    buttons = [
        [
            InlineKeyboardButton("🤖 Bot Name", callback_data="admin_public_bot_name"),
            InlineKeyboardButton("🏷 Community", callback_data="admin_public_community_name"),
        ],
        [
            InlineKeyboardButton("💬 Support", callback_data="admin_public_support_contact"),
            InlineKeyboardButton("🔒 Force-Sub", callback_data="admin_force_sub_menu"),
        ],
        [
            InlineKeyboardButton("📦 Egress Cap", callback_data="admin_public_egress_cap"),
            InlineKeyboardButton("📁 File Cap", callback_data="admin_public_file_cap"),
        ],
        [
            InlineKeyboardButton(
                f"💎 Premium: {_on_off(prem_sys)}",
                callback_data="admin_public_toggle_prem_system",
            ),
            InlineKeyboardButton(
                f"🎁 Trial: {_on_off(prem_trial)}",
                callback_data="admin_public_toggle_prem_trial",
            ),
        ],
        [
            InlineKeyboardButton(
                f"👑 Deluxe: {_on_off(prem_deluxe)}",
                callback_data="admin_public_toggle_prem_deluxe",
            ),
            InlineKeyboardButton("🎁 Trial Days", callback_data="admin_public_trial_days"),
        ],
        [
            InlineKeyboardButton("💳 Payments", callback_data="admin_payments_menu"),
            InlineKeyboardButton("👁 View Raw", callback_data="admin_public_view"),
        ],
        [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
    ]

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )


# --- Per-row text-input prompts --------------------------------------------
_TEXT_PROMPTS = {
    "bot_name": (
        "awaiting_public_bot_name",
        "🤖 **Edit Bot Name**\n━━━━━━━━━━━━━━━━━━━━\n\nSend the new bot name.",
    ),
    "community_name": (
        "awaiting_public_community_name",
        "🏷 **Edit Community Name**\n━━━━━━━━━━━━━━━━━━━━\n\nSend the new community name.",
    ),
    "support_contact": (
        "awaiting_public_support_contact",
        "💬 **Edit Support Contact**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the new contact (e.g., `@username` or full link).",
    ),
    "egress_cap": (
        "awaiting_public_egress_cap",
        "📦 **Daily Egress Cap**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the new per-user daily egress limit.\n"
        "Examples: `2 GB`, `512 MB`, or `0` to disable.",
    ),
    "file_cap": (
        "awaiting_public_file_cap",
        "📁 **Daily File Cap**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the new per-user daily file count, or `0` to disable.",
    ),
    "trial_days": (
        "awaiting_public_trial_days",
        "🎁 **Premium Trial Duration**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the trial length in days (e.g., `3`).",
    ),
}

_TOGGLE_KEYS = {
    "prem_system": "premium_system_enabled",
    "prem_trial":  "premium_trial_enabled",
    "prem_deluxe": "premium_deluxe_enabled",
}


@Client.on_callback_query(
    filters.regex(
        r"^(admin_public_settings|admin_public_view|admin_public_bot_name|"
        r"admin_public_community_name|admin_public_support_contact|"
        r"admin_public_egress_cap|admin_public_file_cap|admin_public_trial_days|"
        r"admin_public_toggle_(?:prem_system|prem_trial|prem_deluxe)|"
        r"prompt_public_(?:bot_name|community_name|support_contact|"
        r"egress_cap|file_cap|trial_days))$"
    )
)
async def public_settings_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    if not Config.PUBLIC_MODE:
        await callback_query.answer("Public mode is disabled.", show_alert=True)
        return

    data = callback_query.data
    await callback_query.answer()

    if data == "admin_public_settings":
        await _render_public_settings(callback_query)
        return

    if data == "admin_public_view":
        config = await db.get_public_config()
        lines = [
            "**👁 Public Mode Config — Raw**",
            SEPARATOR,
            "",
            f"**Bot Name:** `{config.get('bot_name', 'Not set')}`",
            f"**Community Name:** `{config.get('community_name', 'Not set')}`",
            f"**Support Contact:** `{config.get('support_contact', 'Not set')}`",
            f"**Force-Sub Channel:** `{config.get('force_sub_channel', 'Not set')}`",
            f"**Daily Egress Limit:** `{config.get('daily_egress_mb', 0)} MB`",
            f"**Daily File Limit:** `{config.get('daily_file_count', 0)} files`",
            f"**Premium System:** `{_on_off(config.get('premium_system_enabled', False))}`",
            f"**Premium Trial:** `{_on_off(config.get('premium_trial_enabled', False))}` "
            f"({config.get('premium_trial_days', 1)} days)",
            f"**Premium Deluxe:** `{_on_off(config.get('premium_deluxe_enabled', False))}`",
        ]
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back", callback_data="admin_public_settings")]]
                ),
            )
        return

    # --- Boolean toggles ---
    if data.startswith("admin_public_toggle_"):
        suffix = data.replace("admin_public_toggle_", "")
        key = _TOGGLE_KEYS.get(suffix)
        if key is None:
            return
        cfg = await db.get_public_config()
        new_val = not bool(cfg.get(key, False))
        await db.update_public_config(key, new_val)
        await _render_public_settings(callback_query)
        return

    # --- Detail screens that show "current value + ✏️ Change" ---
    detail_map = {
        "admin_public_bot_name":          ("bot_name",         "🤖 Bot Name",         "bot_name"),
        "admin_public_community_name":    ("community_name",   "🏷 Community Name",   "community_name"),
        "admin_public_support_contact":   ("support_contact",  "💬 Support Contact",  "support_contact"),
        "admin_public_egress_cap":        ("daily_egress_mb",  "📦 Daily Egress Cap", "egress_cap"),
        "admin_public_file_cap":          ("daily_file_count", "📁 Daily File Cap",   "file_cap"),
        "admin_public_trial_days":        ("premium_trial_days","🎁 Trial Duration",  "trial_days"),
    }
    if data in detail_map:
        cfg_key, title, prompt_key = detail_map[data]
        cfg = await db.get_public_config()
        current_val = cfg.get(cfg_key, "Not set")
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"**{title}**\n{SEPARATOR}\n\nCurrent: `{current_val}`\n\nTap below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_public_{prompt_key}")],
                        [InlineKeyboardButton("← Back", callback_data="admin_public_settings")],
                    ]
                ),
            )
        return

    # --- Prompt for text input ---
    if data.startswith("prompt_public_"):
        field = data.replace("prompt_public_", "")
        if field not in _TEXT_PROMPTS:
            return
        state, prompt_text = _TEXT_PROMPTS[field]
        admin_sessions[user_id] = {"state": state, "msg_id": callback_query.message.id}
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                prompt_text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_public_settings")]]
                ),
            )
        return


# ---------------------------------------------------------------------------
# Text-input state handler (registered with text_dispatcher)
# ---------------------------------------------------------------------------
def _parse_mb(val: str) -> int | None:
    """Parse `2 GB`, `512 MB`, or a bare integer (treated as MB) → MB int.
    Returns None on parse error. `0` is valid (means "unlimited")."""
    val = val.strip().lower()
    try:
        if "gb" in val:
            return int(float(val.replace("gb", "").strip()) * 1024)
        if "mb" in val:
            return int(float(val.replace("mb", "").strip()))
        return int(float(val))
    except ValueError:
        return None


async def handle_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_public_* states."""
    user_id = message.from_user.id
    field = state.replace("awaiting_public_", "")

    val = message.text.strip() if message.text else ""
    if not val:
        raise ContinuePropagation

    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="admin_public_settings")]]
    )

    # --- Plain-text fields ---
    plain_text_fields = {
        "bot_name":        ("bot_name",        "Bot Name"),
        "community_name":  ("community_name",  "Community Name"),
        "support_contact": ("support_contact", "Support Contact"),
    }
    if field in plain_text_fields:
        cfg_key, label = plain_text_fields[field]
        await db.update_public_config(cfg_key, val)
        await edit_or_reply(
            client, message, msg_id,
            f"✅ {label} updated to `{val}`.",
            reply_markup=back_kb,
        )
        admin_sessions.pop(user_id, None)
        return

    # --- Public-Settings-entry numeric inputs (route back to public settings) ---
    if field == "egress_cap":
        mb = _parse_mb(val)
        if mb is None or mb < 0:
            await edit_or_reply(
                client, message, msg_id,
                "❌ Invalid value. Send something like `2 GB`, `512 MB`, or `0`.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_public_settings")]]
                ),
            )
            return
        await db.update_public_config("daily_egress_mb", mb)
        await edit_or_reply(
            client, message, msg_id,
            f"✅ Daily egress cap set to `{mb} MB`."
            + (" (unlimited)" if mb == 0 else ""),
            reply_markup=back_kb,
        )
        admin_sessions.pop(user_id, None)
        return

    if field == "file_cap":
        if not val.isdigit() or int(val) < 0:
            await edit_or_reply(
                client, message, msg_id,
                "❌ Invalid number. Send a non-negative integer.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_public_settings")]]
                ),
            )
            return
        n = int(val)
        await db.update_public_config("daily_file_count", n)
        await edit_or_reply(
            client, message, msg_id,
            f"✅ Daily file cap set to `{n}`." + (" (unlimited)" if n == 0 else ""),
            reply_markup=back_kb,
        )
        admin_sessions.pop(user_id, None)
        return

    if field == "trial_days":
        if not val.isdigit() or int(val) < 1:
            await edit_or_reply(
                client, message, msg_id,
                "❌ Invalid number. Send a positive integer.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_public_settings")]]
                ),
            )
            return
        await db.update_public_config("premium_trial_days", int(val))
        await edit_or_reply(
            client, message, msg_id,
            f"✅ Trial duration set to `{val}` day(s).",
            reply_markup=back_kb,
        )
        admin_sessions.pop(user_id, None)
        return

    # --- Force-Sub passthrough (legacy from the dedicated force-sub menu) ---
    if field == "force_sub":
        if val.lower() == "/cancel":
            admin_sessions.pop(user_id, None)
            await edit_or_reply(
                client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]]
                ),
            )
        else:
            await edit_or_reply(
                client, message, msg_id,
                "⏳ **Still Waiting...**\n\nPlease add me as an Admin to the channel, or type `/cancel` to abort.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                ),
            )
        return

    # --- Free-Plan editor passthroughs (kept for the "admin_edit_plan_free" UI) ---
    if field == "rate_limit":
        if not val.isdigit():
            await edit_or_reply(
                client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_public_settings")]]
                ),
            )
            return
        await db.update_public_config("rate_limit_delay", int(val))
        await edit_or_reply(
            client, message, msg_id,
            f"✅ Rate limit updated to `{val}` seconds.",
            reply_markup=back_kb,
        )
        admin_sessions.pop(user_id, None)
        return

    if field == "daily_egress":
        mb = _parse_mb(val)
        if mb is None:
            await edit_or_reply(
                client, message, msg_id,
                "❌ Invalid number format. Try `2 GB`, `512 MB`, or a bare MB integer.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]]
                ),
            )
            return
        await db.update_public_config("daily_egress_mb", mb)
        await edit_or_reply(
            client, message, msg_id,
            f"✅ **Success!**\n\nThe Daily Egress Limit for the **Free Plan** has been updated to **{mb} MB**.\n\nChanges have been saved and applied globally.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_edit_plan_free")]]
            ),
        )
        admin_sessions.pop(user_id, None)
        return

    if field == "daily_files":
        if not val.isdigit():
            await edit_or_reply(
                client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]]
                ),
            )
            return
        await db.update_public_config("daily_file_count", int(val))
        await edit_or_reply(
            client, message, msg_id,
            f"✅ **Success!**\n\nThe Daily File Limit for the **Free Plan** has been updated to **{val} files**.\n\nChanges have been saved and applied globally.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_edit_plan_free")]]
            ),
        )
        admin_sessions.pop(user_id, None)
        return


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_public_", handle_text)
