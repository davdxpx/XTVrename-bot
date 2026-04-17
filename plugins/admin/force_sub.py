# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Force-Sub admin domain.

Covers the force-subscription settings: channel management (add, remove,
toggle), gate banner, gate message, button customisation, and welcome
message.

Text-input flows (`awaiting_fs_*`) are registered with the shared
``text_dispatcher`` and handled here via ``handle_text``.
"""

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin


async def get_force_sub_menu_content():
    """Build force-sub menu text and keyboard (no message editing)."""
    config = await db.get_public_config()
    channels = config.get("force_sub_channels", [])
    legacy_ch = config.get("force_sub_channel")

    num_channels = len(channels) if channels else (1 if legacy_ch else 0)
    status = "ON" if num_channels > 0 else "OFF"

    banner_set = "✅ Set" if config.get("force_sub_banner_file_id") else "❌ None"
    msg_set = "Custom" if config.get("force_sub_message_text") else "Default"

    btn_emoji = config.get("force_sub_button_emoji", "📢")
    btn_label = config.get("force_sub_button_label", "Join Channel")

    text = (
        f"📡 **Force-Sub Config**\n"
        f"Channels: {num_channels} configured\n"
        f"Banner: {banner_set}\n"
        f"Message: {msg_set}\n"
        f"Button: {btn_emoji} {btn_label}\n\n"
        f"Select an option to configure:"
    )

    keyboard = [
        [InlineKeyboardButton(f"📡 Force-Sub: {status}", callback_data="admin_fs_toggle")],
        [
            InlineKeyboardButton("➕ Add Channel", callback_data="admin_fs_add_channel"),
            InlineKeyboardButton("📋 Manage Channels", callback_data="admin_fs_manage_channels"),
        ],
        [InlineKeyboardButton("🖼 Set Banner", callback_data="admin_fs_set_banner")],
    ]

    if config.get("force_sub_banner_file_id"):
        keyboard[-1].append(
            InlineKeyboardButton("🗑 Remove Banner", callback_data="admin_fs_rem_banner")
        )

    keyboard.append(
        [
            InlineKeyboardButton("✏️ Edit Message", callback_data="admin_fs_edit_msg"),
            InlineKeyboardButton("↩️ Reset Message", callback_data="admin_fs_reset_msg"),
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton("🔘 Edit Button", callback_data="admin_fs_edit_btn"),
            InlineKeyboardButton("🎉 Edit Welcome Msg", callback_data="admin_fs_edit_welcome"),
        ]
    )
    keyboard.append(
        [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")]
    )

    return text, InlineKeyboardMarkup(keyboard)


async def _render_force_sub_menu(callback_query: CallbackQuery):
    """Build and display the force-sub settings menu."""
    text, markup = await get_force_sub_menu_content()
    try:
        await callback_query.message.edit_text(text, reply_markup=markup)
    except MessageNotModified:
        pass


async def _render_manage_channels(callback_query: CallbackQuery):
    """Build and display the force-sub channel management list."""
    config = await db.get_public_config()
    channels = config.get("force_sub_channels", [])
    legacy_ch = config.get("force_sub_channel")
    legacy_link = config.get("force_sub_link")
    legacy_username = config.get("force_sub_username")

    if not channels and legacy_ch:
        channels = [
            {
                "id": legacy_ch,
                "link": legacy_link,
                "username": legacy_username,
                "title": "Legacy Channel",
            }
        ]

    if not channels:
        await callback_query.answer("No channels configured.", show_alert=True)
        return

    keyboard = []
    for i, ch in enumerate(channels):
        title = ch.get("title", f"Channel {i+1}")
        keyboard.append(
            [InlineKeyboardButton(f"❌ Remove {title}", callback_data=f"admin_fs_rem_ch_{i}")]
        )
    keyboard.append(
        [InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]
    )

    try:
        await callback_query.message.edit_text(
            "📋 **Manage Channels**\n\nSelect a channel to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(
    filters.regex(
        r"^(admin_force_sub_menu$|admin_fs_)"
    )
)
async def force_sub_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    if not Config.PUBLIC_MODE:
        return
    data = callback_query.data

    # --- Force-sub menu ---
    if data == "admin_force_sub_menu":
        await callback_query.answer()
        await _render_force_sub_menu(callback_query)
        return

    # --- Add channel ---
    if data == "admin_fs_add_channel":
        admin_sessions[user_id] = {
            "state": "awaiting_fs_add_channel",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                "📢 **Add Force-Sub Channel**\n\n"
                "⏳ **I am waiting...**\n\n"
                "Simply **add me as an Administrator** to your desired channel right now!\n"
                "Make sure I have the 'Invite Users via Link' permission.\n\n"
                "I will automatically detect the channel and set it up instantly.\n\n"
                "__Send /cancel to cancel.__",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Toggle ---
    if data == "admin_fs_toggle":
        config = await db.get_public_config()
        channels = config.get("force_sub_channels", [])
        legacy_ch = config.get("force_sub_channel")
        num_channels = len(channels) if channels else (1 if legacy_ch else 0)

        if num_channels > 0:
            await db.update_public_config("force_sub_channels", [])
            await db.update_public_config("force_sub_channel", None)
            await db.update_public_config("force_sub_link", None)
            await db.update_public_config("force_sub_username", None)
            await callback_query.answer("Force-Sub disabled.", show_alert=True)
        else:
            await callback_query.answer(
                "Please add a channel to enable Force-Sub.", show_alert=True
            )

        await _render_force_sub_menu(callback_query)
        return

    # --- Manage channels ---
    if data == "admin_fs_manage_channels":
        await callback_query.answer()
        await _render_manage_channels(callback_query)
        return

    # --- Remove channel ---
    if data.startswith("admin_fs_rem_ch_"):
        idx = int(data.replace("admin_fs_rem_ch_", ""))
        config = await db.get_public_config()
        channels = config.get("force_sub_channels", [])
        legacy_ch = config.get("force_sub_channel")

        if not channels and legacy_ch:
            channels = [
                {
                    "id": legacy_ch,
                    "link": config.get("force_sub_link"),
                    "username": config.get("force_sub_username"),
                    "title": "Legacy Channel",
                }
            ]

        if 0 <= idx < len(channels):
            channels.pop(idx)
            await db.update_public_config("force_sub_channels", channels)

            if len(channels) > 0:
                await db.update_public_config("force_sub_channel", channels[0].get("id"))
                await db.update_public_config("force_sub_link", channels[0].get("link"))
                await db.update_public_config("force_sub_username", channels[0].get("username"))
            else:
                await db.update_public_config("force_sub_channel", None)
                await db.update_public_config("force_sub_link", None)
                await db.update_public_config("force_sub_username", None)

            await callback_query.answer("Channel removed.", show_alert=True)

        await _render_manage_channels(callback_query)
        return

    # --- Set banner ---
    if data == "admin_fs_set_banner":
        admin_sessions[user_id] = {
            "state": "awaiting_fs_banner",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                "🖼 **Send me a photo** to use as the Force-Sub gate banner.\n\n"
                "Send /cancel to keep the current one.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Remove banner ---
    if data == "admin_fs_rem_banner":
        await db.update_public_config("force_sub_banner_file_id", None)
        await callback_query.answer("Banner removed.", show_alert=True)
        await _render_force_sub_menu(callback_query)
        return

    # --- Edit message ---
    if data == "admin_fs_edit_msg":
        config = await db.get_public_config()
        current_msg = config.get("force_sub_message_text")

        text = "✏️ **Edit Gate Message**\n\nCurrent:\n"
        if current_msg:
            text += f"`{current_msg}`\n\n"
        else:
            text += "__Default Message__\n\n"
        text += (
            "Send your new gate message. You can use `{channel}`, "
            "`{bot_name}`, `{community}`.\n"
            "Send /cancel to keep the current one."
        )

        admin_sessions[user_id] = {
            "state": "awaiting_fs_msg",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Reset message ---
    if data == "admin_fs_reset_msg":
        await db.update_public_config("force_sub_message_text", None)
        await callback_query.answer("Message reset to default.", show_alert=True)
        await _render_force_sub_menu(callback_query)
        return

    # --- Edit button ---
    if data == "admin_fs_edit_btn":
        await callback_query.answer()
        try:
            await callback_query.message.edit_text(
                "🔘 **Edit Button**\n\nSelect what to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🔘 Edit Label", callback_data="admin_fs_btn_label"),
                            InlineKeyboardButton("😀 Edit Emoji", callback_data="admin_fs_btn_emoji"),
                        ],
                        [InlineKeyboardButton("↩️ Reset Button", callback_data="admin_fs_btn_reset")],
                        [
                            InlineKeyboardButton(
                                "← Back to Force-Sub Settings",
                                callback_data="admin_force_sub_menu",
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_fs_btn_label":
        admin_sessions[user_id] = {
            "state": "awaiting_fs_btn_label",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                "🔘 **Edit Button Label**\n\nSend the new label text (without emoji):",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_fs_edit_btn")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_fs_btn_emoji":
        admin_sessions[user_id] = {
            "state": "awaiting_fs_btn_emoji",
            "msg_id": callback_query.message.id,
        }
        try:
            await callback_query.message.edit_text(
                "😀 **Edit Button Emoji**\n\nSend a single emoji character:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_fs_edit_btn")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_fs_btn_reset":
        await db.update_public_config("force_sub_button_label", None)
        await db.update_public_config("force_sub_button_emoji", None)
        await callback_query.answer("Button reset to default.", show_alert=True)
        await _render_force_sub_menu(callback_query)
        return

    # --- Edit welcome message ---
    if data == "admin_fs_edit_welcome":
        admin_sessions[user_id] = {
            "state": "awaiting_fs_welcome",
            "msg_id": callback_query.message.id,
        }
        config = await db.get_public_config()
        current_msg = config.get(
            "force_sub_welcome_text",
            "✅ Welcome aboard! You're all set. Send your file and let's go.",
        )
        try:
            await callback_query.message.edit_text(
                f"🎉 **Edit Welcome Message**\n\nCurrent:\n`{current_msg}`\n\n"
                "Send the new welcome message text:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                ),
            )
        except MessageNotModified:
            pass
        return


# ---------------------------------------------------------------------------
# Text-input state handler (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def handle_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_fs_* states."""
    user_id = message.from_user.id
    val = message.text.strip() if message.text else ""
    if val == "/cancel":
        admin_sessions.pop(user_id, None)
        await edit_or_reply(client, message, msg_id, "Cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]]))
        return

    field = state.replace("awaiting_fs_", "")

    if field == "msg":
        await db.update_public_config("force_sub_message_text", val)
        await edit_or_reply(client, message, msg_id, "✅ Gate message updated successfully.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]])
        )
    elif field == "btn_label":
        await db.update_public_config("force_sub_button_label", val)
        await edit_or_reply(client, message, msg_id, f"✅ Button label updated to `{val}`.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Button Settings", callback_data="admin_fs_edit_btn")]])
        )
    elif field == "btn_emoji":
        emoji = val[0] if val else "📢"
        await db.update_public_config("force_sub_button_emoji", emoji)
        await edit_or_reply(client, message, msg_id, f"✅ Button emoji updated to {emoji}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Button Settings", callback_data="admin_fs_edit_btn")]])
        )
    elif field == "welcome":
        await db.update_public_config("force_sub_welcome_text", val)
        await edit_or_reply(client, message, msg_id, "✅ Welcome message updated successfully.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]])
        )

    admin_sessions.pop(user_id, None)


from plugins.admin.text_dispatcher import register as _register
_register("awaiting_fs_", handle_text)
