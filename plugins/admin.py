# --- Imports ---
from utils.logger import debug
from pyrogram import ContinuePropagation
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from utils.log import get_logger
import asyncio
import io

logger = get_logger("plugins.admin")
admin_sessions = {}


async def get_admin_state(user_id):
    doc = await db.users.find_one({"user_id": user_id})
    return doc.get("admin_state") if doc else None


async def set_admin_state(user_id, state_dict):
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"admin_state": state_dict}},
        upsert=True
    )


async def clear_admin_state(user_id):
    await db.users.update_one(
        {"user_id": user_id},
        {"$unset": {"admin_state": ""}}
    )

# === Helper Functions ===


def get_admin_main_menu(pro_session, public_mode):
    pro_btn_text = "🚀 Manage 𝕏TV Pro™" if pro_session else "🚀 Setup 𝕏TV Pro™"

    keyboard = []

    keyboard.append([InlineKeyboardButton(
        "👤 User Management", callback_data="admin_users_menu")])

    if public_mode:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🌐 Public Mode Settings", callback_data="adm_pub_set"
                ),
                InlineKeyboardButton(
                    "🔒 Settings", callback_data="adm_pln_limits"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "💳 Manage Payments", callback_data="adm_pay_menu"
                ),
                InlineKeyboardButton(
                    "📢 Force-Sub Settings", callback_data="adm_fs_menu"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📺 Dumb Channels", callback_data="adm_dmb_menu"
                ),
                InlineKeyboardButton(
                    "⏱ Edit Dumb Channel Timeout", callback_data="adm_dmb_tout"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📊 Usage Dashboard", callback_data="admin_usage_dashboard"
                ),
                InlineKeyboardButton(
                    "📢 Broadcast Message", callback_data="admin_broadcast"
                ),
            ]
        )
    else:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🖼 Manage Thumbnail", callback_data="adm_thm_menu"
                ),
                InlineKeyboardButton(
                    "📋 Templates", callback_data="adm_tpl_menu"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📺 Dumb Channels",
                    callback_data="adm_dmb_menu"),
                InlineKeyboardButton(
                    "⚙️ General Settings",
                    callback_data="adm_gen_menu"),
            ])
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📊 Usage Dashboard",
                    callback_data="admin_usage_dashboard"),
                InlineKeyboardButton(
                    "👀 View Settings",
                    callback_data="adm_view"),
            ])
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔒 Access & Limits", callback_data="adm_pln_limits"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📁 /myfiles Settings", callback_data="adm_myf_set"
                ),
            ]
        )

    keyboard.append(
        [InlineKeyboardButton(pro_btn_text, callback_data="pro_setup_menu")]
    )

    return InlineKeyboardMarkup(keyboard)


def get_admin_templates_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📝 Edit Filename Templates",
                    callback_data="adm_tpl_fn",
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit Caption Template", callback_data="adm_tpl_cap"
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit Metadata Templates", callback_data="adm_tpl_meta"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔤 Preferred Separator", callback_data="adm_tpl_sep"
                )
            ],
            [InlineKeyboardButton("← Back to Admin Panel", callback_data="adm_main")],
        ]
    )


async def get_admin_access_limits_menu():
    buttons = []

    if Config.PUBLIC_MODE:
        buttons.append([InlineKeyboardButton(
            "📋 Per-Plan Settings", callback_data="adm_pln_per")])
        buttons.append([InlineKeyboardButton(
            "🌍 Global Daily Egress Limit", callback_data="adm_pln_gl_lim")])
        pro_session = await db.get_pro_session()
        if pro_session:
            buttons.append(
                [
                    InlineKeyboardButton(
                        "🚀 XTV Pro 4GB Access", callback_data="adm_pln_4gb"
                    )
                ]
            )
    else:
        buttons.append([InlineKeyboardButton(
            "🌍 Set Global Daily Egress Limit", callback_data="adm_pln_gl_eg")])

    buttons.append([InlineKeyboardButton(
        "← Back", callback_data="adm_pln_limits")])
    return InlineKeyboardMarkup(buttons)


def get_admin_public_settings_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🤖 Edit Bot Name", callback_data="adm_pub_name"
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 Edit Community Name",
                    callback_data="adm_pub_comm",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔗 Edit Support Contact",
                    callback_data="adm_pub_supp",
                )
            ],
            [
                InlineKeyboardButton(
                    "👀 View Public Config", callback_data="adm_pub_view"
                )
            ],
            [InlineKeyboardButton("← Back to Admin Panel", callback_data="adm_main")],
        ]
    )


def is_admin(user_id):

    return user_id == Config.CEO_ID


@Client.on_message(filters.command("admin") & filters.private)
# --- Handlers ---
async def admin_panel(client, message):
    if not is_admin(message.from_user.id):
        return

    pro_session = await db.get_pro_session()

    if Config.PUBLIC_MODE:
        text = (
            "🛠 **Public Mode Admin Panel** 🛠\n\n> Manage global settings for Public Mode.\n"
            "Welcome, CEO.\n"
            "Manage global settings for Public Mode.\n"
            "These settings apply globally to the bot, such as branding and rate limits.\n"
            "*(Use /settings to configure your personal renaming templates)*")
    else:
        text = (
            "🛠 **𝕏TV Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for the 𝕏TV MediaStudio™.\n"
            "These settings affect all files processed by the bot."
        )

    await message.reply_text(
        text, reply_markup=get_admin_main_menu(pro_session, Config.PUBLIC_MODE)
    )


debug("✅ Loaded handler: admin_callback")



async def admin_callback(client, callback_query):
    # Route internal recursive calls to the appropriate domain handler
    data = callback_query.data
    if data.startswith("adm_myf_"):
        await admin_myf_callback(client, callback_query)
    elif data.startswith("adm_pln_"):
        await admin_pln_callback(client, callback_query)
    elif data.startswith("adm_dmb_"):
        await admin_dmb_callback(client, callback_query)
    elif data.startswith("adm_pay_"):
        await admin_pay_callback(client, callback_query)
    elif data.startswith("adm_pub_") or data.startswith("adm_fs_") or data.startswith("adm_pln_free_") or data.startswith("adm_pln_p_"):
        await admin_pub_callback(client, callback_query)
    elif data.startswith("adm_tpl_") or data.startswith("adm_fn_"):
        await admin_tpl_callback(client, callback_query)
    elif data.startswith("adm_thm_"):
        await admin_thm_callback(client, callback_query)
    elif data.startswith("adm_gen_"):
        await admin_gen_callback(client, callback_query)
    else:
        await admin_misc_callback(client, callback_query)

