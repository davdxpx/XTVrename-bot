from pyrogram import filters
from config import Config

def is_authorized(user_id):
    return user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS

def is_admin(user_id):
    return user_id == Config.CEO_ID

# For Messages
auth_filter = filters.create(lambda _, __, message: is_authorized(message.from_user.id if message.from_user else 0))
admin_filter = filters.create(lambda _, __, message: is_admin(message.from_user.id if message.from_user else 0))

# For Callback Queries (they don't have .chat directly, but .message.chat)
# Actually, filters.private checks update.chat or update.message.chat.
# For CallbackQuery, it's update.message.chat.
# But `filters.private` implementation in Pyrogram might differ.
# Let's see the error again: "AttributeError: 'CallbackQuery' object has no attribute 'chat'"
# This happens when filters.private is applied to a CallbackQuery handler.
# Pyrogram filters usually work on the Update object passed (Message or CallbackQuery).
# CallbackQuery has .message which has .chat.
# But CallbackQuery itself does not have .chat.

# Solution: Don't use filters.private on CallbackQuery handlers if standard Pyrogram filters don't support it (they should though).
# OR create a custom filter that handles CallbackQuery correctly.
# OR just rely on the fact that if it's a callback from a button, it's likely private if the original message was private.

# However, looking at the code, we use `filters.regex(...) & filters.private`.
# Let's remove `filters.private` from CallbackQuery handlers, as callbacks usually come from the bot's messages which are in the chat.
# Or better, check `callback_query.message.chat.type` inside the handler if needed.
# But `auth_filter` also uses `message.from_user`. CallbackQuery has `.from_user`.
# Wait, `auth_filter` takes `message` (3rd arg). In `on_callback_query`, this 3rd arg is `CallbackQuery`.
# So `auth_filter` works fine because both have `.from_user`.

# The crash is in `filters.private`.
# We should remove `filters.private` from `on_callback_query` decorators.
