import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import db
from config import Config

def is_public_mode():
    return Config.PUBLIC_MODE
from utils.currency import convert_to_usd_str
from utils.help_builder import format_egress


def get_features_display(settings, global_toggles):
    features = settings.get("features", {})
    display_lines = []

    # Core Perks (Static)
    if features.get("priority_queue"):
        display_lines.append("🚀 Priority Queue")
    if features.get("batch_sharing"):
        display_lines.append("🔗 Batch Sharing")
    if features.get("xtv_pro_4gb"):
        display_lines.append("⚡ XTV Pro 4GB Bypass")

    # Media Tools (Dynamic Cascade)
    # Only advertise if enabled in plan AND disabled globally
    if features.get("subtitle_extractor") and not global_toggles.get("subtitle_extractor", True):
        display_lines.append("💬 Subtitle Extractor")
    if features.get("watermarker") and not global_toggles.get("watermarker", True):
        display_lines.append("🎨 Image Watermarker")
    if features.get("file_converter") and not global_toggles.get("file_converter", True):
        display_lines.append("🔄 File Converter")
    if features.get("audio_editor") and not global_toggles.get("audio_editor", True):
        display_lines.append("🎵 Audio Editor")
    if features.get("youtube_tool") and not global_toggles.get("youtube_tool", True):
        display_lines.append("▶️ YouTube Tool")
    if features.get("torrent_downloader") and not global_toggles.get("torrent_downloader", True):
        display_lines.append("🧲 Torrent Downloader")

    return "\n".join(display_lines) if display_lines else "None"

# --- Helpers ---