# === MYFILES SETTINGS MODULE ===
@Client.on_callback_query(filters.regex(r"^adm_myf_"))
async def admin_myf_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_myf_set":
        text = "📁 **/myfiles Settings**\n\nConfigure database channels, storage limits, and cleanup unused files."
        buttons = [[InlineKeyboardButton(
            "🗄️ Database Channels", callback_data="adm_myf_db")], ]
        if not Config.PUBLIC_MODE:
            buttons.append([InlineKeyboardButton(
                "⚙️ Global Limits", callback_data="adm_myf_lim")])

        buttons.append([InlineKeyboardButton(
            "🧹 DB Cleanup Tools", callback_data="adm_myf_cln")])
        buttons.append([InlineKeyboardButton(
            "← Back", callback_data="adm_pln_limits" if Config.PUBLIC_MODE else "adm_main")])
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data == "adm_myf_db":
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
                [InlineKeyboardButton("✏️ Edit Free", callback_data="adm_myf_db_free"),
                 InlineKeyboardButton("✏️ Edit Standard", callback_data="adm_myf_db_std")],
                [InlineKeyboardButton("✏️ Edit Deluxe", callback_data="adm_myf_db_dlx")],
                [InlineKeyboardButton("← Back", callback_data="adm_myf_set")]
            ]
        else:
            global_ch = channels.get("global", "Not Set")
            text = (
                "🗄️ **Global Database Channel**\n\n"
                "Set the channel used for storing all files globally.\n\n"
                f"**Global Channel:** `{global_ch}`\n"
            )
            buttons = [
                [InlineKeyboardButton("✏️ Edit Global", callback_data="adm_myf_db_gl")],
                [InlineKeyboardButton("← Back", callback_data="adm_myf_set")]
            ]

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_myf_db_"):
        plan = data.replace("adm_myf_db_", "")
        await set_admin_state(user_id, {"state": f"awaiting_myfiles_db_{plan}", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                f"🗄️ **Set DB Channel for {plan.capitalize()}**\n\n"
                f"⚠️ **IMPORTANT:** You MUST add me as an Administrator to this channel with 'Post Messages' permissions so I can save files there!\n\n"
                f"Please forward any message from the desired channel, or send the channel ID (e.g. `-100...`).",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_myf_db")]])
            )
        except MessageNotModified:
            pass
    if data == "adm_myf_lim":
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
            [InlineKeyboardButton("✏️ Edit Global Limits", callback_data="adm_myf_ed_gl")],
            [InlineKeyboardButton("← Back", callback_data="adm_myf_set")]
        ]

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_myf_ed_"):
        plan = data.replace("adm_myf_ed_", "")
        text = (
            f"⚙️ **Edit {plan.capitalize()} Storage Limits**\n\n"
            f"Select which specific quota you want to modify for this tier:"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    "📌 Edit Permanent Limit", callback_data=f"adm_myf_l_{plan}_permanent")], [
                InlineKeyboardButton(
                    "📁 Edit Folder Limit", callback_data=f"adm_myf_l_{plan}_folder")], [
                        InlineKeyboardButton(
                            "⏳ Edit Expiry Days", callback_data=f"adm_myf_l_{plan}_expiry")], [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_myf_lim")]]
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_myf_l_"):
        parts = data.replace("adm_myf_l_", "").split("_")
        plan = parts[0]
        field = parts[1]
        await set_admin_state(user_id, {"state": f"awaiting_myfiles_lim_{plan}_{field}", "msg_id": callback_query.message.id})

        display_names = {
            "permanent": "📌 Permanent Storage Slots",
            "folder": "📁 Custom Folder Limit",
            "expiry": "⏳ Temporary File Expiry (Days)"
        }
        name = display_names.get(field, field.capitalize())

        cancel_cb = "adm_myf_ed_gl" if plan == "global" else f"adm_pln_ed_{plan}"

        try:
            await callback_query.message.edit_text(
                f"⚙️ **Set {name}**\n"
                f"For the **{plan.capitalize()}** Tier.\n\n"
                f"Please send a number in the chat (e.g. `50` or `30`).\n"
                f"> 💡 *Tip: Send `-1` to set this limit to UNLIMITED.*",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]])
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_myf_cln":
        text = (
            "🧹 **DB Cleanup Tools**\n\n"
            "Run maintenance tasks to clear up storage."
        )
        buttons = [
            [InlineKeyboardButton("🧹 Clear Free Expired", callback_data="adm_myf_cln_free")],
            [InlineKeyboardButton("🧹 Clear Donator Expired", callback_data="adm_myf_cln_don")],
            [InlineKeyboardButton("← Back", callback_data="adm_myf_set")]
        ]
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data == "adm_myf_cln_free" or data == "adm_myf_cln_don":
        try:
            await callback_query.answer("Cleanup job started in background.", show_alert=True)

            import asyncio
            import datetime

            async def run_admin_cleanup():
                now = datetime.datetime.utcnow()
                count = 0
                if data == "adm_myf_cln_free":
                    # Get all free users
                    cursor = db.users.find(
                        {"$or": [{"is_premium": False}, {"premium_plan": "free"}]})
                    free_users = await cursor.to_list(length=None)
                    free_ids = [u["user_id"] for u in free_users]

                    if free_ids:
                        res = await db.files.delete_many({"user_id": {"$in": free_ids}, "status": "temporary", "expires_at": {"$lt": now}})
                        count = res.deleted_count
                else:
                    # Donators
                    cursor = db.users.find(
                        {"is_premium": False, "premium_plan": "donator"})
                    donators = await cursor.to_list(length=None)
                    donator_ids = [u["user_id"] for u in donators]

                    if donator_ids:
                        res = await db.files.delete_many({"user_id": {"$in": donator_ids}, "status": "temporary", "expires_at": {"$lt": now}})
                        count = res.deleted_count

                try:
                    await client.send_message(user_id, f"✅ **Cleanup Job Complete**\n\nDeleted {count} expired temporary files.")
                except Exception:
                    pass

            asyncio.create_task(run_admin_cleanup())
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_dmb_"):
        if data.startswith("adm_dmb_mnu"):
            page = 1
            if "_" in data.replace("adm_dmb_mnu", ""):
                parts = data.split("_")
                if len(parts) >= 3:
                    try:
                        page = int(parts[2])
                    except BaseException:
                        pass

            channels = await db.get_dumb_channels()

            text = (
                "📺 **Manage Dumb Channels**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "> Configure globally shared channels for auto-forwarding files.\n\n")

            if not channels:
                text += "❌ *No Dumb Channels configured yet.*\n\n"

            buttons = [[InlineKeyboardButton(
                "➕ Add New Dumb Channel", callback_data="adm_dmb_add")]]

            if channels:
                import math
                ch_items = list(channels.items())
                total_channels = len(ch_items)
                items_per_page = 10
                total_pages = math.ceil(
                    total_channels /
                    items_per_page) if total_channels > 0 else 1
                page = max(1, min(page, total_pages))

                start_idx = (page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                current_channels = ch_items[start_idx:end_idx]

                buttons.append([InlineKeyboardButton(
                    "─── Your Channels ───", callback_data="noop")])
                for ch_id, ch_name in current_channels:
                    buttons.append([InlineKeyboardButton(
                        f"📺 {ch_name}", callback_data=f"adm_dmb_opt_{ch_id}")])

                if total_pages > 1:
                    nav = []
                    if page > 1:
                        nav.append(
                            InlineKeyboardButton(
                                "⬅️", callback_data=f"adm_dmb_mnu_{
                                    page - 1}"))
                    nav.append(
                        InlineKeyboardButton(
                            f"{page}/{total_pages}",
                            callback_data="noop"))
                    if page < total_pages:
                        nav.append(
                            InlineKeyboardButton(
                                "➡️", callback_data=f"adm_dmb_mnu_{
                                    page + 1}"))
                    buttons.append(nav)

            buttons.append([InlineKeyboardButton(
                "← Back to Admin Panel", callback_data="adm_main")])

            try:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
            return

        elif data.startswith("dumb_opt_"):
            ch_id = data.replace("dumb_opt_", "")
            channels = await db.get_dumb_channels()
            if ch_id not in channels:
                await callback_query.answer("Channel not found.", show_alert=True)
                return

            ch_name = channels[ch_id]
            default_ch = await db.get_default_dumb_channel()
            movie_ch = await db.get_movie_dumb_channel()
            series_ch = await db.get_series_dumb_channel()

            is_def = "✅" if str(ch_id) == default_ch else "❌"
            is_mov = "✅" if str(ch_id) == movie_ch else "❌"
            is_ser = "✅" if str(ch_id) == series_ch else "❌"

            text = (
                f"⚙️ **Channel Settings**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"> **Name:** `{ch_name}`\n"
                f"> **ID:** `{ch_id}`\n\n"
                f"**Current Status:**\n"
                f"> 🔸 Standard Default: `{is_def}`\n"
                f"> 🎬 Movie Default: `{is_mov}`\n"
                f"> 📺 Series Default: `{is_ser}`\n\n"
                f"Select an action below to manage this global channel."
            )

            buttons = [
                [InlineKeyboardButton("✏️ Rename Channel", callback_data=f"adm_dmb_ren_{ch_id}")],
                [InlineKeyboardButton(f"🔸 Set Standard Default", callback_data=f"adm_dmb_ds_{ch_id}")],
                [InlineKeyboardButton(f"🎬 Set Movie Default", callback_data=f"adm_dmb_dm_{ch_id}")],
                [InlineKeyboardButton(f"📺 Set Series Default", callback_data=f"adm_dmb_dse_{ch_id}")],
                [InlineKeyboardButton("🗑 Delete Channel", callback_data=f"adm_dmb_del_{ch_id}")],
                [InlineKeyboardButton("← Back", callback_data="adm_dmb_menu")]
            ]

            try:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
            return

        elif data.startswith("dumb_ren_"):
            ch_id = data.replace("dumb_ren_", "")
            await set_admin_state(user_id, {"state": f"awaiting_dumb_rename_{ch_id}", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "✏️ **Rename Channel**\n\n"
                    "Please enter the new name for this global channel:\n\n"
                    "*(Send `disable` to cancel)*",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"adm_dmb_opt_{ch_id}")]])
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("dumb_def_std_"):
            ch_id = data.replace("dumb_def_std_", "")
            await db.set_default_dumb_channel(ch_id)
            await callback_query.answer("Standard Default channel set.", show_alert=True)
            callback_query.data = f"adm_dmb_opt_{ch_id}"
            await admin_callback(client, callback_query)
            return

        elif data.startswith("dumb_def_mov_"):
            ch_id = data.replace("dumb_def_mov_", "")
            await db.set_movie_dumb_channel(ch_id)
            await callback_query.answer("Movie Default channel set.", show_alert=True)
            callback_query.data = f"adm_dmb_opt_{ch_id}"
            await admin_callback(client, callback_query)
            return

        elif data.startswith("dumb_def_ser_"):
            ch_id = data.replace("dumb_def_ser_", "")
            await db.set_series_dumb_channel(ch_id)
            await callback_query.answer("Series Default channel set.", show_alert=True)
            callback_query.data = f"adm_dmb_opt_{ch_id}"
            await admin_callback(client, callback_query)
            return


# === PLANS & LIMITS MODULE ===
@Client.on_callback_query(filters.regex(r"^adm_pln_(?!free_|p_)"))
async def admin_pln_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_pln_per":
        config = await db.get_public_config()

        limits = config.get("myfiles_limits", {})
        free_lm = limits.get("free", {})
        std_lm = limits.get("standard", {})
        dlx_lm = limits.get("deluxe", {})

        def f(v): return "Unlimited" if v == -1 else v

        # Free limits
        free_egress = config.get("daily_egress_mb", 0)
        free_files = config.get("daily_file_count", 0)

        # Premium limits
        std_settings = config.get("premium_standard", {})
        dlx_settings = config.get("premium_deluxe", {})

        std_egress = std_settings.get("daily_egress_mb", 0)
        std_files = std_settings.get("daily_file_count", 0)

        dlx_egress = dlx_settings.get("daily_egress_mb", 0)
        dlx_files = dlx_settings.get("daily_file_count", 0)

        global_toggles = await db.get_feature_toggles()

        def get_features_str(plan_key):
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            feat_list = []

            # Global toggles apply to everyone if enabled, otherwise check plan
            # override
            if global_toggles.get(
                    "subtitle_extractor",
                    True) or features.get(
                    "subtitle_extractor",
                    False):
                feat_list.append("Subtitle Extractor")
            if global_toggles.get(
                    "watermarker",
                    True) or features.get(
                    "watermarker",
                    False):
                feat_list.append("Watermarker")
            if global_toggles.get(
                    "file_converter",
                    True) or features.get(
                    "file_converter",
                    False):
                feat_list.append("File Converter")
            if global_toggles.get(
                    "audio_editor",
                    True) or features.get(
                    "audio_editor",
                    False):
                feat_list.append("Audio Editor")
            if features.get("priority_queue", False):
                feat_list.append("Priority Queue")
            if features.get("batch_sharing", False):
                feat_list.append("Batch Sharing")

            # Formatting as bullet points
            return "\n".join(
                [f"  • {feat}" for feat in feat_list]) if feat_list else "  • None"

        text = "⚙️ **Per Plan Settings**\n\n> Overview of all tier configurations including limitations, features, and pricing.\n━━━━━━━━━━━━━━━━━━━━\n"

        plans_info = [
            ("🆓 **Free Plan**",
             free_lm,
             free_egress,
             free_files,
             "free_placeholder",
             None),
            ("🌟 **Standard Plan**",
             std_lm,
             std_egress,
             std_files,
             "premium_standard",
             std_settings),
            ("💎 **Deluxe Plan**",
             dlx_lm,
             dlx_egress,
             dlx_files,
             "premium_deluxe",
             dlx_settings)]

        for title, lm, eg, fl, p_key, setts in plans_info:
            text += f"{title}\n\n"
            text += f"📌 Permanent Slots : `{f(lm.get('permanent_limit', 0))}`\n"
            text += f"📁 Custom Folders  : `{f(lm.get('folder_limit', 0))}`\n"
            text += f"⏳ Temp Expiration : `{f(lm.get('expiry_days', 0))} days`\n"
            text += f"📦 Daily Egress: `{f(eg)}` MB\n"
            text += f"📄 Daily Files: `{f(fl)}` files\n\n"
            text += f"✨ **Features:**\n{get_features_str(p_key)}\n"
            if setts is not None:
                text += f"\n💵 **Price (Fiat):** `{
                    setts.get(
                        'price_string',
                        '0 USD')}`\n"
                text += f"⭐ **Price (Stars):** `{
                    setts.get(
                        'stars_price',
                        0)}` Stars\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n"

        buttons = [
            [InlineKeyboardButton("✏️ Edit Free Plan", callback_data="adm_pln_ed_free")],
            [InlineKeyboardButton("✏️ Edit Standard Plan", callback_data="adm_pln_ed_std")],
            [InlineKeyboardButton("✏️ Edit Deluxe Plan", callback_data="adm_pln_ed_dlx")],
            [InlineKeyboardButton("← Back", callback_data="adm_pln_limits")]
        ]

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
    elif data.startswith("adm_pln_ed_"):
        plan_name = data.replace("adm_pln_ed_", "")

        buttons = [
            [
                InlineKeyboardButton(
                    "📌 Edit Permanent Limit", callback_data=f"adm_myf_l_{plan_name}_permanent")], [
                InlineKeyboardButton(
                    "📁 Edit Folder Limit", callback_data=f"adm_myf_l_{plan_name}_folder")], [
                        InlineKeyboardButton(
                            "⏳ Edit Expiry Days", callback_data=f"adm_myf_l_{plan_name}_expiry")]]

        if plan_name == "free":
            buttons.append([InlineKeyboardButton(
                "📦 Edit Egress Limit", callback_data="adm_pln_free_eg")])
            buttons.append([InlineKeyboardButton(
                "📄 Edit File Limit", callback_data="adm_pln_free_fl")])
        else:
            buttons.append([InlineKeyboardButton(
                "📦 Edit Egress Limit", callback_data=f"adm_pln_p_{plan_name}_egress")])
            buttons.append([InlineKeyboardButton(
                "📄 Edit File Limit", callback_data=f"adm_pln_p_{plan_name}_files")])

            # Additional configurations for premium plans (moved from Premium
            # Settings)
            buttons.append([InlineKeyboardButton("💵 Edit Fiat Price",
                                                 callback_data=f"adm_pln_p_{plan_name}_price"),
                            InlineKeyboardButton("⭐ Edit Stars Price",
                                                 callback_data=f"adm_pln_p_{plan_name}_stars")])

        buttons.append([InlineKeyboardButton(
            "⚙️ Configure Features", callback_data=f"adm_pln_feat_{plan_name}")])
        buttons.append([InlineKeyboardButton(
            "← Back", callback_data="adm_pln_per")])

        text = (
            f"⚙️ **Edit {plan_name.capitalize()} Plan Settings**\n\n"
            f"> Configure the quotas, features, and prices for this tier.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Select a setting to modify:"
        )

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data == "admin_feature_toggles":
        toggles = await db.get_feature_toggles()
        # Default True if not set
        audio_en = toggles.get("audio_editor", True)
        conv_en = toggles.get("file_converter", True)
        wm_en = toggles.get("watermarker", True)
        sub_en = toggles.get("subtitle_extractor", True)

        def emoji(state): return "✅" if state else "❌"

        text = (
            "⚙️ **Feature Toggles**\n\n"
            "Enable or disable specific features of the bot to save server resources.\n\n"
            "**Performance Impact:**\n"
            "• **File Converter:** High CPU & RAM\n"
            "• **Watermarker:** Medium CPU\n"
            "• **Audio Editor:** Low CPU\n"
            "• **Subtitle Extractor:** Medium CPU\n\n"
            "Click on a feature below to toggle its state globally:")

        buttons = [
            [InlineKeyboardButton(f"{emoji(conv_en)} File Converter", callback_data="adm_pln_tf_file_converter")],
            [InlineKeyboardButton(f"{emoji(sub_en)} Subtitle Extractor", callback_data="adm_pln_tf_subtitle_extractor")],
            [InlineKeyboardButton(f"{emoji(wm_en)} Image Watermarker", callback_data="adm_pln_tf_watermarker")],
            [InlineKeyboardButton(f"{emoji(audio_en)} Audio Editor", callback_data="adm_pln_tf_audio_editor")],
            [InlineKeyboardButton("← Back", callback_data="admin_access_menu")]
        ]

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data == "adm_pln_4gb" and Config.PUBLIC_MODE:
        config = await db.get_public_config()
        current_val = config.get("xtv_pro_4gb_access", "all")

        display = {
            "all": "Everyone",
            "premium_all": "All Premium Users",
            "premium_deluxe": "Premium Deluxe Only"
        }

        try:
            await callback_query.message.edit_text(
                f"🚀 **XTV Pro™ 4GB Access**\n\n"
                f"Who is allowed to bypass the 2GB limit (up to 4GB)?\n"
                f"Current Setting: **{display.get(current_val, 'Unknown')}**\n\n"
                f"Select an option below:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{'✅ ' if current_val == 'all' else ''}Everyone", callback_data="adm_pln_4gb_all")],
                    [InlineKeyboardButton(f"{'✅ ' if current_val == 'premium_all' else ''}All Premium Users", callback_data="adm_pln_4gb_premium_all")],
                    [InlineKeyboardButton(f"{'✅ ' if current_val == 'premium_deluxe' else ''}Premium Deluxe Only", callback_data="adm_pln_4gb_premium_deluxe")],
                    [InlineKeyboardButton("← Back", callback_data="adm_pln_limits")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_pln_4gb_") and Config.PUBLIC_MODE:
        access_level = data.replace("adm_pln_4gb_", "")
        await db.update_public_config("xtv_pro_4gb_access", access_level)
        await callback_query.answer("4GB Access updated!", show_alert=True)
        callback_query.data = "adm_pln_4gb"
        await admin_callback(client, callback_query)
        return

    if data.startswith("adm_pln_tf_"):
        parts = data.replace("adm_pln_tf_", "").rsplit("_", 1)
        if parts[-1] in ["free", "standard", "deluxe"]:
            feature = parts[0]
            plan_name = parts[1]
        else:
            feature = data.replace("adm_pln_tf_", "")
            plan_name = "free"

        toggles = await db.get_feature_toggles()
        current_state = toggles.get(feature, True)
        new_state = not current_state
        await db.update_feature_toggle(feature, new_state)
        await callback_query.answer(f"{'Enabled' if new_state else 'Disabled'} feature.", show_alert=True)
        # Re-render the menu
        callback_query.data = f"adm_pln_feat_{plan_name}"
        await admin_callback(client, callback_query)
        return

    if data == "adm_pln_gl_eg":
        current_val = await db.get_global_daily_egress_limit()
        try:
            await callback_query.message.edit_text(
                f"🌍 **Edit Global Daily Egress Limit**\n\nCurrent: `{current_val}` MB\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="adm_pln_p_gleg"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_pln_limits"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if Config.PUBLIC_MODE and ((data.startswith("adm_pln_p_") or data.startswith("adm_pln_feat_") or data.startswith("adm_pln_pf_") or data.startswith("adm_pln_pm_") or data.startswith("adm_pln_pt_")) or data.startswith(
            "prompt_premium_") or data.startswith("adm_pln_p_trd") or data.startswith("adm_pln_tr_tgl")):
        if data == "adm_pln_prem_set":
            config = await db.get_public_config()
            enabled = config.get("premium_system_enabled", False)
            deluxe_enabled = config.get("premium_deluxe_enabled", False)
            trial_enabled = config.get("premium_trial_enabled", False)
            trial_days = config.get("premium_trial_days", 0)

            status_emoji = "✅ ON" if enabled else "❌ OFF"
            deluxe_status_emoji = "✅ ON" if deluxe_enabled else "❌ OFF"
            trial_status_emoji = "✅ ON" if trial_enabled else "❌ OFF"

            text = (
                f"💎 **Premium Settings**\n\n"
                f"System Status: {status_emoji}\n"
                f"Deluxe Plan: {deluxe_status_emoji}\n\n"
                f"⏳ **Trial System (Standard Plan Only)**\n"
                f"Status: {trial_status_emoji}\n"
                f"Duration: `{trial_days}` days\n\n"
                "Select a setting to edit:"
            )

            buttons = [[InlineKeyboardButton(
                f"Toggle System: {status_emoji}", callback_data="adm_pln_p_tgl")]]

            if enabled:
                buttons.append([InlineKeyboardButton(
                    f"Toggle Deluxe Plan: {deluxe_status_emoji}", callback_data="adm_pln_d_tgl")])

                buttons.append([InlineKeyboardButton(
                    f"Toggle Trial System: {trial_status_emoji}", callback_data="adm_pln_tr_tgl")])
                if trial_enabled:
                    buttons.append([InlineKeyboardButton(
                        "⏱ Edit Trial Duration", callback_data="adm_pln_p_trd")])

            buttons.append([InlineKeyboardButton(
                "← Back", callback_data="adm_pln_limits")])

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pln_p_tgl":
            config = await db.get_public_config()
            enabled = config.get("premium_system_enabled", False)
            await db.update_public_config("premium_system_enabled", not enabled)
            await callback_query.answer("Toggled Premium System", show_alert=True)
            callback_query.data = "adm_pln_prem_set"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_pln_tr_tgl":
            config = await db.get_public_config()
            enabled = config.get("premium_trial_enabled", False)
            await db.update_public_config("premium_trial_enabled", not enabled)
            await callback_query.answer("Toggled Premium Trial System", show_alert=True)
            callback_query.data = "adm_pln_prem_set"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_pln_d_tgl":
            config = await db.get_public_config()
            enabled = config.get("premium_deluxe_enabled", False)
            await db.update_public_config("premium_deluxe_enabled", not enabled)
            await callback_query.answer("Toggled Premium Deluxe System", show_alert=True)
            callback_query.data = "adm_pln_prem_set"
            await admin_callback(client, callback_query)
            return

        elif data.startswith("adm_pln_feat_"):
            plan_name = data.replace("adm_pln_feat_", "")
            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            global_toggles = await db.get_feature_toggles()

            def emoji(state): return "✅" if state else "❌"

            pq = features.get("priority_queue", False)
            bs = features.get("batch_sharing", False)
            ps = features.get("privacy_settings", False)

            buttons = [
                [InlineKeyboardButton(f"{emoji(pq)} Priority Queue", callback_data=f"adm_pln_pf_{plan_name}_priority_queue")],
                [InlineKeyboardButton(f"{emoji(bs)} Batch Sharing", callback_data=f"adm_pln_pf_{plan_name}_batch_sharing")],
                [InlineKeyboardButton(f"{emoji(ps)} Privacy Settings", callback_data=f"adm_pln_pf_{plan_name}_privacy_settings")]
            ]

            media_features = [
                ("file_converter", "File Converter"),
                ("audio_editor", "Audio Editor"),
                ("watermarker", "Watermarker"),
                ("subtitle_extractor", "Subtitle Extractor")
            ]

            for key, label in media_features:
                if plan_name == "free":
                    state = global_toggles.get(key, True)
                    buttons.append([InlineKeyboardButton(
                        f"{emoji(state)} {label}", callback_data=f"adm_pln_tf_{key}_{plan_name}")])
                else:
                    if not global_toggles.get(key, True):
                        state = features.get(key, False)
                        buttons.append([InlineKeyboardButton(
                            f"{emoji(state)} {label}", callback_data=f"adm_pln_pf_{plan_name}_{key}")])

            buttons.append([InlineKeyboardButton(
                "← Back", callback_data=f"adm_pln_ed_{plan_name}")])

            if plan_name == "free":
                text = f"⚙️ **Free Plan Features**\n\nToggle features. Note: Free Plan media features (Converter, Editor, etc.) apply globally by default. If you disable them here, you can re-enable them individually on Premium plans."
            else:
                text = f"⚙️ **{plan_name.capitalize()} Plan Features**\n\nToggle which features users on this plan can access (overrides global limits):"

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("adm_pln_pf_"):
            parts = data.replace("adm_pln_pf_", "").split("_", 1)
            plan_name = parts[0]
            feature_name = parts[1]

            if feature_name == "privacy_settings":
                # Expand into a new menu
                callback_query.data = f"adm_pln_pm_{plan_name}"
                await admin_callback(client, callback_query)
                return

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})

            current = features.get(feature_name, False)
            features[feature_name] = not current
            plan_settings["features"] = features

            await db.update_public_config(plan_key, plan_settings)

            callback_query.data = f"adm_pln_feat_{plan_name}"
            await admin_callback(client, callback_query)
            return

        elif data.startswith("adm_pln_pm_"):
            plan_name = data.replace("adm_pln_pm_", "")
            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            privacy = features.get("privacy", {})

            def emoji(state): return "✅" if state else "❌"

            buttons = [
                [InlineKeyboardButton(f"{emoji(privacy.get('hide_display_name', False))} Hide Display Name", callback_data=f"adm_pln_pt_{plan_name}_hide_display_name")],
                [InlineKeyboardButton(f"{emoji(privacy.get('hide_forward_tags', False))} Hide Forward Tags", callback_data=f"adm_pln_pt_{plan_name}_hide_forward_tags")],
                [InlineKeyboardButton(f"{emoji(privacy.get('link_anonymity', False))} Link Anonymity (UUID)", callback_data=f"adm_pln_pt_{plan_name}_link_anonymity")],
                [InlineKeyboardButton("← Back", callback_data=f"adm_pln_feat_{plan_name}")]
            ]

            text = f"🔒 **Privacy Feature Access ({
                plan_name.capitalize()})**\n\nToggle which privacy controls are **available** for users on this plan to configure in their /settings:"

            try:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
            return

        elif data.startswith("adm_pln_pt_"):
            parts = data.replace("adm_pln_pt_", "").split("_", 1)
            plan_name = parts[0]
            feature_name = parts[1]

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            privacy = features.get("privacy", {})

            current = privacy.get(feature_name, False)
            privacy[feature_name] = not current
            features["privacy"] = privacy
            plan_settings["features"] = features

            await db.update_public_config(plan_key, plan_settings)

            callback_query.data = f"adm_pln_pm_{plan_name}"
            await admin_callback(client, callback_query)
            return

        elif data.startswith("adm_pln_p_"):
            parts = data.replace("adm_pln_p_", "").split("_")
            if len(parts) >= 2 and parts[0] in ["standard", "deluxe"]:
                plan_name = parts[0]
                field = parts[1]

                if field == "egress":
                    try:
                        await callback_query.message.edit_text(
                            f"📦 **Edit Daily Egress Limit** ({plan_name.capitalize()} Plan)\n\n"
                            f"Select a predefined size or click **Change Custom** to enter a value manually (e.g. `20 GB` or `512 MB`):",
                            reply_markup=InlineKeyboardMarkup(
                                [
                                    [
                                        InlineKeyboardButton("512 MB", callback_data=f"adm_pln_se_{plan_name}_512"),
                                        InlineKeyboardButton("1 GB", callback_data=f"adm_pln_se_{plan_name}_1024")
                                    ],
                                    [
                                        InlineKeyboardButton("2 GB", callback_data=f"adm_pln_se_{plan_name}_2048"),
                                        InlineKeyboardButton("4 GB", callback_data=f"adm_pln_se_{plan_name}_4096")
                                    ],
                                    [
                                        InlineKeyboardButton(
                                            "✏️ Change Custom", callback_data=f"adm_pln_pe_{plan_name}"
                                        )
                                    ],
                                    [
                                        InlineKeyboardButton(
                                            "← Back", callback_data=f"adm_pln_ed_{plan_name}"
                                        )
                                    ],
                                ]
                            ),
                        )
                    except MessageNotModified:
                        pass
                    return

                if field == "price":
                    try:
                        await callback_query.message.edit_text(
                            "💵 **Select Currency**\n\nFirst, select the fiat currency you want to use for this plan:",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("USD ($)", callback_data=f"adm_pln_pc_{plan_name}_USD"),
                                 InlineKeyboardButton("EUR (€)", callback_data=f"adm_pln_pc_{plan_name}_EUR"),
                                 InlineKeyboardButton("GBP (£)", callback_data=f"adm_pln_pc_{plan_name}_GBP")],
                                [InlineKeyboardButton("INR (₹)", callback_data=f"adm_pln_pc_{plan_name}_INR"),
                                 InlineKeyboardButton("RUB (₽)", callback_data=f"adm_pln_pc_{plan_name}_RUB"),
                                 InlineKeyboardButton("BRL (R$)", callback_data=f"adm_pln_pc_{plan_name}_BRL")],
                                [InlineKeyboardButton("❌ Cancel", callback_data=f"adm_pln_ed_{plan_name}")]
                            ])
                        )
                    except MessageNotModified:
                        pass
                    return

                await set_admin_state(user_id, {"state": f"awaiting_premium_{plan_name}_{field}", "msg_id": callback_query.message.id})

                prompts = {
                    "files": "📄 **Send the new daily file limit.**\nSend `0` to disable.", }

                if field == "stars":
                    from utils.currency import convert_to_usd_str
                    config = await db.get_public_config()
                    plan_settings = config.get(f"premium_{plan_name}", {})
                    current_fiat = plan_settings.get("price_string", "0 USD")
                    usd_str = await convert_to_usd_str(current_fiat)

                    try:
                        usd_val = float(usd_str.replace("$", ""))
                        recommended_stars = int(usd_val / 0.015)
                        star_prompt = f"⭐ **Send the new Telegram Stars price (integer).**\n\nYour fiat price converts to roughly `{usd_str}`.\nWe recommend setting this to `{recommended_stars}` Stars (assuming ~$0.015 per Star)."
                    except BaseException:
                        star_prompt = "⭐ **Send the new Telegram Stars price (integer).**"

                    prompts["stars"] = star_prompt

                cancel_cb = f"adm_pln_ed_{plan_name}"

                try:
                    await callback_query.message.edit_text(
                        prompts.get(field, "Enter new value:"),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]])
                    )
                except MessageNotModified:
                    pass
                return

    if data.startswith("adm_pln_pe_"):
        plan_name = data.replace("adm_pln_pe_", "")
        await set_admin_state(user_id, {"state": f"awaiting_premium_{plan_name}_egress", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "📦 **Send the new daily egress limit.**\n\nYou can send the value in MB (e.g., `2048`) or use `GB` format (e.g., `2 GB` or `5.5 GB`).\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"adm_pln_ed_{plan_name}")]])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_pln_se_"):
        parts = data.replace("adm_pln_se_", "").split("_")
        if len(parts) >= 2:
            plan_name = parts[0]
            val = int(parts[1])

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            plan_settings["daily_egress_mb"] = val
            await db.update_public_config(plan_key, plan_settings)

            await callback_query.answer(f"{plan_name.capitalize()} Egress limit updated to {val} MB.", show_alert=True)
            callback_query.data = f"adm_pln_ed_{plan_name}"
            await admin_callback(client, callback_query)
        return

    if data.startswith("adm_pln_pc_"):
        parts = data.replace("adm_pln_pc_", "").split("_")
        plan_name = parts[0]
        currency = parts[1]

        await set_admin_state(user_id, {"state": f"awaiting_premium_{plan_name}_price", "currency": currency, "msg_id": callback_query.message.id})

        try:
            await callback_query.message.edit_text(
                f"💵 **Set Price in {currency}**\n\nPlease enter the numeric amount (e.g., `9.99` or `500`):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_pln_p_trd":
        await set_admin_state(user_id, {"state": "awaiting_trial_days", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "⏱ **Send the new PREMIUM TRIAL duration in days (e.g., 7).**\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_pln_prem_set")]])
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_pln_p_gleg":
        await set_admin_state(user_id, {"state": "awaiting_global_daily_egress", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "🌍 **Send the new global daily egress limit in MB (e.g., 102400 for 100GB).**\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="adm_pln_limits")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_pln_limits":
        try:
            reply_markup = await get_admin_access_limits_menu()
            await callback_query.message.edit_text(
                "🔒 **Settings Menu**\n\n" "Select a category:",
                reply_markup=reply_markup,
            )
        except MessageNotModified:
            pass

# === DUMB CHANNELS MODULE ===


@Client.on_callback_query(filters.regex(r"^adm_dmb_"))
async def admin_dmb_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_dmb_add":
        await set_admin_state(user_id, {"state": "awaiting_dumb_add", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "➕ **Add Dumb Channel**\n\n"
                "Please add me as an Administrator in the desired channel.\n"
                "Then, forward any message from that channel to me, OR send the Channel ID (e.g. `-100...`) or Public Username.\n\n"
                "*(Send `disable` to cancel)*",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="adm_dmb_menu")]]
                ),
            )
        except MessageNotModified:
            pass
        return
    elif data.startswith("adm_dmb_del_"):
        ch_id = data.replace("adm_dmb_del_", "")
        await db.remove_dumb_channel(ch_id)
        await callback_query.answer("Channel removed.", show_alert=True)
        callback_query.data = "adm_dmb_menu"
        await admin_callback(client, callback_query)
        return

    if data == "adm_dmb_menu":
        callback_query.data = "adm_dmb_menu"
        await admin_callback(client, callback_query)
        return

    if data == "adm_dmb_tout":
        current_val = await db.get_dumb_channel_timeout()
        try:
            await callback_query.message.edit_text(
                f"⏱ **Edit Dumb Channel Timeout**\n\n"
                f"This is the max time (in seconds) the bot will wait for earlier files before uploading to the Dumb Channel.\n\n"
                f"Current: `{current_val}` seconds\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="adm_dmb_ed_tout"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_main"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_dmb_ed_tout":
        await set_admin_state(user_id, {"state": "awaiting_dumb_timeout", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "⏱ **Send the new timeout in seconds (e.g., 3600 for 1 hour):**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="adm_main")]]
                ),
            )
        except MessageNotModified:
            pass
        return


# === PAYMENTS MODULE ===
@Client.on_callback_query(filters.regex(r"^adm_pay_"))
async def admin_pay_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_pay_menu":
        config = await db.get_public_config()
        pm = config.get("payment_methods", {})

        try:
            await callback_query.message.edit_text(
                "💳 **Manage Payments**\n\nManage payment methods, discounts, and view pending transactions.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Payment Settings", callback_data="adm_pay_set")],
                    [InlineKeyboardButton("📉 Discount Settings", callback_data="adm_pay_disc")],
                    [InlineKeyboardButton("📬 Pending Approvals Queue", callback_data="adm_pay_queue")],
                    [InlineKeyboardButton("← Back to Admin Panel", callback_data="adm_main")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_pay_set":
        config = await db.get_public_config()
        pm = config.get("payment_methods", {})

        def emoji(state): return "✅" if state else "❌"

        pp = pm.get("paypal_enabled", False)
        cr = pm.get("crypto_enabled", False)
        up = pm.get("upi_enabled", False)
        st = pm.get("stars_enabled", False)

        usdt = pm.get("crypto_usdt", "Not set")
        btc = pm.get("crypto_btc", "Not set")
        eth = pm.get("crypto_eth", "Not set")

        text = (
            "⚙️ **Payment Settings**\n\n"
            "Toggle payment methods and configure their respective addresses/IDs.\n"
            "*(Users will only see the enabled methods during checkout)*\n\n"
            f"**PayPal Email:** `{pm.get('paypal_email', 'Not set')}`\n"
            f"**UPI ID:** `{pm.get('upi_id', 'Not set')}`\n\n"
            f"**Crypto Addresses:**\n"
            f"• USDT: `{usdt}`\n"
            f"• BTC: `{btc}`\n"
            f"• ETH: `{eth}`"
        )

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{emoji(pp)} PayPal", callback_data="adm_pay_tgl_pp"),
                     InlineKeyboardButton("✏️ Edit Email", callback_data="adm_pay_ed_pp")],
                    [InlineKeyboardButton(f"{emoji(up)} UPI", callback_data="adm_pay_tgl_upi"),
                     InlineKeyboardButton("✏️ Edit ID", callback_data="adm_pay_ed_upi")],
                    [InlineKeyboardButton(f"{emoji(cr)} Crypto", callback_data="adm_pay_tgl_cr"),
                     InlineKeyboardButton("✏️ Edit Addresses", callback_data="adm_pay_cr_mnu")],
                    [InlineKeyboardButton(f"{emoji(st)} Telegram Stars", callback_data="adm_pay_tgl_st")],
                    [InlineKeyboardButton("← Back", callback_data="adm_pay_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_pay_cr_mnu":
        try:
            await callback_query.message.edit_text(
                "🪙 **Crypto Address Settings**\n\nSelect which cryptocurrency address you want to edit:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("USDT (TRC20/ERC20)", callback_data="adm_pay_ed_usdt")],
                    [InlineKeyboardButton("BTC (Bitcoin)", callback_data="adm_pay_ed_btc")],
                    [InlineKeyboardButton("ETH (Ethereum)", callback_data="adm_pay_ed_eth")],
                    [InlineKeyboardButton("← Back", callback_data="adm_pay_set")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_pay_tgl_"):
        method = data.replace("adm_pay_tgl_", "")
        config = await db.get_public_config()
        pm = config.get("payment_methods", {})
        current = pm.get(f"{method}_enabled", False)
        pm[f"{method}_enabled"] = not current
        await db.update_public_config("payment_methods", pm)
        callback_query.data = "adm_pay_set"
        await admin_callback(client, callback_query)
        return

    if data.startswith("prompt_pay_"):
        method = data.replace("prompt_pay_", "")
        await set_admin_state(user_id, {"state": f"awaiting_pay_{method}", "msg_id": callback_query.message.id})

        cancel_data = "adm_pay_set"
        if method.startswith("crypto_"):
            cancel_data = "adm_pay_cr_mnu"

        try:
            await callback_query.message.edit_text(
                f"✏️ **Edit {method.replace('_', ' ').upper()} Details**\n\nPlease send the new address/ID/email:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)]])
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_pay_disc":
        config = await db.get_public_config()
        disc = config.get("discounts", {})
        m3 = disc.get("months_3", 0)
        m12 = disc.get("months_12", 0)

        text = (
            "📉 **Discount Settings**\n\n"
            "Set the percentage discount (0-99) for longer billing cycles.\n\n"
            f"**3 Months:** `{m3}% Off`\n"
            f"**12 Months:** `{m12}% Off`\n"
        )

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Edit 3-Month Discount", callback_data="adm_pay_ed_d3")],
                    [InlineKeyboardButton("✏️ Edit 12-Month Discount", callback_data="adm_pay_ed_d12")],
                    [InlineKeyboardButton("← Back", callback_data="adm_pay_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("prompt_pay_disc_"):
        months = data.replace("prompt_pay_disc_", "")
        await set_admin_state(user_id, {"state": f"awaiting_pay_disc_{months}", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                f"📉 **Edit {months}-Month Discount**\n\nPlease send the new discount percentage (e.g. `10` or `15`):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_pay_disc")]])
            )
        except MessageNotModified:
            pass
        return

    if data == "adm_pay_queue":
        pending = await db.get_all_pending_payments()
        if not pending:
            try:
                await callback_query.message.edit_text(
                    "📬 **Pending Approvals Queue**\n\nNo pending payments found.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_pay_menu")]])
                )
            except MessageNotModified:
                pass
            return

        p = pending[0]
        text = (
            "📬 **Pending Approvals Queue**\n\n"
            f"**Payment ID:** `{p['_id']}`\n"
            f"**User ID:** `{p['user_id']}`\n"
            f"**Plan:** `{p['plan'].capitalize()}`\n"
            f"**Duration:** `{p['duration_months']} Months`\n"
            f"**Amount:** `{p['amount']}`\n"
            f"**Method:** `{p['method']}`\n\n"
            "Review this transaction and approve or reject it."
        )

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve", callback_data=f"adm_pay_ap_{p['_id']}"),
                     InlineKeyboardButton("❌ Reject", callback_data=f"adm_pay_rj_{p['_id']}")],
                    [InlineKeyboardButton("⏭ Skip", callback_data="adm_pay_queue")],
                    [InlineKeyboardButton("← Back", callback_data="adm_pay_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("adm_pay_ap_"):
        payment_id = data.replace("adm_pay_ap_", "")
        p = await db.get_pending_payment(payment_id)
        if not p or p['status'] != 'pending':
            await callback_query.answer("Payment already processed.", show_alert=True)
        else:
            await db.update_pending_payment_status(payment_id, "approved")
            days = p['duration_months'] * 30
            await db.add_premium_user(p['user_id'], days, plan=p['plan'])
            await db.add_log("approve_payment", user_id, f"Approved {payment_id} for user {p['user_id']}")

            try:
                await client.send_message(
                    p['user_id'],
                    f"✅ **Payment Approved!**\n\nYour payment for the **Premium {p['plan'].capitalize()} Plan** ({p['duration_months']} Months) has been verified.\nYour account is now upgraded. Enjoy!"
                )
            except BaseException:
                pass

            await callback_query.answer("Payment Approved & User Upgraded!", show_alert=True)

        callback_query.data = "adm_pay_queue"
        await admin_callback(client, callback_query)
        return

    if data.startswith("adm_pay_rj_"):
        payment_id = data.replace("adm_pay_rj_", "")
        p = await db.get_pending_payment(payment_id)
        if not p or p['status'] != 'pending':
            await callback_query.answer("Payment already processed.", show_alert=True)
        else:
            await db.update_pending_payment_status(payment_id, "rejected")
            await db.add_log("reject_payment", user_id, f"Rejected {payment_id} for user {p['user_id']}")

            try:
                await client.send_message(
                    p['user_id'],
                    f"❌ **Payment Rejected**\n\nYour payment (ID: `{payment_id}`) for the Premium {p['plan'].capitalize()} Plan could not be verified. Please contact support."
                )
            except BaseException:
                pass

            await callback_query.answer("Payment Rejected.", show_alert=True)

        callback_query.data = "adm_pay_queue"
        await admin_callback(client, callback_query)
        return


# === PUBLIC CONFIG MODULE ===
@Client.on_callback_query(filters.regex(r"^(adm_pub_|adm_fs_|adm_pln_free_|adm_pln_p_)"))
async def admin_pub_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if Config.PUBLIC_MODE and (
        data.startswith("adm_pub_")
        or (data.startswith("adm_pln_free_eg") or data.startswith("adm_pln_free_fl"))
        or data.startswith("adm_fs_")
        or data.startswith("adm_fs_")
        or (data.startswith("adm_pln_p_") or data.startswith("adm_pln_feat_") or data.startswith("adm_pln_pf_") or data.startswith("adm_pln_pm_") or data.startswith("adm_pln_pt_"))
        or data.startswith("adm_pln_p_")
    ):
        if data == "adm_pub_view":
            config = await db.get_public_config()
            text = "👀 **Public Mode Config**\n\n"
            text += f"**Bot Name:** {config.get('bot_name', 'Not set')}\n"
            text += f"**Community Name:** {
                config.get(
                    'community_name',
                    'Not set')}\n"
            text += f"**Support Contact:** {
                config.get(
                    'support_contact',
                    'Not set')}\n"
            text += (
                f"**Force-Sub Channel:** {config.get('force_sub_channel', 'Not set')}\n"
            )
            text += f"**Daily Egress Limit:** {
                config.get(
                    'daily_egress_mb',
                    0)} MB\n"
            text += f"**Daily File Limit:** {
                config.get(
                    'daily_file_count',
                    0)} files\n"

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ]
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pub_name":
            config = await db.get_public_config()
            current_val = config.get("bot_name", "Not set")
            try:
                await callback_query.message.edit_text(
                    f"🤖 **Edit Bot Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="adm_pub_p_nam"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pub_comm":
            config = await db.get_public_config()
            current_val = config.get("community_name", "Not set")
            try:
                await callback_query.message.edit_text(
                    f"👥 **Edit Community Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change",
                                    callback_data="adm_pub_p_com",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pub_supp":
            config = await db.get_public_config()
            current_val = config.get("support_contact", "Not set")
            try:
                await callback_query.message.edit_text(
                    f"🔗 **Edit Support Contact**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change",
                                    callback_data="adm_pub_p_con",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_menu":
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")

            num_channels = len(channels) if channels else (
                1 if legacy_ch else 0)
            status = "ON" if num_channels > 0 else "OFF"

            banner_set = "✅ Set" if config.get(
                "force_sub_banner_file_id") else "❌ None"
            msg_set = "Custom" if config.get(
                "force_sub_message_text") else "Default"

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
                [InlineKeyboardButton(f"📡 Force-Sub: {status}", callback_data="adm_fs_tgl")],
                [InlineKeyboardButton("➕ Add Channel", callback_data="adm_fs_add"),
                 InlineKeyboardButton("📋 Manage Channels", callback_data="adm_fs_mng")],
                [InlineKeyboardButton("🖼 Set Banner", callback_data="adm_fs_ban")]
            ]

            if config.get("force_sub_banner_file_id"):
                keyboard[-1].append(InlineKeyboardButton("🗑 Remove Banner",
                                    callback_data="adm_fs_rban"))

            keyboard.append([
                InlineKeyboardButton("✏️ Edit Message", callback_data="adm_fs_msg"),
                InlineKeyboardButton("↩️ Reset Message", callback_data="adm_fs_rmsg")
            ])
            keyboard.append([
                InlineKeyboardButton("🔘 Edit Button", callback_data="adm_fs_btn"),
                InlineKeyboardButton("🎉 Edit Welcome Msg", callback_data="adm_fs_welc")
            ])
            keyboard.append([InlineKeyboardButton(
                "← Back", callback_data="adm_main")])

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_add":
            await set_admin_state(user_id, {"state": "awaiting_fs_add_channel", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "📢 **Add Force-Sub Channel**\n\n"
                    "⏳ **I am waiting...**\n\n"
                    "Simply **add me as an Administrator** to your desired channel right now!\n"
                    "Make sure I have the 'Invite Users via Link' permission.\n\n"
                    "I will automatically detect the channel and set it up instantly.\n\n"
                    "*Send /cancel to cancel.*",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]]
                    )
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_tgl":
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")
            num_channels = len(channels) if channels else (
                1 if legacy_ch else 0)

            if num_channels > 0:
                await db.update_public_config("force_sub_channels", [])
                await db.update_public_config("force_sub_channel", None)
                await db.update_public_config("force_sub_link", None)
                await db.update_public_config("force_sub_username", None)
                await callback_query.answer("Force-Sub disabled.", show_alert=True)
            else:
                await callback_query.answer("Please add a channel to enable Force-Sub.", show_alert=True)

            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_mng":
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")
            legacy_link = config.get("force_sub_link")
            legacy_username = config.get("force_sub_username")

            if not channels and legacy_ch:
                channels = [{"id": legacy_ch,
                             "link": legacy_link,
                             "username": legacy_username,
                             "title": "Legacy Channel"}]

            if not channels:
                await callback_query.answer("No channels configured.", show_alert=True)
                return

            keyboard = []
            for i, ch in enumerate(channels):
                title = ch.get("title", f"Channel {i + 1}")
                keyboard.append([InlineKeyboardButton(
                    f"❌ Remove {title}", callback_data=f"adm_fs_rmc_{i}")])

            keyboard.append([InlineKeyboardButton(
                "← Back", callback_data="adm_fs_menu")])

            try:
                await callback_query.message.edit_text(
                    "📋 **Manage Channels**\n\nSelect a channel to remove:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("adm_fs_rmc_"):
            idx = int(data.replace("adm_fs_rmc_", ""))
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")

            if not channels and legacy_ch:
                channels = [{"id": legacy_ch,
                             "link": config.get("force_sub_link"),
                             "username": config.get("force_sub_username"),
                             "title": "Legacy Channel"}]

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

            callback_query.data = "adm_fs_mng"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_ban":
            await set_admin_state(user_id, {"state": "awaiting_fs_banner", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "🖼 **Send me a photo** to use as the Force-Sub gate banner.\n\nSend /cancel to keep the current one.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_rban":
            await db.update_public_config("force_sub_banner_file_id", None)
            await callback_query.answer("Banner removed.", show_alert=True)
            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_msg":
            config = await db.get_public_config()
            current_msg = config.get("force_sub_message_text")

            text = "✏️ **Edit Gate Message**\n\nCurrent:\n"
            if current_msg:
                text += f"`{current_msg}`\n\n"
            else:
                text += "*Default Message*\n\n"

            text += "Send your new gate message. You can use `{channel}`, `{bot_name}`, `{community}`.\nSend /cancel to keep the current one."

            await set_admin_state(user_id, {"state": "awaiting_fs_msg", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_rmsg":
            await db.update_public_config("force_sub_message_text", None)
            await callback_query.answer("Message reset to default.", show_alert=True)
            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_btn":
            try:
                await callback_query.message.edit_text(
                    "🔘 **Edit Button**\n\nSelect what to edit:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔘 Edit Label", callback_data="adm_fs_blbl"),
                         InlineKeyboardButton("😀 Edit Emoji", callback_data="adm_fs_bemo")],
                        [InlineKeyboardButton("↩️ Reset Button", callback_data="adm_fs_brst")],
                        [InlineKeyboardButton("← Back", callback_data="adm_fs_menu")]
                    ])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_blbl":
            await set_admin_state(user_id, {"state": "awaiting_fs_btn_label", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "🔘 **Edit Button Label**\n\nSend the new label text (without emoji):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_btn")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_bemo":
            await set_admin_state(user_id, {"state": "awaiting_fs_btn_emoji", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "😀 **Edit Button Emoji**\n\nSend a single emoji character:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_btn")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_brst":
            await db.update_public_config("force_sub_button_label", None)
            await db.update_public_config("force_sub_button_emoji", None)
            await callback_query.answer("Button reset to default.", show_alert=True)
            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_welc":
            await set_admin_state(user_id, {"state": "awaiting_fs_welcome", "msg_id": callback_query.message.id})
            config = await db.get_public_config()
            current_msg = config.get(
                "force_sub_welcome_text",
                "✅ Welcome aboard! You're all set. Send your file and let's go.")
            try:
                await callback_query.message.edit_text(
                    f"🎉 **Edit Welcome Message**\n\nCurrent:\n`{current_msg}`\n\nSend the new welcome message text:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pln_free_eg":
            config = await db.get_public_config()
            current_val = config.get("daily_egress_mb", 0)
            try:
                await callback_query.message.edit_text(
                    f"📦 **Edit Daily Egress Limit** (Free Plan)\n\n"
                    f"Current: `{current_val}` MB\n\n"
                    f"Select a predefined size or click **Change Custom** to enter a value manually (e.g. `20 GB` or `512 MB`):",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("512 MB", callback_data="adm_pln_fe_512"),
                                InlineKeyboardButton("1 GB", callback_data="adm_pln_fe_1024")
                            ],
                            [
                                InlineKeyboardButton("2 GB", callback_data="adm_pln_fe_2048"),
                                InlineKeyboardButton("4 GB", callback_data="adm_pln_fe_4096")
                            ],
                            [
                                InlineKeyboardButton(
                                    "✏️ Change Custom", callback_data="adm_pln_p_fe"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pln_ed_free"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("adm_pln_fe_"):
            val = int(data.replace("adm_pln_fe_", ""))
            await db.update_public_config("daily_egress_mb", val)
            await callback_query.answer(f"Egress limit updated to {val} MB.", show_alert=True)
            callback_query.data = "adm_pln_ed_free"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_pln_free_fl":
            config = await db.get_public_config()
            current_val = config.get("daily_file_count", 0)
            try:
                await callback_query.message.edit_text(
                    f"📄 **Edit Daily File Limit** (Free Plan)\n\nCurrent: `{current_val}` files\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="adm_pln_p_ff"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pln_ed_free"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

    if Config.PUBLIC_MODE and (
        data.startswith("adm_pub_p_") or data.startswith("adm_pln_p_")
    ):
        field_map = {"nam": "bot_name", "com": "community_name", "con": "support_contact", "gleg": "global_daily_egress"}
        raw_field = data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_")
        field = field_map.get(raw_field, raw_field)
        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})

        if field == "bot_name":
            text = "🤖 **Send the new bot name:**"
        elif field == "community_name":
            text = "👥 **Send the new community name:**"
        elif field == "support_contact":
            text = "🔗 **Send the new support contact (e.g., @username or link):**"
        elif field == "force_sub":
            text = (
                "📢 **Setup Force-Sub Channel**\n\n"
                "⏳ **I am waiting...**\n\n"
                "Simply **add me as an Administrator** to your desired channel right now!\n"
                "Make sure I have the 'Invite Users via Link' permission.\n\n"
                "I will automatically detect the channel and set it up instantly.\n\n"
                "*Send /cancel to cancel.*")
        elif field == "daily_egress":
            text = "📦 **Send the new daily egress limit.**\n\nYou can send the value in MB (e.g., `2048`) or use `GB` format (e.g., `2 GB` or `5.5 GB`).\nSend `0` to disable."
            cancel_btn = "adm_pln_ed_free"
        elif field == "daily_files":
            text = "📄 **Send the new daily file limit.**\nSend `0` to disable."
            cancel_btn = "adm_pln_ed_free"
        else:
            text = "Send the new value:"
            cancel_btn = "adm_pub_set"

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data=cancel_btn
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return
    if data == "adm_pub_set":
        try:
            await callback_query.message.edit_text(
                "🌐 **Public Mode Settings**\n\n" "Select a setting to edit:",
                reply_markup=get_admin_public_settings_menu(),
            )
        except MessageNotModified:
            pass



@Client.on_callback_query(filters.regex(r"^(adm_pln_free_|adm_pln_p_)"))
async def admin_pln_free_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if Config.PUBLIC_MODE and (
        data.startswith("adm_pub_")
        or (data.startswith("adm_pln_free_eg") or data.startswith("adm_pln_free_fl"))
        or data.startswith("adm_fs_")
        or data.startswith("adm_fs_")
        or (data.startswith("adm_pln_p_") or data.startswith("adm_pln_feat_") or data.startswith("adm_pln_pf_") or data.startswith("adm_pln_pm_") or data.startswith("adm_pln_pt_"))
        or data.startswith("adm_pln_p_")
    ):
        if data == "adm_pub_view":
            config = await db.get_public_config()
            text = "👀 **Public Mode Config**\n\n"
            text += f"**Bot Name:** {config.get('bot_name', 'Not set')}\n"
            text += f"**Community Name:** {
                config.get(
                    'community_name',
                    'Not set')}\n"
            text += f"**Support Contact:** {
                config.get(
                    'support_contact',
                    'Not set')}\n"
            text += (
                f"**Force-Sub Channel:** {config.get('force_sub_channel', 'Not set')}\n"
            )
            text += f"**Daily Egress Limit:** {
                config.get(
                    'daily_egress_mb',
                    0)} MB\n"
            text += f"**Daily File Limit:** {
                config.get(
                    'daily_file_count',
                    0)} files\n"

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ]
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pub_name":
            config = await db.get_public_config()
            current_val = config.get("bot_name", "Not set")
            try:
                await callback_query.message.edit_text(
                    f"🤖 **Edit Bot Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="adm_pub_p_nam"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pub_comm":
            config = await db.get_public_config()
            current_val = config.get("community_name", "Not set")
            try:
                await callback_query.message.edit_text(
                    f"👥 **Edit Community Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change",
                                    callback_data="adm_pub_p_com",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pub_supp":
            config = await db.get_public_config()
            current_val = config.get("support_contact", "Not set")
            try:
                await callback_query.message.edit_text(
                    f"🔗 **Edit Support Contact**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change",
                                    callback_data="adm_pub_p_con",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pub_set"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_menu":
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")

            num_channels = len(channels) if channels else (
                1 if legacy_ch else 0)
            status = "ON" if num_channels > 0 else "OFF"

            banner_set = "✅ Set" if config.get(
                "force_sub_banner_file_id") else "❌ None"
            msg_set = "Custom" if config.get(
                "force_sub_message_text") else "Default"

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
                [InlineKeyboardButton(f"📡 Force-Sub: {status}", callback_data="adm_fs_tgl")],
                [InlineKeyboardButton("➕ Add Channel", callback_data="adm_fs_add"),
                 InlineKeyboardButton("📋 Manage Channels", callback_data="adm_fs_mng")],
                [InlineKeyboardButton("🖼 Set Banner", callback_data="adm_fs_ban")]
            ]

            if config.get("force_sub_banner_file_id"):
                keyboard[-1].append(InlineKeyboardButton("🗑 Remove Banner",
                                    callback_data="adm_fs_rban"))

            keyboard.append([
                InlineKeyboardButton("✏️ Edit Message", callback_data="adm_fs_msg"),
                InlineKeyboardButton("↩️ Reset Message", callback_data="adm_fs_rmsg")
            ])
            keyboard.append([
                InlineKeyboardButton("🔘 Edit Button", callback_data="adm_fs_btn"),
                InlineKeyboardButton("🎉 Edit Welcome Msg", callback_data="adm_fs_welc")
            ])
            keyboard.append([InlineKeyboardButton(
                "← Back", callback_data="adm_main")])

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_add":
            await set_admin_state(user_id, {"state": "awaiting_fs_add_channel", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "📢 **Add Force-Sub Channel**\n\n"
                    "⏳ **I am waiting...**\n\n"
                    "Simply **add me as an Administrator** to your desired channel right now!\n"
                    "Make sure I have the 'Invite Users via Link' permission.\n\n"
                    "I will automatically detect the channel and set it up instantly.\n\n"
                    "*Send /cancel to cancel.*",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]]
                    )
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_tgl":
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")
            num_channels = len(channels) if channels else (
                1 if legacy_ch else 0)

            if num_channels > 0:
                await db.update_public_config("force_sub_channels", [])
                await db.update_public_config("force_sub_channel", None)
                await db.update_public_config("force_sub_link", None)
                await db.update_public_config("force_sub_username", None)
                await callback_query.answer("Force-Sub disabled.", show_alert=True)
            else:
                await callback_query.answer("Please add a channel to enable Force-Sub.", show_alert=True)

            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_mng":
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")
            legacy_link = config.get("force_sub_link")
            legacy_username = config.get("force_sub_username")

            if not channels and legacy_ch:
                channels = [{"id": legacy_ch,
                             "link": legacy_link,
                             "username": legacy_username,
                             "title": "Legacy Channel"}]

            if not channels:
                await callback_query.answer("No channels configured.", show_alert=True)
                return

            keyboard = []
            for i, ch in enumerate(channels):
                title = ch.get("title", f"Channel {i + 1}")
                keyboard.append([InlineKeyboardButton(
                    f"❌ Remove {title}", callback_data=f"adm_fs_rmc_{i}")])

            keyboard.append([InlineKeyboardButton(
                "← Back", callback_data="adm_fs_menu")])

            try:
                await callback_query.message.edit_text(
                    "📋 **Manage Channels**\n\nSelect a channel to remove:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("adm_fs_rmc_"):
            idx = int(data.replace("adm_fs_rmc_", ""))
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")

            if not channels and legacy_ch:
                channels = [{"id": legacy_ch,
                             "link": config.get("force_sub_link"),
                             "username": config.get("force_sub_username"),
                             "title": "Legacy Channel"}]

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

            callback_query.data = "adm_fs_mng"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_ban":
            await set_admin_state(user_id, {"state": "awaiting_fs_banner", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "🖼 **Send me a photo** to use as the Force-Sub gate banner.\n\nSend /cancel to keep the current one.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_rban":
            await db.update_public_config("force_sub_banner_file_id", None)
            await callback_query.answer("Banner removed.", show_alert=True)
            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_msg":
            config = await db.get_public_config()
            current_msg = config.get("force_sub_message_text")

            text = "✏️ **Edit Gate Message**\n\nCurrent:\n"
            if current_msg:
                text += f"`{current_msg}`\n\n"
            else:
                text += "*Default Message*\n\n"

            text += "Send your new gate message. You can use `{channel}`, `{bot_name}`, `{community}`.\nSend /cancel to keep the current one."

            await set_admin_state(user_id, {"state": "awaiting_fs_msg", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_rmsg":
            await db.update_public_config("force_sub_message_text", None)
            await callback_query.answer("Message reset to default.", show_alert=True)
            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_btn":
            try:
                await callback_query.message.edit_text(
                    "🔘 **Edit Button**\n\nSelect what to edit:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔘 Edit Label", callback_data="adm_fs_blbl"),
                         InlineKeyboardButton("😀 Edit Emoji", callback_data="adm_fs_bemo")],
                        [InlineKeyboardButton("↩️ Reset Button", callback_data="adm_fs_brst")],
                        [InlineKeyboardButton("← Back", callback_data="adm_fs_menu")]
                    ])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_blbl":
            await set_admin_state(user_id, {"state": "awaiting_fs_btn_label", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "🔘 **Edit Button Label**\n\nSend the new label text (without emoji):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_btn")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_bemo":
            await set_admin_state(user_id, {"state": "awaiting_fs_btn_emoji", "msg_id": callback_query.message.id})
            try:
                await callback_query.message.edit_text(
                    "😀 **Edit Button Emoji**\n\nSend a single emoji character:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_btn")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_fs_brst":
            await db.update_public_config("force_sub_button_label", None)
            await db.update_public_config("force_sub_button_emoji", None)
            await callback_query.answer("Button reset to default.", show_alert=True)
            callback_query.data = "adm_fs_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_fs_welc":
            await set_admin_state(user_id, {"state": "awaiting_fs_welcome", "msg_id": callback_query.message.id})
            config = await db.get_public_config()
            current_msg = config.get(
                "force_sub_welcome_text",
                "✅ Welcome aboard! You're all set. Send your file and let's go.")
            try:
                await callback_query.message.edit_text(
                    f"🎉 **Edit Welcome Message**\n\nCurrent:\n`{current_msg}`\n\nSend the new welcome message text:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "adm_pln_free_eg":
            config = await db.get_public_config()
            current_val = config.get("daily_egress_mb", 0)
            try:
                await callback_query.message.edit_text(
                    f"📦 **Edit Daily Egress Limit** (Free Plan)\n\n"
                    f"Current: `{current_val}` MB\n\n"
                    f"Select a predefined size or click **Change Custom** to enter a value manually (e.g. `20 GB` or `512 MB`):",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("512 MB", callback_data="adm_pln_fe_512"),
                                InlineKeyboardButton("1 GB", callback_data="adm_pln_fe_1024")
                            ],
                            [
                                InlineKeyboardButton("2 GB", callback_data="adm_pln_fe_2048"),
                                InlineKeyboardButton("4 GB", callback_data="adm_pln_fe_4096")
                            ],
                            [
                                InlineKeyboardButton(
                                    "✏️ Change Custom", callback_data="adm_pln_p_fe"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pln_ed_free"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("adm_pln_fe_"):
            val = int(data.replace("adm_pln_fe_", ""))
            await db.update_public_config("daily_egress_mb", val)
            await callback_query.answer(f"Egress limit updated to {val} MB.", show_alert=True)
            callback_query.data = "adm_pln_ed_free"
            await admin_callback(client, callback_query)
            return

        elif data == "adm_pln_free_fl":
            config = await db.get_public_config()
            current_val = config.get("daily_file_count", 0)
            try:
                await callback_query.message.edit_text(
                    f"📄 **Edit Daily File Limit** (Free Plan)\n\nCurrent: `{current_val}` files\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="adm_pln_p_ff"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="adm_pln_ed_free"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

    if Config.PUBLIC_MODE and (
        data.startswith("adm_pub_p_") or data.startswith("adm_pln_p_")
    ):
        field_map = {"nam": "bot_name", "com": "community_name", "con": "support_contact", "gleg": "global_daily_egress"}
        raw_field = data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_")
        field = field_map.get(raw_field, raw_field)
        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})

        if field == "bot_name":
            text = "🤖 **Send the new bot name:**"
        elif field == "community_name":
            text = "👥 **Send the new community name:**"
        elif field == "support_contact":
            text = "🔗 **Send the new support contact (e.g., @username or link):**"
        elif field == "force_sub":
            text = (
                "📢 **Setup Force-Sub Channel**\n\n"
                "⏳ **I am waiting...**\n\n"
                "Simply **add me as an Administrator** to your desired channel right now!\n"
                "Make sure I have the 'Invite Users via Link' permission.\n\n"
                "I will automatically detect the channel and set it up instantly.\n\n"
                "*Send /cancel to cancel.*")
        elif field == "daily_egress":
            text = "📦 **Send the new daily egress limit.**\n\nYou can send the value in MB (e.g., `2048`) or use `GB` format (e.g., `2 GB` or `5.5 GB`).\nSend `0` to disable."
            cancel_btn = "adm_pln_ed_free"
        elif field == "daily_files":
            text = "📄 **Send the new daily file limit.**\nSend `0` to disable."
            cancel_btn = "adm_pln_ed_free"
        else:
            text = "Send the new value:"
            cancel_btn = "adm_pub_set"

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data=cancel_btn
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return
    if data == "adm_pub_set":
        try:
            await callback_query.message.edit_text(
                "🌐 **Public Mode Settings**\n\n" "Select a setting to edit:",
                reply_markup=get_admin_public_settings_menu(),
            )
        except MessageNotModified:
            pass


# === TEMPLATES MODULE ===


@Client.on_callback_query(filters.regex(r"^(adm_tpl_|adm_fn_)"))
async def admin_tpl_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_tpl_menu":
        try:
            await callback_query.message.edit_text(
                "📋 **Templates Menu**\n\n" "Select a template category to edit:",
                reply_markup=get_admin_templates_menu(),
            )
        except MessageNotModified:
            pass
    if data == "adm_tpl_sep":
        try:
            current_sep = await db.get_preferred_separator(user_id)
            sep_display = "Space" if current_sep == " " else current_sep
            await callback_query.message.edit_text(
                f"🔤 **Preferred Separator**\n\n"
                f"Choose the separator used when cleaning up filename templates.\n"
                f"Current: **{sep_display}**\n\n"
                f"Select your preferred separator below:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Dot (.)", callback_data="admin_set_sep_."),
                            InlineKeyboardButton("Underscore (_)", callback_data="adm_tpl_s_us"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="adm_tpl_s_sp"),
                        ],
                        [InlineKeyboardButton("← Back", callback_data="adm_tpl_menu")],
                    ]
                )
            )
        except MessageNotModified:
            pass
    elif data.startswith("adm_tpl_s_"):
        try:
            new_sep = data.split("adm_tpl_s_")[1]
            if new_sep == "space":
                new_sep = " "

            await db.update_preferred_separator(new_sep, user_id)
            sep_display = "Space" if new_sep == " " else new_sep

            await callback_query.answer(f"Separator set to: {sep_display}", show_alert=True)

            await callback_query.message.edit_text(
                f"🔤 **Preferred Separator**\n\n"
                f"Choose the separator used when cleaning up filename templates.\n"
                f"Current: **{sep_display}**\n\n"
                f"Select your preferred separator below:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Dot (.)", callback_data="admin_set_sep_."),
                            InlineKeyboardButton("Underscore (_)", callback_data="adm_tpl_s_us"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="adm_tpl_s_sp"),
                        ],
                        [InlineKeyboardButton("← Back", callback_data="adm_tpl_menu")],
                    ]
                )
            )
        except MessageNotModified:
            pass
    if data == "adm_tpl_meta":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Metadata Templates**\n\n" "Select a field to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Title", callback_data="adm_tpl_ed_tit"
                            ),
                            InlineKeyboardButton(
                                "Author", callback_data="adm_tpl_ed_aut"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "Artist", callback_data="adm_tpl_ed_art"
                            ),
                            InlineKeyboardButton(
                                "Video", callback_data="adm_tpl_ed_vid"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "Audio", callback_data="adm_tpl_ed_aud"
                            ),
                            InlineKeyboardButton(
                                "Subtitle", callback_data="adm_tpl_ed_sub"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_tpl_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_tpl_cap":
        templates = await db.get_all_templates()
        current_caption = templates.get("caption", "{random}")
        try:
            await callback_query.message.edit_text(
                f"📝 **Edit Caption Template**\n\n"
                f"Current: `{current_caption}`\n\n"
                "**Variables:**\n"
                "- `{filename}` : The final filename\n"
                "- `{size}` : File size (e.g. 1.5 GB)\n"
                "- `{duration}` : Video duration\n"
                "- `{random}` : Random string (Anti-Hash)\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="adm_tpl_p_cap"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_tpl_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_tpl_p_cap":
        await set_admin_state(user_id, {"state": "awaiting_template_caption", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "📝 **Send the new caption text:**\n\n(Use `{random}` to use the default random text generator)",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="adm_tpl_menu"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_tpl_fn":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Filename Templates**\n\n" "Select media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Movies", callback_data="adm_fn_mov"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Series", callback_data="adm_fn_ser"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal", callback_data="adm_fn_per"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Subtitles",
                                callback_data="adm_fn_sub",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_tpl_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_fn_per":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Personal Filename Templates**\n\n"
                "Select media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Personal Files",
                                callback_data="adm_fn_p_fil",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal Photos",
                                callback_data="adm_fn_p_pho",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal Videos",
                                callback_data="adm_fn_p_vid",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_tpl_fn"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_fn_sub":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Subtitles Filename Templates**\n\n"
                "Select media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Movies",
                                callback_data="adm_fn_s_mov",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Series",
                                callback_data="adm_fn_s_ser",
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("edit_fn_template_"):
        field = data.replace("edit_fn_template_", "")
        templates = await db.get_filename_templates()
        current_val = templates.get(field, "")
        try:
            vars_text = "`{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, `{Season_Episode}`, `{Language}`, `{Channel}`"
            if field.lower() in ["series", "subtitles_series"]:
                vars_text = "`{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, `{Season_Episode}`, `{Language}`, `{Channel}`, `{Specials}`, `{Codec}`, `{Audio}`"

            await callback_query.message.edit_text(
                f"✏️ **Edit Filename Template ({field.capitalize()})**\n\n"
                f"Current: `{current_val}`\n\n"
                f"Variables: {vars_text}\n"
                f"Note: File extension will be added automatically.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data=f"adm_fn_pt_{field}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_tpl_fn"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("prompt_fn_template_"):
        field = data.replace("prompt_fn_template_", "")
        await set_admin_state(user_id, {"state": f"awaiting_fn_template_{field}", "msg_id": callback_query.message.id})
        try:
            vars_text = ""
            if field.lower() in ["series", "subtitles_series"]:
                vars_text = "\n\nVariables: `{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, `{Season_Episode}`, `{Language}`, `{Channel}`, `{Specials}`, `{Codec}`, `{Audio}`"
            else:
                vars_text = "\n\nVariables: `{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, `{Season_Episode}`, `{Language}`, `{Channel}`"

            await callback_query.message.edit_text(
                f"✏️ **Send the new filename template for {field.capitalize()}:**{vars_text}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="adm_tpl_fn"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass

# === THUMBNAIL MODULE ===


@Client.on_callback_query(filters.regex(r"^adm_thm_"))
async def admin_thm_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_thm_menu":
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
                    callback_data="adm_thm_md_auto"
                ),
                InlineKeyboardButton(
                    "✅ Custom" if thumb_mode == "custom" else "Custom",
                    callback_data="adm_thm_md_cus"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Deactivated (None)" if thumb_mode == "none" else "Deactivated (None)",
                    callback_data="adm_thm_md_no"
                )
            ]
        ]

        if thumb_mode == "custom":
            buttons.append([InlineKeyboardButton(
                "👀 View Custom Thumbnail", callback_data="adm_thm_view")])
            buttons.append([InlineKeyboardButton(
                "📤 Upload New Thumbnail", callback_data="adm_thm_set")])
            buttons.append([InlineKeyboardButton(
                "🗑 Remove Thumbnail", callback_data="adm_thm_rem")])

        buttons.append([InlineKeyboardButton(
            "← Back", callback_data="adm_main")])

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except MessageNotModified:
            pass

    elif data.startswith("set_admin_thumb_mode_"):
        new_mode = data.replace("set_admin_thumb_mode_", "")
        await db.update_thumbnail_mode(new_mode, None)
        await callback_query.answer(f"Global thumbnail mode set to {new_mode.capitalize()}!", show_alert=True)
        callback_query.data = "adm_thm_menu"
        await admin_callback(client, callback_query)
        return

    if data == "adm_thm_rem":
        await db.update_thumbnail(None, None, None)
        await db.update_thumbnail_mode("none", None)
        try:
            await callback_query.message.edit_text(
                "✅ **Thumbnail Removed & Deactivated**\n\nFiles will no longer use a default custom thumbnail and the global thumbnail mode has been set to None.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back", callback_data="adm_thm_menu")]]
                ),
            )
        except MessageNotModified:
            pass

    if data == "adm_thm_view":
        thumb_bin, _ = await db.get_thumbnail()
        if thumb_bin:
            try:
                f = io.BytesIO(thumb_bin)
                f.name = "thumbnail.jpg"

                sent_msg = await client.send_photo(
                    user_id,
                    f,
                    caption="🖼 **Current Default Thumbnail**\n*(This message will auto-delete to keep the chat clean)*",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✅ OK", callback_data="adm_del_msg")]]
                    )
                )

                import asyncio

                async def auto_delete():
                    await asyncio.sleep(30)
                    try:
                        await sent_msg.delete()
                    except Exception:
                        pass

                asyncio.create_task(auto_delete())

                await callback_query.answer("Thumbnail sent! Check below.", show_alert=False)

            except Exception as e:
                logger.error(f"Failed to send thumbnail: {e}")
                await callback_query.answer("Error sending thumbnail!", show_alert=True)
        else:
            await callback_query.answer("No custom thumbnail currently uploaded!", show_alert=True)

    if data == "adm_thm_set":
        try:
            await callback_query.message.edit_text(
                "📤 **Set Default Thumbnail**\n\n"
                "Click below to upload a new thumbnail. "
                "This will be embedded into every video processed.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📤 Upload New", callback_data="adm_thm_p_set"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_thm_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_thm_p_set":
        await set_admin_state(user_id, {"state": "awaiting_thumb", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "🖼 **Send the new photo** to set as the default thumbnail:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="adm_thm_menu"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass

# === GENERAL SETTINGS MODULE ===


@Client.on_callback_query(filters.regex(r"^adm_gen_"))
async def admin_gen_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_gen_menu":
        try:
            await callback_query.message.edit_text(
                f"⚙️ **Global General Settings**\n\n"
                "Select a setting to configure:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📢 Channel Username", callback_data="adm_gen_chan"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🌍 Preferred Language", callback_data="adm_gen_lang"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⚙️ Workflow Mode", callback_data="adm_gen_wf"
                            )
                        ],
                        [InlineKeyboardButton("← Back", callback_data="adm_main")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_gen_wf":
        current_mode = await db.get_workflow_mode(None)
        mode_str = "🧠 Smart Media Mode" if current_mode == "smart_media_mode" else "⚡ Quick Rename Mode"
        try:
            await callback_query.message.edit_text(
                f"⚙️ **Global Workflow Mode Settings**\n\n"
                f"Current Mode: `{mode_str}`\n\n"
                "**🧠 Smart Media Mode:** Auto-detects Series/Movies and fetches TMDb metadata.\n"
                "**⚡ Quick Rename Mode:** Bypasses auto-detection and goes straight to general rename (great for personal/general files).\n\n"
                "Select the default mode for all users:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Smart Media Mode" if current_mode == "smart_media_mode" else "🧠 Smart Media Mode",
                                callback_data="adm_gen_wf_smt"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "✅ Quick Rename Mode" if current_mode == "quick_rename_mode" else "⚡ Quick Rename Mode",
                                callback_data="adm_gen_wf_qk"
                            )
                        ],
                        [InlineKeyboardButton("← Back", callback_data="adm_gen_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("adm_gen_wf_"):
        new_mode = "smart_media_mode" if data.endswith(
            "smart") else "quick_rename_mode"
        await db.update_workflow_mode(new_mode, None)
        await callback_query.answer("Global Workflow Mode updated!", show_alert=True)

        class MockQuery:
            def __init__(self, msg, usr):
                self.message = msg
                self.from_user = usr
                self.data = "adm_gen_wf"

            async def answer(self, *args, **kwargs): pass
        await admin_callback(client, MockQuery(callback_query.message, callback_query.from_user))
    if data == "adm_gen_chan":
        current_channel = await db.get_channel(None)
        try:
            await callback_query.message.edit_text(
                f"📢 **Global Channel Username Settings**\n\n"
                f"Current Channel Variable: `{current_channel}`\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="adm_gen_p_chan"
                            )
                        ],
                        [InlineKeyboardButton("← Back", callback_data="adm_gen_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_gen_p_chan":
        await set_admin_state(user_id, {"state": "awaiting_admin_channel", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                "⚙️ **Send the new Global Channel name variable to use in templates (e.g. `@MyChannel`):**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="adm_gen_chan")]]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_gen_lang":
        current_language = await db.get_preferred_language(None)
        try:
            await callback_query.message.edit_text(
                f"🌍 **Global Preferred Language Settings**\n\n"
                f"Current Preferred Language: `{current_language}`\n\n"
                "This language code is used when fetching data from TMDb (e.g., `en-US`, `de-DE`, `es-ES`).\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="adm_gen_p_lang"
                            )
                        ],
                        [InlineKeyboardButton("← Back", callback_data="adm_gen_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_gen_p_lang":
        try:
            await callback_query.message.edit_text(
                "🌍 **Select global preferred language for TMDb Metadata:**\n\n"
                "*(Default is English)*",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🇺🇸 English", callback_data="adm_gen_ln_en-US"),
                            InlineKeyboardButton("🇩🇪 German", callback_data="adm_gen_ln_de-DE"),
                        ],
                        [
                            InlineKeyboardButton("🇪🇸 Spanish", callback_data="adm_gen_ln_es-ES"),
                            InlineKeyboardButton("🇫🇷 French", callback_data="adm_gen_ln_fr-FR"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Hindi", callback_data="adm_gen_ln_hi-IN"),
                            InlineKeyboardButton("🇮🇳 Tamil", callback_data="adm_gen_ln_ta-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Telugu", callback_data="adm_gen_ln_te-IN"),
                            InlineKeyboardButton("🇮🇳 Malayalam", callback_data="adm_gen_ln_ml-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇯🇵 Japanese", callback_data="adm_gen_ln_ja-JP"),
                            InlineKeyboardButton("🇰🇷 Korean", callback_data="adm_gen_ln_ko-KR"),
                        ],
                        [
                            InlineKeyboardButton("🇨🇳 Chinese", callback_data="adm_gen_ln_zh-CN"),
                            InlineKeyboardButton("🇷🇺 Russian", callback_data="adm_gen_ln_ru-RU"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇹 Italian", callback_data="adm_gen_ln_it-IT"),
                            InlineKeyboardButton("🇧🇷 Portuguese", callback_data="adm_gen_ln_pt-BR"),
                        ],
                        [InlineKeyboardButton("← Back", callback_data="adm_gen_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("adm_gen_ln_"):
        new_language = data.replace("adm_gen_ln_", "")
        await db.update_preferred_language(new_language, None)
        callback_query.data = "adm_gen_lang"
        await admin_callback(client, callback_query)
        return

# === MAIN & MISC MODULE ===


@Client.on_callback_query(filters.regex(r"^(adm_main|adm_cancel|adm_view)"))
async def admin_main_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_view":
        settings = await db.get_settings()
        templates = settings.get("templates", {}) if settings else {}
        thumb_mode = settings.get(
            "thumbnail_mode",
            "none") if settings else "none"
        has_thumb = ("✅ Yes" if settings and settings.get(
            "thumbnail_binary") else "❌ No")

        mode_str = "Deactivated (None)"
        if thumb_mode == "auto":
            mode_str = "Auto-detect (Preview)"
        elif thumb_mode == "custom":
            mode_str = "Custom Thumbnail"

        text = f"👀 **Current Settings**\n\n"
        text += f"**Thumbnail Mode:** `{mode_str}`\n"
        text += f"**Custom Thumbnail Set:** {has_thumb}\n\n"
        text += "**Metadata Templates:**\n"
        if templates:
            for k, v in templates.items():
                if k == "caption":
                    text += f"- **Caption:** `{v}`\n"
                else:
                    text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No templates set.\n"
        text += "\n**Filename Templates:**\n"
        fn_templates = settings.get(
            "filename_templates",
            {}) if settings else {}
        if fn_templates:
            for k, v in fn_templates.items():
                text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No filename templates set.\n"
        text += f"\n**Channel Variable:** `{
            settings.get(
                'channel',
                Config.DEFAULT_CHANNEL) if settings else Config.DEFAULT_CHANNEL}`\n"
        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← Back to Admin Panel", callback_data="adm_main"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
    if data == "adm_main":
        await clear_admin_state(user_id)

        pro_session = await db.get_pro_session()

        if Config.PUBLIC_MODE:
            try:
                await callback_query.message.edit_text(
                    "🛠 **Public Mode Admin Panel** 🛠\n\n> Manage global settings for Public Mode.\n"
                    "Welcome, CEO.\n"
                    "Manage global settings for Public Mode.\n"
                    "These settings apply globally to the bot, such as branding and rate limits.\n"
                    "*(Use /settings to configure your personal renaming templates)*",
                    reply_markup=get_admin_main_menu(pro_session, Config.PUBLIC_MODE),
                )
            except MessageNotModified:
                pass
        else:
            try:
                await callback_query.message.edit_text(
                    "🛠 **𝕏TV Admin Panel** 🛠\n\n"
                    "Welcome, CEO.\n"
                    "Manage global settings for the 𝕏TV MediaStudio™.\n"
                    "These settings affect all files processed by the bot.",
                    reply_markup=get_admin_main_menu(pro_session, Config.PUBLIC_MODE),
                )
            except MessageNotModified:
                pass

    elif data.startswith("adm_tpl_ed_"):
        field_map = {"tit": "title", "aut": "author", "art": "artist", "vid": "video", "aud": "audio", "sub": "subtitle"}
        field = field_map.get(data.split("_")[-1], data.split("_")[-1])
        templates = await db.get_all_templates()
        current_val = templates.get(field, "")
        try:
            await callback_query.message.edit_text(
                f"✏️ **Edit {field.capitalize()} Template**\n\n"
                f"Current: `{current_val}`\n\n"
                f"Variables: `{{title}}`, `{{season_episode}}`, `{{lang}}` (for audio/subtitle)\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data=f"adm_tpl_pt_{field}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="adm_tpl_meta"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("prompt_template_"):
        field = data.replace("prompt_template_", "")
        await set_admin_state(user_id, {"state": f"awaiting_template_{field}", "msg_id": callback_query.message.id})
        try:
            await callback_query.message.edit_text(
                f"✏️ **Send the new template text for {field.capitalize()}:**",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="adm_tpl_meta"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass


@Client.on_message(filters.photo & filters.private, group=1)
async def handle_admin_photo(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state_obj = await get_admin_state(user_id)
    state = state_obj if isinstance(state_obj, str) else (
        state_obj.get("state") if state_obj else None)
    if state == "awaiting_fs_banner":
        try:
            file_id = message.photo.file_id
            await db.update_public_config("force_sub_banner_file_id", file_id)
            await message.reply_photo(
                file_id,
                caption="✅ Banner updated successfully! It will appear like this.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Menu", callback_data="adm_fs_menu")]])
            )
            await clear_admin_state(user_id)
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
            "✅ Global thumbnail updated successfully!\nThe global thumbnail mode has been set to **Custom**.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back to Menu", callback_data="adm_thm_menu"
                        )
                    ]
                ]
            ),
        )
        await clear_admin_state(user_id)
    except Exception as e:
        logger.error(f"Thumbnail upload failed: {e}")
        try:
            await msg.edit_text(f"❌ Error: {e}")
        except MessageNotModified:
            pass


async def edit_or_reply(client, message, msg_id, text, reply_markup=None):
    # Try to edit the original bot prompt to reduce spam
    try:
        await message.delete()  # delete user's input
    except Exception:
        pass

    if msg_id:
        try:
            return await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup
            )
        except Exception:
            pass

    # Fallback if editing fails
    return await message.reply_text(text, reply_markup=reply_markup)


# === MISC/UNKNOWN MODULE ===
@Client.on_callback_query(filters.regex(r"^(adm_del_msg|adm_cancel)"))
async def admin_misc_callback(client, callback_query):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    if data == "adm_del_msg":
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        return

    if data == "adm_cancel":
        await clear_admin_state(user_id)
        await callback_query.message.delete()
        return







@Client.on_message((filters.text | filters.forwarded) &
                   filters.private & ~filters.regex(r"^/"), group=1, )
async def handle_admin_text(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state_obj = await get_admin_state(user_id)
    if not state_obj:
        raise ContinuePropagation

    state = state_obj if isinstance(state_obj, str) else state_obj.get("state")
    msg_id = None if isinstance(state_obj, str) else state_obj.get("msg_id")

    # Dispatch to state machine routers
    handled = False
    for prefix, handler in ADMIN_TEXT_ROUTERS.items():
        if isinstance(
            state,
            str) and state.startswith(prefix) or (
            isinstance(
                state_obj,
                dict) and str(
                state_obj.get(
                    "state",
                    "")).startswith(prefix)):
            try:
                await handler(client, message, user_id, state, msg_id, state_obj)
                return
            except Exception as e:
                # Let exceptions bubble up
                raise

    if not handled:
        raise ContinuePropagation




async def _handle_awaiting_myfiles_db__0(
        client, message, user_id, state, msg_id, state_obj):
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
            await edit_or_reply(client, message, msg_id, f"❌ Error finding channel: {e}\nTry forwarding a message instead.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_myf_db")]])
                                )
            return

    if ch_id:
        await db.update_db_channel(plan, ch_id)
        await edit_or_reply(client, message, msg_id, f"✅ {plan.capitalize()} DB Channel updated to `{ch_id}`.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_myf_db")]])
                            )
        await clear_admin_state(user_id)

        return


async def _handle_awaiting_myfiles_lim__1(
        client, message, user_id, state, msg_id, state_obj):
    parts = state.replace("awaiting_myfiles_lim_", "").split("_")
    plan = parts[0]
    field = parts[1]
    val = message.text.strip() if message.text else ""

    cancel_cb = "adm_myf_ed_gl" if plan == "global" else f"adm_pln_ed_{plan}"

    try:
        val_int = int(val)
    except ValueError:
        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]])
                            )
        return

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

    await edit_or_reply(client, message, msg_id, f"✅ {plan.capitalize()} {field} limit updated to `{val_int}`.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=cancel_cb)]])
                        )
    await clear_admin_state(user_id)
    return


async def _handle_awaiting_global_daily_egress_2(
        client, message, user_id, state, msg_id, state_obj):
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton("❌ Cancel", callback_data="adm_pln_limits")]]
                            ),
                            )
        return
    await db.update_global_daily_egress_limit(float(val))
    await edit_or_reply(client, message, msg_id, f"✅ Global daily egress limit updated to `{val}` MB.",
                        reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="adm_pln_limits")]]
    ),
    )
    await clear_admin_state(user_id)
    return


async def _handle_wait_search_query_3(
        client,
        message,
        user_id,
        state,
        msg_id,
        state_obj):
    query = message.text.strip()
    results = await db.search_users(query)

    if not results:
        await message.reply("❌ No users found.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Try Again", callback_data="adm_usr_srch")],
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_users_menu")]
        ]))
        await clear_admin_state(user_id)
        return

    text = f"**🔍 Search Results: '{query}'**\n\n"
    markup = []
    for u in results[:10]:
        uid = u.get("user_id")
        name = u.get("first_name", "Unknown")[:15]
        uname = f"(@{u.get('username')})" if u.get("username") else ""
        markup.append([InlineKeyboardButton(
            f"{name} {uname} ({uid})", callback_data=f"view_user|{uid}")])

    markup.append([InlineKeyboardButton(
        "← Back", callback_data="admin_users_menu")])
    await message.reply(text, reply_markup=InlineKeyboardMarkup(markup))
    await clear_admin_state(user_id)
    return


async def _handle_state_4(client, message, user_id, state, msg_id, state_obj):
    try:
        days = float(message.text.strip())
        uid = state_obj["target_id"]
        plan = state_obj.get("plan", "standard")
        await db.add_premium_user(uid, days, plan=plan)
        await db.add_log("add_premium", user_id, f"Added {days} days premium ({plan}) to {uid}")

        await message.reply(f"✅ **Success!**\nUser `{uid}` has received {days} days of Premium ({plan}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Profile", callback_data=f"view_user|{uid}")]]))
        await clear_admin_state(user_id)
    except ValueError:
        await message.reply("❌ Invalid number. Enter days (e.g. 30).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"view_user|{state['target_id']}")]]))
    return


async def _handle_awaiting_user_lookup_5(
        client, message, user_id, state, msg_id, state_obj):
    val = message.text.strip()
    from utils.state import clear_session

    if val.isdigit():
        user_id = int(val)
    else:

        try:
            user = await client.get_users(val)
            user_id = user.id
        except Exception:
            await edit_or_reply(client, message, msg_id, "❌ Could not find a user with that ID or username. Please make sure the ID is correct.",
                                reply_markup=InlineKeyboardMarkup(
                                    [
                                        [
                                            InlineKeyboardButton(
                                                "← Back", callback_data="admin_usage_dashboard"
                                            )
                                        ]
                                    ]
                                ),
                                )
            await clear_admin_state(message.from_user.id)
            return

    await show_user_lookup(client, message, user_id)
    await clear_admin_state(message.from_user.id)
    return


async def _handle_awaiting_dumb_timeout_6(
        client, message, user_id, state, msg_id, state_obj):
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                            reply_markup=InlineKeyboardMarkup(
                                [
                                    [
                                        InlineKeyboardButton(
                                            "❌ Cancel", callback_data="adm_main"
                                        )
                                    ]
                                ]
                            ),
                            )
        return
    await db.update_dumb_channel_timeout(int(val))
    await edit_or_reply(client, message, msg_id, f"✅ Dumb channel timeout updated to `{val}` seconds.",
                        reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="adm_tpl_menu")]]
    ),
    )
    await clear_admin_state(user_id)
    return


async def _handle_awaiting_dumb_rename__7(
        client, message, user_id, state, msg_id, state_obj):
    ch_id = state.replace("awaiting_dumb_rename_", "")
    val = message.text.strip() if message.text else ""
    if val.lower() == "disable":
        await clear_admin_state(user_id)
        await edit_or_reply(client, message, msg_id, "Cancelled.",
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton("← Back", callback_data=f"adm_dmb_opt_{ch_id}")]]
                            ),
                            )
        return

    channels = await db.get_dumb_channels()
    if ch_id in channels:
        channels[ch_id] = val
        doc_id = "global_settings"
        await db.settings.update_one({"_id": doc_id}, {"$set": {"dumb_channels": channels}}, upsert=True)
        await edit_or_reply(client, message, msg_id, f"✅ Channel renamed to **{val}**.",
                            reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back", callback_data=f"adm_dmb_opt_{ch_id}")]]
        ),
        )
    await clear_admin_state(user_id)
    return


async def _handle_awaiting_dumb_add_8(
        client,
        message,
        user_id,
        state,
        msg_id,
        state_obj):
    val = message.text.strip() if message.text else ""
    if val.lower() == "disable":
        await clear_admin_state(user_id)
        await edit_or_reply(client, message, msg_id, "Cancelled.",
                            reply_markup=InlineKeyboardMarkup(
                                [
                                    [
                                        InlineKeyboardButton(
                                            "← Back to Menu", callback_data="adm_dmb_menu"
                                        )
                                    ]
                                ]
                            ),
                            )
        return

    ch_id = None
    ch_name = "Custom Channel"
    if message.forward_from_chat:
        ch_id = message.forward_from_chat.id
        ch_name = message.forward_from_chat.title
    elif val:
        try:
            chat = await client.get_chat(val)
            ch_id = chat.id
            ch_name = chat.title or "Channel"
        except Exception as e:
            await edit_or_reply(client, message, msg_id, f"❌ Error finding channel: {e}\nTry forwarding a message instead.",
                                reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="adm_dmb_menu")]]
            ),
            )
            return

    if ch_id:
        invite_link = None
        try:
            invite_link = await client.export_chat_invite_link(ch_id)
        except Exception as e:
            logger.warning(f"Could not export invite link for {ch_id}: {e}")

        await db.add_dumb_channel(ch_id, ch_name, invite_link=invite_link)
        await edit_or_reply(client, message, msg_id, f"✅ Added Dumb Channel: **{ch_name}** (`{ch_id}`)",
                            reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                            "← Back to Menu", callback_data="adm_dmb_menu"
                            )
                ]
            ]
        ),
        )
        await clear_admin_state(user_id)
    return


async def _handle_awaiting_pay__9(
        client,
        message,
        user_id,
        state,
        msg_id,
        state_obj):
    val = message.text.strip() if message.text else ""
    if not val:
        return

    if state.startswith("awaiting_pay_disc_"):
        months = state.replace("awaiting_pay_disc_", "")
        if not val.isdigit() or not (0 <= int(val) <= 99):
            await edit_or_reply(client, message, msg_id, "❌ Invalid discount percentage. Must be a number between 0 and 99.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_pay_disc")]])
                                )
            return

        config = await db.get_public_config()
        disc = config.get("discounts", {})
        disc[f"months_{months}"] = int(val)
        await db.update_public_config("discounts", disc)

        await edit_or_reply(client, message, msg_id, f"✅ {months}-Month discount updated to `{val}%`.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_pay_disc")]])
                            )
        await clear_admin_state(user_id)
        return

    else:
        method = state.replace("awaiting_pay_", "")
        config = await db.get_public_config()
        pm = config.get("payment_methods", {})

        if method == "paypal":
            pm["paypal_email"] = val
        elif method == "upi":
            pm["upi_id"] = val
        elif method == "crypto_usdt":
            pm["crypto_usdt"] = val
        elif method == "crypto_btc":
            pm["crypto_btc"] = val
        elif method == "crypto_eth":
            pm["crypto_eth"] = val

        await db.update_public_config("payment_methods", pm)

        back_data = "adm_pay_set"
        if method.startswith("crypto_"):
            back_data = "adm_pay_cr_mnu"

        await edit_or_reply(client, message, msg_id, f"✅ {method.replace('_', ' ').upper()} details updated to `{val}`.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=back_data)]])
                            )
        await clear_admin_state(user_id)
        return


async def _handle_awaiting_public__10(
        client,
        message,
        user_id,
        state,
        msg_id,
        state_obj):
    field = state.replace("awaiting_public_", "")

    val = message.text.strip() if message.text else ""
    if not val:
        return

    if field == "bot_name":
        await db.update_public_config("bot_name", val)
        await edit_or_reply(client, message, msg_id, f"✅ Bot Name updated to `{val}`",
                            reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                            "← Back to Menu", callback_data="adm_main"
                            )
                ]
            ]
        ),
        )
    elif field == "community_name":
        await db.update_public_config("community_name", val)
        await edit_or_reply(client, message, msg_id, f"✅ Community Name updated to `{val}`",
                            reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                            "← Back to Menu", callback_data="adm_main"
                            )
                ]
            ]
        ),
        )
    elif field == "support_contact":
        await db.update_public_config("support_contact", val)
        await edit_or_reply(client, message, msg_id, f"✅ Support Contact updated to `{val}`",
                            reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                            "← Back to Menu", callback_data="adm_main"
                            )
                ]
            ]
        ),
        )
    elif field == "force_sub":
        if val.lower() == "/cancel":
            await clear_admin_state(user_id)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                                reply_markup=InlineKeyboardMarkup(
                                    [[InlineKeyboardButton("← Back to Config", callback_data="adm_fs_menu")]]
                                )
                                )
        else:
            await edit_or_reply(client, message, msg_id, "⏳ **Still Waiting...**\n\nPlease add me as an Admin to the channel, or type `/cancel` to abort.",
                                reply_markup=InlineKeyboardMarkup(
                                    [[InlineKeyboardButton("❌ Cancel", callback_data="adm_fs_menu")]]
                                )
                                )
        return
    elif field == "rate_limit":
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                                reply_markup=InlineKeyboardMarkup(
                                    [
                                        [
                                            InlineKeyboardButton(
                                                "❌ Cancel", callback_data="adm_main"
                                            )
                                        ]
                                    ]
                                ),
                                )
            return
        await db.update_public_config("rate_limit_delay", int(val))
        await edit_or_reply(client, message, msg_id, f"✅ Rate limit updated to `{val}` seconds.",
                            reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                            "← Back to Menu", callback_data="adm_main"
                            )
                ]
            ]
        ),
        )
    elif field == "daily_egress":
        val_lower = val.lower().strip()
        val_num = 0

        if "gb" in val_lower:
            try:
                gb_val = float(val_lower.replace("gb", "").strip())
                val_num = int(gb_val * 1024)
            except ValueError:
                await edit_or_reply(client, message, msg_id, "❌ Invalid GB format. Please use something like `2 GB`.",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_pln_ed_free")]])
                                    )
                return
        else:
            try:
                val_num = int(float(val_lower.replace("mb", "").strip()))
            except ValueError:
                await edit_or_reply(client, message, msg_id, "❌ Invalid number format. Try again.",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_pln_ed_free")]])
                                    )
                return

        await db.update_public_config("daily_egress_mb", val_num)
        await edit_or_reply(client, message, msg_id, f"✅ **Success!**\n\nThe Daily Egress Limit for the **Free Plan** has been updated to **{val_num} MB**.\n\nChanges have been saved and applied globally.",
                            reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                            "← Back to Free Plan Limits", callback_data="adm_pln_ed_free"
                            )
                ]
            ]
        ),
        )
    elif field == "daily_files":
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                                reply_markup=InlineKeyboardMarkup(
                                    [
                                        [
                                            InlineKeyboardButton(
                                                "❌ Cancel", callback_data="adm_main"
                                            )
                                        ]
                                    ]
                                ),
                                )
            return
        await db.update_public_config("daily_file_count", int(val))
        await edit_or_reply(client, message, msg_id, f"✅ **Success!**\n\nThe Daily File Limit for the **Free Plan** has been updated to **{val} files**.\n\nChanges have been saved and applied globally.",
                            reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                            "← Back to Free Plan Limits", callback_data="adm_pln_ed_free"
                            )
                ]
            ]
        ),
        )

    await clear_admin_state(user_id)
    return


async def _handle_awaiting_premium__11(
        client,
        message,
        user_id,
        state,
        msg_id,
        state_obj):
    parts = state.replace("awaiting_premium_", "").split("_")
    if len(parts) >= 2 and parts[0] in ["standard", "deluxe"]:
        plan_name = parts[0]
        field = parts[1]
        val = message.text.strip() if message.text else ""

        config = await db.get_public_config()
        plan_key = f"premium_{plan_name}"
        plan_settings = config.get(plan_key, {})

        if field in ["egress", "files", "stars"]:
            val_num = 0
            if field == "egress":
                val_lower = val.lower().strip()
                if "gb" in val_lower:
                    try:
                        gb_val = float(val_lower.replace("gb", "").strip())
                        val_num = int(gb_val * 1024)
                    except ValueError:
                        await edit_or_reply(client, message, msg_id, "❌ Invalid GB format. Please use something like `2 GB`.",
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"adm_pln_ed_{plan_name}")]])
                                            )
                        return
                else:
                    try:
                        val_num = int(
                            float(
                                val_lower.replace(
                                    "mb",
                                    "").strip()))
                    except ValueError:
                        await edit_or_reply(client, message, msg_id, "❌ Invalid number format. Try again.",
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"adm_pln_ed_{plan_name}")]])
                                            )
                        return

                plan_settings["daily_egress_mb"] = val_num
            elif field == "files":
                if not val.isdigit():
                    await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                                        )
                    return
                val_num = int(val)
                plan_settings["daily_file_count"] = val_num
            elif field == "stars":
                if not val.isdigit():
                    await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                                        )
                    return
                val_num = int(val)
                plan_settings["stars_price"] = val_num

        await db.update_public_config(plan_key, plan_settings)

        back_btn_cb = f"adm_pln_ed_{plan_name}"

        await edit_or_reply(client, message, msg_id, f"✅ **Success!**\n\nThe {field.capitalize()} Limit for the **{plan_name.capitalize()} Plan** has been successfully updated to **{val_num}**.\n\nChanges have been saved and applied globally.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=back_btn_cb)]])
                            )
        await clear_admin_state(user_id)
        return


async def _handle_state_12(client, message, user_id, state, msg_id, state_obj):
    parts = state_obj["state"].replace("awaiting_premium_", "").split("_")
    if len(parts) >= 2 and parts[0] in ["standard", "deluxe"]:
        plan_name = parts[0]
        field = parts[1]

        if field == "price":
            val = message.text.strip() if message.text else ""

            # Check if it's a valid float/number
            try:
                float_val = float(val.replace(",", "."))
            except ValueError:
                await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"adm_pln_ed_{plan_name}")]])
                                    )
                return

            currency = state.get("currency", "USD")
            formatted_price = f"{float_val:g} {currency}"

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            plan_settings["price_string"] = formatted_price

            await db.update_public_config(plan_key, plan_settings)

            await edit_or_reply(client, message, msg_id, f"✅ {plan_name.capitalize()} fiat price updated to `{formatted_price}`.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=f"adm_pln_ed_{plan_name}")]])
                                )
            await clear_admin_state(user_id)
            return


async def _handle_awaiting_trial_days_13(
        client, message, user_id, state, msg_id, state_obj):
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_pln_prem_set")]])
                            )
        return
    await db.update_public_config("premium_trial_days", int(val))
    await edit_or_reply(client, message, msg_id, f"✅ Premium trial duration updated to `{val}` days.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_pln_prem_set")]])
                        )
    await clear_admin_state(user_id)
    return


async def _handle_awaiting_fs__14(
        client,
        message,
        user_id,
        state,
        msg_id,
        state_obj):
    val = message.text.strip() if message.text else ""
    if val == "/cancel":
        await clear_admin_state(user_id)
        await edit_or_reply(client, message, msg_id, "Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Menu", callback_data="adm_fs_menu")]]))
        return

    field = state.replace("awaiting_fs_", "")

    if field == "msg":
        await db.update_public_config("force_sub_message_text", val)
        await edit_or_reply(client, message, msg_id, "✅ Gate message updated successfully.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_fs_menu")]])
                            )
    elif field == "btn_label":
        await db.update_public_config("force_sub_button_label", val)
        await edit_or_reply(client, message, msg_id, f"✅ Button label updated to `{val}`.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_fs_btn")]])
                            )
    elif field == "btn_emoji":

        emoji = val[0] if val else "📢"
        await db.update_public_config("force_sub_button_emoji", emoji)
        await edit_or_reply(client, message, msg_id, f"✅ Button emoji updated to {emoji}.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_fs_btn")]])
                            )
    elif field == "welcome":
        await db.update_public_config("force_sub_welcome_text", val)
        await edit_or_reply(client, message, msg_id, "✅ Welcome message updated successfully.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="adm_fs_menu")]])
                            )

    await clear_admin_state(user_id)
    return


async def _handle_awaiting_template__15(
        client,
        message,
        user_id,
        state,
        msg_id,
        state_obj):
    field_map = {"tit": "title", "aut": "author", "art": "artist", "vid": "video", "aud": "audio", "sub": "subtitle"}
    field = field_map.get(state.split("_")[-1], state.split("_")[-1])
    new_template = message.text
    await db.update_template(field, new_template)
    if field == "caption":
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back", callback_data="adm_tpl_menu")]]
        )
    else:
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "← Back to Templates", callback_data="adm_tpl_meta"
                    )
                ]
            ]
        )
    await edit_or_reply(client, message, msg_id, f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`",
                        reply_markup=reply_markup,
                        )
    await clear_admin_state(user_id)


async def _handle_awaiting_fn_template__16(
        client, message, user_id, state, msg_id, state_obj):
    field_map = {"mov": "movies", "ser": "series", "p_fil": "personal_file", "p_pho": "personal_photo", "p_vid": "personal_video", "s_mov": "subtitles_movies", "s_ser": "subtitles_series"}
    field = field_map.get(state.replace("awaiting_fn_template_", ""), state.replace("awaiting_fn_template_", ""))
    new_template = message.text
    await db.update_filename_template(field, new_template)
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "← Back to Filename Templates",
                    callback_data="adm_tpl_fn",
                )
            ]
        ]
    )
    await edit_or_reply(client, message, msg_id, f"✅ Filename template for **{field.capitalize()}** updated to:\n`{new_template}`",
                        reply_markup=reply_markup,
                        )
    await clear_admin_state(user_id)


async def _handle_awaiting_admin_channel_17(
        client, message, user_id, state, msg_id, state_obj):
    new_channel = message.text
    await db.update_channel(new_channel, None)

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="adm_gen_chan")]]
    )
    await edit_or_reply(client, message, msg_id, f"✅ Global channel variable updated to:\n`{new_channel}`",
                        reply_markup=reply_markup,
                        )
    await clear_admin_state(user_id)


debug("✅ Loaded handler: admin_dashboard_overview_cb")


@Client.on_callback_query(
    filters.regex("^adm_dash_main$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_overview_cb(
        client: Client,
        callback_query: CallbackQuery):
    stats = await db.get_dashboard_stats()

    from plugins.process import _SEMAPHORES

    active_slots = 0
    for phase in ["download", "process", "upload"]:
        for user_sems in _SEMAPHORES.values():
            if phase in user_sems and user_sems[phase] is not None:

                active_slots += 3 - user_sems[phase]._value

    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb:.2f} MB"

    import datetime

    current_time_str = datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    start_date_obj = datetime.datetime.strptime(
        stats.get("bot_start_date"), "%Y-%m-%d")
    start_date_str = start_date_obj.strftime("%d %b %Y")

    text = (
        f"📊 **𝕏TV Usage Dashboard**\n"
        f"Updated: {current_time_str}\n"
        f"═════════════════════════\n"
        f"👥 Total Users: `{stats.get('total_users')}`\n"
        f"📁 Files Processed Today: `{stats.get('files_today')}`\n"
        f"📦 Egress Today: `{format_egress(stats.get('egress_today_mb'))}`\n"
    )

    if Config.PUBLIC_MODE:
        text += f"⚡ Active Right Now: `{active_slots}`\n"

    text += (
        f"─────────────────────────\n"
        f"📈 **All-Time**\n"
        f"─────────────────────────\n"
        f"📁 Total Files: `{stats.get('total_files')}`\n"
        f"📦 Total Egress: `{format_egress(stats.get('total_egress_mb'))}`\n"
        f"🗓️ Bot Running Since: `{start_date_str}`\n"
    )

    if Config.PUBLIC_MODE:
        text += (
            f"─────────────────────────\n"
            f"⚠️ Quota Hits Today: `{stats.get('quota_hits_today')}`\n"
            f"🚫 Blocked Users: `{stats.get('blocked_users')}`\n"
        )

    text += f"─────────────────────────"

    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔝 Top Users", callback_data="adm_dash_t_0"
                        ),
                        InlineKeyboardButton(
                            "📅 Daily Breakdown", callback_data="admin_dashboard_daily"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🔍 User Lookup", callback_data="prompt_user_lookup"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "← Back to Admin Panel", callback_data="adm_main"
                        )
                    ],
                ]
            ),
        )
    except MessageNotModified:
        pass

