from pyrogram import filters
from config import Config

def is_authorized(user_id):
    return user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS

def is_admin(user_id):
    return user_id == Config.CEO_ID

auth_filter = filters.create(lambda _, __, message: is_authorized(message.from_user.id if message.from_user else 0))
admin_filter = filters.create(lambda _, __, message: is_admin(message.from_user.id if message.from_user else 0))
