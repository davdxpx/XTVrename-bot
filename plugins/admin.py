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

logger = get_logger("plugins.admin")
admin_sessions = {}

# === Helper Functions ===
def get_admin_main_menu(pro_session, public_mode):
    pro_btn_text = "🚀 Manage 𝕏TV Pro™" if pro_session else "🚀 Setup 𝕏TV Pro™"

    keyboard = []

    keyboard.append(
        [InlineKeyboardButton("👤 User Management", callback_data="admin_users_menu")]
    )

    if public_mode:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🌐 Public Mode Settings", callback_data="admin_public_settings"
                ),
                InlineKeyboardButton(
                    "🔒 Access & Limits", callback_data="admin_access_limits"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "💳 Manage Payments", callback_data="admin_payments_menu"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📺 Dumb Channels", callback_data="admin_dumb_channels"
                ),
                InlineKeyboardButton(
                    "⏱ Edit Dumb Channel Timeout", callback_data="admin_dumb_timeout"
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
                    "🖼 Manage Thumbnail", callback_data="admin_thumb_menu"
                ),
                InlineKeyboardButton(
                    "📋 Templates", callback_data="admin_templates_menu"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📺 Dumb Channels", callback_data="admin_dumb_channels"
                ),
                InlineKeyboardButton("⚙️ General Settings", callback_data="admin_general_settings_menu"),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📊 Usage Dashboard", callback_data="admin_usage_dashboard"
                ),
                InlineKeyboardButton("👀 View Settings", callback_data="admin_view"),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔒 Access & Limits", callback_data="admin_access_limits"
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
                    callback_data="admin_filename_templates",
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit Caption Template", callback_data="admin_caption"
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit Metadata Templates", callback_data="admin_templates"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔤 Preferred Separator", callback_data="admin_pref_separator"
                )
            ],
            [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
        ]
    )

async def get_admin_access_limits_menu():
    buttons = []
    if Config.PUBLIC_MODE:
        buttons.append(
            [
                InlineKeyboardButton(
                    "📢 Force-Sub Settings", callback_data="admin_force_sub_menu"
                )
            ]
        )

        pro_session = await db.get_pro_session()
        if pro_session:
            buttons.append(
                [
                    InlineKeyboardButton(
                        "🚀 XTV Pro 4GB Access", callback_data="admin_4gb_access"
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    "📄 Set Daily Per-User File Limit", callback_data="admin_daily_files"
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    "💎 Premium Settings", callback_data="admin_premium_settings"
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "🌍 Set Global Daily Egress Limit", callback_data="admin_global_daily_egress"
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                "⚙️ Feature Toggles", callback_data="admin_feature_toggles"
            )
        ]
    )
    buttons.append([InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")])
    return InlineKeyboardMarkup(buttons)

def get_admin_public_settings_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🤖 Edit Bot Name", callback_data="admin_public_bot_name"
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 Edit Community Name",
                    callback_data="admin_public_community_name",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔗 Edit Support Contact",
                    callback_data="admin_public_support_contact",
                )
            ],
            [
                InlineKeyboardButton(
                    "👀 View Public Config", callback_data="admin_public_view"
                )
            ],
            [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
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
            "🛠 **Public Mode Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for Public Mode.\n"
            "These settings apply globally to the bot, such as branding and rate limits.\n"
            "*(Use /settings to configure your personal renaming templates)*"
        )
    else:
        text = (
            "🛠 **𝕏TV Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for the 𝕏TV Rename Bot.\n"
            "These settings affect all files processed by the bot."
        )

    await message.reply_text(
        text, reply_markup=get_admin_main_menu(pro_session, Config.PUBLIC_MODE)
    )

from pyrogram import ContinuePropagation
from utils.logger import debug

debug("✅ Loaded handler: admin_callback")

