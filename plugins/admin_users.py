# --- Imports ---
import json
import io
import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from database import db
from utils.log import get_logger
from plugins.admin import admin_sessions

logger = get_logger("plugins.admin_users")

# === Helper Functions ===
def is_admin(user_id):
    return user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS

async def show_users_menu(client, update):
    text = (
        "**👤 Global User Management**\n\n"
        "Manage all users across the network.\n"
        "Search, filter, ban, and view detailed profiles."
    )

    buttons = [
        [InlineKeyboardButton("🔍 Search User", callback_data="admin_user_search_start")],
        [
            InlineKeyboardButton("👥 All Users", callback_data="list_users|all|0"),
            InlineKeyboardButton("🚫 Banned", callback_data="list_users|banned|0")
        ]
    ]

    if Config.PUBLIC_MODE:
        buttons[1].append(InlineKeyboardButton("💎 Premium", callback_data="list_users|premium|0"))

    buttons.append([InlineKeyboardButton("🕒 Recent", callback_data="list_users|recent|0")])
    buttons.append([InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")])

    markup = InlineKeyboardMarkup(buttons)

    if isinstance(update, Message):
        await update.reply(text, reply_markup=markup)
    else:

        try:
            await update.edit_message_text(text, reply_markup=markup)
        except Exception:

            await client.send_message(update.from_user.id, text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^admin_users_menu$"))

# --- Handlers ---
async def admin_users_menu(client, callback):
    if not is_admin(callback.from_user.id):
        return

    await show_users_menu(client, callback)

@Client.on_callback_query(filters.regex(r"^list_users\|"))
async def list_users(client, callback):

    if not is_admin(callback.from_user.id): return

    try:
        _, mode, page = callback.data.split("|")
        page = int(page)
    except:
        mode = "all"
        page = 0

    limit = 10
    skip = page * limit

    filter_dict = {}
    sort_by = "joined_at"

    if mode == "premium":
        filter_dict = {"is_premium": True}
    elif mode == "banned":
        filter_dict = {"banned": True}
    elif mode == "recent":
        sort_by = "updated_at"

    users = await db.get_users_paginated(filter_dict, skip, limit, sort_by)
    total = await db.count_users(filter_dict)

    text = f"**👤 User List ({mode.title()})**\nPage {page + 1} (Total: {total})\n\n"

    markup = []
    if not users:
        text += "No users found."
    else:
        for u in users:
            uid = u.get("user_id")
            name = u.get("first_name", "Unknown")[:15]
            uname = f"(@{u.get('username')})" if u.get("username") else ""
            status = "🚫" if u.get("banned") else ("💎" if u.get("is_premium") else "👤")

            label = f"{status} {name} {uname}"
            markup.append([InlineKeyboardButton(label, callback_data=f"view_user|{uid}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"list_users|{mode}|{page-1}"))
    if (skip + limit) < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"list_users|{mode}|{page+1}"))

    if nav: markup.append(nav)

    markup.append([InlineKeyboardButton("← Back to User Management", callback_data="admin_users_menu")])

    await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^admin_user_search_start$"))
async def start_user_search(client, callback):
    if not is_admin(callback.from_user.id): return
    admin_sessions[callback.from_user.id] = "wait_search_query"
    try:
        await callback.message.edit_text(
            "**🔍 User Search**\n\n"
            "Send the **User ID**, **Username**, or **First Name** to search.\n"
            "(Supports partial match for names)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_users_menu")]])
        )
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^view_user\|"))
async def view_user_profile(client, callback):
    if not is_admin(callback.from_user.id): return

    try:
        target_id = int(callback.data.split("|")[1])
    except:
        await callback.answer("Invalid User ID", show_alert=True)
        return

    user = await db.get_user(target_id)
    if not user:
        await callback.answer("User not found in DB.", show_alert=True)
        return

    username = f"@{user.get('username')}" if user.get("username") else "N/A"
    joined_ts = user.get("joined_at", 0)
    joined_date = datetime.fromtimestamp(joined_ts).strftime('%Y-%m-%d') if joined_ts else "Unknown"

    last_active_ts = user.get("last_active", 0)
    last_active = datetime.fromtimestamp(last_active_ts).strftime('%Y-%m-%d %H:%M') if last_active_ts else "Unknown"

    is_prem = user.get("is_premium", False)
    prem_exp = user.get("premium_expiry", 0)
    prem_plan = user.get("premium_plan", "standard")

    prem_status = "🆓 Free Plan"
    if is_prem:
        plan_display = "⭐ Standard" if prem_plan == "standard" else "💎 Deluxe"

        if not prem_exp:
            prem_status = f"{plan_display} (Lifetime)"
        elif prem_exp > time.time():
            dt = datetime.fromtimestamp(prem_exp).strftime('%Y-%m-%d')
            prem_status = f"{plan_display} (Exp: {dt})"
        else:
            prem_status = f"🔴 Expired (was {plan_display})"

    banned = user.get("banned", False)
    status_emoji = "🔴 BANNED" if banned else "🟢 Active"

    usage = await db.get_user_usage(target_id) or {}
    import datetime as dt_module
    current_utc_date = dt_module.datetime.utcnow().strftime('%Y-%m-%d')
    files_today = usage.get("file_count", 0) if usage.get("date") == current_utc_date else 0
    files_alltime = usage.get("file_count_alltime", 0)

    text = (
        f"**👤 User Profile: {target_id}**\n\n"
        f"📛 **Name:** {user.get('first_name', 'Unknown')}\n"
        f"🔗 **Username:** {username}\n"
        f"📅 **Joined:** {joined_date}\n"
        f"⏱ **Last Active:** {last_active}\n"
        f"📊 **Status:** {status_emoji}\n"
        f"💎 **Plan:** {prem_status}\n\n"
        f"📈 **Stats:**\n"
        f"• Files Today: `{files_today}`\n"
        f"• Files All-Time: `{files_alltime}`\n"
    )

    markup = []

    if banned:
        markup.append([InlineKeyboardButton("🟢 Unban User", callback_data=f"act_unban|{target_id}")])
    else:
        markup.append([InlineKeyboardButton("🔴 Ban User", callback_data=f"act_ban|{target_id}")])

    if Config.PUBLIC_MODE:
        if is_prem:
            markup.append([
                InlineKeyboardButton("🔄 Extend Plan", callback_data=f"act_add_prem_ask|{target_id}"),
                InlineKeyboardButton("❌ Remove Premium", callback_data=f"act_reset_prem|{target_id}")
            ])
        else:
            markup.append([
                InlineKeyboardButton("➕ Add Standard", callback_data=f"act_add_prem_ask_standard|{target_id}"),
                InlineKeyboardButton("➕ Add Deluxe", callback_data=f"act_add_prem_ask_deluxe|{target_id}")
            ])

    markup.append([
        InlineKeyboardButton("🗑 Delete Data", callback_data=f"act_del_data_ask|{target_id}"),
        InlineKeyboardButton("📄 Export JSON", callback_data=f"act_export_json|{target_id}")
    ])

    markup.append([
        InlineKeyboardButton("← Back to User Management", callback_data="admin_users_menu")
    ])

    await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^act_ban\|"))
