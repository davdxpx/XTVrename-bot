import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import db
from config import Config
from utils.gate import is_public_mode
from utils.currency import convert_to_usd_str

# --- Handlers ---

@Client.on_message(filters.command("premium") & filters.private)
async def handle_premium_command(client, message):
    if not is_public_mode():
        return

    user_id = message.from_user.id
    user = await db.get_user(user_id)
    config = await db.get_public_config()

    premium_system_enabled = config.get("premium_system_enabled", False)

    if not premium_system_enabled:
        await message.reply_text("❌ **Premium System is currently disabled.**")
        return

    is_prem = False
    current_plan = "standard"
    if user:
        exp = user.get("premium_expiry")
        if user.get("is_premium") and (exp is None or exp > time.time()):
            is_prem = True
            current_plan = user.get("premium_plan", "standard")

    if is_prem:
        exp_text = "Lifetime"
        if user.get("premium_expiry"):
            exp_text = datetime.fromtimestamp(user.get("premium_expiry")).strftime('%Y-%m-%d %H:%M')

        plan_display = "⭐ Premium Standard" if current_plan == "standard" else "💎 Premium Deluxe"
        status_emoji = "⭐" if current_plan == "standard" else "💎"

        dash_text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{status_emoji} **YOUR PREMIUM DASHBOARD**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> **Plan:** `{plan_display}`\n"
            f"> **Status:** `Active ✅`\n"
            f"> **Expiry:** `{exp_text}`\n\n"
            f"✨ *Thank you for supporting 𝕏TV! Enjoy your exclusive benefits, priority processing, and enhanced limits.*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        buttons = [
            [InlineKeyboardButton("⚙️ Custom Defaults", callback_data="premium_settings")],
            [InlineKeyboardButton("🚀 Priority Queue", callback_data="premium_priority")],
            [InlineKeyboardButton("🔄 Refresh Status", callback_data="user_premium_menu")]
        ]

        await message.reply_text(dash_text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    trial_enabled = config.get("premium_trial_enabled", False)
    trial_days = config.get("premium_trial_days", 0)
    trial_claimed = user.get("trial_claimed", False) if user else False

    deluxe_enabled = config.get("premium_deluxe_enabled", False)

    standard_settings = config.get("premium_standard", {})
    deluxe_settings = config.get("premium_deluxe", {})

    std_usd = await convert_to_usd_str(standard_settings.get("price_string", "0 USD"))
    dlx_usd = await convert_to_usd_str(deluxe_settings.get("price_string", "0 USD"))

    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb} MB"

    std_mb = standard_settings.get('daily_egress_mb', 0)
    std_egress = format_egress(std_mb) if std_mb > 0 else "Unlimited"
    std_files = f"{standard_settings.get('daily_file_count', 0)}" if standard_settings.get("daily_file_count", 0) > 0 else "Unlimited"

    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 **UPGRADE TO PREMIUM** 💎\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Unlock the full power of 𝕏TV. Say goodbye to limits and hello to exclusive features!\n\n"
    )

    text += (
        f"**⭐ Premium Standard**\n"
        f"> 📂 **Daily Egress Limit:** `{std_egress}`\n"
        f"> 📑 **Daily File Limit:** `{std_files}`\n"
    )
    if standard_settings.get("features", {}).get("priority_queue"):
        text += f"> 🚀 **Priority Queue:** `Enabled`\n"
    if standard_settings.get("features", {}).get("xtv_pro_4gb"):
        text += f"> ⚡ **XTV Pro 4GB Bypass:** `Enabled`\n"

    text += f"> 🛠️ **File Converter:** `Included`\n"
    text += f"> 🎨 **Image Watermarker:** `Included`\n"
    text += f"\n**Price:** `{std_usd}`\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    if deluxe_enabled:
        dlx_mb = deluxe_settings.get('daily_egress_mb', 0)
        dlx_egress = format_egress(dlx_mb) if dlx_mb > 0 else "Unlimited"
        dlx_files = f"{deluxe_settings.get('daily_file_count', 0)}" if deluxe_settings.get("daily_file_count", 0) > 0 else "Unlimited"

        text += (
            f"**💎 Premium Deluxe**\n"
            f"> 📂 **Daily Egress Limit:** `{dlx_egress}`\n"
            f"> 📑 **Daily File Limit:** `{dlx_files}`\n"
        )
        if deluxe_settings.get("features", {}).get("priority_queue"):
            text += f"> 🚀 **Priority Queue:** `Enabled`\n"
        if deluxe_settings.get("features", {}).get("xtv_pro_4gb"):
            text += f"> ⚡ **XTV Pro 4GB Bypass:** `Enabled`\n"

        text += f"> 🛠️ **File Converter:** `Included`\n"
        text += f"> 🎨 **Image Watermarker:** `Included`\n"
        text += f"> 📽️ **4K Upscaling/Enhancement:** `Exclusive`\n"
        text += f"\n**Price:** `{dlx_usd}`\n"
        text += f"━━━━━━━━━━━━━━━━━━━━\n"

    buttons = []

    if trial_enabled and trial_days > 0 and not trial_claimed:
        text += f"\n🎁 *Special Offer: You are eligible for a {trial_days}-Day Trial!*\n"
        buttons.append([InlineKeyboardButton("🎁 Claim Free Trial", callback_data="claim_trial")])

    buttons.append([InlineKeyboardButton("⭐ Purchase Standard", callback_data="buy_premium_dur_standard")])

    if deluxe_enabled:
        buttons.append([InlineKeyboardButton("💎 Purchase Deluxe", callback_data="buy_premium_dur_deluxe")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^user_premium_menu$"))
async def handle_user_premium_menu(client, callback_query):
    if not is_public_mode():
        await callback_query.answer("Disabled in this mode.", show_alert=True)
        return

    user_id = callback_query.from_user.id
    user = await db.get_user(user_id)
    config = await db.get_public_config()

    premium_system_enabled = config.get("premium_system_enabled", False)

    if not premium_system_enabled:
        await callback_query.answer("Premium System is currently disabled.", show_alert=True)
        return

    is_prem = False
    current_plan = "standard"
    if user:
        exp = user.get("premium_expiry")
        if user.get("is_premium") and (exp is None or exp > time.time()):
            is_prem = True
            current_plan = user.get("premium_plan", "standard")

    if is_prem:
        exp_text = "Lifetime"
        if user.get("premium_expiry"):
            exp_text = datetime.fromtimestamp(user.get("premium_expiry")).strftime('%Y-%m-%d %H:%M')

        plan_display = "⭐ Premium Standard" if current_plan == "standard" else "💎 Premium Deluxe"
        status_emoji = "⭐" if current_plan == "standard" else "💎"

        dash_text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{status_emoji} **YOUR PREMIUM DASHBOARD**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> **Plan:** `{plan_display}`\n"
            f"> **Status:** `Active ✅`\n"
            f"> **Expiry:** `{exp_text}`\n\n"
            f"✨ *Thank you for supporting 𝕏TV! Enjoy your exclusive benefits, priority processing, and enhanced limits.*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        buttons = [
            [InlineKeyboardButton("⚙️ Custom Defaults", callback_data="premium_settings")],
            [InlineKeyboardButton("🚀 Priority Queue", callback_data="premium_priority")],
            [InlineKeyboardButton("🔄 Refresh Status", callback_data="user_premium_menu")]
        ]

        await callback_query.message.edit_text(dash_text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    trial_enabled = config.get("premium_trial_enabled", False)
    trial_days = config.get("premium_trial_days", 0)
    trial_claimed = user.get("trial_claimed", False) if user else False

    deluxe_enabled = config.get("premium_deluxe_enabled", False)

    standard_settings = config.get("premium_standard", {})
    deluxe_settings = config.get("premium_deluxe", {})

    std_usd = await convert_to_usd_str(standard_settings.get("price_string", "0 USD"))
    dlx_usd = await convert_to_usd_str(deluxe_settings.get("price_string", "0 USD"))

    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb} MB"

    std_mb = standard_settings.get('daily_egress_mb', 0)
    std_egress = format_egress(std_mb) if std_mb > 0 else "Unlimited"
    std_files = f"{standard_settings.get('daily_file_count', 0)}" if standard_settings.get("daily_file_count", 0) > 0 else "Unlimited"

    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 **UPGRADE TO PREMIUM** 💎\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Unlock the full power of 𝕏TV. Say goodbye to limits and hello to exclusive features!\n\n"
    )

    text += (
        f"**⭐ Premium Standard**\n"
        f"> 📂 **Daily Egress Limit:** `{std_egress}`\n"
        f"> 📑 **Daily File Limit:** `{std_files}`\n"
    )
    if standard_settings.get("features", {}).get("priority_queue"):
        text += f"> 🚀 **Priority Queue:** `Enabled`\n"
    if standard_settings.get("features", {}).get("xtv_pro_4gb"):
        text += f"> ⚡ **XTV Pro 4GB Bypass:** `Enabled`\n"

    text += f"> 🛠️ **File Converter:** `Included`\n"
    text += f"> 🎨 **Image Watermarker:** `Included`\n"
    text += f"\n**Price:** `{std_usd}`\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    if deluxe_enabled:
        dlx_mb = deluxe_settings.get('daily_egress_mb', 0)
        dlx_egress = format_egress(dlx_mb) if dlx_mb > 0 else "Unlimited"
        dlx_files = f"{deluxe_settings.get('daily_file_count', 0)}" if deluxe_settings.get("daily_file_count", 0) > 0 else "Unlimited"

        text += (
            f"**💎 Premium Deluxe**\n"
            f"> 📂 **Daily Egress Limit:** `{dlx_egress}`\n"
            f"> 📑 **Daily File Limit:** `{dlx_files}`\n"
        )
        if deluxe_settings.get("features", {}).get("priority_queue"):
            text += f"> 🚀 **Priority Queue:** `Enabled`\n"
        if deluxe_settings.get("features", {}).get("xtv_pro_4gb"):
            text += f"> ⚡ **XTV Pro 4GB Bypass:** `Enabled`\n"

        text += f"> 🛠️ **File Converter:** `Included`\n"
        text += f"> 🎨 **Image Watermarker:** `Included`\n"
        text += f"> 📽️ **4K Upscaling/Enhancement:** `Exclusive`\n"
        text += f"\n**Price:** `{dlx_usd}`\n"
        text += f"━━━━━━━━━━━━━━━━━━━━\n"

    buttons = []

    if trial_enabled and trial_days > 0 and not trial_claimed:
        text += f"\n🎁 *Special Offer: You are eligible for a {trial_days}-Day Trial!*\n"
        buttons.append([InlineKeyboardButton("🎁 Claim Free Trial", callback_data="claim_trial")])

    buttons.append([InlineKeyboardButton("⭐ Purchase Standard", callback_data="buy_premium_dur_standard")])

    if deluxe_enabled:
        buttons.append([InlineKeyboardButton("💎 Purchase Deluxe", callback_data="buy_premium_dur_deluxe")])

    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^claim_trial$"))
