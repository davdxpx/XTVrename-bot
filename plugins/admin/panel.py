# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Admin Panel entry points.

Two handlers:
- /admin command → initial render of the admin panel (routes to the
  setup wizard if the bot hasn't finished first-run setup).
- admin_main callback → "← Back to Admin Panel" universal return; edits
  the current message back to the main menu.

Both use the shared get_admin_main_menu builder from core.py, so the
menu layout stays in one place.
"""

import contextlib

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified

from config import Config
from database import db
from plugins.admin.core import admin_sessions, get_admin_main_menu, is_admin

_PUBLIC_PANEL_TEXT = (
    "⚙️ **Control Center** · __Public Mode__\n\n"
    "You're running the show.\n"
    "Everything here applies globally — branding, rate limits, payment methods, the works.\n\n"
    "__(Your personal renaming templates live in /settings)__"
)

_PRIVATE_PANEL_TEXT = (
    "⚙️ **𝕏TV Admin Panel**\n\n"
    "__Your studio. Your rules.__\n"
    "These settings shape how every file passing through the bot gets handled."
)


@Client.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message):
    if not is_admin(message.from_user.id):
        return

    # Redirect to setup wizard if initial setup is not complete
    setup_complete = await db.get_setting(
        "is_bot_setup_complete", default=False, user_id=Config.CEO_ID
    )
    if not setup_complete:
        from plugins.admin.setup import send_ceo_setup_menu
        await send_ceo_setup_menu(client, message.chat.id)
        return

    pro_session = await db.get_pro_session()
    myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)

    text = _PUBLIC_PANEL_TEXT if Config.PUBLIC_MODE else _PRIVATE_PANEL_TEXT

    await message.reply_text(
        text,
        reply_markup=get_admin_main_menu(pro_session, Config.PUBLIC_MODE, myfiles_enabled),
    )


@Client.on_callback_query(filters.regex(r"^admin_main$"))
async def admin_main_cb(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return

    # Any pending text-input state is cancelled when the user backs out.
    admin_sessions.pop(user_id, None)

    pro_session = await db.get_pro_session()
    myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)

    text = _PUBLIC_PANEL_TEXT if Config.PUBLIC_MODE else _PRIVATE_PANEL_TEXT

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text,
            reply_markup=get_admin_main_menu(pro_session, Config.PUBLIC_MODE, myfiles_enabled),
        )
