# --- Imports ---
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from utils.log import get_logger
from utils.state import clear_session

logger = get_logger("plugins.start")
logger.info("Loading plugins.start...")

from database import db
from utils.auth import check_force_sub
from utils.gate import send_force_sub_gate, check_and_send_welcome
from plugins.force_sub_handler import send_starter_setup_message

@Client.on_message(filters.regex(r"^/(start|new)") & filters.private, group=0)

# --- Handlers ---
async def handle_start_command_unique(client, message):
    user_id = message.from_user.id
    logger.debug(f"CMD received: {message.text} from {user_id}")

    if not Config.PUBLIC_MODE:
        if not (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS):
            logger.warning(f"Unauthorized access by {user_id}")
            return
        bot_name = "**𝕏TV MediaStudio™**"
        community_name = "official XTV"
    else:
        config = await db.get_public_config()
        if not await check_force_sub(client, user_id):
            await send_force_sub_gate(client, message, config)
            return

        await check_and_send_welcome(client, message, config)

        bot_name = f"**{config.get('bot_name', '𝕏TV MediaStudio™')}**"
        community_name = config.get("community_name", "Our Community")

    is_new_user = False
    user_usage = await db.get_user_usage(user_id)
    if not user_usage:
        is_new_user = True

    if Config.PUBLIC_MODE:
        has_setup = await db.has_completed_setup(user_id)
        if not has_setup:
            await db.ensure_user(user_id=message.from_user.id, first_name=message.from_user.first_name, username=message.from_user.username, last_name=message.from_user.last_name, language_code=message.from_user.language_code, is_bot=message.from_user.is_bot)
            await send_starter_setup_message(client, user_id, message.from_user.first_name)
            return

    await db.ensure_user(
        user_id=message.from_user.id,
        first_name=message.from_user.first_name,
        username=message.from_user.username,
        last_name=message.from_user.last_name,
        language_code=message.from_user.language_code,
        is_bot=message.from_user.is_bot
    )

    toggles = await db.get_feature_toggles()
    show_other = toggles.get("audio_editor", True) or toggles.get("file_converter", True) or toggles.get("watermarker", True) or toggles.get("subtitle_extractor", True)

    is_premium_user = False
    plan_display = "Standard"
    status_emoji = "⭐"

    if Config.PUBLIC_MODE and not show_other:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            is_premium_user = True
            plan_name = user_doc.get("premium_plan", "standard")
            plan_display = "Deluxe" if plan_name == "deluxe" else "Standard"
            status_emoji = "💎" if plan_name == "deluxe" else "⭐"
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                pf = plan_settings.get("features", {})
                if pf.get("audio_editor", True) or pf.get("file_converter", True) or pf.get("watermarker", True) or pf.get("subtitle_extractor", True):
                    show_other = True

    if Config.PUBLIC_MODE and show_other and not is_premium_user:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            is_premium_user = True
            plan_name = user_doc.get("premium_plan", "standard")
            plan_display = "Deluxe" if plan_name == "deluxe" else "Standard"
            status_emoji = "💎" if plan_name == "deluxe" else "⭐"

    buttons = [
        [InlineKeyboardButton("📁 Rename / Tag Media", callback_data="start_renaming")]
    ]
    if show_other:
        buttons.append([InlineKeyboardButton("✨ Other Features", callback_data="other_features_menu")])
    if Config.PUBLIC_MODE and is_premium_user:
        buttons.append([InlineKeyboardButton("💎 Premium Dashboard", callback_data="user_premium_menu")])
    buttons.append([InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")])

    if is_premium_user:
        await message.reply_text(
            f"{status_emoji} **Welcome back, {message.from_user.first_name}!** {status_emoji}\n\n"
            f"> Your **Premium {plan_display}** status is Active ✅\n\n"
            f"I am {bot_name}, your advanced media processing engine by the {community_name}.\n\n"
            f"**Quick Actions:**\n"
            f"• Send me any media file to begin priority processing\n"
            f"• Explore your premium tools in the dashboard below\n\n"
            f"Thank you for being a valued Premium member!",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        await message.reply_text(
            f"{bot_name}\n\n"
            f"Welcome to the {community_name} media processing and management bot.\n"
            f"This bot provides professional tools to organize and modify your files.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 **Tip:** You don't need to click anything to begin!\n"
            f"Simply send or forward a file directly to me, and I will auto-detect the details.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Click below to start manually or to view the guide.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

@Client.on_message(filters.command(["r", "rename"]) & filters.private, group=0)
async def handle_rename_command(client, message):
    user_id = message.from_user.id
    from plugins.flow import handle_start_renaming

    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "start_renaming"

        async def answer(self, *args, **kwargs):
            pass

    mock_cb = MockCallbackQuery(message)
    msg = await message.reply_text("Loading menu...")
    mock_cb.message = msg
    await handle_start_renaming(client, mock_cb)

@Client.on_message(filters.command(["g", "general"]) & filters.private, group=0)
async def handle_general_command(client, message):
    user_id = message.from_user.id
    from plugins.flow import handle_type_general

    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "type_general"

        async def answer(self, *args, **kwargs):
            pass

    mock_cb = MockCallbackQuery(message)
    msg = await message.reply_text("Loading general mode...")
    mock_cb.message = msg
    await handle_type_general(client, mock_cb)

@Client.on_message(filters.command(["a", "audio"]) & filters.private, group=0)
async def handle_audio_command(client, message):
    user_id = message.from_user.id

    toggles = await db.get_feature_toggles()
    allowed = toggles.get("audio_editor", True)

    if Config.PUBLIC_MODE and not allowed:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                if plan_settings.get("features", {}).get("audio_editor", False):
                    allowed = True

    if not allowed:
        await message.reply_text("❌ This feature is currently disabled by the Admin.")
        return

    from plugins.flow import handle_audio_editor_menu

    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "audio_editor_menu"

        async def answer(self, *args, **kwargs):
            pass

    mock_cb = MockCallbackQuery(message)
    msg = await message.reply_text("Loading audio editor...")
    mock_cb.message = msg
    await handle_audio_editor_menu(client, mock_cb)

@Client.on_message(filters.command(["p", "personal"]) & filters.private, group=0)
async def handle_personal_command(client, message):
    user_id = message.from_user.id
    from plugins.flow import handle_type_personal

    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "type_personal_file"

        async def answer(self, *args, **kwargs):
            pass

    mock_cb = MockCallbackQuery(message)
    msg = await message.reply_text("Loading personal mode...")
    mock_cb.message = msg
    await handle_type_personal(client, mock_cb)

@Client.on_message(filters.command(["c", "convert"]) & filters.private, group=0)
async def handle_convert_command(client, message):
    user_id = message.from_user.id

    toggles = await db.get_feature_toggles()
    allowed = toggles.get("file_converter", True)

    if Config.PUBLIC_MODE and not allowed:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                if plan_settings.get("features", {}).get("file_converter", False):
                    allowed = True

    if not allowed:
        await message.reply_text("❌ This feature is currently disabled by the Admin.")
        return

    from plugins.flow import handle_file_converter_menu

    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "file_converter_menu"

        async def answer(self, *args, **kwargs):
            pass

    mock_cb = MockCallbackQuery(message)
    msg = await message.reply_text("Loading converter...")
    mock_cb.message = msg
    await handle_file_converter_menu(client, mock_cb)

@Client.on_message(filters.command(["w", "watermark"]) & filters.private, group=0)
async def handle_watermark_command(client, message):
    user_id = message.from_user.id

    toggles = await db.get_feature_toggles()
    allowed = toggles.get("watermarker", True)

    if Config.PUBLIC_MODE and not allowed:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                if plan_settings.get("features", {}).get("watermarker", False):
                    allowed = True

    if not allowed:
        await message.reply_text("❌ This feature is currently disabled by the Admin.")
        return

    from plugins.flow import handle_watermarker_menu

    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "watermarker_menu"

        async def answer(self, *args, **kwargs):
            pass

    mock_cb = MockCallbackQuery(message)
    msg = await message.reply_text("Loading watermarker...")
    mock_cb.message = msg
    await handle_watermarker_menu(client, mock_cb)

@Client.on_message(filters.command(["s", "subtitle"]) & filters.private, group=0)
async def handle_subtitle_command(client, message):
    user_id = message.from_user.id

    toggles = await db.get_feature_toggles()
    allowed = toggles.get("subtitle_extractor", True)

    if Config.PUBLIC_MODE and not allowed:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                if plan_settings.get("features", {}).get("subtitle_extractor", False):
                    allowed = True

    if not allowed:
        await message.reply_text("❌ This feature is currently disabled by the Admin.")
        return

    from plugins.flow import handle_subtitle_extractor_menu

    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "subtitle_extractor_menu"

        async def answer(self, *args, **kwargs):
            pass

    mock_cb = MockCallbackQuery(message)
    msg = await message.reply_text("Loading subtitle extractor...")
    mock_cb.message = msg
    await handle_subtitle_extractor_menu(client, mock_cb)

@Client.on_message(filters.command("help") & filters.private, group=0)
async def handle_help_command_unique(client, message):
    user_id = message.from_user.id
    logger.debug(f"CMD received: {message.text} from {user_id}")

    await message.reply_text(
        "**📖 MediaStudio Guide**\n\n"
        "> Welcome to your complete reference manual.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Whether you are organizing a massive media library of popular series and movies, "
        "or just want to process and manage your **personal media** and files, I can help!\n\n"
        "Please select a topic below to explore the guide:",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🛠 All Tools & Features", callback_data="help_tools")],
                [InlineKeyboardButton("📁 File Management", callback_data="help_file_management")],
                [InlineKeyboardButton("🤖 Auto-Detect Magic", callback_data="help_auto_detect")],
                [InlineKeyboardButton("📄 Personal & General Mode", callback_data="help_general")],
                [InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")],
                [InlineKeyboardButton("❌ Close", callback_data="help_close")],
            ]
        ),
    )

@Client.on_message(filters.command("end") & filters.private, group=0)
async def handle_end_command_unique(client, message):
    user_id = message.from_user.id
    logger.debug(f"CMD received: {message.text} from {user_id}")
    clear_session(user_id)
    toggles = await db.get_feature_toggles()
    show_other = toggles.get("audio_editor", True) or toggles.get("file_converter", True) or toggles.get("watermarker", True) or toggles.get("subtitle_extractor", True)

    if Config.PUBLIC_MODE and not show_other:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                pf = plan_settings.get("features", {})
                if pf.get("audio_editor", True) or pf.get("file_converter", True) or pf.get("watermarker", True) or pf.get("subtitle_extractor", True):
                    show_other = True

    buttons = [
        [InlineKeyboardButton("🎬 Start Renaming Manually", callback_data="start_renaming")]
    ]
    if show_other:
        buttons.append([InlineKeyboardButton("✨ Other Features", callback_data="other_features_menu")])
    buttons.append([InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")])

    await message.reply_text(
        "**Current Task Cancelled** ❌\n\n"
        "Your progress has been cleared.\n"
        "You can simply send me a file anytime to start over, or use the buttons below.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

from utils.logger import debug

debug("✅ Loaded handler: help_callback")

@Client.on_callback_query(filters.regex(r"^other_features_menu$"))
async def handle_other_features_menu(client, callback_query):
    await callback_query.answer()
    toggles = await db.get_feature_toggles()
    user_id = callback_query.from_user.id

    pf = {}
    if Config.PUBLIC_MODE:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                pf = plan_settings.get("features", {})

    buttons = []
    if toggles.get("audio_editor", True) or pf.get("audio_editor", False):
        buttons.append([InlineKeyboardButton("🎵 Audio Metadata Editor", callback_data="audio_editor_menu")])
    if toggles.get("file_converter", True) or pf.get("file_converter", False):
        buttons.append([InlineKeyboardButton("🔀 File Converter", callback_data="file_converter_menu")])
    if toggles.get("watermarker", True) or pf.get("watermarker", False):
        buttons.append([InlineKeyboardButton("© Image Watermarker", callback_data="watermarker_menu")])
    if toggles.get("subtitle_extractor", True) or pf.get("subtitle_extractor", False):
        buttons.append([InlineKeyboardButton("📝 Subtitle Extractor", callback_data="subtitle_extractor_menu")])

    buttons.append([InlineKeyboardButton("❌ Close", callback_data="help_close")])

    try:
        await callback_query.message.edit_text(
            "**✨ Other Features**\n\n"
            "Select an additional tool below:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except MessageNotModified:
        pass

@Client.on_callback_query(filters.regex(r"^help_"))
async def handle_help_callbacks(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = callback_query.data
    debug(f"Help callback received: {data} from {user_id}")

    back_button = [
        [InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_guide")]
    ]

    if data == "help_guide":
        try:
            await callback_query.message.edit_text(
                "**📖 MediaStudio Guide**\n\n"
                "> Welcome to your complete reference manual.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Whether you are organizing a massive media library of popular series and movies, "
                "or just want to process and manage your **personal media** and files, I can help!\n\n"
                "Please select a topic below to explore the guide:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🛠 All Tools & Features", callback_data="help_tools")],
                        [InlineKeyboardButton("📁 File Management", callback_data="help_file_management")],
                        [InlineKeyboardButton("🤖 Auto-Detect Magic", callback_data="help_auto_detect")],
                        [InlineKeyboardButton("📄 Personal & General Mode", callback_data="help_general")],
                        [InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")],
                        [InlineKeyboardButton("❌ Close", callback_data="help_close")],
                    ]
                ),
            )
        except MessageNotModified:
            pass

    elif data == "help_tools":
        try:
            await callback_query.message.edit_text(
                "**🛠 All Tools & Features**\n\n"
                "> A complete suite of media processing tools.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Here is an overview of everything I can do. Click on any tool below to learn more about how to use it, what it does, and any shortcuts available.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("📁 Rename & Tag Media", callback_data="help_tool_rename")],
                        [InlineKeyboardButton("🎵 Audio Editor", callback_data="help_tool_audio"),
                         InlineKeyboardButton("🔀 File Converter", callback_data="help_tool_convert")],
                        [InlineKeyboardButton("© Image Watermarker", callback_data="help_tool_watermark"),
                         InlineKeyboardButton("📝 Subtitle Extractor", callback_data="help_tool_subtitle")],
                        [InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_guide")]
                    ]
                )
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_tool_"):
        tool = data.split("_")[-1]
        back_to_tools = [[InlineKeyboardButton("🔙 Back to Tools", callback_data="help_tools")]]

        if tool == "rename":
            text = (
                "**📁 Rename & Tag Media**\n\n"
                "> The core feature of the bot.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**How to Use:**\n"
                "Simply send any file to the bot. I will automatically scan the name and extract metadata!\n\n"
                "**🧠 Smart Media Mode vs ⚡ Quick Rename Mode:**\n"
                "• **Smart Media Mode:** The bot attempts to parse Movie/Series details and fetches official TMDb posters and metadata. Ideal for TV shows and Movies.\n"
                "• **Quick Rename Mode:** Bypasses auto-detection completely, jumping straight into renaming without pulling metadata. Best for personal files or general media.\n\n"
                "**Shortcuts:**\n"
                "• `/r` or `/rename` - Start the manual rename wizard.\n"
                "• `/g` or `/general` - Open General (Quick Rename) mode directly.\n"
                "• `/p` or `/personal` - Open Personal Files mode."
            )
        elif tool == "audio":
            text = (
                "**🎵 Audio Metadata Editor**\n\n"
                "> Perfect for your music collection.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Allows you to modify the internal ID3 tags of MP3, FLAC, and other audio formats.\n\n"
                "**Features:**\n"
                "• Edit the Title, Artist, and Album.\n"
                "• Upload and embed custom Cover Art.\n"
                "• Keeps your music library looking pristine on any device.\n\n"
                "**Shortcut:** `/a` or `/audio`."
            )
        elif tool == "convert":
            text = (
                "**🔀 File Converter**\n\n"
                "> Change formats instantly.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Converts media files from one container format to another.\n\n"
                "**Examples:**\n"
                "• Convert an unsupported `.mkv` into a universally compatible `.mp4`.\n"
                "• Transcode heavy `.webm` files.\n"
                "• Fast stream-copying to ensure quality isn't lost.\n\n"
                "**Shortcut:** `/c` or `/convert`."
            )
        elif tool == "watermark":
            text = (
                "**© Image Watermarker**\n\n"
                "> Brand your media.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Adds a custom image watermark (like a logo) to your videos or images.\n\n"
                "**Features:**\n"
                "• Fully customize the position (Top Left, Bottom Right, Center, etc.).\n"
                "• Adjust the size of the watermark relative to the video.\n"
                "• Protect your original content from being stolen.\n\n"
                "**Shortcut:** `/w` or `/watermark`."
            )
        elif tool == "subtitle":
            text = (
                "**📝 Subtitle Extractor**\n\n"
                "> Pull subs from MKV files.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Extracts embedded subtitle tracks from video files and gives them to you as standalone text files.\n\n"
                "**Features:**\n"
                "• Supports multi-track videos (select which language track you want to extract).\n"
                "• Outputs in standard formats like `.srt` or `.ass`.\n"
                "• Perfect for downloading subtitles to use on a different video release.\n\n"
                "**Shortcut:** `/s` or `/subtitle`."
            )

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_to_tools))
        except MessageNotModified:
            pass

    elif data == "help_file_management":
        try:
            await callback_query.message.edit_text(
                "**📁 File Management (/myfiles)**\n\n"
                "> Your personal cloud storage.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Use the `/myfiles` command to access your digital storage locker.\n\n"
                "• **Temporary Files:** Files you have recently processed are saved here temporarily (based on your plan's expiry limits).\n"
                "• **Permanent Slots:** You can pin important files to keep them forever! (Limit depends on plan).\n"
                "• **Custom Folders:** Organize your permanent files into categories.",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_auto_detect":
        try:
            await callback_query.message.edit_text(
                "**🤖 Auto-Detect Magic**\n\n"
                "> Automatic Metadata Lookup.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "When you send a file directly, my Auto-Detection Matrix scans the filename.\n\n"
                "• **Series/Movies:** I look for the title, year, season, episode, and quality.\n"
                "• **Smart Metadata:** If it's a known movie or series, I pull official posters and metadata from TMDb!\n\n"
                "You always get a chance to confirm or correct the details before processing begins.",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_general":
        try:
            await callback_query.message.edit_text(
                "**📄 Personal & General Mode**\n\n"
                "> Bypass the smart scanners.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**📁 Personal Files & Home Videos**\n"
                "1. Send your personal video.\n"
                "2. When prompted with TMDb results, select **'Skip / Manual'**.\n"
                "3. Set custom names and thumbnails for things not on TMDb.\n\n"
                "**📄 General Mode & Variables**\n"
                "General mode bypasses metadata completely. Use `/g`.\n"
                "• `{filename}` - Original filename\n"
                "• `{Season_Episode}` - Ex: S01E01\n"
                "• `{Quality}` - Ex: 1080p\n"
                "• `{Year}`, `{Title}`\n"
                "*(Extensions are always added automatically)*",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_settings":
        if Config.PUBLIC_MODE:
            text = (
                "**⚙️ Settings & Info**\n\n"
                "> Customize your experience.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Use the `/settings` command to access your personal settings.\n"
                "• Configure custom **Filename Templates** (e.g., `{Title} ({Year}) [{Quality}]`).\n"
                "• Set your own **Default Thumbnail** or disable it.\n"
                "• Customize **Caption Templates** and Metadata.\n"
                "• Use `/info` to see details about this bot and support contact."
            )
        else:
            text = (
                "**⚙️ Settings & Admin**\n\n"
                "> Customize your experience.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Use the `/admin` command to access advanced settings.\n"
                "• Configure custom **Filename Templates** (e.g., `{Title} ({Year}) [{Quality}]`).\n"
                "• Set a **Default Thumbnail** for all your uploads.\n"
                "• Customize **Caption Templates** and more!"
            )
        try:
            await callback_query.message.edit_text(
                text, reply_markup=InlineKeyboardMarkup(back_button)
            )
        except MessageNotModified:
            pass
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
