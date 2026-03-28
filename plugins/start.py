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
        bot_name = "**𝕏TV Rename Bot**"
        community_name = "official XTV"
    else:
        config = await db.get_public_config()
        if not await check_force_sub(client, user_id):
            await send_force_sub_gate(client, message, config)
            return

        await check_and_send_welcome(client, message, config)

        bot_name = f"**{config.get('bot_name', 'XTV Rename Bot')}**"
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

    await message.reply_text(
        f"{bot_name}\n\n"
        f"Welcome to the {community_name} file renaming tool.\n"
        "This bot provides professional renaming and metadata management.\n\n"
        "💡 **Tip:** You don't need to click anything to begin! Simply send or forward a file directly to me, and I will auto-detect the details.\n\n"
        "Click below to start manually or to view the guide.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📁 Rename / Tag Media", callback_data="start_renaming"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✨ Other Features", callback_data="other_features_menu"
                    )
                ],
                [InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")],
            ]
        ),
    )

@Client.on_message(filters.command(["r", "rename"]) & filters.private, group=0)
async def handle_rename_command(client, message):
    user_id = message.from_user.id
    if not Config.PUBLIC_MODE and not (
        user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS
    ):
        return
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
    if not Config.PUBLIC_MODE and not (
        user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS
    ):
        return
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
    if not Config.PUBLIC_MODE and not (
        user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS
    ):
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
    if not Config.PUBLIC_MODE and not (
        user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS
    ):
        return
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
    if not Config.PUBLIC_MODE and not (
        user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS
    ):
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
    if not Config.PUBLIC_MODE and not (
        user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS
    ):
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

@Client.on_message(filters.command("help") & filters.private, group=0)
async def handle_help_command_unique(client, message):
    user_id = message.from_user.id
    logger.debug(f"CMD received: {message.text} from {user_id}")

    await message.reply_text(
        "**📖 Help & Guide**\n\n"
        "Welcome to the Rename Bot Guide!\n"
        "Whether you are organizing a massive media library of popular series and movies, "
        "or just want to rename and manage your **personal home videos** and files, I can help!\n\n"
        "Please select a topic below to learn more:",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🛠 How to Use", callback_data="help_how_to_use")],
                [
                    InlineKeyboardButton(
                        "🤖 Auto-Detect Magic", callback_data="help_auto_detect"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📁 Personal Files & Home Videos", callback_data="help_personal"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⚙️ Settings & Info", callback_data="help_settings"
                    )
                ],
                [InlineKeyboardButton("❌ Close", callback_data="help_close")],
            ]
        ),
    )

@Client.on_message(filters.command("end") & filters.private, group=0)
async def handle_end_command_unique(client, message):
    user_id = message.from_user.id
    logger.debug(f"CMD received: {message.text} from {user_id}")
    clear_session(user_id)
    await message.reply_text(
        "**Current Task Cancelled** ❌\n\n"
        "Your progress has been cleared.\n"
        "You can simply send me a file anytime to start over, or use the buttons below.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎬 Start Renaming Manually", callback_data="start_renaming"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✨ Other Features", callback_data="other_features_menu"
                    )
                ],
                [InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")],
            ]
        ),
    )

from utils.logger import debug

debug("✅ Loaded handler: help_callback")

@Client.on_callback_query(filters.regex(r"^other_features_menu$"))
async def handle_other_features_menu(client, callback_query):
    await callback_query.answer()
    try:
        await callback_query.message.edit_text(
            "**✨ Other Features**\n\n"
            "Select an additional tool below:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🎵 Audio Metadata Editor", callback_data="audio_editor_menu"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔀 File Converter", callback_data="file_converter_menu"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "© Image Watermarker", callback_data="watermarker_menu"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📝 Subtitle Extractor", callback_data="subtitle_extractor_menu"
                        )
                    ],
                    [InlineKeyboardButton("❌ Close", callback_data="help_close")],
                ]
            ),
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
                "**📖 Help & Guide**\n\n"
                "Welcome to the Rename Bot Guide!\n"
                "Whether you are organizing a massive media library of popular series and movies, "
                "or just want to rename and manage your **personal home videos** and files, I can help!\n\n"
                "Please select a topic below to learn more:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🛠 How to Use", callback_data="help_how_to_use"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🤖 Auto-Detect Magic", callback_data="help_auto_detect"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📁 Personal Files & Home Videos",
                                callback_data="help_personal",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📄 General Mode & Variables",
                                callback_data="help_general",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⚙️ Settings & Info", callback_data="help_settings"
                            )
                        ],
                        [InlineKeyboardButton("❌ Close", callback_data="help_close")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
    elif data == "help_how_to_use":
        try:
            await callback_query.message.edit_text(
                "**🛠 How to Use**\n\n"
                "1. **The Quick Way**: Simply send or forward any media file directly to me. I will scan the file and start the renaming process.\n\n"
                "2. **The Manual Way**: Press the 'Start Renaming Manually' button or use `/start` to begin the guided process.\n\n"
                "3. **Cancel Anytime**: Made a mistake? Use `/end` or the Cancel button at any point to reset your progress.",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass
    elif data == "help_auto_detect":
        try:
            await callback_query.message.edit_text(
                "**🤖 Auto-Detect Magic**\n\n"
                "When you send a file directly, my Auto-Detection Matrix scans the filename.\n\n"
                "• **Series/Movies:** I look for the title, year, season, episode, and quality.\n"
                "• **Smart Metadata:** If it's a known movie or series, I pull official posters and metadata from TMDb!\n\n"
                "You always get a chance to confirm or correct the details before processing begins.",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass
    elif data == "help_personal":
        try:
            await callback_query.message.edit_text(
                "**📁 Personal Files & Home Videos**\n\n"
                "Not just for popular movies! Many users manage their personal home videos, tutorials, or family archives.\n\n"
                "**How?**\n"
                "1. Send your personal video.\n"
                "2. When prompted with TMDb search results, select **'Skip / Manual'** or similar option if it's not a public release.\n"
                "3. You can still set custom names, add your own thumbnails, and organize them exactly how you want them!",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass
    elif data == "help_general":
        try:
            await callback_query.message.edit_text(
                "**📄 General Mode & Variables**\n\n"
                "General mode allows you to rename ANY file exactly how you want, bypassing all metadata lookups.\n\n"
                "**Available Variables for Renaming:**\n"
                "• `{filename}` - The original filename (without extension)\n"
                "• `{Season_Episode}` - Example: S01E01 (if detected)\n"
                "• `{Quality}` - Example: 1080p, 720p (if detected)\n"
                "• `{Year}` - Example: 2024 (if detected)\n"
                "• `{Title}` - Example: The Matrix (if detected)\n\n"
                "*(The file extension like .mkv or .pdf is always added automatically!)*\n\n"
                "**Shortcuts:**\n"
                "• `/r` or `/rename` - Start rename flow\n"
                "• `/p` or `/personal` - Open Personal Files mode directly\n"
                "• `/g` or `/general` - Open General Mode directly\n"
                "• `/a` or `/audio` - Open Audio Metadata Editor\n"
                "• `/c` or `/convert` - Open File Converter\n"
                "• `/w` or `/watermark` - Open Image Watermarker",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass
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
