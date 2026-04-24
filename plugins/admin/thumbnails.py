# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Thumbnail management admin domain.

Covers the thumbnail settings menu, mode switching (auto / custom / none),
uploading a custom thumbnail via the photo handler, viewing and removing
thumbnails, and the generic admin_delete_msg helper.

The photo handler also routes the `awaiting_fs_banner` state for force-sub
banner uploads — that part will move to `force_sub.py` when that domain is
extracted.
"""

import asyncio
import contextlib
import io

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from plugins.admin.core import admin_sessions, is_admin
from utils.tasks import spawn as _spawn_task
from utils.telegram.log import get_logger

logger = get_logger("plugins.admin.thumbnails")


async def _render_thumb_menu(callback_query: CallbackQuery):
    """Build and display the thumbnail settings menu."""
    thumb_mode = await db.get_thumbnail_mode(None)
    mode_str = "Deactivated (None)"
    if thumb_mode == "auto":
        mode_str = "Auto-detect (Preview)"
    elif thumb_mode == "custom":
        mode_str = "Custom Thumbnail"

    text = (
        "🖼 **Manage Global Thumbnail Preferences**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "> **Choose how thumbnails should be handled for all processed files.**\n\n"
        f"**Current Mode:** `{mode_str}`\n\n"
        "**Options:**\n"
        "• **Auto-detect:** Uses the automatic preview image from TMDb.\n"
        "• **Custom:** Uses your uploaded default thumbnail.\n"
        "• **Deactivated:** Skips applying any thumbnail."
    )

    buttons = [
        [
            InlineKeyboardButton(
                "✅ Auto-detect" if thumb_mode == "auto" else "Auto-detect",
                callback_data="set_admin_thumb_mode_auto",
            ),
            InlineKeyboardButton(
                "✅ Custom" if thumb_mode == "custom" else "Custom",
                callback_data="set_admin_thumb_mode_custom",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Deactivated (None)" if thumb_mode == "none" else "Deactivated (None)",
                callback_data="set_admin_thumb_mode_none",
            )
        ],
    ]

    if thumb_mode == "custom":
        buttons.append(
            [InlineKeyboardButton("👀 View Custom Thumbnail", callback_data="admin_thumb_view")]
        )
        buttons.append(
            [InlineKeyboardButton("📤 Upload New Thumbnail", callback_data="admin_thumb_set")]
        )
        buttons.append(
            [InlineKeyboardButton("🗑 Remove Thumbnail", callback_data="admin_thumb_remove")]
        )

    buttons.append(
        [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")]
    )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )


@Client.on_callback_query(
    filters.regex(
        r"^(admin_thumb_(?:menu|view|set|remove)$"
        r"|set_admin_thumb_mode_"
        r"|prompt_admin_thumb_set$"
        r"|admin_delete_msg$)"
    )
)
async def thumbnails_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    # --- Thumbnail menu ---
    if data == "admin_thumb_menu":
        await callback_query.answer()
        await _render_thumb_menu(callback_query)
        return

    # --- Mode switch ---
    if data.startswith("set_admin_thumb_mode_"):
        new_mode = data.replace("set_admin_thumb_mode_", "")
        await db.update_thumbnail_mode(new_mode, None)
        await callback_query.answer(
            f"Global thumbnail mode set to {new_mode.capitalize()}!",
            show_alert=True,
        )
        await _render_thumb_menu(callback_query)
        return

    # --- Remove thumbnail ---
    if data == "admin_thumb_remove":
        await callback_query.answer()
        await db.update_thumbnail(None, None, None)
        await db.update_thumbnail_mode("none", None)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "✅ **Thumbnail Removed & Deactivated**\n\n"
                "Files will no longer use a default custom thumbnail and the "
                "global thumbnail mode has been set to None.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← Back to Thumbnail Settings",
                                callback_data="admin_thumb_menu",
                            )
                        ]
                    ]
                ),
            )
        return

    # --- View thumbnail ---
    if data == "admin_thumb_view":
        thumb_bin, _ = await db.get_thumbnail()
        if thumb_bin:
            try:
                f = io.BytesIO(thumb_bin)
                f.name = "thumbnail.jpg"

                sent_msg = await client.send_photo(
                    user_id,
                    f,
                    caption=(
                        "🖼 **Current Default Thumbnail**\n"
                        "__(This message will auto-delete to keep the chat clean)__"
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✅ OK", callback_data="admin_delete_msg")]]
                    ),
                )

                async def auto_delete():
                    await asyncio.sleep(30)
                    with contextlib.suppress(Exception):
                        await sent_msg.delete()

                _spawn_task(auto_delete(), label="auto_delete_msg")

                await callback_query.answer("Thumbnail sent! Check below.", show_alert=False)
            except Exception as e:
                logger.error(f"Failed to send thumbnail: {e}")
                await callback_query.answer("Error sending thumbnail!", show_alert=True)
        else:
            await callback_query.answer(
                "No custom thumbnail currently uploaded!", show_alert=True
            )
        return

    # --- Upload entry ---
    if data == "admin_thumb_set":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📤 **Set Default Thumbnail**\n\n"
                "Click below to upload a new thumbnail. "
                "This will be embedded into every video processed.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📤 Upload New",
                                callback_data="prompt_admin_thumb_set",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Thumbnail Settings",
                                callback_data="admin_thumb_menu",
                            )
                        ],
                    ]
                ),
            )
        return

    # --- Prompt for photo ---
    if data == "prompt_admin_thumb_set":
        admin_sessions[user_id] = {
            "state": "awaiting_thumb",
            "msg_id": callback_query.message.id,
        }
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🖼 **Send the new photo** to set as the default thumbnail:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="admin_thumb_menu"
                            )
                        ]
                    ]
                ),
            )
        return

    # --- Delete message helper ---
    if data == "admin_delete_msg":
        with contextlib.suppress(Exception):
            await callback_query.message.delete()
        return


# --- Photo handler (thumbnail upload + force-sub banner) ---
@Client.on_message(filters.photo & filters.private, group=1)
async def handle_admin_photo(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state_obj = admin_sessions.get(user_id)
    state = (
        state_obj
        if isinstance(state_obj, str)
        else (state_obj.get("state") if state_obj else None)
    )

    # Force-sub banner upload (temporary — moves to force_sub.py in step 13b)
    if state == "awaiting_fs_banner":
        try:
            file_id = message.photo.file_id
            await db.update_public_config("force_sub_banner_file_id", file_id)
            await message.reply_photo(
                file_id,
                caption="✅ Banner updated successfully! It will appear like this.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← Back to Force-Sub Settings",
                                callback_data="admin_force_sub_menu",
                            )
                        ]
                    ]
                ),
            )
            admin_sessions.pop(user_id, None)
        except Exception as e:
            logger.error(f"Gate banner upload failed: {e}")
            await message.reply_text(f"❌ Error: {e}")
        return

    if state != "awaiting_thumb":
        raise ContinuePropagation

    msg = await message.reply_text("Processing thumbnail...")
    try:
        file_id = message.photo.file_id
        path = await client.download_media(message, file_name=Config.THUMB_PATH)
        with open(path, "rb") as f:
            binary_data = f.read()
        await db.update_thumbnail(file_id, binary_data)
        await db.update_thumbnail_mode("custom", None)
        await msg.edit_text(
            "✅ Global thumbnail updated successfully!\n"
            "The global thumbnail mode has been set to **Custom**.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back to Thumbnail Settings",
                            callback_data="admin_thumb_menu",
                        )
                    ]
                ]
            ),
        )
        admin_sessions.pop(user_id, None)
    except Exception as e:
        logger.error(f"Thumbnail upload failed: {e}")
        with contextlib.suppress(MessageNotModified):
            await msg.edit_text(f"❌ Error: {e}")
