from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from utils.log import get_logger
from utils.state import clear_session

logger = get_logger("plugins.start")
logger.info("Loading plugins.start...")

from database import db
from utils.auth import check_force_sub

# Group 0 (Default) - Runs before flow (Group 2)
# Using regex for explicit command matching to avoid any filter ambiguity
@Client.on_message(filters.regex(r"^/(start|new)") & filters.private, group=0)
async def handle_start_command_unique(client, message):
    user_id = message.from_user.id
    logger.info(f"CMD received: {message.text} from {user_id}")

    if not Config.PUBLIC_MODE:
        if not (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS):
            logger.warning(f"Unauthorized access by {user_id}")
            return
        bot_name = "**XTV Rename Bot**"
        community_name = "official XTV"
    else:
        # Public Mode checks
        if not await check_force_sub(client, user_id):
            config = await db.get_public_config()
            invite_link = config.get("force_sub_link") or config.get("force_sub_channel", "")
            community_name = config.get("community_name", "Our Community")

            await message.reply_text(
                f"👋 **Welcome to {community_name}!**\n\n"
                f"To use the **{config.get('bot_name', 'XTV Rename Bot')}** and all its features, you need to become a member of our community channel first.\n\n"
                "**How to get started:**\n"
                "1️⃣ Click the button below to join the channel.\n"
                "2️⃣ Come back to this bot.\n"
                "3️⃣ Send or forward any file to start renaming!\n\n"
                "🔒 *This is required to prevent spam and keep the bot free for everyone.*",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Our Community Channel", url=invite_link)]
                ])
            )
            return

        config = await db.get_public_config()
        bot_name = f"**{config.get('bot_name', 'XTV Rename Bot')}**"
        community_name = config.get("community_name", "Our Community")

    await message.reply_text(
        f"{bot_name}\n\n"
        f"Welcome to the {community_name} file renaming tool.\n"
        "This bot provides professional renaming and metadata management.\n\n"
        "💡 **Tip:** You don't need to click anything to begin! Simply send or forward a file directly to me, and I will auto-detect the details.\n\n"
        "Click below to start manually or to view the guide.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Start Renaming Manually", callback_data="start_renaming")],
            [InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")]
        ])
    )

@Client.on_message(filters.command("help") & filters.private, group=0)
async def handle_help_command_unique(client, message):
    user_id = message.from_user.id
    logger.info(f"CMD received: {message.text} from {user_id}")

    await message.reply_text(
        "**📖 Help & Guide**\n\n"
        "Welcome to the Rename Bot Guide!\n"
        "Whether you are organizing a massive media library of popular series and movies, "
        "or just want to rename and manage your **personal home videos** and files, I can help!\n\n"
        "Please select a topic below to learn more:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 How to Use", callback_data="help_how_to_use")],
            [InlineKeyboardButton("🤖 Auto-Detect Magic", callback_data="help_auto_detect")],
            [InlineKeyboardButton("📁 Personal Files & Home Videos", callback_data="help_personal")],
            [InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")],
            [InlineKeyboardButton("❌ Close", callback_data="help_close")]
        ])
    )

@Client.on_message(filters.command("end") & filters.private, group=0)
async def handle_end_command_unique(client, message):
    user_id = message.from_user.id
    logger.info(f"CMD received: {message.text} from {user_id}")
    clear_session(user_id)
    await message.reply_text(
        "**Current Task Cancelled** ❌\n\n"
        "Your progress has been cleared.\n"
        "You can simply send me a file anytime to start over, or use the buttons below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Start Renaming Manually", callback_data="start_renaming")],
            [InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^help_"))
async def handle_help_callbacks(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    logger.info(f"Help callback received: {data} from {user_id}")

    back_button = [[InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_guide")]]

    if data == "help_guide":
        await callback_query.message.edit_text(
            "**📖 Help & Guide**\n\n"
            "Welcome to the Rename Bot Guide!\n"
            "Whether you are organizing a massive media library of popular series and movies, "
            "or just want to rename and manage your **personal home videos** and files, I can help!\n\n"
            "Please select a topic below to learn more:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛠 How to Use", callback_data="help_how_to_use")],
                [InlineKeyboardButton("🤖 Auto-Detect Magic", callback_data="help_auto_detect")],
                [InlineKeyboardButton("📁 Personal Files & Home Videos", callback_data="help_personal")],
                [InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")],
                [InlineKeyboardButton("❌ Close", callback_data="help_close")]
            ])
        )
    elif data == "help_how_to_use":
        await callback_query.message.edit_text(
            "**🛠 How to Use**\n\n"
            "1. **The Quick Way**: Simply send or forward any media file directly to me. I will scan the file and start the renaming process.\n\n"
            "2. **The Manual Way**: Press the 'Start Renaming Manually' button or use `/start` to begin the guided process.\n\n"
            "3. **Cancel Anytime**: Made a mistake? Use `/end` or the Cancel button at any point to reset your progress.",
            reply_markup=InlineKeyboardMarkup(back_button)
        )
    elif data == "help_auto_detect":
        await callback_query.message.edit_text(
            "**🤖 Auto-Detect Magic**\n\n"
            "When you send a file directly, my Auto-Detection Matrix scans the filename.\n\n"
            "• **Series/Movies:** I look for the title, year, season, episode, and quality.\n"
            "• **Smart Metadata:** If it's a known movie or series, I pull official posters and metadata from TMDb!\n\n"
            "You always get a chance to confirm or correct the details before processing begins.",
            reply_markup=InlineKeyboardMarkup(back_button)
        )
    elif data == "help_personal":
        await callback_query.message.edit_text(
            "**📁 Personal Files & Home Videos**\n\n"
            "Not just for popular movies! Many users manage their personal home videos, tutorials, or family archives.\n\n"
            "**How?**\n"
            "1. Send your personal video.\n"
            "2. When prompted with TMDb search results, select **'Skip / Manual'** or similar option if it's not a public release.\n"
            "3. You can still set custom names, add your own thumbnails, and organize them exactly how you want them!",
            reply_markup=InlineKeyboardMarkup(back_button)
        )
    elif data == "help_settings":
        if Config.PUBLIC_MODE:
            text = (
                "**⚙️ Settings & Info**\n\n"
                "Customize how your files are named and processed.\n\n"
                "• Use the `/settings` command to access your personal settings.\n"
                "• Configure custom **Filename Templates** (e.g., `{Title} ({Year}) [{Quality}]`).\n"
                "• Set your own **Default Thumbnail** or disable it.\n"
                "• Customize **Caption Templates** and Metadata.\n"
                "• Use `/info` to see details about this bot and support contact."
            )
        else:
            text = (
                "**⚙️ Settings & Admin**\n\n"
                "Customize how your files are named and processed.\n\n"
                "• Use the `/admin` command to access advanced settings.\n"
                "• Configure custom **Filename Templates** (e.g., `{Title} ({Year}) [{Quality}]`).\n"
                "• Set a **Default Thumbnail** for all your uploads.\n"
                "• Customize **Caption Templates** and more!"
            )
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "help_close":
        await callback_query.message.delete()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
