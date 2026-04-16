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
        r"^(admin_(?!usage_dashboard|dashboard_|block_|unblock_|reset_quota_|broadcast|users_menu|user_search_start|dumb_channels|dumb_timeout|view$|general_settings_menu$|main$|access_limits$|quick_toggle_(?:premium|deluxe|trial|myfiles)$|feature_toggles$|gtoggle_|per_plan_limits$|global_daily_egress$|thumb_(?:menu|view|set|remove)$|delete_msg$|templates_menu$|templates$|caption$|filename_templates$|fn_templates_(?:personal|subtitles)$|pref_separator$|set_sep_|public_(?:settings|view|bot_name|community_name|support_contact)$|force_sub_menu$|fs_|myfiles_|clean_)|prompt_admin_(?!dumb_timeout|thumb_set|caption|fs_)|prompt_daily_|prompt_global_|prompt_premium_|prompt_trial_|admin_set_lang_|set_admin_workflow_|admin_pay_|prompt_pay_|set_4gb_access_|admin_prem_cur_|set_daily_egress_|set_prem_egress_|prompt_prem_egress_custom_)"
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
    if data.startswith("admin_edit_plan_"):
        plan_name = data.replace("admin_edit_plan_", "")

        config = await db.get_public_config()
        limits = config.get("myfiles_limits", {})
        plan_lm = limits.get(plan_name, {})

        def f(v): return "Unlimited" if v == -1 else v

        global_toggles = await db.get_feature_toggles()

        def get_features_str(plan_key):
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            feat_list = []

            # Media tools: both global AND per-plan must be enabled
            tool_checks = [
                ("subtitle_extractor", "💬 Subtitle Extractor"),
                ("watermarker", "🎨 Image Watermarker"),
                ("file_converter", "🔄 File Converter"),
                ("audio_editor", "🎵 Audio Editor"),
                ("video_trimmer", "✂️ Video Trimmer"),
                ("media_info", "ℹ️ Media Info"),
                ("voice_converter", "🎙️ Voice Converter"),
                ("video_note_converter", "⭕ Video Note"),
                ("youtube_tool", "▶️ YouTube Tool"),
                ("4k_enhancement", "📺 4K Enhancement"),
                ("batch_processing_pro", "📦 Batch Pro"),
            ]
            for feat_key, label in tool_checks:
                global_on = global_toggles.get(feat_key, True)
                plan_on = features.get(feat_key, global_on)
                if global_on and plan_on:
                    feat_list.append(label)

            # Account perks
            if features.get("priority_queue", False):
                feat_list.append("🚀 Priority Queue")
            if features.get("batch_sharing", False):
                feat_list.append("🔗 Batch Sharing")
            if features.get("xtv_pro_4gb", False):
                feat_list.append("⚡ XTV Pro 4GB Bypass")

            return "\n".join([f"  • {feat}" for feat in feat_list]) if feat_list else "  • None"

        if plan_name == "free":
            plan_emoji = "🆓"
            plan_title = "Free Plan"
            egress_mb = config.get("daily_egress_mb", 0)
            file_count = config.get("daily_file_count", 0)
            features_text = get_features_str('free_placeholder')
            price_text = ""
        else:
            plan_emoji = "🌟" if plan_name == "standard" else "💎"
            plan_title = f"{plan_name.capitalize()} Plan"
            plan_settings = config.get(f"premium_{plan_name}", {})
            egress_mb = plan_settings.get("daily_egress_mb", 0)
            file_count = plan_settings.get("daily_file_count", 0)
            features_text = get_features_str(f"premium_{plan_name}")
            price_text = (
                f"\n💵 **Price (Fiat):** `{plan_settings.get('price_string', '0 USD')}`\n"
                f"⭐ **Price (Stars):** `{plan_settings.get('stars_price', 0)}` Stars\n"
            )

        text = (
            f"⚙️ **Edit {plan_title} Settings**\n\n"
            f"> Configure the quotas, features, and prices for this tier.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{plan_emoji} **{plan_title}**\n\n"
            f"📌 Permanent Slots : `{f(plan_lm.get('permanent_limit', 0))}`\n"
            f"📁 Custom Folders  : `{f(plan_lm.get('folder_limit', 0))}`\n"
            f"⏳ Temp Expiration : `{f(plan_lm.get('expiry_days', 0))} days`\n"
            f"📦 Daily Egress: `{f(egress_mb)}` MB\n"
            f"📄 Daily Files: `{f(file_count)}` files\n\n"
            f"✨ **Features:**\n"
            f"{features_text}\n"
            f"{price_text}"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        buttons = [
            [InlineKeyboardButton("📌 Edit Permanent Limit", callback_data=f"prompt_myfiles_lim_{plan_name}_permanent")],
            [InlineKeyboardButton("📁 Edit Folder Limit", callback_data=f"prompt_myfiles_lim_{plan_name}_folder")],
            [InlineKeyboardButton("⏳ Edit Expiry Days", callback_data=f"prompt_myfiles_lim_{plan_name}_expiry")]
        ]

        if plan_name == "free":
            buttons.append([InlineKeyboardButton("📦 Edit Egress Limit", callback_data="admin_daily_egress")])
            buttons.append([InlineKeyboardButton("📄 Edit File Limit", callback_data="admin_daily_files")])
        else:
            buttons.append([InlineKeyboardButton("📦 Edit Egress Limit", callback_data=f"prompt_premium_{plan_name}_egress")])
            buttons.append([InlineKeyboardButton("📄 Edit File Limit", callback_data=f"prompt_premium_{plan_name}_files")])

            # Additional configurations for premium plans (moved from Premium Settings)
            buttons.append([
                InlineKeyboardButton("💵 Edit Fiat Price", callback_data=f"prompt_premium_{plan_name}_price"),
                InlineKeyboardButton("⭐ Edit Stars Price", callback_data=f"prompt_premium_{plan_name}_stars")
            ])

        buttons.append([InlineKeyboardButton("⚙️ Configure Features", callback_data=f"admin_premium_features_{plan_name}")])
        buttons.append([InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_per_plan_limits")])

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return


    # admin_myfiles_limits, admin_myfiles_edit_limits_*, prompt_myfiles_lim_*,
    # set_unlimited_myfiles_lim_*, admin_myfiles_cleanup, admin_clean_*
    # moved to plugins/admin/myfiles.py

    # dumb_* callbacks moved to plugins/admin/dumb_channels.py

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
            "__(Users will only see the enabled methods during checkout)__\n\n"
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
                    [InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]
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
                    [InlineKeyboardButton("← Back to Payment Settings", callback_data="admin_pay_settings")]
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
        admin_sessions[user_id] = {"state": f"awaiting_pay_{method}", "msg_id": callback_query.message.id}

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
                    [InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("prompt_pay_disc_"):
        months = data.replace("prompt_pay_disc_", "")
        admin_sessions[user_id] = {"state": f"awaiting_pay_disc_{months}", "msg_id": callback_query.message.id}
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
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]])
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
                    [InlineKeyboardButton("← Back to Payments", callback_data="admin_payments_menu")]
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
            except Exception:
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
            except Exception:
                pass

            await callback_query.answer("Payment Rejected.", show_alert=True)

        callback_query.data = "admin_pay_queue"
        await admin_callback(client, callback_query)
        return

    # admin_feature_toggles and admin_gtoggle_* moved to plugins/admin/feature_toggles.py

    if data.startswith("admin_toggle_"):
        # Per-plan free toggles: admin_toggle_{feature}_{plan}
        suffix = data.replace("admin_toggle_", "")
        plan_name = None
        for plan_suffix in ("_free", "_standard", "_deluxe"):
            if suffix.endswith(plan_suffix):
                plan_name = plan_suffix.lstrip("_")
                feature = suffix[: -len(plan_suffix)]
                break
        if plan_name is None:
            feature = suffix
            plan_name = "free"

        toggles = await db.get_feature_toggles()
        current_state = toggles.get(feature, True)
        new_state = not current_state
        await db.update_feature_toggle(feature, new_state)
        await callback_query.answer(f"{'Enabled' if new_state else 'Disabled'} {feature.replace('_', ' ').title()}.", show_alert=True)
        callback_query.data = f"admin_features_media_{plan_name}"
        await admin_callback(client, callback_query)
        return

    # admin_global_daily_egress preview moved to plugins/admin/feature_toggles.py

    if Config.PUBLIC_MODE and (
        data.startswith("admin_premium_") or data.startswith("prompt_premium_") or data.startswith("prompt_trial_") or data.startswith("admin_trial_") or data.startswith("admin_features_") or data.startswith("admin_privacy_")
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

                buttons.append([InlineKeyboardButton(f"Toggle Trial System: {trial_status_emoji}", callback_data="admin_trial_toggle")])
                if trial_enabled:
                    buttons.append([InlineKeyboardButton("⏱ Edit Trial Duration", callback_data="prompt_trial_days")])

            buttons.append([InlineKeyboardButton("← Back to Settings", callback_data="admin_access_limits")])

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


        elif data.startswith("admin_premium_features_"):
            plan_name = data.replace("admin_premium_features_", "")

            buttons = [
                [InlineKeyboardButton("🌟 Account Perks", callback_data=f"admin_features_perks_{plan_name}")],
                [InlineKeyboardButton("🛠️ Media Tools", callback_data=f"admin_features_media_{plan_name}")],
                [InlineKeyboardButton("🔒 Privacy Settings", callback_data=f"admin_features_privacy_{plan_name}")],
                [InlineKeyboardButton("📁 MyFiles Limits", callback_data=f"admin_edit_plan_{plan_name}")],
                [InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")]
            ]

            if plan_name == "free":
                text = (
                    "⚙️ **Free Plan Features**\n\n"
                    "Select a category to configure features for this plan.\n"
                    "> __Free plan media tools use the global toggles.__\n"
                    "> __Per-plan overrides are available for premium tiers.__"
                )
            else:
                text = (
                    f"⚙️ **{plan_name.capitalize()} Plan Features**\n\n"
                    "Select a category to configure features for this plan.\n"
                    "> Each tool can be individually enabled or disabled."
                )

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("admin_features_perks_"):
            plan_name = data.replace("admin_features_perks_", "")
            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})

            def emoji(state): return "✅" if state else "❌"

            pq = features.get("priority_queue", False)
            bs = features.get("batch_sharing", False)
            access_4gb = features.get("xtv_pro_4gb", False)

            buttons = [
                [InlineKeyboardButton(f"{emoji(access_4gb)} 🚀 4GB Access", callback_data=f"admin_premium_feat_{plan_name}_xtv_pro_4gb")],
                [InlineKeyboardButton(f"{emoji(pq)} ⚡ Priority Queue", callback_data=f"admin_premium_feat_{plan_name}_priority_queue"),
                 InlineKeyboardButton(f"{emoji(bs)} 📦 Batch Sharing", callback_data=f"admin_premium_feat_{plan_name}_batch_sharing")],
                [InlineKeyboardButton("← Back to Feature Categories", callback_data=f"admin_premium_features_{plan_name}")]
            ]

            text = f"🌟 **Account Perks ({plan_name.capitalize()})**\n\nConfigure account perks for this tier:"

            try:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
            return

        elif data.startswith("admin_features_media_"):
            plan_name = data.replace("admin_features_media_", "")
            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            global_toggles = await db.get_feature_toggles()

            def emoji(state): return "✅" if state else "❌"

            # Define all media tools with their display info
            tool_defs = [
                ("subtitle_extractor", "🎬 Subtitle Extractor"),
                ("watermarker", "🖼 Watermarker"),
                ("file_converter", "🔄 Converter"),
                ("audio_editor", "🎵 Audio Editor"),
                ("video_trimmer", "✂️ Video Trimmer"),
                ("media_info", "ℹ️ Media Info"),
                ("voice_converter", "🎙️ Voice Converter"),
                ("video_note_converter", "⭕ Video Note"),
                ("youtube_tool", "▶️ YouTube Tool"),
                ("4k_enhancement", "📺 4K Enhancement"),
                ("batch_processing_pro", "📦 Batch Pro"),
            ]

            buttons = []
            if plan_name == "free":
                # Free plan uses global toggles directly
                for i in range(0, len(tool_defs), 2):
                    row = []
                    for j in range(i, min(i + 2, len(tool_defs))):
                        feat_key, label = tool_defs[j]
                        state = global_toggles.get(feat_key, True)
                        row.append(InlineKeyboardButton(
                            f"{emoji(state)} {label}",
                            callback_data=f"admin_toggle_{feat_key}_{plan_name}"
                        ))
                    buttons.append(row)
            else:
                # Premium plans: show ALL tools with per-plan toggle
                for i in range(0, len(tool_defs), 2):
                    row = []
                    for j in range(i, min(i + 2, len(tool_defs))):
                        feat_key, label = tool_defs[j]
                        # Per-plan state (defaults to True for premium)
                        plan_state = features.get(feat_key, True)
                        global_state = global_toggles.get(feat_key, True)
                        # Effective = both global AND per-plan must be on
                        effective = plan_state and global_state
                        # Show indicator if globally off
                        suffix = " ⛔" if not global_state else ""
                        row.append(InlineKeyboardButton(
                            f"{emoji(effective)} {label}{suffix}",
                            callback_data=f"admin_premium_feat_{plan_name}_{feat_key}"
                        ))
                    buttons.append(row)

            buttons.append([InlineKeyboardButton("← Back to Feature Categories", callback_data=f"admin_premium_features_{plan_name}")])

            if plan_name == "free":
                text = (
                    f"🛠️ **Media Tools (Free)**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Toggle media tools for free users.\n"
                    f"> These are the **global** toggles (apply to all non-premium users)."
                )
            else:
                text = (
                    f"🛠️ **Media Tools ({plan_name.capitalize()})**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Toggle media tools for this plan.\n"
                    f"> ⛔ = Globally disabled (enable in Feature Toggles first)\n"
                    f"> Per-plan toggles control access within this tier."
                )

            try:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
            return

        elif data.startswith("admin_features_privacy_"):
            plan_name = data.replace("admin_features_privacy_", "")
            # Route to the existing privacy menu
            callback_query.data = f"admin_privacy_menu_{plan_name}"
            await admin_callback(client, callback_query)
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

            # Deep routing to stay inside the appropriate sub-menu
            if feature_name in ["xtv_pro_4gb", "priority_queue", "batch_sharing"]:
                callback_query.data = f"admin_features_perks_{plan_name}"
            elif feature_name == "privacy_settings":
                callback_query.data = f"admin_privacy_menu_{plan_name}"
            else:
                callback_query.data = f"admin_features_media_{plan_name}"

            await admin_callback(client, callback_query)
            return

        elif data.startswith("admin_privacy_menu_"):
            plan_name = data.replace("admin_privacy_menu_", "")
            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            features = plan_settings.get("features", {})
            privacy = features.get("privacy", {})

            def emoji(state): return "✅" if state else "❌"

            ps = features.get("privacy_settings", False)

            buttons = [
                [InlineKeyboardButton(f"{emoji(ps)} 🔒 Enable Privacy Settings", callback_data=f"admin_premium_feat_{plan_name}_privacy_settings")],
            ]

            if ps:
                hdn = privacy.get('hide_display_name', False)
                hft = privacy.get('hide_forward_tags', False)
                la = privacy.get('link_anonymity', False)
                hu = privacy.get('hide_username', False)
                ael = privacy.get('auto_expire_links', False)

                buttons.extend([
                    [InlineKeyboardButton("━━━ 🔒 Available Controls ━━━", callback_data="noop")],
                    [InlineKeyboardButton(f"{emoji(hdn)} 👤 Hide Display Name", callback_data=f"admin_privacy_toggle_{plan_name}_hide_display_name")],
                    [InlineKeyboardButton(f"{emoji(hft)} 🏷️ Hide Forward Tags", callback_data=f"admin_privacy_toggle_{plan_name}_hide_forward_tags")],
                    [InlineKeyboardButton(f"{emoji(la)} 🔗 Link Anonymity (UUID)", callback_data=f"admin_privacy_toggle_{plan_name}_link_anonymity")],
                    [InlineKeyboardButton(f"{emoji(hu)} 🙈 Hide Username", callback_data=f"admin_privacy_toggle_{plan_name}_hide_username")],
                    [InlineKeyboardButton(f"{emoji(ael)} ⏳ Auto-Expire Links", callback_data=f"admin_privacy_toggle_{plan_name}_auto_expire_links")],
                ])

            buttons.append([InlineKeyboardButton("← Back to Feature Categories", callback_data=f"admin_premium_features_{plan_name}")])

            text = (
                f"🔒 **Privacy Settings ({plan_name.capitalize()})**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Toggle which privacy controls are **available** for users on this plan to configure in their /settings:\n\n"
            )
            if ps:
                text += (
                    f"> 👤 **Hide Display Name:** {'Enabled' if privacy.get('hide_display_name', False) else 'Disabled'}\n"
                    f"> __Users can hide their name on shared files__\n"
                    f"> 🏷️ **Hide Forward Tags:** {'Enabled' if privacy.get('hide_forward_tags', False) else 'Disabled'}\n"
                    f"> __Remove 'Forwarded from' on shares__\n"
                    f"> 🔗 **Link Anonymity:** {'Enabled' if privacy.get('link_anonymity', False) else 'Disabled'}\n"
                    f"> __Use anonymous hash in share links__\n"
                    f"> 🙈 **Hide Username:** {'Enabled' if privacy.get('hide_username', False) else 'Disabled'}\n"
                    f"> __Hide username on shared content__\n"
                    f"> ⏳ **Auto-Expire Links:** {'Enabled' if privacy.get('auto_expire_links', False) else 'Disabled'}\n"
                    f"> __Share links expire automatically__\n"
                )
            else:
                text += "> ⚠️ __Privacy settings are disabled for this plan.__\n"

            try:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
            return

        elif data.startswith("admin_privacy_toggle_"):
            parts = data.replace("admin_privacy_toggle_", "").split("_", 1)
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

            callback_query.data = f"admin_privacy_menu_{plan_name}"
            await admin_callback(client, callback_query)
            return


        elif data.startswith("prompt_premium_"):
            parts = data.replace("prompt_premium_", "").split("_")
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
                                        InlineKeyboardButton("512 MB", callback_data=f"set_prem_egress_{plan_name}_512"),
                                        InlineKeyboardButton("1 GB", callback_data=f"set_prem_egress_{plan_name}_1024")
                                    ],
                                    [
                                        InlineKeyboardButton("2 GB", callback_data=f"set_prem_egress_{plan_name}_2048"),
                                        InlineKeyboardButton("4 GB", callback_data=f"set_prem_egress_{plan_name}_4096")
                                    ],
                                    [
                                        InlineKeyboardButton(
                                            "✏️ Change Custom", callback_data=f"prompt_prem_egress_custom_{plan_name}"
                                        )
                                    ],
                                    [
                                        InlineKeyboardButton(
                                            "← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}"
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
                                [InlineKeyboardButton("USD ($)", callback_data=f"admin_prem_cur_{plan_name}_USD"),
                                 InlineKeyboardButton("EUR (€)", callback_data=f"admin_prem_cur_{plan_name}_EUR"),
                                 InlineKeyboardButton("GBP (£)", callback_data=f"admin_prem_cur_{plan_name}_GBP")],
                                [InlineKeyboardButton("INR (₹)", callback_data=f"admin_prem_cur_{plan_name}_INR"),
                                 InlineKeyboardButton("RUB (₽)", callback_data=f"admin_prem_cur_{plan_name}_RUB"),
                                 InlineKeyboardButton("BRL (R$)", callback_data=f"admin_prem_cur_{plan_name}_BRL")],
                                [InlineKeyboardButton("← Back to Plan Settings", callback_data=f"admin_edit_plan_{plan_name}")]
                            ])
                        )
                    except MessageNotModified:
                        pass
                    return

                admin_sessions[user_id] = {"state": f"awaiting_premium_{plan_name}_{field}", "msg_id": callback_query.message.id}

                prompts = {
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
                    except (ValueError, TypeError):
                        star_prompt = "⭐ **Send the new Telegram Stars price (integer).**"

                    prompts["stars"] = star_prompt

                cancel_cb = f"admin_edit_plan_{plan_name}"

                try:
                    await callback_query.message.edit_text(
                        prompts.get(field, "Enter new value:"),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]])
                    )
                except MessageNotModified:
                    pass
                return

    if data.startswith("prompt_prem_egress_custom_"):
        plan_name = data.replace("prompt_prem_egress_custom_", "")
        admin_sessions[user_id] = {"state": f"awaiting_premium_{plan_name}_egress", "msg_id": callback_query.message.id}
        try:
            await callback_query.message.edit_text(
                "📦 **Send the new daily egress limit.**\n\nYou can send the value in MB (e.g., `2048`) or use `GB` format (e.g., `2 GB` or `5.5 GB`).\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_edit_plan_{plan_name}")]])
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("set_prem_egress_"):
        parts = data.replace("set_prem_egress_", "").split("_")
        if len(parts) >= 2:
            plan_name = parts[0]
            val = int(parts[1])

            config = await db.get_public_config()
            plan_key = f"premium_{plan_name}"
            plan_settings = config.get(plan_key, {})
            plan_settings["daily_egress_mb"] = val
            await db.update_public_config(plan_key, plan_settings)

            await callback_query.answer(f"{plan_name.capitalize()} Egress limit updated to {val} MB.", show_alert=True)
            callback_query.data = f"admin_edit_plan_{plan_name}"
            await admin_callback(client, callback_query)
        return

    if data.startswith("admin_prem_cur_"):
        parts = data.replace("admin_prem_cur_", "").split("_")
        plan_name = parts[0]
        currency = parts[1]

        admin_sessions[user_id] = {"state": f"awaiting_premium_{plan_name}_price", "currency": currency
        , "msg_id": callback_query.message.id}

        try:
            await callback_query.message.edit_text(
                f"💵 **Set Price in {currency}**\n\nPlease enter the numeric amount (e.g., `9.99` or `500`):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_premium_plan_{plan_name}")]])
            )
        except MessageNotModified:
            pass
        return

    if data == "prompt_trial_days":
        admin_sessions[user_id] = {"state": "awaiting_trial_days", "msg_id": callback_query.message.id}
        try:
            await callback_query.message.edit_text(
                "⏱ **Send the new PREMIUM TRIAL duration in days (e.g., 7).**\nSend `0` to disable.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_premium_settings")]])
            )
        except MessageNotModified:
            pass
        return

    if data == "prompt_global_daily_egress":
        admin_sessions[user_id] = {"state": "awaiting_global_daily_egress", "msg_id": callback_query.message.id}
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

    # dumb_add / dumb_del_ / admin_dumb_channels / admin_dumb_timeout /
    # prompt_admin_dumb_timeout moved to plugins/admin/dumb_channels.py

    # admin_public_view, admin_public_bot_name, admin_public_community_name,
    # admin_public_support_contact moved to plugins/admin/public_settings.py

    # admin_force_sub_menu, admin_fs_* moved to plugins/admin/force_sub.py

    if Config.PUBLIC_MODE and (
        data.startswith("admin_daily_")
        or data.startswith("admin_premium_")
        or data.startswith("prompt_premium_")
        or data.startswith("set_daily_egress_")
    ):
        if data == "admin_daily_egress":
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
                                InlineKeyboardButton("512 MB", callback_data="set_daily_egress_512"),
                                InlineKeyboardButton("1 GB", callback_data="set_daily_egress_1024")
                            ],
                            [
                                InlineKeyboardButton("2 GB", callback_data="set_daily_egress_2048"),
                                InlineKeyboardButton("4 GB", callback_data="set_daily_egress_4096")
                            ],
                            [
                                InlineKeyboardButton(
                                    "✏️ Change Custom", callback_data="prompt_daily_egress"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back to Plan Settings", callback_data="admin_edit_plan_free"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

        elif data.startswith("set_daily_egress_"):
            val = int(data.replace("set_daily_egress_", ""))
            await db.update_public_config("daily_egress_mb", val)
            await callback_query.answer(f"Egress limit updated to {val} MB.", show_alert=True)
            callback_query.data = "admin_edit_plan_free"
            await admin_callback(client, callback_query)
            return

        elif data == "admin_daily_files":
            config = await db.get_public_config()
            current_val = config.get("daily_file_count", 0)
            try:
                await callback_query.message.edit_text(
                    f"📄 **Edit Daily File Limit** (Free Plan)\n\nCurrent: `{current_val}` files\n\nClick below to change it.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Change", callback_data="prompt_daily_files"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "← Back to Plan Settings", callback_data="admin_edit_plan_free"
                                )
                            ],
                        ]
                    ),
                )
            except MessageNotModified:
                pass
            return

    # prompt_public_bot_name/community_name/support_contact moved to
    # plugins/admin/public_settings.py; prompt_daily_* stays here.
    if Config.PUBLIC_MODE and data.startswith("prompt_daily_"):
        field = data.replace("prompt_daily_", "daily_")
        admin_sessions[user_id] = {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id}

        if field == "daily_egress":
            text = "📦 **Send the new daily egress limit.**\n\nYou can send the value in MB (e.g., `2048`) or use `GB` format (e.g., `2 GB` or `5.5 GB`).\nSend `0` to disable."
        elif field == "daily_files":
            text = "📄 **Send the new daily file limit.**\nSend `0` to disable."
        else:
            text = "Send the new value:"
        cancel_btn = "admin_edit_plan_free"

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
    # admin_thumb_* moved to plugins/admin/thumbnails.py
    # admin_templates_menu moved to plugins/admin/templates.py
    # admin_access_limits moved to plugins/admin/feature_toggles.py
    # admin_public_settings moved to plugins/admin/public_settings.py
    # admin_pref_separator, admin_set_sep_*, admin_templates, admin_caption,
    # prompt_admin_caption, admin_filename_templates, admin_fn_templates_*,
    # edit_fn_template_*, prompt_fn_template_* moved to plugins/admin/templates.py
    # admin_general_settings_menu moved to plugins/admin/general.py
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