async def generate_premium_dashboard(user_id, client):
    """
    Returns (text, reply_markup, error_message).
    If error_message is not None, the calling function should display it and abort.
    """
    user = await db.get_user(user_id)
    config = await db.get_public_config()

    premium_system_enabled = config.get("premium_system_enabled", False)

    if not premium_system_enabled:
        return None, None, "Premium System is currently disabled."

    is_prem = False
    current_plan = "standard"
    if user:
        exp = user.get("premium_expiry")
        if user.get("is_premium") and (exp is None or exp > time.time()):
            is_prem = True
            current_plan = user.get("premium_plan", "standard")

    limits = config.get("myfiles_limits", {}).get(current_plan, {})
    perm_limit = limits.get("permanent_limit", 50)
    folder_limit = limits.get("folder_limit", 5)

    perm_str = str(perm_limit) if perm_limit != -1 else "Unlimited"
    folder_str = str(folder_limit) if folder_limit != -1 else "Unlimited"

    if is_prem:
        exp_text = "Lifetime"
        if user.get("premium_expiry"):
            exp_text = datetime.fromtimestamp(user.get("premium_expiry")).strftime('%Y-%m-%d %H:%M')

        plan_display = "⭐ Premium Standard" if current_plan == "standard" else "💎 Premium Deluxe"
        status_emoji = "⭐" if current_plan == "standard" else "💎"

        dash_text = (
            f"{status_emoji} **YOUR PREMIUM DASHBOARD**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> **Plan:** `{plan_display}`\n"
            f"> **Status:** `Active ✅`\n"
            f"> **Expiry:** `{exp_text}`\n\n"
            f"**MyFiles Limits:**\n"
            f"> **Permanent Files:** `Up to {perm_str}`\n"
            f"> **Custom Folders:** `Up to {folder_str}`\n\n"
            f"✨ __Thank you for supporting 𝕏TV! Enjoy your exclusive benefits, priority processing, and enhanced limits.__\n\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        buttons = [
            [InlineKeyboardButton("⚙️ Custom Defaults", callback_data="premium_settings")],
            [InlineKeyboardButton("📁 MyFiles Storage", callback_data="myfiles_main")],
            [InlineKeyboardButton("🚀 Priority Queue", callback_data="premium_priority")],
            [InlineKeyboardButton("🔄 Refresh Status", callback_data="user_premium_menu")]
        ]

        return dash_text, InlineKeyboardMarkup(buttons), None

    trial_enabled = config.get("premium_trial_enabled", False)
    trial_days = config.get("premium_trial_days", 0)
    trial_claimed = user.get("trial_claimed", False) if user else False

    deluxe_enabled = config.get("premium_deluxe_enabled", False)

    standard_settings = config.get("premium_standard", {})
    deluxe_settings = config.get("premium_deluxe", {})

    std_usd = await convert_to_usd_str(standard_settings.get("price_string", "0 USD"))
    dlx_usd = await convert_to_usd_str(deluxe_settings.get("price_string", "0 USD"))

    std_mb = standard_settings.get('daily_egress_mb', 0)
    std_egress = format_egress(std_mb) if std_mb > 0 else "Unlimited"
    std_files = f"{standard_settings.get('daily_file_count', 0)}" if standard_settings.get("daily_file_count", 0) > 0 else "Unlimited"

    myfiles_limits = config.get("myfiles_limits", {})
    std_limits = myfiles_limits.get("standard", {})
    dlx_limits = myfiles_limits.get("deluxe", {})

    std_perm_limit = std_limits.get("permanent_limit", 50)
    std_perm_str = str(std_perm_limit) if std_perm_limit != -1 else "Unlimited"
    std_folder_limit = std_limits.get("folder_limit", 5)
    std_folder_str = str(std_folder_limit) if std_folder_limit != -1 else "Unlimited"

    dlx_perm_limit = dlx_limits.get("permanent_limit", -1)
    dlx_perm_str = str(dlx_perm_limit) if dlx_perm_limit != -1 else "Unlimited"
    dlx_folder_limit = dlx_limits.get("folder_limit", -1)
    dlx_folder_str = str(dlx_folder_limit) if dlx_folder_limit != -1 else "Unlimited"

    global_toggles = await db.get_feature_toggles()

    text = (
        f"💎 **UPGRADE TO PREMIUM** 💎\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Unlock the full power of 𝕏TV. Say goodbye to limits!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    text += (
        f"⭐ **Premium Standard**\n\n"
        f"📂 Daily Egress Limit: `{std_egress}`\n"
        f"📑 Daily File Limit: `{std_files}`\n"
        f"🗂 MyFiles Folders: `{std_folder_str}`\n"
        f"📦 Perm Storage: `{std_perm_str}`\n\n"
        f"**Perks:**\n"
    )

    std_perks = get_features_display(standard_settings, global_toggles)
    text += f"{std_perks}\n\n"
    text += f"**Price:** `{std_usd}`\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n"

    if deluxe_enabled:
        dlx_mb = deluxe_settings.get('daily_egress_mb', 0)
        dlx_egress = format_egress(dlx_mb) if dlx_mb > 0 else "Unlimited"
        dlx_files = f"{deluxe_settings.get('daily_file_count', 0)}" if deluxe_settings.get("daily_file_count", 0) > 0 else "Unlimited"

        text += (
            f"💎 **Premium Deluxe**\n\n"
            f"📂 Daily Egress Limit: `{dlx_egress}`\n"
            f"📑 Daily File Limit: `{dlx_files}`\n"
            f"🗂 MyFiles Folders: `{dlx_folder_str}`\n"
            f"📦 Perm Storage: `{dlx_perm_str}`\n\n"
            f"**Perks:**\n"
            f"(All Standard Perks, plus:)\n"
        )

        # Calculate diff for deluxe specific perks to avoid repeating standard
        dlx_perks = get_features_display(deluxe_settings, global_toggles)
        std_perks_list = std_perks.split('\n')
        dlx_only_perks = [p for p in dlx_perks.split('\n') if p not in std_perks_list]

        if dlx_only_perks:
            text += "\n".join(dlx_only_perks) + "\n"

        text += f"\n**Price:** `{dlx_usd}`\n"
        text += f"━━━━━━━━━━━━━━━━━━━━\n"

    buttons = []

    plan_buttons = []
    plan_buttons.append(InlineKeyboardButton("⭐ Buy Standard", callback_data="buy_premium_dur_standard"))
    if deluxe_enabled:
        plan_buttons.append(InlineKeyboardButton("💎 Buy Deluxe", callback_data="buy_premium_dur_deluxe"))
    buttons.append(plan_buttons)

    if trial_enabled and trial_days > 0 and not trial_claimed:
        buttons.append([InlineKeyboardButton("🎁 Claim Free Trial", callback_data="claim_trial")])

    return text, InlineKeyboardMarkup(buttons), None

# --- Handlers ---

@Client.on_message(filters.command("premium") & filters.private)
async def handle_premium_command(client, message):
    if not is_public_mode():
        return

    text, markup, err = await generate_premium_dashboard(message.from_user.id, client)
    if err:
        await message.reply_text(f"❌ **{err}**")
        return

    await message.reply_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^user_premium_menu$"))
async def handle_user_premium_menu(client, callback_query):
    if not is_public_mode():
        await callback_query.answer("Disabled in this mode.", show_alert=True)
        return

    text, markup, err = await generate_premium_dashboard(callback_query.from_user.id, client)
    if err:
        await callback_query.answer(err, show_alert=True)
        return

    await callback_query.message.edit_text(text, reply_markup=markup)

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