async def handle_claim_trial(client, callback_query):
    if not is_public_mode():
        await callback_query.answer("Disabled in this mode.", show_alert=True)
        return

    user_id = callback_query.from_user.id
    user = await db.get_user(user_id)
    config = await db.get_public_config()

    premium_system_enabled = config.get("premium_system_enabled", False)
    trial_enabled = config.get("premium_trial_enabled", False)
    trial_days = config.get("premium_trial_days", 0)

    if not premium_system_enabled or not trial_enabled or trial_days <= 0:
        await callback_query.answer("Trial is not available right now.", show_alert=True)
        return

    if user and user.get("trial_claimed", False):
        await callback_query.answer("You have already claimed your trial.", show_alert=True)
        return

    if user and user.get("is_premium"):
        await callback_query.answer("You already have an active premium subscription.", show_alert=True)
        return

    await db.add_premium_user(user_id, trial_days)
    await db.users.update_one({"_id": user_id}, {"$set": {"trial_claimed": True}})

    await callback_query.message.edit_text(
        f"🎉 **Trial Claimed Successfully!**\n\n"
        f"You now have {trial_days} days of **Premium Standard** access. Enjoy enhanced limits and priority processing!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Start Using", url=f"https://t.me/{client.me.username}?start=start")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^premium_settings$"))
async def handle_premium_settings(client, callback_query):
    await callback_query.answer("Custom Defaults settings coming soon!", show_alert=True)

@Client.on_callback_query(filters.regex(r"^premium_priority$"))
async def handle_premium_priority(client, callback_query):
    await callback_query.answer("Priority Queue settings coming soon!", show_alert=True)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
