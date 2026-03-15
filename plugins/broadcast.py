import asyncio
import time
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from config import Config
from utils.state import set_state, get_state, update_data, get_data, clear_session
from plugins.admin import is_admin


@Client.on_callback_query(
    filters.regex(
        r"^(admin_broadcast|broadcast_add_btn|broadcast_preview|broadcast_send|broadcast_cancel)$"
    )
)
async def broadcast_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        await callback_query.answer("Not authorized.", show_alert=True)
        return

    if not Config.PUBLIC_MODE:
        await callback_query.answer("Broadcast is only available in Public Mode.", show_alert=True)
        return

    data = callback_query.data

    if data == "admin_broadcast":
        set_state(user_id, "awaiting_broadcast_message")
        update_data(user_id, "broadcast_buttons", [])
        await callback_query.message.edit_text(
            "📢 **Broadcast Message**\n\n"
            "Please send the message (text, photo, video, etc.) that you want to broadcast to all users.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")]]
            ),
        )

    elif data == "broadcast_add_btn":
        set_state(user_id, "awaiting_broadcast_button")
        await callback_query.message.edit_text(
            "➕ **Add Inline Button**\n\n"
            "Please send the button text and URL separated by a pipe `|`.\n\n"
            "Example:\n`Click Here | https://google.com`",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Menu", callback_data="broadcast_preview"
                        )
                    ]
                ]
            ),
        )

    elif data == "broadcast_preview":
        set_state(user_id, "broadcast_ready")
        ud = get_data(user_id)
        msg_id = ud.get("broadcast_message_id")
        buttons = ud.get("broadcast_buttons", [])

        reply_markup = None
        if buttons:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text=b["text"], url=b["url"])] for b in buttons]
            )

        await callback_query.message.delete()
        preview_msg = await client.copy_message(
            chat_id=user_id,
            from_chat_id=user_id,
            message_id=msg_id,
            reply_markup=reply_markup,
        )
        await preview_msg.reply_text(
            "👀 **Broadcast Preview**\n\n"
            "This is how your message will look. What would you like to do?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "➕ Add Button", callback_data="broadcast_add_btn"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "✅ Send Broadcast", callback_data="broadcast_send"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data="broadcast_cancel"
                        )
                    ],
                ]
            ),
        )

    elif data == "broadcast_send":
        await callback_query.message.edit_text(
            "🚀 **Broadcast started!**\n\nFetching users..."
        )
        # Pass necessary data directly to the task before clearing session
        ud = get_data(user_id)
        msg_id = ud.get("broadcast_message_id")
        buttons = ud.get("broadcast_buttons", [])
        asyncio.create_task(run_broadcast(client, user_id, callback_query.message, msg_id, buttons))
        clear_session(user_id)

    elif data == "broadcast_cancel":
        clear_session(user_id)
        await callback_query.message.edit_text("❌ **Broadcast cancelled.**")


@Client.on_message(filters.private, group=1)
async def broadcast_message_handler(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == "awaiting_broadcast_message":
        update_data(user_id, "broadcast_message_id", message.id)
        set_state(user_id, "broadcast_ready")
        await message.reply_text(
            "✅ **Message saved!**\n\nWhat would you like to do next?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "➕ Add Button", callback_data="broadcast_add_btn"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "👀 Preview", callback_data="broadcast_preview"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "✅ Send Broadcast", callback_data="broadcast_send"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data="broadcast_cancel"
                        )
                    ],
                ]
            ),
        )
        return

    elif state == "awaiting_broadcast_button":
        text = message.text
        if not text or "|" not in text:
            await message.reply_text(
                "❌ **Invalid format!**\n\nPlease send it as `Text | URL`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="broadcast_preview"
                            )
                        ]
                    ]
                ),
            )
            return

        btn_text, btn_url = [x.strip() for x in text.split("|", 1)]
        if not btn_url.startswith(("http://", "https://", "tg://")):
            btn_url = "https://" + btn_url

        ud = get_data(user_id)
        buttons = ud.get("broadcast_buttons", [])
        buttons.append({"text": btn_text, "url": btn_url})
        update_data(user_id, "broadcast_buttons", buttons)
        set_state(user_id, "broadcast_ready")

        await message.reply_text(
            "✅ **Button added!**",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Menu", callback_data="broadcast_preview"
                        )
                    ]
                ]
            ),
        )
        return

    raise ContinuePropagation


async def run_broadcast(client, admin_id, status_message, msg_id, buttons):
    users = await db.get_all_users()
    reply_markup = None
    if buttons:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=b["text"], url=b["url"])] for b in buttons]
        )

    total = len(users)
    sent = 0
    failed = 0

    await status_message.edit_text(
        f"🚀 **Broadcast started!**\n\nSending to {total} users..."
    )

    start_time = time.time()

    for user in users:
        try:
            await client.copy_message(
                chat_id=user,
                from_chat_id=admin_id,
                message_id=msg_id,
                reply_markup=reply_markup,
            )
            sent += 1
        except Exception:
            failed += 1

        if (sent + failed) % 20 == 0:
            try:
                await status_message.edit_text(
                    f"🚀 **Broadcasting...**\n\nTotal: {total}\nSent: {sent}\nFailed: {failed}"
                )
            except Exception:
                pass

        await asyncio.sleep(0.1)  # Rate limiting

    end_time = time.time()
    duration = round(end_time - start_time, 2)

    await status_message.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"📊 **Statistics:**\n"
        f"Total Users: `{total}`\n"
        f"Successfully Sent: `{sent}`\n"
        f"Failed/Blocked: `{failed}`\n"
        f"Time Taken: `{duration}s`"
    )


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
