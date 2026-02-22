from pyrogram import filters
from config import Config

def is_authorized(user_id):
    return user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS

def is_admin(user_id):
    return user_id == Config.CEO_ID

# Simply use `message` (which is the update object)
# Pyrogram filters pass (filter, client, update)
# `update` is Message or CallbackQuery
# Both have `.from_user`
auth_filter = filters.create(lambda _, __, update: is_authorized(update.from_user.id if update.from_user else 0))
admin_filter = filters.create(lambda _, __, update: is_admin(update.from_user.id if update.from_user else 0))