debug("✅ Loaded handler: admin_dashboard_top_cb")


@Client.on_callback_query(
    filters.regex(r"^admin_dashboard_top_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_top_cb(
        client: Client,
        callback_query: CallbackQuery):
    page = int(callback_query.matches[0].group(1))
    limit = 10
    skip = page * limit

    users, total = await db.get_top_users_today(limit=limit, skip=skip)

    import datetime

    current_date = datetime.datetime.utcnow().strftime("%d %b")

    text = f"🏆 **Top Users — Today ({current_date})**\n\n"

    if not users:
        text += "No usage tracked today."
    else:
        for i, user in enumerate(users):
            rank = skip + i + 1
            user_id = user["_id"].replace("user_", "")

            try:
                user_obj = await client.get_users(int(user_id))
                display_name = (
                    f"@{user_obj.username}"
                    if user_obj.username
                    else f"{user_obj.first_name}"
                )
            except Exception:
                display_name = f"User {user_id}"

            usage = user.get("usage", {})
            files = usage.get("file_count", 0)
            mb = usage.get("egress_mb", 0.0)

            if mb >= 1024:
                mb_str = f"{mb / 1024:.2f} GB"
            else:
                mb_str = f"{mb:.2f} MB"

            text += f"**#{rank}** {display_name} — {files} files · {mb_str}\n"

    buttons = []
    nav_row = []

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                "← Prev", callback_data=f"adm_dash_t_{page - 1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton("← Prev", callback_data="noop"))

    nav_row.append(
        InlineKeyboardButton(
            f"Page {
                page +
                1} / {total_pages}",
            callback_data="noop"))

    if skip + limit < total:
        nav_row.append(
            InlineKeyboardButton(
                "Next →", callback_data=f"adm_dash_t_{page + 1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton("Next →", callback_data="noop"))

    buttons.append(nav_row)

    buttons.append(
        [InlineKeyboardButton("← Back", callback_data="admin_usage_dashboard")]
    )

    try:
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass

debug("✅ Loaded handler: admin_dashboard_daily_cb")


@Client.on_callback_query(
    filters.regex("^adm_dash_dly$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_daily_cb(
        client: Client,
        callback_query: CallbackQuery):
    daily_stats = await db.get_daily_stats(limit=7)

    text = "📅 **Last 7 Days Breakdown**\n\n"
    text += "`Date          Files    Egress`\n"
    text += "`──────────────────────────────`\n"

    if not daily_stats:
        text += "No history available."
    else:
        import datetime

        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        for stat in daily_stats:
            date_obj = datetime.datetime.strptime(stat["date"], "%Y-%m-%d")
            date_str = date_obj.strftime("%d %b %Y")

            files = stat.get("file_count", 0)
            mb = stat.get("egress_mb", 0.0)

            if mb >= 1048576:
                egress_str = f"{mb / 1048576:.2f} TB"
            elif mb >= 1024:
                egress_str = f"{mb / 1024:.2f} GB"
            else:
                egress_str = f"{mb:.2f} MB"

            is_today = " ← today" if stat["date"] == current_utc_date else ""

            text += f"`{date_str:<13} {files:<7} {egress_str:>7}`{is_today}\n"

    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back", callback_data="admin_usage_dashboard"
                        )
                    ]
                ]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_message(filters.regex(r"^/lookup (\d+)$")
                   & filters.user(Config.CEO_ID))
