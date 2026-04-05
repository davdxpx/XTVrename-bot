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
                "> The core intelligent media processor.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "The Renamer isn't just about changing a filename; it's a full-fledged metadata tagging engine.\n\n"
                "**🚀 How to Start:**\n"
                "Simply send, forward, or reply to any file to trigger the Auto-Detector. Or, use `/r` or `/rename` to manually start the wizard.\n\n"
                "**🧠 Smart Media Mode (Default):**\n"
                "When you upload a file, the bot uses a complex Regex Matrix to tear apart the filename. It looks for:\n"
                "• **Title & Year:** E.g., 'Inception 1999'.\n"
                "• **Seasons & Episodes:** E.g., 'S01E05' or '1x05'.\n"
                "• **Quality:** E.g., '1080p', '4K', 'HDR'.\n"
                "• **Language/Codec:** E.g., 'HEVC', 'Dual Audio'.\n\n"
                "It then queries **The Movie Database (TMDb)** to fetch the official poster, plot summary, and correct capitalization, giving your file a highly professional look.\n\n"
                "**⚡ Quick Rename Mode:**\n"
                "If you are uploading random files, courses, or home videos, you can switch your default workflow to Quick Rename Mode via `/settings`. This instantly skips TMDb lookups and applies your custom template.\n\n"
                "**💡 Pro Tip:**\n"
                "If the bot guesses the wrong movie/series, you can always hit **'Skip / Manual'** during the prompt to override it with your own name."
            )
        elif tool == "audio":
            text = (
                "**🎵 Audio Metadata Editor**\n\n"
                "> Perfect for audiophiles and music collectors.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "The Audio Editor allows you to permanently embed or modify the internal ID3 tags of audio files (like MP3, FLAC, M4A, etc.). This ensures that music players display the correct information instead of 'Unknown Artist'.\n\n"
                "**🎛️ Features:**\n"
                "• **Title & Artist:** Correct track names and artist attributions.\n"
                "• **Album:** Group your songs together flawlessly.\n"
                "• **Cover Art:** Upload any image to embed it directly inside the audio file. It will show up on your car stereo, phone, or Spotify player.\n\n"
                "**How to Use:**\n"
                "Use the shortcut `/a` or `/audio`, then send the bot an audio file to begin the process. You will be prompted step-by-step for the Title, Artist, and Thumbnail."
            )
        elif tool == "convert":
            text = (
                "**🔀 File Converter**\n\n"
                "> Ultimate format flexibility at blazing speeds.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "The File Converter utilizes advanced FFmpeg parameters to seamlessly convert media files from one container format to another without needing third-party software on your phone.\n\n"
                "**🚀 Conversion Modes:**\n"
                "• **Stream Copy (Lightning Fast):** If the video/audio codecs are compatible, the bot simply changes the 'box' (e.g., from `.mkv` to `.mp4`). This takes seconds and results in **ZERO quality loss**.\n"
                "• **Transcoding:** If the codecs are completely incompatible (e.g., trying to put a VP9 video into an AVI container), the bot will carefully re-encode the file. *(Note: This can take time depending on file size).* \n\n"
                "**How to Use:**\n"
                "Type `/c` or `/convert`, send your media file, and click the button for your desired output format."
            )
        elif tool == "watermark":
            text = (
                "**© Image Watermarker**\n\n"
                "> Brand, protect, and claim your media.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "The Watermarker allows you to overlay a permanent, transparent image (like your channel logo or a custom icon) on top of your video and image files.\n\n"
                "**🎛️ Detailed Customization:**\n"
                "• **Positioning Grid:** Place your logo perfectly in the Top Left, Top Right, Center, Bottom Left, or Bottom Right corner.\n"
                "• **Relative Sizing:** You can adjust how large the watermark appears! Choose from 5% (tiny logo) up to 20% (large overlay) of the video's width.\n"
                "• **Transparency:** The bot automatically blends the image smoothly so it doesn't ruin the viewing experience.\n\n"
                "**How to Use:**\n"
                "Type `/w` or `/watermark`. The bot will ask you to send the video, followed by the image you want to use as the logo."
            )
        elif tool == "subtitle":
            text = (
                "**📝 Subtitle Extractor**\n\n"
                "> Extract hidden text tracks instantly.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Many `.mkv` files have soft-coded subtitle tracks embedded deep inside them. The Subtitle Extractor allows you to rip these tracks out and save them as standalone text files (`.srt`, `.ass`, `.vtt`).\n\n"
                "**🌟 Why use this?**\n"
                "• If you downloaded a movie but the built-in subtitles don't work on your TV.\n"
                "• If you want to translate a subtitle track and re-mux it later.\n"
                "• If you need to share just the subtitle file with a friend.\n\n"
                "**Features:**\n"
                "• **Multi-Track Support:** If a movie has English, Spanish, and French tracks, the bot will list them all. You just click the button for the one you want!\n\n"
                "**How to Use:**\n"
                "Type `/s` or `/subtitle` and send an MKV file."
            )

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_to_tools))
        except MessageNotModified:
            pass

    elif data == "help_file_management":
        try:
            await callback_query.message.edit_text(
                "**📁 File Management (/myfiles)**\n\n"
                "> Welcome to your advanced digital storage locker.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "By using the `/myfiles` command, you enter an interactive dashboard that keeps track of everything you've ever processed through the bot.\n\n"
                "**⏳ Temporary Storage:**\n"
                "Every file you rename or convert is saved here temporarily. Depending on your Tier (Free, Standard, Deluxe), files will expire after a set number of days to save space.\n\n"
                "**📌 Permanent Slots:**\n"
                "Got a file you NEVER want to lose? You can 'Pin' files to a Permanent Slot. Pinned files bypass the expiration timer and stay safe in your cloud forever.\n\n"
                "**📁 Custom Folders:**\n"
                "Tired of a messy list? You can create virtual Folders (e.g., 'Marvel Movies', 'Homework', 'Music') and move your pinned files into them for ultimate organization.\n\n"
                "**🔄 Restoring Files:**\n"
                "At any time, you can browse your `/myfiles` list and click 'Resend' to have the bot instantly drop the file back into your chat. Perfect for forwarding things to friends months later!",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_auto_detect":
        try:
            await callback_query.message.edit_text(
                "**🤖 Auto-Detect Magic (The Matrix)**\n\n"
                "> How the bot thinks and sees your files.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "When you forward a file to the bot, it doesn't just read the text; it analyzes it using a powerful Regex engine called 'Guessit'.\n\n"
                "**🔍 The Scanning Process:**\n"
                "1. **Normalization:** It strips out dots `.`, underscores `_`, and garbage text like `[10bit]` or `www.website.com`.\n"
                "2. **Pattern Matching:** It isolates the Year (e.g., 2023) to definitively split the 'Title' from the 'Quality' tags.\n"
                "3. **TMDb Query:** It securely contacts The Movie Database API using your isolated Title and Year.\n\n"
                "**🎭 Smart Handling:**\n"
                "• **Multi-Episode Files:** If a file is named `S01E01-E02`, the bot knows it contains two episodes and will properly format the final output.\n"
                "• **Anime & Absolute Numbering:** It supports weird absolute episode numbers often used in Anime releases.\n\n"
                "**💡 Tip:** If the Auto-Detector fails to find the right movie, rename the file on your device to just `Movie Title (Year).mkv` and send it again. A cleaner filename guarantees a 100% TMDb match!",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_general":
        try:
            await callback_query.message.edit_text(
                "**📄 Personal & General Mode**\n\n"
                "> For everything that isn't a blockbuster movie.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Not everyone uses the bot for TV shows. If you are uploading courses, tutorials, family home videos, or PDF documents, you need to bypass the smart scanners.\n\n"
                "**📁 Personal Mode (`/p`)**\n"
                "1. Use `/p` to enter Personal Mode.\n"
                "2. Send your file. The bot immediately asks you: *'What do you want to name this?'*\n"
                "3. It completely skips TMDb searches and just applies your exact text. You can also attach your own custom image to serve as the video thumbnail!\n\n"
                "**📄 General Mode (`/g`) & Variables**\n"
                "General Mode behaves like a coding template. You can set a Master Template in your `/settings`, and the bot will automatically inject variables into it.\n\n"
                "**Available Variables:**\n"
                "• `{filename}` - The original name of the file.\n"
                "• `{Season_Episode}` - Output: S01E05.\n"
                "• `{Quality}` - Output: 1080p, HDR.\n"
                "• `{Year}` - Output: 2024.\n"
                "• `{Title}` - The base title.\n\n"
                "*(Note: You never need to type the extension like `.pdf` or `.mp4`. The bot ALWAYS adds the correct extension automatically!)*",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_settings":
        if Config.PUBLIC_MODE:
            text = (
                "**⚙️ Settings & Info**\n\n"
                "> Total control over your renaming experience.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "By typing the `/settings` command, you open up your Personal Configuration dashboard. These settings apply globally to everything you upload.\n\n"
                "**📝 Template Management:**\n"
                "• **Filename Templates:** You can create different output structures for Movies, Series, and Subtitles. \n"
                "  *(Example: `[MyChannel] {Title} ({Year}) - {Quality}`)*\n"
                "• **Caption Templates:** Customize the text that appears *under* the video when it's sent. You can inject `{size}`, `{duration}`, and `{filename}` dynamically!\n\n"
                "**🖼️ Default Thumbnail:**\n"
                "Upload a universal thumbnail (like your channel logo). If you upload a video that doesn't have a poster, the bot will instantly stamp your Default Thumbnail onto it.\n\n"
                "**🔤 Preferred Separator:**\n"
                "Choose if you want spaces (` `), dots (`.`), or underscores (`_`) to separate words in your final filenames.\n\n"
                "**🌍 Language & Workflow:**\n"
                "Change the language TMDb uses to fetch plots (e.g., Spanish, German, Hindi), and toggle between Smart Mode and Quick Mode."
            )
        else:
            text = (
                "**⚙️ Settings & Admin**\n\n"
                "> Total control over the global renaming experience.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "By typing the `/admin` command, you open up the CEO Configuration dashboard. These settings affect ALL files processed by the bot.\n\n"
                "**📝 Template Management:**\n"
                "• **Filename Templates:** You can create different output structures for Movies, Series, and Subtitles. \n"
                "  *(Example: `[MyChannel] {Title} ({Year}) - {Quality}`)*\n"
                "• **Caption Templates:** Customize the text that appears *under* the video when it's sent. You can inject `{size}`, `{duration}`, and `{filename}` dynamically!\n\n"
                "**🖼️ Default Thumbnail:**\n"
                "Upload a universal thumbnail (like your channel logo). If you upload a video that doesn't have a poster, the bot will instantly stamp your Default Thumbnail onto it.\n\n"
                "**🔤 Preferred Separator:**\n"
                "Choose if you want spaces (` `), dots (`.`), or underscores (`_`) to separate words in your final filenames.\n\n"
                "**🌍 Language & Workflow:**\n"
                "Change the language TMDb uses to fetch plots (e.g., Spanish, German, Hindi), and toggle between Smart Mode and Quick Mode."
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
