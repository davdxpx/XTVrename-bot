# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
MyFiles admin domain handlers.

Manages MyFiles settings, database channel configuration, global storage
limits, and DB cleanup tools.  Carved out of the legacy monolithic admin
module during the domain-specific submodule refactor.
"""

import asyncio
import contextlib
import datetime

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin
from utils.tasks import spawn as _spawn_task
from utils.telegram.log import get_logger

logger = get_logger("plugins.admin.myfiles")


@Client.on_callback_query(
    filters.regex(
        r"^(admin_myfiles_|prompt_myfiles_|set_unlimited_myfiles_lim_|admin_clean_)"
    )
)
async def admin_myfiles_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "admin_myfiles_settings":
        myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)
        if not myfiles_enabled:
            text = "📁 **Setup MyFiles™**\n\nConfigure database channels, storage limits, and cleanup unused files."
        else:
            text = "📁 **MyFiles Settings**\n\nConfigure database channels, storage limits, and cleanup unused files."
        buttons = [
            [InlineKeyboardButton("🗄️ Database Channels", callback_data="admin_myfiles_db_channels")],
        ]
        if not Config.PUBLIC_MODE:
            buttons.append([InlineKeyboardButton("⚙️ Global Limits", callback_data="admin_myfiles_limits")])

        buttons.append([InlineKeyboardButton("🧹 DB Cleanup Tools", callback_data="admin_myfiles_cleanup")])
        buttons.append([InlineKeyboardButton("🗂 Retention & Quotas", callback_data="admin_mf_retention")])
        buttons.append([InlineKeyboardButton("🎛 MyFiles Feature Toggles", callback_data="admin_ftmenu_myfiles")])
        buttons.append([InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data == "admin_myfiles_db_channels":
        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        channels = config.get("database_channels", {})

        if Config.PUBLIC_MODE:
            free = channels.get("free", "Not Set")
            std = channels.get("standard", "Not Set")
            dlx = channels.get("deluxe", "Not Set")
            text = (
                "🗄️ **Database Channels**\n\n"
                "Set the channels used for storing permanent/temporary files.\n\n"
                f"**Free Plan Channel:** `{free}`\n"
                f"**Standard Plan Channel:** `{std}`\n"
                f"**Deluxe Plan Channel:** `{dlx}`\n"
            )
            buttons = [
                [InlineKeyboardButton("✏️ Edit Free", callback_data="prompt_myfiles_db_free"),
                 InlineKeyboardButton("✏️ Edit Standard", callback_data="prompt_myfiles_db_standard")],
                [InlineKeyboardButton("✏️ Edit Deluxe", callback_data="prompt_myfiles_db_deluxe")],
                [InlineKeyboardButton("← Back to MyFiles Settings", callback_data="admin_myfiles_settings")]
            ]
        else:
            global_ch = channels.get("global", "Not Set")
            text = (
                "🗄️ **Global Database Channel**\n\n"
                "Set the channel used for storing all files globally.\n\n"
                f"**Global Channel:** `{global_ch}`\n"
            )
            buttons = [
                [InlineKeyboardButton("✏️ Edit Global", callback_data="prompt_myfiles_db_global")],
                [InlineKeyboardButton("← Back to MyFiles Settings", callback_data="admin_myfiles_settings")]
            ]

        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("prompt_myfiles_db_"):
        plan = data.replace("prompt_myfiles_db_", "")
        admin_sessions[user_id] = {"state": f"awaiting_myfiles_db_{plan}", "msg_id": callback_query.message.id}
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"🗄️ **Set DB Channel for {plan.capitalize()}**\n\n"
                f"⚠️ **IMPORTANT:** You MUST add me as an Administrator to this channel with 'Post Messages' permissions so I can save files there!\n\n"
                f"Please forward any message from the desired channel, or send the channel ID (e.g. `-100...`).",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_myfiles_db_channels")]])
            )

    if data == "admin_myfiles_limits":
        config = await db.settings.find_one({"_id": "global_settings"})
        limits = config.get("myfiles_limits", {})

        def f(v): return "Unlimited" if v == -1 else v

        global_limits = limits.get("global", {})
        text = (
            "⚙️ **Global Storage Limits**\n\n"
            "> Manage Team Drive storage quotas.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌍 **All Users (Team Drive)**\n"
            f"📌 Permanent Slots : `{f(global_limits.get('permanent_limit', -1))}`\n"
            f"📁 Custom Folders  : `{f(global_limits.get('folder_limit', -1))}`\n"
            f"⏳ Temp Expiration : `{f(global_limits.get('expiry_days', -1))} days`\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        buttons = [
            [InlineKeyboardButton("✏️ Edit Global Limits", callback_data="admin_myfiles_edit_limits_global")],
            [InlineKeyboardButton("← Back to MyFiles Settings", callback_data="admin_myfiles_settings")]
        ]

        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("admin_myfiles_edit_limits_"):
        plan = data.replace("admin_myfiles_edit_limits_", "")
        text = (
            f"⚙️ **Edit {plan.capitalize()} Storage Limits**\n\n"
            f"Select which specific quota you want to modify for this tier:"
        )
        buttons = [
            [InlineKeyboardButton("📌 Edit Permanent Limit", callback_data=f"prompt_myfiles_lim_{plan}_permanent")],
            [InlineKeyboardButton("📁 Edit Folder Limit", callback_data=f"prompt_myfiles_lim_{plan}_folder")],
            [InlineKeyboardButton("⏳ Edit Expiry Days", callback_data=f"prompt_myfiles_lim_{plan}_expiry")],
            [InlineKeyboardButton("← Back to Storage Limits", callback_data="admin_myfiles_limits")]
        ]
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("prompt_myfiles_lim_"):
        parts = data.replace("prompt_myfiles_lim_", "").split("_")
        plan = parts[0]
        field = parts[1]
        admin_sessions[user_id] = {"state": f"awaiting_myfiles_lim_{plan}_{field}", "msg_id": callback_query.message.id}

        display_names = {
            "permanent": "📌 Permanent Storage Slots",
            "folder": "📁 Custom Folder Limit",
            "expiry": "⏳ Temporary File Expiry (Days)"
        }
        name = display_names.get(field, field.capitalize())

        cancel_cb = "admin_myfiles_edit_limits_global" if plan == "global" else f"admin_edit_plan_{plan}"

        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"⚙️ **Set {name}**\n"
                f"For the **{plan.capitalize()}** Tier.\n\n"
                f"Please send a number in the chat (e.g. `50` or `30`).\n"
                f"> 💡 __Tip: Send `-1` to set this limit to UNLIMITED.__",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("∞ Set Unlimited", callback_data=f"set_unlimited_myfiles_lim_{plan}_{field}")],
                    [InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]
                ])
            )
        return

    if data.startswith("set_unlimited_myfiles_lim_"):
        parts = data.replace("set_unlimited_myfiles_lim_", "").split("_")
        plan = parts[0]
        field = parts[1]

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        limits = config.get("myfiles_limits", {})
        if plan not in limits:
            limits[plan] = {}

        if field == "permanent":
            limits[plan]["permanent_limit"] = -1
        elif field == "folder":
            limits[plan]["folder_limit"] = -1
        elif field == "expiry":
            limits[plan]["expiry_days"] = -1

        if Config.PUBLIC_MODE:
            await db.update_public_config("myfiles_limits", limits)
        else:
            await db.settings.update_one({"_id": "global_settings"}, {"$set": {"myfiles_limits": limits}}, upsert=True)

        admin_sessions.pop(user_id, None)
        cancel_cb = "admin_myfiles_edit_limits_global" if plan == "global" else f"admin_edit_plan_{plan}"
        display_names = {"permanent": "Permanent Storage Slots", "folder": "Custom Folder Limit", "expiry": "Temporary File Expiry"}
        name = display_names.get(field, field)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✅ **{plan.capitalize()}** {name} set to **Unlimited**.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=cancel_cb)]])
            )
        return

    if data == "admin_myfiles_cleanup":
        text = (
            "🧹 **DB Cleanup Tools**\n\n"
            "Run maintenance tasks to clear up storage.\n"
            "Select a cleanup operation:"
        )
        buttons = []
        if Config.PUBLIC_MODE:
            buttons.append([InlineKeyboardButton("🧹 Clear Free Expired", callback_data="admin_myfiles_clean_free")])
            buttons.append([InlineKeyboardButton("🧹 Clear Donator Expired", callback_data="admin_myfiles_clean_donator")])
            buttons.append([InlineKeyboardButton("🧹 Clear All Expired (All Plans)", callback_data="admin_clean_all_expired")])
            buttons.append([InlineKeyboardButton("🗑️ Purge Orphaned Files", callback_data="admin_clean_orphaned_files")])
            buttons.append([InlineKeyboardButton("🗑️ Purge Empty Folders", callback_data="admin_clean_empty_folders")])
            buttons.append([InlineKeyboardButton("📊 Storage Stats", callback_data="admin_clean_storage_stats")])
        else:
            buttons.append([InlineKeyboardButton("🧹 Clear All Expired Temp Files", callback_data="admin_clean_all_expired")])
            buttons.append([InlineKeyboardButton("🗑️ Purge Orphaned Files", callback_data="admin_clean_orphaned_files")])
            buttons.append([InlineKeyboardButton("🗑️ Purge Empty Folders", callback_data="admin_clean_empty_folders")])
            buttons.append([InlineKeyboardButton("🗑️ Clear Stale Flow Sessions", callback_data="admin_clean_stale_sessions")])
            buttons.append([InlineKeyboardButton("📊 Storage Stats", callback_data="admin_clean_storage_stats")])
        buttons.append([InlineKeyboardButton("← Back to MyFiles Settings", callback_data="admin_myfiles_settings")])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data in ("admin_myfiles_clean_free", "admin_myfiles_clean_donator", "admin_clean_all_expired",
                "admin_clean_orphaned_files", "admin_clean_empty_folders", "admin_clean_stale_sessions",
                "admin_clean_storage_stats"):

        if data == "admin_clean_storage_stats":
            perm_count = await db.files.count_documents({"status": "permanent"})
            temp_count = await db.files.count_documents({"status": "temporary"})
            now = datetime.datetime.utcnow()
            expired_count = await db.files.count_documents({"status": "temporary", "expires_at": {"$lt": now}})
            folder_count = await db.folders.count_documents({})
            empty_folders = 0
            async for folder in db.folders.find():
                fcount = await db.files.count_documents({"folder_id": folder["_id"]})
                if fcount == 0:
                    empty_folders += 1
            stale_sessions = await db.users.count_documents({"flow_session": {"$exists": True}})

            text = (
                "📊 **Storage Statistics**\n\n"
                f"**Permanent Files:** `{perm_count}`\n"
                f"**Temporary Files:** `{temp_count}`\n"
                f"**Expired Temp Files:** `{expired_count}`\n"
                f"**Total Folders:** `{folder_count}`\n"
                f"**Empty Folders:** `{empty_folders}`\n"
                f"**Stale Flow Sessions:** `{stale_sessions}`"
            )
            with contextlib.suppress(MessageNotModified):
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← Back to Cleanup", callback_data="admin_myfiles_cleanup")]
                ]))
            return

        await callback_query.answer("Cleanup job started in background.", show_alert=True)

        async def run_admin_cleanup():
            now = datetime.datetime.utcnow()
            count = 0
            job_name = ""

            if data == "admin_myfiles_clean_free":
                job_name = "Free Expired Temp"
                cursor = db.users.find({"$or": [{"is_premium": False}, {"premium_plan": "free"}]})
                free_users = await cursor.to_list(length=None)
                free_ids = [u["user_id"] for u in free_users]
                if free_ids:
                    res = await db.files.delete_many({"user_id": {"$in": free_ids}, "status": "temporary", "expires_at": {"$lt": now}})
                    count = res.deleted_count

            elif data == "admin_myfiles_clean_donator":
                job_name = "Donator Expired Temp"
                cursor = db.users.find({"is_premium": False, "premium_plan": "donator"})
                donators = await cursor.to_list(length=None)
                donator_ids = [u["user_id"] for u in donators]
                if donator_ids:
                    res = await db.files.delete_many({"user_id": {"$in": donator_ids}, "status": "temporary", "expires_at": {"$lt": now}})
                    count = res.deleted_count

            elif data == "admin_clean_all_expired":
                job_name = "All Expired Temp"
                res = await db.files.delete_many({"status": "temporary", "expires_at": {"$lt": now}})
                count = res.deleted_count

            elif data == "admin_clean_orphaned_files":
                job_name = "Orphaned Files (no folder match)"
                folder_ids = set()
                async for folder in db.folders.find():
                    folder_ids.add(folder["_id"])
                if folder_ids:
                    res = await db.files.delete_many({
                        "folder_id": {"$ne": None, "$nin": list(folder_ids)}
                    })
                    count = res.deleted_count

            elif data == "admin_clean_empty_folders":
                job_name = "Empty Folders"
                async for folder in db.folders.find():
                    fcount = await db.files.count_documents({"folder_id": folder["_id"]})
                    if fcount == 0:
                        await db.folders.delete_one({"_id": folder["_id"]})
                        count += 1

            elif data == "admin_clean_stale_sessions":
                job_name = "Stale Flow Sessions"
                res = await db.users.update_many(
                    {"flow_session": {"$exists": True}},
                    {"$unset": {"flow_session": "", "flow_session_updated": ""}}
                )
                count = res.modified_count

            with contextlib.suppress(Exception):
                await client.send_message(user_id, f"✅ **Cleanup Complete: {job_name}**\n\nProcessed: {count} items.")

        _spawn_task(run_admin_cleanup(), label="admin_myfiles_cleanup")
        return


# ---------------------------------------------------------------------------
# Text-input state handler (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def handle_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_myfiles_db_* and awaiting_myfiles_lim_* states."""
    from pyrogram import StopPropagation

    user_id = message.from_user.id

    if state.startswith("awaiting_myfiles_db_"):
        plan = state.replace("awaiting_myfiles_db_", "")
        val = message.text.strip() if message.text else ""

        ch_id = None
        if message.forward_from_chat:
            ch_id = message.forward_from_chat.id
        elif val:
            try:
                chat = await client.get_chat(val)
                ch_id = chat.id
            except Exception as e:
                await edit_or_reply(client, message, msg_id,
                    f"❌ Error finding channel: {e}\nTry forwarding a message instead.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_myfiles_db_channels")]])
                )
                return

        if ch_id:
            await db.update_db_channel(plan, ch_id)
            await edit_or_reply(client, message, msg_id,
                f"✅ {plan.capitalize()} DB Channel updated to `{ch_id}`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to DB Channels", callback_data="admin_myfiles_db_channels")]])
            )
            admin_sessions.pop(user_id, None)
            raise StopPropagation
        return

    if state.startswith("awaiting_myfiles_lim_"):
        parts = state.replace("awaiting_myfiles_lim_", "").split("_")
        plan = parts[0]
        field = parts[1]
        val = message.text.strip() if message.text else ""

        cancel_cb = "admin_myfiles_edit_limits_global" if plan == "global" else f"admin_edit_plan_{plan}"

        try:
            val_int = int(val)
        except ValueError:
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]])
            )
            raise StopPropagation from None

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        limits = config.get("myfiles_limits", {})
        if plan not in limits:
            limits[plan] = {}

        if field == "permanent":
            limits[plan]["permanent_limit"] = val_int
        elif field == "folder":
            limits[plan]["folder_limit"] = val_int
        elif field == "expiry":
            limits[plan]["expiry_days"] = val_int

        if Config.PUBLIC_MODE:
            await db.update_public_config("myfiles_limits", limits)
        else:
            await db.settings.update_one({"_id": "global_settings"}, {"$set": {"myfiles_limits": limits}}, upsert=True)

        await edit_or_reply(client, message, msg_id,
            f"✅ {plan.capitalize()} {field} limit updated to `{val_int}`.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=cancel_cb)]])
        )
        admin_sessions.pop(user_id, None)
        raise StopPropagation


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_myfiles_", handle_text)