async def admin_lookup_user(client: Client, message: Message):
    user_id = int(message.matches[0].group(1))
    await show_user_lookup(client, message, user_id)


async def show_user_lookup(client: Client, message: Message, user_id: int):
    usage = await db.get_user_usage(user_id)
    is_blocked = await db.is_user_blocked(user_id)

    import datetime

    current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    current_date_display = datetime.datetime.utcnow().strftime("%d %b")

    files_today = 0
    egress_today_mb = 0.0
    quota_hits_today = 0

    if usage.get("date") == current_utc_date:
        files_today = usage.get("file_count", 0)
        egress_today_mb = usage.get("egress_mb", 0.0)
        quota_hits_today = usage.get("quota_hits", 0)

    files_alltime = usage.get("file_count_alltime", 0)
    egress_alltime_mb = usage.get("egress_mb_alltime", 0.0)

    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb:.2f} MB"

    try:
        user_obj = await client.get_users(user_id)
        name = user_obj.first_name
        username = f"@{user_obj.username}" if user_obj.username else "N/A"
    except Exception:
        name = "Unknown User"
        username = "N/A"

    user_settings = await db.get_settings(user_id)
    joined_date = "Unknown"

    has_thumb = "No"
    current_template = "Default"

    if user_settings:
        if user_settings.get("thumbnail_file_id") or user_settings.get(
            "thumbnail_binary"
        ):
            has_thumb = "Yes"

        templates = user_settings.get("templates", {})
        if templates and templates.get("caption") != "{random}":
            current_template = "Custom"

        _id = user_settings.get("_id")
        if _id:
            try:

                import bson

                if isinstance(_id, bson.ObjectId):
                    joined_date = _id.generation_time.strftime("%d %b %Y")
                else:
                    joined_date = usage.get("date", "Unknown")
            except Exception:
                joined_date = usage.get("date", "Unknown")

    text = (
        f"👤 **User Lookup**\n\n"
        f"**ID:** `{user_id}`\n"
        f"**Name:** {name}\n"
        f"**Username:** {username}\n"
        f"**Joined:** {joined_date}\n"
        f"**Template:** {current_template}\n"
        f"**Custom Thumb:** {has_thumb}\n"
        f"──────────────────────────\n"
        f"📊 **Today ({current_date_display})**\n"
        f"Files: `{files_today}`\n"
        f"Egress: `{format_egress(egress_today_mb)}`\n"
        f"Quota hits: `{quota_hits_today}`\n\n"
        f"📈 **All-Time**\n"
        f"Files: `{files_alltime}`\n"
        f"Egress: `{format_egress(egress_alltime_mb)}`\n"
        f"──────────────────────────\n"
    )

    if is_blocked:
        text += "🔴 **Status: BLOCKED**\n"

    buttons = []

    if is_blocked:
        buttons.append(
            [
                InlineKeyboardButton(
                    "✅ Unblock User", callback_data=f"adm_usr_ublk_{user_id}"
                )
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    "🚫 Block User", callback_data=f"adm_usr_blk_{user_id}"
                )
            ]
        )

    buttons.append([InlineKeyboardButton(
        "🗑️ Reset Today's Quota", callback_data=f"adm_usr_rsq_{user_id}")])
    buttons.append(
        [InlineKeyboardButton("← Back", callback_data="admin_usage_dashboard")]
    )

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