async def action_ban_user(client, callback):
    uid = int(callback.data.split("|")[1])

    if uid == Config.CEO_ID or uid in Config.ADMIN_IDS:
        await callback.answer("⛔ Cannot ban Admins.", show_alert=True)
        return

    await db.block_user(uid)
    if db.users is not None:
        await db.users.update_one({"user_id": uid}, {"$set": {"banned": True}})
    await db.add_log("ban_user", callback.from_user.id, f"Banned User {uid}")
    await callback.answer(f"🚫 User {uid} BANNED globally.", show_alert=True)
    await view_user_profile(client, callback)

@Client.on_callback_query(filters.regex(r"^act_unban\|"))
async def action_unban_user(client, callback):
    uid = int(callback.data.split("|")[1])
    await db.unblock_user(uid)
    if db.users is not None:
        await db.users.update_one({"user_id": uid}, {"$set": {"banned": False}})
    await db.add_log("unban_user", callback.from_user.id, f"Unbanned User {uid}")
    await callback.answer(f"✅ User {uid} Unbanned.", show_alert=True)
    await view_user_profile(client, callback)

@Client.on_callback_query(filters.regex(r"^act_reset_prem\|"))
async def action_reset_prem(client, callback):
    uid = int(callback.data.split("|")[1])
    await db.reset_user_premium(uid)
    await db.add_log("reset_premium", callback.from_user.id, f"Reset Premium for {uid}")
    await callback.answer("✅ Premium reset to Free.", show_alert=True)
    await view_user_profile(client, callback)

@Client.on_callback_query(filters.regex(r"^act_add_prem_ask(_standard|_deluxe)?\|"))
async def action_add_prem_ask(client, callback):
    data = callback.data.split("|")[0]
    uid = int(callback.data.split("|")[1])

    plan = "standard"
    if data.endswith("_standard"):
        plan = "standard"
    elif data.endswith("_deluxe"):
        plan = "deluxe"
    else:
        user = await db.get_user(uid)
        plan = user.get("premium_plan", "standard") if user else "standard"

    admin_sessions[callback.from_user.id] = {"state": "wait_add_prem_days", "target_id": uid, "plan": plan}

    try:
        await callback.message.edit_text(
            f"**➕ Add Premium ({plan.capitalize()}) for User {uid}**\n\nEnter the duration in **DAYS** (e.g. `30`):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"view_user|{uid}")]])
        )
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^act_del_data_ask\|"))
async def action_del_data_ask(client, callback):
    uid = int(callback.data.split("|")[1])
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ CONFIRM DELETE", callback_data=f"act_del_data_exec|{uid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"view_user|{uid}")]
    ])
    await callback.edit_message_text(
        f"**⚠️ DELETE USER DATA: {uid}**\n\n"
        "Are you sure? This will wipe history, requests, and settings.\n"
        "It cannot be undone.",
        reply_markup=markup
    )

@Client.on_callback_query(filters.regex(r"^act_del_data_exec\|"))
async def action_del_data_exec(client, callback):
    uid = int(callback.data.split("|")[1])
    if uid == Config.CEO_ID or uid in Config.ADMIN_IDS:
        await callback.answer("⛔ Cannot delete Admin data.", show_alert=True)
        return

    await db.delete_user_data(uid)
    await db.add_log("delete_user", callback.from_user.id, f"Deleted User {uid}")
    await callback.answer("User Deleted.", show_alert=True)
    await admin_users_menu(client, callback)

@Client.on_callback_query(filters.regex(r"^act_export_json\|"))
async def action_export_json(client, callback):
    uid = int(callback.data.split("|")[1])
    user = await db.get_user(uid)

    if not user:
        await callback.answer("User not found.", show_alert=True)
        return

    usage = await db.get_user_usage(uid)
    user['usage_stats'] = usage

    def default_serializer(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return str(obj)

    json_str = json.dumps(user, indent=4, default=default_serializer)

    bio = io.BytesIO(json_str.encode("utf-8"))
    bio.name = f"user_{uid}.json"

    await callback.message.delete()
    await client.send_document(
        callback.from_user.id,
        document=bio,
        caption=f"📄 **User Data Export:** `{uid}`"
    )

    await show_users_menu(client, callback)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