@Client.on_callback_query(
    filters.regex(
        r"^(admin_(?!usage_dashboard|dashboard_|block_|unblock_|reset_quota_|broadcast|users_menu|user_search_start)|edit_template_|edit_fn_template_|prompt_admin_|prompt_public_|prompt_daily_|prompt_global_|prompt_fn_template_|prompt_template_|prompt_premium_|prompt_trial_|dumb_(?!user_)|admin_set_lang_|set_admin_workflow_|admin_pay_|prompt_pay_|set_4gb_access_|admin_prem_cur_)"
    )
)
async def admin_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data
    debug(f"Admin callback: {data} from user {user_id}")

    if data.startswith("dumb_"):
        if data == "dumb_menu":
            channels = await db.get_dumb_channels()
            default_ch = await db.get_default_dumb_channel()
            text = "📺 **Manage Dumb Channels**\n\n"
            text += "These channels can be used to forward processed files automatically.\n\n"
            text += "**Configured Channels:**\n"
            if not channels:
                text += "- None\n"
            else:
                for ch_id, ch_name in channels.items():
                    marker = " (Default)" if str(ch_id) == default_ch else ""
                    text += f"- {ch_name} `{ch_id}`{marker}\n"

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "➕ Add New Dumb Channel", callback_data="dumb_add"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "➖ Remove Dumb Channel",
                                    callback_data="dumb_remove",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "⭐ Set Default", callback_data="dumb_set_default"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="admin_main"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return


    if data == "admin_payments_menu":
        config = await db.get_public_config()
        pm = config.get("payment_methods", {})

        try:
            await callback_query.message.edit_text(
                "💳 **Manage Payments**\n\nManage payment methods, discounts, and view pending transactions.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Payment Settings", callback_data="admin_pay_settings")],
                    [InlineKeyboardButton("📉 Discount Settings", callback_data="admin_pay_discounts")],
                    [InlineKeyboardButton("📬 Pending Approvals Queue", callback_data="admin_pay_queue")],
                    [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_pay_settings":
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
                    [InlineKeyboardButton(f"{emoji(pp)} PayPal", callback_data="admin_pay_toggle_paypal"),
                     InlineKeyboardButton("✏️ Edit Email", callback_data="prompt_pay_paypal")],
                    [InlineKeyboardButton(f"{emoji(up)} UPI", callback_data="admin_pay_toggle_upi"),
                     InlineKeyboardButton("✏️ Edit ID", callback_data="prompt_pay_upi")],
                    [InlineKeyboardButton(f"{emoji(cr)} Crypto", callback_data="admin_pay_toggle_crypto"),
                     InlineKeyboardButton("✏️ Edit Addresses", callback_data="admin_pay_crypto_menu")],
                    [InlineKeyboardButton(f"{emoji(st)} Telegram Stars", callback_data="admin_pay_toggle_stars")],
                    [InlineKeyboardButton("← Back", callback_data="admin_payments_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_pay_crypto_menu":
        try:
            await callback_query.message.edit_text(
                "🪙 **Crypto Address Settings**\n\nSelect which cryptocurrency address you want to edit:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("USDT (TRC20/ERC20)", callback_data="prompt_pay_crypto_usdt")],
                    [InlineKeyboardButton("BTC (Bitcoin)", callback_data="prompt_pay_crypto_btc")],
                    [InlineKeyboardButton("ETH (Ethereum)", callback_data="prompt_pay_crypto_eth")],
                    [InlineKeyboardButton("← Back", callback_data="admin_pay_settings")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("admin_pay_toggle_"):
        method = data.replace("admin_pay_toggle_", "")
        config = await db.get_public_config()
        pm = config.get("payment_methods", {})
        current = pm.get(f"{method}_enabled", False)
        pm[f"{method}_enabled"] = not current
        await db.update_public_config("payment_methods", pm)
        callback_query.data = "admin_pay_settings"
        await admin_callback(client, callback_query)
        return

    if data.startswith("prompt_pay_"):
        method = data.replace("prompt_pay_", "")
        admin_sessions[user_id] = f"awaiting_pay_{method}"

        cancel_data = "admin_pay_settings"
        if method.startswith("crypto_"):
            cancel_data = "admin_pay_crypto_menu"

        try:
            await callback_query.message.edit_text(
                f"✏️ **Edit {method.replace('_', ' ').upper()} Details**\n\nPlease send the new address/ID/email:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)]])
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_pay_discounts":
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
                    [InlineKeyboardButton("✏️ Edit 3-Month Discount", callback_data="prompt_pay_disc_3")],
                    [InlineKeyboardButton("✏️ Edit 12-Month Discount", callback_data="prompt_pay_disc_12")],
                    [InlineKeyboardButton("← Back", callback_data="admin_payments_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("prompt_pay_disc_"):
        months = data.replace("prompt_pay_disc_", "")
        admin_sessions[user_id] = f"awaiting_pay_disc_{months}"
        try:
            await callback_query.message.edit_text(
                f"📉 **Edit {months}-Month Discount**\n\nPlease send the new discount percentage (e.g. `10` or `15`):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_pay_discounts")]])
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_pay_queue":
        pending = await db.get_all_pending_payments()
        if not pending:
            try:
                await callback_query.message.edit_text(
                    "📬 **Pending Approvals Queue**\n\nNo pending payments found.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_payments_menu")]])
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
                    [InlineKeyboardButton("✅ Approve", callback_data=f"admin_pay_approve_{p['_id']}"),
                     InlineKeyboardButton("❌ Reject", callback_data=f"admin_pay_reject_{p['_id']}")],
                    [InlineKeyboardButton("⏭ Skip", callback_data="admin_pay_queue")],
                    [InlineKeyboardButton("← Back", callback_data="admin_payments_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("admin_pay_approve_"):
        payment_id = data.replace("admin_pay_approve_", "")
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
            except:
                pass

            await callback_query.answer("Payment Approved & User Upgraded!", show_alert=True)

        callback_query.data = "admin_pay_queue"
        await admin_callback(client, callback_query)
        return

    if data.startswith("admin_pay_reject_"):
        payment_id = data.replace("admin_pay_reject_", "")
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
            except:
                pass

            await callback_query.answer("Payment Rejected.", show_alert=True)

        callback_query.data = "admin_pay_queue"
        await admin_callback(client, callback_query)
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
            "Click on a feature below to toggle its state globally:"
        )

        buttons = [
            [InlineKeyboardButton(f"{emoji(conv_en)} File Converter", callback_data="admin_toggle_file_converter")],
            [InlineKeyboardButton(f"{emoji(sub_en)} Subtitle Extractor", callback_data="admin_toggle_subtitle_extractor")],
            [InlineKeyboardButton(f"{emoji(wm_en)} Image Watermarker", callback_data="admin_toggle_watermarker")],
            [InlineKeyboardButton(f"{emoji(audio_en)} Audio Editor", callback_data="admin_toggle_audio_editor")],
            [InlineKeyboardButton("← Back", callback_data="admin_access_limits")]
        ]

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data == "admin_4gb_access" and Config.PUBLIC_MODE:
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
                    [InlineKeyboardButton(f"{'✅ ' if current_val == 'all' else ''}Everyone", callback_data="set_4gb_access_all")],
                    [InlineKeyboardButton(f"{'✅ ' if current_val == 'premium_all' else ''}All Premium Users", callback_data="set_4gb_access_premium_all")],
                    [InlineKeyboardButton(f"{'✅ ' if current_val == 'premium_deluxe' else ''}Premium Deluxe Only", callback_data="set_4gb_access_premium_deluxe")],
                    [InlineKeyboardButton("← Back", callback_data="admin_access_limits")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("set_4gb_access_") and Config.PUBLIC_MODE:
        access_level = data.replace("set_4gb_access_", "")
        await db.update_public_config("xtv_pro_4gb_access", access_level)
        await callback_query.answer("4GB Access updated!", show_alert=True)
        callback_query.data = "admin_4gb_access"
        await admin_callback(client, callback_query)
        return

    if data.startswith("admin_toggle_"):
        feature = data.replace("admin_toggle_", "")
        toggles = await db.get_feature_toggles()
        current_state = toggles.get(feature, True)
        new_state = not current_state
        await db.update_feature_toggle(feature, new_state)
        await callback_query.answer(f"{'Enabled' if new_state else 'Disabled'} feature.", show_alert=True)
        # Re-render the menu
        callback_query.data = "admin_feature_toggles"
        await admin_callback(client, callback_query)
        return

    if data == "admin_global_daily_egress":
        current_val = await db.get_global_daily_egress_limit()
        try:
            await callback_query.message.edit_text(
                f"🌍 **Edit Global Daily Egress Limit**\n\nCurrent: `{current_val}` MB\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_global_daily_egress"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_access_limits"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if Config.PUBLIC_MODE and (
        data.startswith("admin_premium_") or data.startswith("prompt_premium_") or data.startswith("prompt_trial_") or data.startswith("admin_trial_")
    ):
        if data == "admin_premium_settings":
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

            buttons = [
                [InlineKeyboardButton(f"Toggle System: {status_emoji}", callback_data="admin_premium_toggle")]
            ]

            if enabled:
                buttons.append([InlineKeyboardButton(f"Toggle Deluxe Plan: {deluxe_status_emoji}", callback_data="admin_premium_deluxe_toggle")])
                buttons.append([InlineKeyboardButton("⚙️ Configure Standard Plan", callback_data="admin_premium_plan_standard")])
                if deluxe_enabled:
                    buttons.append([InlineKeyboardButton("⚙️ Configure Deluxe Plan", callback_data="admin_premium_plan_deluxe")])

                buttons.append([InlineKeyboardButton(f"Toggle Trial System: {trial_status_emoji}", callback_data="admin_trial_toggle")])
                if trial_enabled:
                    buttons.append([InlineKeyboardButton("⏱ Edit Trial Duration", callback_data="prompt_trial_days")])

            buttons.append([InlineKeyboardButton("← Back", callback_data="admin_access_limits")])

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_premium_toggle":
            config = await db.get_public_config()
            enabled = config.get("premium_system_enabled", False)
            await db.update_public_config("premium_system_enabled", not enabled)
            await callback_query.answer("Toggled Premium System", show_alert=True)
            callback_query.data = "admin_premium_settings"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_trial_toggle":
            config = await db.get_public_config()
            enabled = config.get("premium_trial_enabled", False)
            await db.update_public_config("premium_trial_enabled", not enabled)
            await callback_query.answer("Toggled Premium Trial System", show_alert=True)
            callback_query.data = "admin_premium_settings"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_premium_deluxe_toggle":
            config = await db.get_public_config()
            enabled = config.get("premium_deluxe_enabled", False)
            await db.update_public_config("premium_deluxe_enabled", not enabled)
            await callback_query.answer("Toggled Premium Deluxe System", show_alert=True)
            callback_query.data = "admin_premium_settings"
            await admin_callback(client, callback_query)
            return

        elif data.startswith("admin_premium_plan_"):
            plan_name = data.replace("admin_premium_plan_", "")
            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})

            egress = plan_settings.get("daily_egress_mb", 0)
            files = plan_settings.get("daily_file_count", 0)
            price = plan_settings.get("price_string", "0 USD")
            stars_price = plan_settings.get("stars_price", 0)

            text = (
                f"💎 **{plan_name.capitalize()} Plan Settings**\n\n"
                f"📦 Daily Egress: `{egress}` MB\n"
                f"📄 Daily Files: `{files}` files\n"
                f"*(0 means unlimited)*\n\n"
                f"💵 Price (Fiat): `{price}`\n"
                f"⭐ Price (Stars): `{stars_price}` Stars\n\n"
                "Select a setting to edit:"
            )

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("📦 Edit Egress Limit", callback_data=f"prompt_premium_{plan_name}_egress"),
                            InlineKeyboardButton("📄 Edit File Limit", callback_data=f"prompt_premium_{plan_name}_files")
                        ],
                        [
                            InlineKeyboardButton("💵 Edit Fiat Price", callback_data=f"prompt_premium_{plan_name}_price"),
                            InlineKeyboardButton("⭐ Edit Stars Price", callback_data=f"prompt_premium_{plan_name}_stars")
                        ],
                        [InlineKeyboardButton("⚙️ Configure Features", callback_data=f"admin_premium_features_{plan_name}")],
                        [InlineKeyboardButton("← Back", callback_data="admin_premium_settings")]
                    ])
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("admin_premium_features_"):
            plan_name = data.replace("admin_premium_features_", "")
            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            global_toggles = await db.get_feature_toggles()

            def emoji(state): return "✅" if state else "❌"

            pq = features.get("priority_queue", False)

            buttons = [
                [InlineKeyboardButton(f"{emoji(pq)} Priority Queue", callback_data=f"admin_premium_feat_{plan_name}_priority_queue")]
            ]

            # Only show these if they are disabled globally, since if they are enabled globally, everyone gets them anyway.
            if not global_toggles.get("file_converter", True):
                fc = features.get("file_converter", False)
                buttons.append([InlineKeyboardButton(f"{emoji(fc)} File Converter", callback_data=f"admin_premium_feat_{plan_name}_file_converter")])

            if not global_toggles.get("audio_editor", True):
                ae = features.get("audio_editor", False)
                buttons.append([InlineKeyboardButton(f"{emoji(ae)} Audio Editor", callback_data=f"admin_premium_feat_{plan_name}_audio_editor")])

            if not global_toggles.get("watermarker", True):
                wm = features.get("watermarker", False)
                buttons.append([InlineKeyboardButton(f"{emoji(wm)} Watermarker", callback_data=f"admin_premium_feat_{plan_name}_watermarker")])

            if not global_toggles.get("subtitle_extractor", True):
                se = features.get("subtitle_extractor", False)
                buttons.append([InlineKeyboardButton(f"{emoji(se)} Subtitle Extractor", callback_data=f"admin_premium_feat_{plan_name}_subtitle_extractor")])

            buttons.append([InlineKeyboardButton("← Back", callback_data=f"admin_premium_plan_{plan_name}")])

            text = f"⚙️ **{plan_name.capitalize()} Plan Features**\n\nToggle which features users on this plan can access (overrides global toggles):"

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("admin_premium_feat_"):
            parts = data.replace("admin_premium_feat_", "").split("_", 1)
            plan_name = parts[0]
            feature_name = parts[1]

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})

            current = features.get(feature_name, False)
            features[feature_name] = not current
            plan_settings["features"] = features

            await db.update_public_config(plan_key, plan_settings)

            callback_query.data = f"admin_premium_features_{plan_name}"
            await admin_callback(client, callback_query)
            return

        elif data.startswith("prompt_premium_"):
            parts = data.replace("prompt_premium_", "").split("_")
            if len(parts) >= 2 and parts[0] in ["standard", "deluxe"]:
                plan_name = parts[0]
                field = parts[1]

                if field == "price":
                    try:
                        await callback_query.message.edit_text(
                            "💵 **Select Currency**\n\nFirst, select the fiat currency you want to use for this plan:",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("USD ($)", callback_data=f"admin_prem_cur_{plan_name}_USD"),
                                 InlineKeyboardButton("EUR (€)", callback_data=f"admin_prem_cur_{plan_name}_EUR"),
                                 InlineKeyboardButton("GBP (£)", callback_data=f"admin_prem_cur_{plan_name}_GBP")],
                                [InlineKeyboardButton("INR (₹)", callback_data=f"admin_prem_cur_{plan_name}_INR"),
                                 InlineKeyboardButton("RUB (₽)", callback_data=f"admin_prem_cur_{plan_name}_RUB"),
                                 InlineKeyboardButton("BRL (R$)", callback_data=f"admin_prem_cur_{plan_name}_BRL")],
                                [InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]
                            ])
                        )
                    except MessageNotModified:
                        pass
                    return

                admin_sessions[user_id] = f"awaiting_premium_{plan_name}_{field}"

                prompts = {
                    "egress": "📦 **Send the new daily egress limit in MB (e.g., 2048).**\nSend `0` to disable.",
                    "files": "📄 **Send the new daily file limit.**\nSend `0` to disable.",
                }

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
                    except:
                        star_prompt = "⭐ **Send the new Telegram Stars price (integer).**"

                    prompts["stars"] = star_prompt

                try:
                    await callback_query.message.edit_text(
                        prompts.get(field, "Enter new value:"),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                    )
                except MessageNotModified:
                    pass
                return

        elif data.startswith("admin_prem_cur_"):
            parts = data.replace("admin_prem_cur_", "").split("_")
            plan_name = parts[0]
            currency = parts[1]

            admin_sessions[user_id] = {
                "state": f"awaiting_premium_{plan_name}_price",
                "currency": currency
            }

            try:
                await callback_query.message.edit_text(
                    f"💵 **Set Price in {currency}**\n\nPlease enter the numeric amount (e.g., `9.99` or `500`):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "prompt_trial_days":
            admin_sessions[user_id] = "awaiting_trial_days"
            try:
                await callback_query.message.edit_text(
                    "⏱ **Send the new PREMIUM TRIAL duration in days (e.g., 7).**\nSend `0` to disable.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_premium_settings")]])
                )
            except MessageNotModified:
                pass
            return

    if data == "prompt_global_daily_egress":
        admin_sessions[user_id] = "awaiting_global_daily_egress"
        try:
            await callback_query.message.edit_text(
                "🌍 **Send the new global daily egress limit in MB (e.g., 102400 for 100GB).**\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_access_limits")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "dumb_add":
        admin_sessions[user_id] = "awaiting_dumb_add"
        try:
            await callback_query.message.edit_text(
                "➕ **Add Dumb Channel**\n\n"
                "Please add me as an Administrator in the desired channel.\n"
                "Then, forward any message from that channel to me, OR send the Channel ID (e.g. `-100...`) or Public Username.\n\n"
                "*(Send `disable` to cancel)*",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]]
                ),
            )
        except MessageNotModified:
            pass
        return
    elif data == "dumb_remove":
        channels = await db.get_dumb_channels()
        if not channels:
            await callback_query.answer("No channels configured.", show_alert=True)
            return
        buttons = []
        for ch_id, ch_name in channels.items():
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"❌ {ch_name}", callback_data=f"dumb_del_{ch_id}"
                    )
                ]
            )
        buttons.append([InlineKeyboardButton("← Back", callback_data="dumb_menu")])
        try:
            await callback_query.message.edit_text(
                "Select a channel to remove:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except MessageNotModified:
            pass
        return
    elif data.startswith("dumb_del_"):
        ch_id = data.replace("dumb_del_", "")
        await db.remove_dumb_channel(ch_id)
        await callback_query.answer("Channel removed.", show_alert=True)
        callback_query.data = "dumb_menu"
        await admin_callback(client, callback_query)
        return
    elif data == "dumb_set_default":
        channels = await db.get_dumb_channels()
        if not channels:
            await callback_query.answer("No channels configured.", show_alert=True)
            return
        buttons = []
        for ch_id, ch_name in channels.items():
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"⭐ {ch_name}", callback_data=f"dumb_def_{ch_id}"
                    )
                ]
            )
        buttons.append([InlineKeyboardButton("← Back", callback_data="dumb_menu")])
        try:
            await callback_query.message.edit_text(
                "Select default auto-detect channel:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except MessageNotModified:
            pass
        return
    elif data.startswith("dumb_def_"):
        ch_id = data.replace("dumb_def_", "")
        await db.set_default_dumb_channel(ch_id)
        await callback_query.answer("Default channel set.", show_alert=True)
        callback_query.data = "dumb_menu"
        await admin_callback(client, callback_query)
        return

    if data == "admin_dumb_channels":
        callback_query.data = "dumb_menu"
        await admin_callback(client, callback_query)
        return

    if data == "admin_dumb_timeout":
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
                                "✏️ Change", callback_data="prompt_admin_dumb_timeout"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_main"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "prompt_admin_dumb_timeout":
        admin_sessions[user_id] = "awaiting_dumb_timeout"
        try:
            await callback_query.message.edit_text(
                "⏱ **Send the new timeout in seconds (e.g., 3600 for 1 hour):**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    if Config.PUBLIC_MODE and (
        data.startswith("admin_public_")
        or data.startswith("admin_daily_")
        or data.startswith("admin_force_sub_")
        or data.startswith("admin_fs_")
        or data.startswith("admin_premium_")
        or data.startswith("prompt_premium_")
    ):
        if data == "admin_public_view":
            config = await db.get_public_config()
            text = "👀 **Public Mode Config**\n\n"
            text += f"**Bot Name:** {config.get('bot_name', 'Not set')}\n"
            text += f"**Community Name:** {config.get('community_name', 'Not set')}\n"
            text += f"**Support Contact:** {config.get('support_contact', 'Not set')}\n"
            text += (
                f"**Force-Sub Channel:** {config.get('force_sub_channel', 'Not set')}\n"
            )
            text += f"**Daily Egress Limit:** {config.get('daily_egress_mb', 0)} MB\n"
            text += f"**Daily File Limit:** {config.get('daily_file_count', 0)} files\n"

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="admin_public_settings"
                                )
                            ]
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_public_bot_name":
            config = await db.get_public_config()
            current_val = config.get("bot_name", "Not set")
            try:
                await callback_query.message.edit_text(
                    f"🤖 **Edit Bot Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="prompt_public_bot_name"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="admin_public_settings"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_public_community_name":
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
                                    callback_data="prompt_public_community_name",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="admin_public_settings"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_public_support_contact":
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
                                    callback_data="prompt_public_support_contact",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="admin_public_settings"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_force_sub_menu":
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
                [InlineKeyboardButton("➕ Add Channel", callback_data="admin_fs_add_channel"),
                 InlineKeyboardButton("📋 Manage Channels", callback_data="admin_fs_manage_channels")],
                [InlineKeyboardButton("🖼 Set Banner", callback_data="admin_fs_set_banner")]
            ]

            if config.get("force_sub_banner_file_id"):
                keyboard[-1].append(InlineKeyboardButton("🗑 Remove Banner", callback_data="admin_fs_rem_banner"))

            keyboard.append([
                InlineKeyboardButton("✏️ Edit Message", callback_data="admin_fs_edit_msg"),
                InlineKeyboardButton("↩️ Reset Message", callback_data="admin_fs_reset_msg")
            ])
            keyboard.append([
                InlineKeyboardButton("🔘 Edit Button", callback_data="admin_fs_edit_btn"),
                InlineKeyboardButton("🎉 Edit Welcome Msg", callback_data="admin_fs_edit_welcome")
            ])
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_access_limits")])

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_fs_add_channel":
            admin_sessions[user_id] = "awaiting_fs_add_channel"
            try:
                await callback_query.message.edit_text(
                    "📢 **Add Force-Sub Channel**\n\n"
                    "⏳ **I am waiting...**\n\n"
                    "Simply **add me as an Administrator** to your desired channel right now!\n"
                    "Make sure I have the 'Invite Users via Link' permission.\n\n"
                    "I will automatically detect the channel and set it up instantly.\n\n"
                    "*Send /cancel to cancel.*",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                    )
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_fs_toggle":
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
                await callback_query.answer("Please add a channel to enable Force-Sub.", show_alert=True)

            callback_query.data = "admin_force_sub_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_fs_manage_channels":
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")
            legacy_link = config.get("force_sub_link")
            legacy_username = config.get("force_sub_username")

            if not channels and legacy_ch:
                channels = [{"id": legacy_ch, "link": legacy_link, "username": legacy_username, "title": "Legacy Channel"}]

            if not channels:
                await callback_query.answer("No channels configured.", show_alert=True)
                return

            keyboard = []
            for i, ch in enumerate(channels):
                title = ch.get("title", f"Channel {i+1}")
                keyboard.append([InlineKeyboardButton(f"❌ Remove {title}", callback_data=f"admin_fs_rem_ch_{i}")])

            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_force_sub_menu")])

            try:
                await callback_query.message.edit_text(
                    "📋 **Manage Channels**\n\nSelect a channel to remove:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("admin_fs_rem_ch_"):
            idx = int(data.replace("admin_fs_rem_ch_", ""))
            config = await db.get_public_config()
            channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")

            if not channels and legacy_ch:
                channels = [{"id": legacy_ch, "link": config.get("force_sub_link"), "username": config.get("force_sub_username"), "title": "Legacy Channel"}]

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

            callback_query.data = "admin_fs_manage_channels"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_fs_set_banner":
            admin_sessions[user_id] = "awaiting_fs_banner"
            try:
                await callback_query.message.edit_text(
                    "🖼 **Send me a photo** to use as the Force-Sub gate banner.\n\nSend /cancel to keep the current one.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_fs_rem_banner":
            await db.update_public_config("force_sub_banner_file_id", None)
            await callback_query.answer("Banner removed.", show_alert=True)
            callback_query.data = "admin_force_sub_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_fs_edit_msg":
            config = await db.get_public_config()
            current_msg = config.get("force_sub_message_text")

            text = "✏️ **Edit Gate Message**\n\nCurrent:\n"
            if current_msg:
                text += f"`{current_msg}`\n\n"
            else:
                text += "*Default Message*\n\n"

            text += "Send your new gate message. You can use `{channel}`, `{bot_name}`, `{community}`.\nSend /cancel to keep the current one."

            admin_sessions[user_id] = "awaiting_fs_msg"
            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_fs_reset_msg":
            await db.update_public_config("force_sub_message_text", None)
            await callback_query.answer("Message reset to default.", show_alert=True)
            callback_query.data = "admin_force_sub_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_fs_edit_btn":
            try:
                await callback_query.message.edit_text(
                    "🔘 **Edit Button**\n\nSelect what to edit:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔘 Edit Label", callback_data="admin_fs_btn_label"),
                         InlineKeyboardButton("😀 Edit Emoji", callback_data="admin_fs_btn_emoji")],
                        [InlineKeyboardButton("↩️ Reset Button", callback_data="admin_fs_btn_reset")],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_force_sub_menu")]
                    ])
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_fs_btn_label":
            admin_sessions[user_id] = "awaiting_fs_btn_label"
            try:
                await callback_query.message.edit_text(
                    "🔘 **Edit Button Label**\n\nSend the new label text (without emoji):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_fs_edit_btn")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_fs_btn_emoji":
            admin_sessions[user_id] = "awaiting_fs_btn_emoji"
            try:
                await callback_query.message.edit_text(
                    "😀 **Edit Button Emoji**\n\nSend a single emoji character:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_fs_edit_btn")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_fs_btn_reset":
            await db.update_public_config("force_sub_button_label", None)
            await db.update_public_config("force_sub_button_emoji", None)
            await callback_query.answer("Button reset to default.", show_alert=True)
            callback_query.data = "admin_force_sub_menu"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_fs_edit_welcome":
            admin_sessions[user_id] = "awaiting_fs_welcome"
            config = await db.get_public_config()
            current_msg = config.get("force_sub_welcome_text", "✅ Welcome aboard! You're all set. Send your file and let's go.")
            try:
                await callback_query.message.edit_text(
                    f"🎉 **Edit Welcome Message**\n\nCurrent:\n`{current_msg}`\n\nSend the new welcome message text:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]])
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_daily_egress":
            config = await db.get_public_config()
            current_val = config.get("daily_egress_mb", 0)
            try:
                await callback_query.message.edit_text(
                    f"📦 **Edit Daily Egress Limit**\n\nCurrent: `{current_val}` MB\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="prompt_daily_egress"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="admin_access_limits"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data == "admin_daily_files":
            config = await db.get_public_config()
            current_val = config.get("daily_file_count", 0)
            try:
                await callback_query.message.edit_text(
                    f"📄 **Edit Daily File Limit**\n\nCurrent: `{current_val}` files\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="prompt_daily_files"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back", callback_data="admin_access_limits"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

    if Config.PUBLIC_MODE and (
        data.startswith("prompt_public_") or data.startswith("prompt_daily_")
    ):
        field = data.replace("prompt_public_", "").replace("prompt_daily_", "daily_")
        admin_sessions[user_id] = f"awaiting_public_{field}"

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
                "*Send /cancel to cancel.*"
            )
        elif field == "daily_egress":
            text = "📦 **Send the new daily egress limit in MB (e.g., 2048).**\nSend `0` to disable."
        elif field == "daily_files":
            text = "📄 **Send the new daily file limit.**\nSend `0` to disable."
        else:
            text = "Send the new value:"

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="admin_public_settings"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return
    if data == "admin_thumb_menu":
        try:
            await callback_query.message.edit_text(
                "🖼 **Manage Thumbnail**\n\n" "Select an action:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "👀 View Current", callback_data="admin_thumb_view"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📤 Set Default", callback_data="admin_thumb_set"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_main"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_thumb_view":
        thumb_bin, _ = await db.get_thumbnail()
        if thumb_bin:
            try:
                f = io.BytesIO(thumb_bin)
                f.name = "thumbnail.jpg"
                await client.send_photo(
                    user_id, f, caption="**Current Default Thumbnail**"
                )
                await callback_query.message.edit_text(
                    "🖼 **Manage Thumbnail**\n\n" "Thumbnail sent above.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "👀 View Current", callback_data="admin_thumb_view"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "📤 Set Default", callback_data="admin_thumb_set"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "🔙 Back", callback_data="admin_main"
                                )
                            ],
                        ]
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to send thumbnail: {e}")
                await callback_query.answer("Error sending thumbnail!", show_alert=True)
        else:
            await callback_query.answer("No thumbnail set in DB!", show_alert=True)
    elif data == "admin_thumb_set":
        try:
            await callback_query.message.edit_text(
                "📤 **Set Default Thumbnail**\n\n"
                "Click below to upload a new thumbnail. "
                "This will be embedded into every video processed.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📤 Upload New", callback_data="prompt_admin_thumb_set"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_thumb_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "prompt_admin_thumb_set":
        admin_sessions[user_id] = "awaiting_thumb"
        try:
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
        except MessageNotModified:
            pass
    elif data == "admin_templates_menu":
        try:
            await callback_query.message.edit_text(
                "📋 **Templates Menu**\n\n" "Select a template category to edit:",
                reply_markup=get_admin_templates_menu(),
            )
        except MessageNotModified:
            pass
    elif data == "admin_access_limits":
        try:
            reply_markup = await get_admin_access_limits_menu()
            await callback_query.message.edit_text(
                "🔒 **Access & Limits Menu**\n\n" "Select a setting to edit:",
                reply_markup=reply_markup,
            )
        except MessageNotModified:
            pass
    elif data == "admin_public_settings":
        try:
            await callback_query.message.edit_text(
                "🌐 **Public Mode Settings**\n\n" "Select a setting to edit:",
                reply_markup=get_admin_public_settings_menu(),
            )
        except MessageNotModified:
            pass
    elif data == "admin_pref_separator":
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
                            InlineKeyboardButton("Underscore (_)", callback_data="admin_set_sep__"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="admin_set_sep_space"),
                        ],
                        [InlineKeyboardButton("← Back", callback_data="admin_templates_menu")],
                    ]
                )
            )
        except MessageNotModified:
            pass
    elif data.startswith("admin_set_sep_"):
        try:
            new_sep = data.split("_set_sep_")[1]
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
                            InlineKeyboardButton("Underscore (_)", callback_data="admin_set_sep__"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="admin_set_sep_space"),
                        ],
                        [InlineKeyboardButton("← Back", callback_data="admin_templates_menu")],
                    ]
                )
            )
        except MessageNotModified:
            pass
    elif data == "admin_templates":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Metadata Templates**\n\n" "Select a field to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Title", callback_data="edit_template_title"
                            ),
                            InlineKeyboardButton(
                                "Author", callback_data="edit_template_author"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "Artist", callback_data="edit_template_artist"
                            ),
                            InlineKeyboardButton(
                                "Video", callback_data="edit_template_video"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "Audio", callback_data="edit_template_audio"
                            ),
                            InlineKeyboardButton(
                                "Subtitle", callback_data="edit_template_subtitle"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_templates_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_caption":
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
                                "✏️ Change", callback_data="prompt_admin_caption"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_templates_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "prompt_admin_caption":
        admin_sessions[user_id] = "awaiting_template_caption"
        try:
            await callback_query.message.edit_text(
                "📝 **Send the new caption text:**\n\n(Use `{random}` to use the default random text generator)",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="admin_templates_menu"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_view":
        settings = await db.get_settings()
        templates = settings.get("templates", {}) if settings else {}
        has_thumb = (
            "✅ Yes" if settings and settings.get("thumbnail_binary") else "❌ No"
        )
        text = f"👀 **Current Settings**\n\n"
        text += f"**Thumbnail Set:** {has_thumb}\n\n"
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
        fn_templates = settings.get("filename_templates", {}) if settings else {}
        if fn_templates:
            for k, v in fn_templates.items():
                text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No filename templates set.\n"
        text += f"\n**Channel Variable:** `{settings.get('channel', Config.DEFAULT_CHANNEL) if settings else Config.DEFAULT_CHANNEL}`\n"
        try:
            await callback_query.message.edit_text(
                text,
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
        except MessageNotModified:
            pass
    elif data == "admin_filename_templates":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Filename Templates**\n\n" "Select media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Movies", callback_data="edit_fn_template_movies"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Series", callback_data="edit_fn_template_series"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal", callback_data="admin_fn_templates_personal"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Subtitles",
                                callback_data="admin_fn_templates_subtitles",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_templates_menu"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_fn_templates_personal":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Personal Filename Templates**\n\n"
                "Select media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Personal Files",
                                callback_data="edit_fn_template_personal_file",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal Photos",
                                callback_data="edit_fn_template_personal_photo",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal Videos",
                                callback_data="edit_fn_template_personal_video",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🔙 Back", callback_data="admin_filename_templates"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_fn_templates_subtitles":
        try:
            await callback_query.message.edit_text(
                "📝 **Edit Subtitles Filename Templates**\n\n"
                "Select media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Movies",
                                callback_data="edit_fn_template_subtitles_movies",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Series",
                                callback_data="edit_fn_template_subtitles_series",
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
                                "✏️ Change", callback_data=f"prompt_fn_template_{field}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🔙 Back", callback_data="admin_filename_templates"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("prompt_fn_template_"):
        field = data.replace("prompt_fn_template_", "")
        admin_sessions[user_id] = f"awaiting_fn_template_{field}"
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
                                "❌ Cancel", callback_data="admin_filename_templates"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_general_settings_menu":
        try:
            await callback_query.message.edit_text(
                f"⚙️ **Global General Settings**\n\n"
                "Select a setting to configure:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📢 Channel Username", callback_data="admin_general_channel"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🌍 Preferred Language", callback_data="admin_general_language"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⚙️ Workflow Mode", callback_data="admin_general_workflow"
                            )
                        ],
                        [InlineKeyboardButton("← Back", callback_data="admin_main")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "admin_general_workflow":
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
                        [InlineKeyboardButton("← Back", callback_data="admin_general_settings_menu")],
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
                        [InlineKeyboardButton("← Back", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "prompt_admin_channel":
        admin_sessions[user_id] = "awaiting_admin_channel"
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
                        [InlineKeyboardButton("← Back", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "prompt_admin_language":
        try:
            await callback_query.message.edit_text(
                "🌍 **Select global preferred language for TMDb Metadata:**\n\n"
                "*(Default is English)*",
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
                        [InlineKeyboardButton("← Back", callback_data="admin_general_settings_menu")],
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
    elif data == "admin_main":
        admin_sessions.pop(user_id, None)

        pro_session = await db.get_pro_session()

        if Config.PUBLIC_MODE:
            try:
                await callback_query.message.edit_text(
                    "🛠 **Public Mode Admin Panel** 🛠\n\n"
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
                    "Manage global settings for the 𝕏TV Rename Bot.\n"
                    "These settings affect all files processed by the bot.",
                    reply_markup=get_admin_main_menu(pro_session, Config.PUBLIC_MODE),
                )
            except MessageNotModified:
                pass

    elif data.startswith("edit_template_"):
        field = data.split("_")[-1]
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
                                "✏️ Change", callback_data=f"prompt_template_{field}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back", callback_data="admin_templates"
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data.startswith("prompt_template_"):
        field = data.replace("prompt_template_", "")
        admin_sessions[user_id] = f"awaiting_template_{field}"
        try:
            await callback_query.message.edit_text(
                f"✏️ **Send the new template text for {field.capitalize()}:**",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="admin_templates"
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass

from pyrogram import ContinuePropagation

@Client.on_message(filters.photo & filters.private, group=1)
async def handle_admin_photo(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state = admin_sessions.get(user_id)
    if state == "awaiting_fs_banner":
        try:
            file_id = message.photo.file_id
            await db.update_public_config("force_sub_banner_file_id", file_id)
            await message.reply_photo(
                file_id,
                caption="✅ Banner updated successfully! It will appear like this.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_force_sub_menu")]])
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
        await msg.edit_text(
            "✅ Thumbnail updated successfully!",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Menu", callback_data="admin_thumb_menu"
                        )
                    ]
                ]
            ),
        )
        admin_sessions.pop(user_id, None)
    except Exception as e:
        logger.error(f"Thumbnail upload failed: {e}")
        try:
            await msg.edit_text(f"❌ Error: {e}")
        except MessageNotModified:
            pass

@Client.on_message(
    (filters.text | filters.forwarded) & filters.private & ~filters.regex(r"^/"),
    group=1,
)
async def handle_admin_text(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state = admin_sessions.get(user_id)
    if not state:
        raise ContinuePropagation

    if state == "awaiting_global_daily_egress":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await message.reply_text(
                "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_access_limits")]]
                ),
            )
            return
        await db.update_global_daily_egress_limit(float(val))
        await message.reply_text(
            f"✅ Global daily egress limit updated to `{val}` MB.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back", callback_data="admin_access_limits")]]
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
            name = u.get("first_name", "Unknown")[:15]
            uname = f"(@{u.get('username')})" if u.get("username") else ""
            markup.append([InlineKeyboardButton(f"{name} {uname} ({uid})", callback_data=f"view_user|{uid}")])

        markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_users_menu")])
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

            await message.reply(f"✅ **Success!**\nUser `{uid}` has received {days} days of Premium ({plan}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Profile", callback_data=f"view_user|{uid}")]]))
            admin_sessions.pop(user_id, None)
        except ValueError:
            await message.reply("❌ Invalid number. Enter days (e.g. 30).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"view_user|{state['target_id']}")]]))
        return

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
                await message.reply_text(
                    "❌ Could not find a user with that ID or username. Please make sure the ID is correct.",
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
                clear_session(message.from_user.id)
                return

        await show_user_lookup(client, message, user_id)
        clear_session(message.from_user.id)
        return

    if state == "awaiting_dumb_timeout":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await message.reply_text(
                "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="admin_access_limits"
                            )
                        ]
                    ]
                ),
            )
            return
        await db.update_dumb_channel_timeout(int(val))
        await message.reply_text(
            f"✅ Dumb channel timeout updated to `{val}` seconds.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back", callback_data="admin_templates_menu")]]
            ),
        )
        admin_sessions.pop(user_id, None)
        return

    if state == "awaiting_dumb_add" and not Config.PUBLIC_MODE:
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            admin_sessions.pop(user_id, None)
            await message.reply_text(
                "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="dumb_menu"
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
                await message.reply_text(
                    f"❌ Error finding channel: {e}\nTry forwarding a message instead.",
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
            await message.reply_text(
                f"✅ Added Dumb Channel: **{ch_name}** (`{ch_id}`)",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="dumb_menu"
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
                await message.reply_text(
                    "❌ Invalid discount percentage. Must be a number between 0 and 99.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_pay_discounts")]])
                )
                return

            config = await db.get_public_config()
            disc = config.get("discounts", {})
            disc[f"months_{months}"] = int(val)
            await db.update_public_config("discounts", disc)

            await message.reply_text(
                f"✅ {months}-Month discount updated to `{val}%`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_pay_discounts")]])
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

            await message.reply_text(
                f"✅ {method.replace('_', ' ').upper()} details updated to `{val}`.",
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
            await message.reply_text(
                f"✅ Bot Name updated to `{val}`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "community_name":
            await db.update_public_config("community_name", val)
            await message.reply_text(
                f"✅ Community Name updated to `{val}`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "support_contact":
            await db.update_public_config("support_contact", val)
            await message.reply_text(
                f"✅ Support Contact updated to `{val}`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "force_sub":
            if val.lower() == "/cancel":
                admin_sessions.pop(user_id, None)
                await message.reply_text(
                    "Cancelled.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🔙 Back to Config", callback_data="admin_force_sub_menu")]]
                    )
                )
            else:
                await message.reply_text(
                    "⏳ **Still Waiting...**\n\nPlease add me as an Admin to the channel, or type `/cancel` to abort.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                    )
                )
            return
        elif field == "rate_limit":
            if not val.isdigit():
                await message.reply_text(
                    "❌ Invalid number. Try again.",
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
            await message.reply_text(
                f"✅ Rate limit updated to `{val}` seconds.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "daily_egress":
            if not val.isdigit():
                await message.reply_text(
                    "❌ Invalid number. Try again.",
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
            await db.update_public_config("daily_egress_mb", int(val))
            await message.reply_text(
                f"✅ Daily egress limit updated to `{val}` MB.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "daily_files":
            if not val.isdigit():
                await message.reply_text(
                    "❌ Invalid number. Try again.",
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
            await message.reply_text(
                f"✅ Daily files limit updated to `{val}` files.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
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

            if field in ["egress", "files", "stars"]:
                if not val.isdigit():
                    await message.reply_text(
                        "❌ Invalid number. Try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                    )
                    return
                val_num = int(val)
                if field == "egress":
                    plan_settings["daily_egress_mb"] = val_num
                elif field == "files":
                    plan_settings["daily_file_count"] = val_num
                elif field == "stars":
                    plan_settings["stars_price"] = val_num

            await db.update_public_config(plan_key, plan_settings)

            await message.reply_text(
                f"✅ {plan_name.capitalize()} {field} updated to `{val}`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=f"admin_premium_plan_{plan_name}")]])
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
                    await message.reply_text(
                        "❌ Invalid number. Try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
                    )
                    return

                currency = state.get("currency", "USD")
                formatted_price = f"{float_val:g} {currency}"

                config = await db.get_public_config()
                plan_key = f"premium_{plan_name}"
                plan_settings = config.get(plan_key, {})
                plan_settings["price_string"] = formatted_price

                await db.update_public_config(plan_key, plan_settings)

                await message.reply_text(
                    f"✅ {plan_name.capitalize()} fiat price updated to `{formatted_price}`.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=f"admin_premium_plan_{plan_name}")]])
                )
                admin_sessions.pop(user_id, None)
                return

    if state == "awaiting_trial_days":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await message.reply_text(
                "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_premium_settings")]])
            )
            return
        await db.update_public_config("premium_trial_days", int(val))
        await message.reply_text(
            f"✅ Premium trial duration updated to `{val}` days.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_premium_settings")]])
        )
        admin_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_fs_"):
        val = message.text.strip() if message.text else ""
        if val == "/cancel":
            admin_sessions.pop(user_id, None)
            await message.reply_text("Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_force_sub_menu")]]))
            return

        field = state.replace("awaiting_fs_", "")

        if field == "msg":
            await db.update_public_config("force_sub_message_text", val)
            await message.reply_text(
                "✅ Gate message updated successfully.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_force_sub_menu")]])
            )
        elif field == "btn_label":
            await db.update_public_config("force_sub_button_label", val)
            await message.reply_text(
                f"✅ Button label updated to `{val}`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fs_edit_btn")]])
            )
        elif field == "btn_emoji":

            emoji = val[0] if val else "📢"
            await db.update_public_config("force_sub_button_emoji", emoji)
            await message.reply_text(
                f"✅ Button emoji updated to {emoji}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fs_edit_btn")]])
            )
        elif field == "welcome":
            await db.update_public_config("force_sub_welcome_text", val)
            await message.reply_text(
                "✅ Welcome message updated successfully.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_force_sub_menu")]])
            )

        admin_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_template_"):
        field = state.split("_")[-1]
        new_template = message.text
        await db.update_template(field, new_template)
        if field == "caption":
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back", callback_data="admin_templates_menu")]]
            )
        else:
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Templates", callback_data="admin_templates"
                        )
                    ]
                ]
            )
        await message.reply_text(
            f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`",
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
                        "🔙 Back to Filename Templates",
                        callback_data="admin_filename_templates",
                    )
                ]
            ]
        )
        await message.reply_text(
            f"✅ Filename template for **{field.capitalize()}** updated to:\n`{new_template}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)
    elif state == "awaiting_admin_channel":
        new_channel = message.text
        await db.update_channel(new_channel, None)

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back", callback_data="admin_general_channel")]]
        )
        await message.reply_text(
            f"✅ Global channel variable updated to:\n`{new_channel}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)

    else:
        raise ContinuePropagation

debug("✅ Loaded handler: admin_dashboard_overview_cb")

@Client.on_callback_query(
    filters.regex("^admin_usage_dashboard$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_overview_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
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
    start_date_obj = datetime.datetime.strptime(stats.get("bot_start_date"), "%Y-%m-%d")
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
                            "🔝 Top Users", callback_data="admin_dashboard_top_0"
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
                            "← Back to Admin Panel", callback_data="admin_main"
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
async def admin_dashboard_top_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
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
                "← Prev", callback_data=f"admin_dashboard_top_{page-1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton("← Prev", callback_data="noop"))

    nav_row.append(
        InlineKeyboardButton(f"Page {page+1} / {total_pages}", callback_data="noop")
    )

    if skip + limit < total:
        nav_row.append(
            InlineKeyboardButton(
                "Next →", callback_data=f"admin_dashboard_top_{page+1}"
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
    filters.regex("^admin_dashboard_daily$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_daily_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
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

@Client.on_message(filters.regex(r"^/lookup (\d+)$") & filters.user(Config.CEO_ID))
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
                    "✅ Unblock User", callback_data=f"admin_unblock_{user_id}"
                )
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    "🚫 Block User", callback_data=f"admin_block_{user_id}"
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "🗑️ Reset Today's Quota", callback_data=f"admin_reset_quota_{user_id}"
            )
        ]
    )
    buttons.append(
        [InlineKeyboardButton("← Back", callback_data="admin_usage_dashboard")]
    )

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

debug("✅ Loaded handler: admin_block_user_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_block_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_block_user_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("User Blocked", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.block_user(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_unblock_user_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_unblock_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_unblock_user_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("User Unblocked", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.unblock_user(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_reset_quota_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_reset_quota_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_reset_quota_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("Quota Reset", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.reset_user_quota(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_prompt_lookup_cb")

@Client.on_callback_query(
    filters.regex("^prompt_user_lookup$") & filters.user(Config.CEO_ID)
)
async def admin_prompt_lookup_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
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
    from utils.state import set_state

    set_state(callback_query.from_user.id, "awaiting_user_lookup")

@Client.on_message(
    filters.text & filters.private & filters.user(Config.CEO_ID), group=1
)
async def admin_handle_user_lookup_text(client: Client, message: Message):
    from utils.state import get_state, clear_session

    state = get_state(message.from_user.id)

    if state == "awaiting_user_lookup":
        val = message.text.strip()

        if val.isdigit():
            user_id = int(val)
        else:

            try:
                user = await client.get_users(val)
                user_id = user.id
            except Exception:
                await message.reply_text(
                    "❌ Could not find a user with that ID or username. Please make sure the ID is correct.",
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
                clear_session(message.from_user.id)
                return

        await show_user_lookup(client, message, user_id)
        clear_session(message.from_user.id)
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