debug("✅ Loaded handler: admin_block_user_cb")


@Client.on_callback_query(
    filters.regex(r"^adm_usr_blk_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_block_user_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("User Blocked", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.block_user(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_unblock_user_cb")


@Client.on_callback_query(
    filters.regex(r"^adm_usr_ublk_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_unblock_user_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("User Unblocked", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.unblock_user(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_reset_quota_cb")


@Client.on_callback_query(
    filters.regex(r"^adm_usr_rsq_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_reset_quota_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("Quota Reset", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.reset_user_quota(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_prompt_lookup_cb")


@Client.on_callback_query(
    filters.regex("^adm_usr_look$") & filters.user(Config.CEO_ID)
)
async def admin_prompt_lookup_cb(
        client: Client,
        callback_query: CallbackQuery):
    try:
        await callback_query.message.edit_text(
            "🔍 **User Lookup**\n\n"
            "Please send the user's Telegram ID (e.g., 123456789) to view their profile.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back", callback_data="admin_usage_dashboard"
                        )
                    ]
                ]
            ),
        )
    except MessageNotModified:
        pass
    await set_admin_state(callback_query.from_user.id, {"state": "awaiting_user_lookup", "msg_id": callback_query.message.id})


@Client.on_message(
    filters.text & filters.private & filters.user(Config.CEO_ID), group=1
)
async def admin_handle_user_lookup_text(client: Client, message: Message):
    state_obj = await get_admin_state(message.from_user.id)
    state = state_obj.get("state") if isinstance(state_obj, dict) else state_obj

    if state == "awaiting_user_lookup":
        val = message.text.strip()

        if val.isdigit():
            user_id = int(val)
        else:

            try:
                user = await client.get_users(val)
                user_id = user.id
            except Exception:
                await message.reply_text("❌ Could not find a user with that ID or username. Please make sure the ID is correct.",
                                         reply_markup=InlineKeyboardMarkup(
                                             [
                                                 [
                                                     InlineKeyboardButton(
                                                         "← Back", callback_data="admin_usage_dashboard"
                                                     )
                                                 ]
                                             ]
                                         ),
                                         )
                await clear_admin_state(message.from_user.id)
                return

        await show_user_lookup(client, message, user_id)
        await clear_admin_state(message.from_user.id)
        raise ContinuePropagation


