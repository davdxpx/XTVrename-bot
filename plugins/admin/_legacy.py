# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Legacy monolithic admin handlers.

During the migration to the plugins/admin/ package this file holds the
original admin.py body unchanged so every flow keeps working. Domain by
domain its contents are carved out into sibling modules; eventually this
file shrinks to nothing and gets deleted.

`admin_sessions`, `is_admin`, `edit_or_reply`, `get_admin_main_menu` and
`get_admin_access_limits_menu` now live in plugins/admin/core.py — this
file imports them from there so state is shared by reference.
"""
# --- Imports ---
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from utils.log import get_logger
import asyncio
import io

from plugins.admin.core import (
    admin_sessions,
    is_admin,
    edit_or_reply,
    get_admin_main_menu,
    get_admin_access_limits_menu,
)

logger = get_logger("plugins.admin")

# === Helper Functions ===
# get_admin_main_menu, get_admin_access_limits_menu, is_admin and
# edit_or_reply now live in plugins/admin/core.py (see import above).
# Domain-specific menu builders below (templates, public settings) stay
# here temporarily — they will move to their respective domain modules
# in later migration steps.

# get_admin_templates_menu moved to plugins/admin/templates.py

# get_admin_public_settings_menu moved to plugins/admin/public_settings.py

# /admin command + admin_main callback moved to plugins/admin/panel.py

from pyrogram import ContinuePropagation
from utils.logger import debug

debug("✅ Loaded handler: admin_callback")

@Client.on_callback_query(
    filters.regex(
        r"^(admin_(?!usage_dashboard|dashboard_|block_|unblock_|reset_quota_|broadcast|users_menu|user_search_start|dumb_channels|dumb_timeout|view$|general_settings_menu$|main$|access_limits$|quick_toggle_(?:premium|deluxe|trial|myfiles)$|feature_toggles$|gtoggle_|per_plan_limits$|global_daily_egress$|thumb_(?:menu|view|set|remove)$|delete_msg$|templates_menu$|templates$|caption$|filename_templates$|fn_templates_(?:personal|subtitles)$|pref_separator$|set_sep_|public_(?:settings|view|bot_name|community_name|support_contact)$|force_sub_menu$|fs_|myfiles_|clean_|payments_menu$|pay_|edit_plan_|toggle_|premium_|trial_|features_|privacy_|daily_|prem_cur_)|prompt_admin_(?!dumb_timeout|thumb_set|caption|fs_)|admin_set_lang_|set_admin_workflow_|set_4gb_access_)"
    )
)
async def admin_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data
    debug(f"Admin callback: {data} from user {user_id}")

    # Quick-toggles and admin_access_limits moved to plugins/admin/feature_toggles.py
    # admin_myfiles_settings, admin_myfiles_db_channels, prompt_myfiles_db_*
    # moved to plugins/admin/myfiles.py

    # admin_per_plan_limits moved to plugins/admin/feature_toggles.py

    # admin_edit_plan_*, admin_toggle_*, admin_premium_*, admin_trial_*,
    # admin_features_*, admin_privacy_*, admin_daily_*, prompt_premium_*,
    # prompt_trial_*, prompt_daily_*, prompt_global_daily_egress,
    # set_prem_egress_*, admin_prem_cur_*, set_daily_egress_*,
    # prompt_prem_egress_custom_* moved to plugins/admin/premium.py

    # admin_thumb_* moved to plugins/admin/thumbnails.py
    # admin_templates_menu moved to plugins/admin/templates.py
    # admin_access_limits moved to plugins/admin/feature_toggles.py
    # admin_public_settings moved to plugins/admin/public_settings.py
    # admin_pref_separator, admin_set_sep_*, admin_templates, admin_caption,
    # prompt_admin_caption, admin_filename_templates, admin_fn_templates_*,
    # edit_fn_template_*, prompt_fn_template_* moved to plugins/admin/templates.py
    # admin_general_settings_menu moved to plugins/admin/general.py
    if data == "admin_general_workflow":
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
                                callback_data="set_admin_workflow_smart"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "✅ Quick Rename Mode" if current_mode == "quick_rename_mode" else "⚡ Quick Rename Mode",
                                callback_data="set_admin_workflow_quick"
                            )
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("set_admin_workflow_"):
        new_mode = "smart_media_mode" if data.endswith("smart") else "quick_rename_mode"
        await db.update_workflow_mode(new_mode, None)
        await callback_query.answer("Global Workflow Mode updated!", show_alert=True)

        class MockQuery:
            def __init__(self, msg, usr):
                self.message = msg
                self.from_user = usr
                self.data = "admin_general_workflow"
            async def answer(self, *args, **kwargs): pass
        await admin_callback(client, MockQuery(callback_query.message, callback_query.from_user))
    elif data == "admin_general_channel":
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
                                "✏️ Change", callback_data="prompt_admin_channel"
                            )
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "prompt_admin_channel":
        admin_sessions[user_id] = {"state": "awaiting_admin_channel", "msg_id": callback_query.message.id}
        try:
            await callback_query.message.edit_text(
                "⚙️ **Send the new Global Channel name variable to use in templates (e.g. `@MyChannel`):**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_general_channel")]]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_general_language":
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
                                "✏️ Change", callback_data="prompt_admin_language"
                            )
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "prompt_admin_language":
        try:
            await callback_query.message.edit_text(
                "🌍 **Select global preferred language for TMDb Metadata:**\n\n"
                "__(Default is English)__",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🇺🇸 English", callback_data="admin_set_lang_en-US"),
                            InlineKeyboardButton("🇩🇪 German", callback_data="admin_set_lang_de-DE"),
                        ],
                        [
                            InlineKeyboardButton("🇪🇸 Spanish", callback_data="admin_set_lang_es-ES"),
                            InlineKeyboardButton("🇫🇷 French", callback_data="admin_set_lang_fr-FR"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Hindi", callback_data="admin_set_lang_hi-IN"),
                            InlineKeyboardButton("🇮🇳 Tamil", callback_data="admin_set_lang_ta-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Telugu", callback_data="admin_set_lang_te-IN"),
                            InlineKeyboardButton("🇮🇳 Malayalam", callback_data="admin_set_lang_ml-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇯🇵 Japanese", callback_data="admin_set_lang_ja-JP"),
                            InlineKeyboardButton("🇰🇷 Korean", callback_data="admin_set_lang_ko-KR"),
                        ],
                        [
                            InlineKeyboardButton("🇨🇳 Chinese", callback_data="admin_set_lang_zh-CN"),
                            InlineKeyboardButton("🇷🇺 Russian", callback_data="admin_set_lang_ru-RU"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇹 Italian", callback_data="admin_set_lang_it-IT"),
                            InlineKeyboardButton("🇧🇷 Portuguese", callback_data="admin_set_lang_pt-BR"),
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("admin_set_lang_"):
        new_language = data.replace("admin_set_lang_", "")
        await db.update_preferred_language(new_language, None)
        callback_query.data = "admin_general_language"
        await admin_callback(client, callback_query)
        return
    elif data == "admin_cancel":
        admin_sessions.pop(user_id, None)
        await callback_query.message.delete()
        return
    # admin_main moved to plugins/admin/panel.py
    # edit_template_*, prompt_template_* moved to plugins/admin/templates.py

# handle_admin_photo moved to plugins/admin/thumbnails.py

from pyrogram import ContinuePropagation

@Client.on_message(
    (filters.text | filters.forwarded) & filters.private & ~filters.regex(r"^/"),
    group=1,
)
async def handle_admin_text(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state_obj = admin_sessions.get(user_id)
    if not state_obj:
        raise ContinuePropagation

    state = state_obj if isinstance(state_obj, str) else state_obj.get("state")
    msg_id = None if isinstance(state_obj, str) else state_obj.get("msg_id")

    if isinstance(state, str) and state.startswith("awaiting_myfiles_db_"):
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
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_myfiles_db_channels")]])
                )
                return

        if ch_id:
            await db.update_db_channel(plan, ch_id)
            await edit_or_reply(client, message, msg_id, f"✅ {plan.capitalize()} DB Channel updated to `{ch_id}`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to DB Channels", callback_data="admin_myfiles_db_channels")]])
            )
            admin_sessions.pop(user_id, None)

            from pyrogram import StopPropagation
            raise StopPropagation

    if isinstance(state, str) and state.startswith("awaiting_myfiles_lim_"):
        parts = state.replace("awaiting_myfiles_lim_", "").split("_")
        plan = parts[0]
        field = parts[1]
        val = message.text.strip() if message.text else ""

        from pyrogram import StopPropagation

        cancel_cb = "admin_myfiles_edit_limits_global" if plan == "global" else f"admin_edit_plan_{plan}"

        try:
            val_int = int(val)
        except ValueError:
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]])
            )
            raise StopPropagation

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
        admin_sessions.pop(user_id, None)
        raise StopPropagation

    if state == "awaiting_global_daily_egress":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="admin_access_limits")]]
                ),
            )
            return
        await db.update_global_daily_egress_limit(float(val))
        await edit_or_reply(client, message, msg_id, f"✅ Global daily egress limit updated to `{val}` MB.",
            reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Settings", callback_data="admin_access_limits")]]
            ),
        )
        admin_sessions.pop(user_id, None)
        return

    if state == "wait_search_query":
        query = message.text.strip()
        results = await db.search_users(query)

        if not results:
            await message.reply("❌ No users found.", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Try Again", callback_data="admin_user_search_start")],
                [InlineKeyboardButton("❌ Cancel", callback_data="admin_users_menu")]
            ]))
            admin_sessions.pop(user_id, None)
            return

        text = f"**🔍 Search Results: '{query}'**\n\n"
        markup = []
        for u in results[:10]:
            uid = u.get("user_id")
            name = u.get("first_name") or "Unknown"
            name = name[:15]
            uname = f"(@{u.get('username')})" if u.get("username") else ""
            markup.append([InlineKeyboardButton(f"{name} {uname} ({uid})", callback_data=f"view_user|{uid}")])

        markup.append([InlineKeyboardButton("← Back to User Management", callback_data="admin_users_menu")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(markup))
        admin_sessions.pop(user_id, None)
        return

    if isinstance(state, dict) and state.get("state") == "wait_add_prem_days":
        try:
            days = float(message.text.strip())
            uid = state["target_id"]
            plan = state.get("plan", "standard")
            await db.add_premium_user(uid, days, plan=plan)
            await db.add_log("add_premium", user_id, f"Added {days} days premium ({plan}) to {uid}")

            await message.reply(f"✅ **Success!**\nUser `{uid}` has received {days} days of Premium ({plan}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Profile", callback_data=f"view_user|{uid}")]]))
            admin_sessions.pop(user_id, None)
        except ValueError:
            await message.reply("❌ Invalid number. Enter days (e.g. 30).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"view_user|{state['target_id']}")]]))
        return

    if not state or state != "awaiting_user_lookup":
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    if state == "awaiting_user_lookup":
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
                                    "← Back to Dashboard", callback_data="admin_usage_dashboard"
                                )
                            ]
                        ]
                    ),
                )
                clear_session(message.from_user.id)
                return

        await show_user_lookup(client, message, user_id)
        clear_session(message.from_user.id)
        return

    if state == "awaiting_dumb_timeout":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                    "❌ Cancel", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
            return
        await db.update_dumb_channel_timeout(int(val))
        await edit_or_reply(client, message, msg_id, f"✅ Dumb channel timeout updated to `{val}` seconds.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Templates", callback_data="admin_templates_menu")]]
            ),
        )
        admin_sessions.pop(user_id, None)
        return

    if isinstance(state, str) and state.startswith("awaiting_dumb_rename_") and not Config.PUBLIC_MODE:
        ch_id = state.replace("awaiting_dumb_rename_", "")
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            admin_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Channel Settings", callback_data=f"dumb_opt_{ch_id}")]]
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
                    [[InlineKeyboardButton("← Back to Channel Settings", callback_data=f"dumb_opt_{ch_id}")]]
                ),
            )
        admin_sessions.pop(user_id, None)
        return

    if state == "awaiting_dumb_add" and not Config.PUBLIC_MODE:
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            admin_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← Back to Dumb Channels", callback_data="dumb_menu"
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
                        [[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]]
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
                                "← Back to Dumb Channels", callback_data="dumb_menu"
                            )
                        ]
                    ]
                ),
            )
            admin_sessions.pop(user_id, None)
        return

    if isinstance(state, str) and state.startswith("awaiting_pay_"):
        val = message.text.strip() if message.text else ""
        if not val:
            raise ContinuePropagation

        if state.startswith("awaiting_pay_disc_"):
            months = state.replace("awaiting_pay_disc_", "")
            if not val.isdigit() or not (0 <= int(val) <= 99):
                await edit_or_reply(client, message, msg_id, "❌ Invalid discount percentage. Must be a number between 0 and 99.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_pay_discounts")]])
                )
                return

            config = await db.get_public_config()
            disc = config.get("discounts", {})
            disc[f"months_{months}"] = int(val)
            await db.update_public_config("discounts", disc)

            await edit_or_reply(client, message, msg_id, f"✅ {months}-Month discount updated to `{val}%`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Discounts", callback_data="admin_pay_discounts")]])
            )
            admin_sessions.pop(user_id, None)
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

            back_data = "admin_pay_settings"
            if method.startswith("crypto_"):
                back_data = "admin_pay_crypto_menu"

            await edit_or_reply(client, message, msg_id, f"✅ {method.replace('_', ' ').upper()} details updated to `{val}`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=back_data)]])
            )
            admin_sessions.pop(user_id, None)
            return

    if state.startswith("awaiting_public_"):
        field = state.replace("awaiting_public_", "")

        val = message.text.strip() if message.text else ""
        if not val:
            raise ContinuePropagation

        if field == "bot_name":
            await db.update_public_config("bot_name", val)
            await edit_or_reply(client, message, msg_id, f"✅ Bot Name updated to `{val}`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← Back to Admin Panel", callback_data="admin_main"
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
                                "← Back to Admin Panel", callback_data="admin_main"
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
                                "← Back to Admin Panel", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "force_sub":
            if val.lower() == "/cancel":
                admin_sessions.pop(user_id, None)
                await edit_or_reply(client, message, msg_id, "Cancelled.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]]
                    )
                )
            else:
                await edit_or_reply(client, message, msg_id, "⏳ **Still Waiting...**\n\nPlease add me as an Admin to the channel, or type `/cancel` to abort.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
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
                                    "❌ Cancel", callback_data="admin_main"
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
                                "← Back to Admin Panel", callback_data="admin_main"
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
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]])
                    )
                    return
            else:
                try:
                    val_num = int(float(val_lower.replace("mb", "").strip()))
                except ValueError:
                    await edit_or_reply(client, message, msg_id, "❌ Invalid number format. Try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]])
                    )
                    return

            await db.update_public_config("daily_egress_mb", val_num)
            await edit_or_reply(client, message, msg_id, f"✅ **Success!**\n\nThe Daily Egress Limit for the **Free Plan** has been updated to **{val_num} MB**.\n\nChanges have been saved and applied globally.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← Back to Plan Settings", callback_data="admin_edit_plan_free"
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
                                    "❌ Cancel", callback_data="admin_main"
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
                                "← Back to Plan Settings", callback_data="admin_edit_plan_free"
                            )
                        ]
                    ]
                ),
            )

        admin_sessions.pop(user_id, None)
        return

    if isinstance(state, str) and state.startswith("awaiting_premium_"):
        parts = state.replace("awaiting_premium_", "").split("_")
        if len(parts) >= 2 and parts[0] in ["standard", "deluxe"]:
            plan_name = parts[0]
            field = parts[1]
            val = message.text.strip() if message.text else ""

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})

            if field == "price":
                try:
                    float_val = float(val.replace(",", "."))
                except ValueError:
                    await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
                    )
                    return
                currency = state_obj.get("currency", "USD") if isinstance(state_obj, dict) else "USD"
                formatted_price = f"{float_val:g} {currency}"
                plan_settings["price_string"] = formatted_price
                await db.update_public_config(plan_key, plan_settings)
                await edit_or_reply(client, message, msg_id, f"✅ {plan_name.capitalize()} fiat price updated to `{formatted_price}`.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")]])
                )
                admin_sessions.pop(user_id, None)
                return

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
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
                            )
                            return
                    else:
                        try:
                            val_num = int(float(val_lower.replace("mb", "").strip()))
                        except ValueError:
                            await edit_or_reply(client, message, msg_id, "❌ Invalid number format. Try again.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
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

            back_btn_cb = f"admin_edit_plan_{plan_name}"

            await edit_or_reply(client, message, msg_id, f"✅ **Success!**\n\nThe {field.capitalize()} Limit for the **{plan_name.capitalize()} Plan** has been successfully updated to **{val_num}**.\n\nChanges have been saved and applied globally.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=back_btn_cb)]])
            )
            admin_sessions.pop(user_id, None)
            return

    if isinstance(state, dict) and state.get("state", "").startswith("awaiting_premium_"):
        parts = state["state"].replace("awaiting_premium_", "").split("_")
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
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
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
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")]])
                )
                admin_sessions.pop(user_id, None)
                return

    if state == "awaiting_trial_days":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_premium_settings")]])
            )
            return
        await db.update_public_config("premium_trial_days", int(val))
        await edit_or_reply(client, message, msg_id, f"✅ Premium trial duration updated to `{val}` days.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Premium Settings", callback_data="admin_premium_settings")]])
        )
        admin_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_fs_"):
        val = message.text.strip() if message.text else ""
        if val == "/cancel":
            admin_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]]))
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
        return

    if state.startswith("awaiting_template_"):
        field = state.split("_")[-1]
        new_template = message.text
        await db.update_template(field, new_template)
        if field == "caption":
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Templates", callback_data="admin_templates_menu")]]
            )
        else:
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back to Metadata Templates", callback_data="admin_templates"
                        )
                    ]
                ]
            )
        await edit_or_reply(client, message, msg_id, f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)
    elif state.startswith("awaiting_fn_template_"):
        field = state.replace("awaiting_fn_template_", "")
        new_template = message.text
        await db.update_filename_template(field, new_template)
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "← Back to Filename Templates",
                        callback_data="admin_filename_templates",
                    )
                ]
            ]
        )
        await edit_or_reply(client, message, msg_id, f"✅ Filename template for **{field.capitalize()}** updated to:\n`{new_template}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)
    elif state == "awaiting_admin_channel":
        new_channel = message.text
        await db.update_channel(new_channel, None)

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_channel")]]
        )
        await edit_or_reply(client, message, msg_id, f"✅ Global channel variable updated to:\n`{new_channel}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)

    else:
        raise ContinuePropagation

# admin_dashboard_overview_cb / admin_dashboard_top_cb /
# admin_dashboard_daily_cb moved to plugins/admin/dashboard.py

# admin_lookup_user / show_user_lookup / admin_block_user_cb /
# admin_unblock_user_cb / admin_reset_quota_cb / admin_prompt_lookup_cb /
# admin_handle_user_lookup_text moved to plugins/admin/users_mod.py

# noop_cb moved to plugins/admin/noop.py

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
