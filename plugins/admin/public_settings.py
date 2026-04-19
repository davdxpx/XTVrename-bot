# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Public Mode Settings — branding for the public-facing bot identity.

This screen only handles **branding**: bot name + tagline, community name,
contacts, channel links, website, footer text. Everything else that used to
live here (force-sub, payments, daily limits, premium toggles) belongs in
its own dedicated admin submenu and is reached from the main admin panel
directly.

Mode: PUBLIC-ONLY. Every callback short-circuits when ``Config.PUBLIC_MODE``
is False.
"""

import contextlib

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━"


def _value_or_dim(value, fallback: str = "__not set__") -> str:
    if value in (None, "", 0):
        return fallback
    return f"`{value}`"


# --- Branding renderer ------------------------------------------------------
# Field key in DB → (button label, sentence label, prompt headline,
#                     prompt body, hint shown on the prompt screen)
BRANDING_FIELDS: dict[str, dict] = {
    "bot_name": {
        "row_label": "🤖 Bot name",
        "button":    "🤖 Bot Name",
        "title":     "🤖 Bot Name",
        "prompt":    "Send the new bot name (shown to every public-mode user).",
    },
    "bot_tagline": {
        "row_label": "✨ Tagline",
        "button":    "✨ Tagline",
        "title":     "✨ Tagline",
        "prompt":    "Send a short one-line tagline. Shown under the bot name "
                     "in /info and /start.",
    },
    "community_name": {
        "row_label": "🏷 Community",
        "button":    "🏷 Community",
        "title":     "🏷 Community Name",
        "prompt":    "Send the community / network name.",
    },
    "support_contact": {
        "row_label": "💬 Support contact",
        "button":    "💬 Support",
        "title":     "💬 Support Contact",
        "prompt":    "Send the support contact (e.g., `@username` or full link).",
    },
    "main_channel_url": {
        "row_label": "📢 Main channel",
        "button":    "📢 Main Channel",
        "title":     "📢 Main Channel",
        "prompt":    "Send the link to the main Telegram channel "
                     "(e.g., `https://t.me/xtvchannel`).",
    },
    "backup_channel_url": {
        "row_label": "📦 Backup channel",
        "button":    "📦 Backup Channel",
        "title":     "📦 Backup Channel",
        "prompt":    "Send the link to the backup channel, or `none` to clear.",
    },
    "website_url": {
        "row_label": "🌐 Website",
        "button":    "🌐 Website",
        "title":     "🌐 Website",
        "prompt":    "Send the website URL (e.g., `https://example.com`), "
                     "or `none` to clear.",
    },
    "footer_text": {
        "row_label": "📝 Footer text",
        "button":    "📝 Footer",
        "title":     "📝 Footer Text",
        "prompt":    "Send the small footer line shown at the bottom of "
                     "/start. Send `none` to clear.",
    },
}


async def _render_public_settings(callback_query: CallbackQuery):
    cfg = await db.get_public_config()

    info_lines = ["**Branding**"]
    for key, meta in BRANDING_FIELDS.items():
        info_lines.append(f"{meta['row_label']}: {_value_or_dim(cfg.get(key))}")

    text = "\n".join(
        [
            "**🌍 Public Mode Branding**",
            SEPARATOR,
            "",
            "<blockquote>" + "\n".join(info_lines) + "</blockquote>",
            "",
            "> Tap a row to edit. Limits, force-sub and payments live in "
            "their own admin sections.",
        ]
    )

    field_keys = list(BRANDING_FIELDS.keys())
    buttons: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(field_keys), 2):
        row = []
        for key in field_keys[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    BRANDING_FIELDS[key]["button"],
                    callback_data=f"admin_public_field|{key}",
                )
            )
        buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton("👁 View Raw", callback_data="admin_public_view"),
            InlineKeyboardButton("← Back", callback_data="admin_main"),
        ]
    )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )


# --- Callback dispatch ------------------------------------------------------
@Client.on_callback_query(
    filters.regex(
        r"^(admin_public_settings|admin_public_view|"
        r"admin_public_field\|[a-z_]+|prompt_public_field\|[a-z_]+)$"
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
        lines = ["**👁 Branding — Raw values**", SEPARATOR, ""]
        for key, meta in BRANDING_FIELDS.items():
            lines.append(f"**{meta['title']}:** {_value_or_dim(config.get(key))}")
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back", callback_data="admin_public_settings")]]
                ),
            )
        return

    if data.startswith("admin_public_field|"):
        key = data.split("|", 1)[1]
        if key not in BRANDING_FIELDS:
            return
        cfg = await db.get_public_config()
        meta = BRANDING_FIELDS[key]
        current_val = _value_or_dim(cfg.get(key))
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"**{meta['title']}**\n{SEPARATOR}\n\nCurrent: {current_val}\n\n"
                f"Tap below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change",
                                callback_data=f"prompt_public_field|{key}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_public_settings"
                            )
                        ],
                    ]
                ),
            )
        return

    if data.startswith("prompt_public_field|"):
        key = data.split("|", 1)[1]
        if key not in BRANDING_FIELDS:
            return
        meta = BRANDING_FIELDS[key]
        admin_sessions[user_id] = {
            "state": f"awaiting_public_field_{key}",
            "msg_id": callback_query.message.id,
        }
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"**{meta['title']}**\n{SEPARATOR}\n\n{meta['prompt']}",
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
    Returns None on parse error. `0` is valid (means "unlimited").
    Kept for the legacy Free-Plan editor passthrough below."""
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
    """Handle awaiting_public_* states.

    The branding screen uses ``awaiting_public_field_<key>``. Other legacy
    states (force_sub, daily_egress, daily_files, rate_limit) are still
    routed here from other admin screens (Force-Sub menu, Free-Plan editor),
    so their handlers are preserved untouched.
    """
    user_id = message.from_user.id
    val = message.text.strip() if message.text else ""
    if not val:
        raise ContinuePropagation

    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="admin_public_settings")]]
    )

    # --- Branding fields (awaiting_public_field_<key>) ---
    if state.startswith("awaiting_public_field_"):
        key = state.replace("awaiting_public_field_", "")
        meta = BRANDING_FIELDS.get(key)
        if meta is None:
            admin_sessions.pop(user_id, None)
            return
        new_val: str | None = val
        if val.lower() == "none" and key in (
            "backup_channel_url", "website_url", "footer_text",
        ):
            new_val = None
        await db.update_public_config(key, new_val)
        display = "_(cleared)_" if new_val is None else f"`{new_val}`"
        await edit_or_reply(
            client, message, msg_id,
            f"✅ {meta['title']} updated to {display}.",
            reply_markup=back_kb,
        )
        admin_sessions.pop(user_id, None)
        return

    # --- Legacy: Force-Sub gate text wait ---
    field = state.replace("awaiting_public_", "")
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

    # --- Legacy: Free-Plan editor passthroughs (admin_edit_plan_free UI) ---
    if field == "rate_limit":
        if not val.isdigit():
            await edit_or_reply(
                client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]]
                ),
            )
            return
        await db.update_public_config("rate_limit_delay", int(val))
        await edit_or_reply(
            client, message, msg_id,
            f"✅ Rate limit updated to `{val}` seconds.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_edit_plan_free")]]
            ),
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