@Client.on_callback_query(filters.regex("^noop$"))
async def noop_cb(client, callback_query):
    try:
        await callback_query.answer()
    except Exception:
        pass

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------


async def _handle_awaiting_premium__master(client, message, user_id, state, msg_id, state_obj):
    if isinstance(state_obj, dict) and state_obj.get("currency"):
        await _handle_state_12(client, message, user_id, state, msg_id, state_obj)
    else:
        await _handle_awaiting_premium__11(client, message, user_id, state, msg_id, state_obj)




ADMIN_TEXT_ROUTERS = {
    "awaiting_myfiles_db_": _handle_awaiting_myfiles_db__0,
    "awaiting_myfiles_lim_": _handle_awaiting_myfiles_lim__1,
    "awaiting_global_daily_egress": _handle_awaiting_global_daily_egress_2,
    "wait_search_query": _handle_wait_search_query_3,
    "wait_add_prem_days": _handle_state_4,
    "awaiting_user_lookup": _handle_awaiting_user_lookup_5,
    "awaiting_dumb_timeout": _handle_awaiting_dumb_timeout_6,
    "awaiting_dumb_rename_": _handle_awaiting_dumb_rename__7,
    "awaiting_dumb_add": _handle_awaiting_dumb_add_8,
    "awaiting_pay_": _handle_awaiting_pay__9,
    "awaiting_public_": _handle_awaiting_public__10,
    "awaiting_premium_": _handle_awaiting_premium__master,
    "awaiting_trial_days": _handle_awaiting_trial_days_13,
    "awaiting_fs_": _handle_awaiting_fs__14,
    "awaiting_template_": _handle_awaiting_template__15,
    "awaiting_fn_template_": _handle_awaiting_fn_template__16,
    "awaiting_admin_channel": _handle_awaiting_admin_channel_17,
}
