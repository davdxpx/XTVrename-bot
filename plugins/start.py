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

    command_parts = message.text.split() if message.text else []
    if len(command_parts) > 1:
        param = command_parts[1]

        if param.startswith("group_"):
            from pyrogram import StopPropagation
            group_id = param.replace("group_", "")
            from bson.objectid import ObjectId
            try:
                group_doc = await db.db.file_groups.find_one({"group_id": group_id})
                if group_doc:
                    if not Config.PUBLIC_MODE:
                        if user_id != Config.CEO_ID and user_id not in Config.ADMIN_IDS:
                            await message.reply_text("❌ Access Denied.")
                            raise StopPropagation
                    else:
                        config = await db.get_public_config()
                        if not await check_force_sub(client, user_id):
                            await send_force_sub_gate(client, message, config)
                            raise StopPropagation

                    file_ids = group_doc.get("files", [])
                    owner_id = group_doc.get("user_id")

                    owner_name = "A user"
                    is_owner_premium = False
                    share_display_name = True

                    if owner_id:
                        owner_settings = await db.get_settings(owner_id)
                        if owner_settings and "share_display_name" in owner_settings:
                            share_display_name = owner_settings["share_display_name"]
                        owner_doc = await db.get_user(owner_id)
                        if owner_doc:
                            is_owner_premium = owner_doc.get("is_premium", False)
                            if share_display_name:
                                owner_name = owner_doc.get("first_name", "A user")

                    # If premium, hide forwarding tags
                    protect = not is_owner_premium

                    await message.reply_text(f"📦 **Batch File Delivery**\n\nReceiving {len(file_ids)} files shared by: `{owner_name if share_display_name else 'Anonymous'}`")

                    # We could queue this or send them slowly
                    import asyncio
                    count = 0
                    for fid_str in file_ids:
                        f = await db.files.find_one({"_id": ObjectId(fid_str)})
                        if f:
                            try:
                                await client.copy_message(
                                    chat_id=user_id,
                                    from_chat_id=f["channel_id"],
                                    message_id=f["message_id"],
                                    protect_content=protect
                                )
                                count += 1
                                await asyncio.sleep(0.5) # Anti-flood delay
                            except Exception as e:
                                logger.error(f"Failed to copy group file {fid_str}: {e}")

                    await message.reply_text(f"✅ Delivered {count} files successfully.")
                    raise StopPropagation
            except Exception as e:
                logger.error(f"Error handling group deep link: {e}")
                pass

        if param.startswith("file_"):
            from pyrogram import StopPropagation
            file_id_str = param.replace("file_", "")
            from bson.objectid import ObjectId
            try:
                f = await db.files.find_one({"_id": ObjectId(file_id_str)})
                if f:
                    if not Config.PUBLIC_MODE:
                        if user_id != Config.CEO_ID and user_id not in Config.ADMIN_IDS:
                            await message.reply_text("❌ Access Denied.")
                            raise StopPropagation
                    else:
                        config = await db.get_public_config()
                        if not await check_force_sub(client, user_id):
                            await send_force_sub_gate(client, message, config)
                            raise StopPropagation

                    owner_id = f.get("user_id")
                    owner_name = "A user"
                    is_owner_premium = False
                    share_display_name = True

                    if owner_id:
                        owner_doc = await db.get_user(owner_id)
                        if owner_doc:
                            is_owner_premium = owner_doc.get("is_premium", False)
                            owner_name = owner_doc.get("first_name", "A user")

                        owner_settings = await db.get_settings(owner_id)
                        if owner_settings and "share_display_name" in owner_settings:
                            share_display_name = owner_settings["share_display_name"]

                    if share_display_name and owner_name != "A user":
                        share_text = f"> **{owner_name}** has shared this file with you."
                    else:
                        share_text = "> A file has been shared with you."

                    await message.reply_text(f"📁 **File Received**\n\n{share_text}")

                    from pyrogram.errors import PeerIdInvalid
                    try:
                        await client.copy_message(
                            chat_id=user_id,
                            from_chat_id=f["channel_id"],
                            message_id=f["message_id"]
                        )
                    except PeerIdInvalid:
                        try:
                            await client.get_chat(f["channel_id"])
                            await client.copy_message(
                                chat_id=user_id,
                                from_chat_id=f["channel_id"],
                                message_id=f["message_id"]
                            )
                        except Exception as inner_e:
                            logger.error(f"Error serving shared file (Peer fallback failed): {inner_e}")
                            await message.reply_text("❌ The file is currently unavailable because the database channel is not accessible.")
                            raise StopPropagation

                    await client.send_sticker(chat_id=user_id, sticker="CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")

                    if not is_owner_premium:
                        ad_text = (
                            "> **Rename. Convert. Organize.**\n"
                            "> Process your own media with 𝕏TV MediaStudio™ today!"
                        )
                        await message.reply_text(
                            ad_text,
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton("🚀 Start Processing", callback_data="start_renaming")]]
                            )
                        )

                    raise StopPropagation
                else:
                    await message.reply_text("❌ File not found.")
                    raise StopPropagation
            except StopPropagation:
                raise
            except Exception as e:
                logger.error(f"Error serving shared file: {e}")
                await message.reply_text("❌ Invalid link or file not found.")
                raise StopPropagation

        if param.startswith("pro_setup_"):
            parts = param.split("_")
            tunnel_id_str = parts[2]

            try:
                tunnel_id = int(tunnel_id_str)
                user_settings = await db.get_settings(user_id)
                user_settings["temp_pro_tunnel_id"] = tunnel_id
                await db.settings.update_one({"_id": f"user_{user_id}"}, {"$set": {"temp_pro_tunnel_id": tunnel_id}}, upsert=True)
                await message.reply_text("✅ Detected Pro Setup Tunnel link. Proceed to connect your Userbot using /setup_pro.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Proceed", callback_data="pro_setup_start")]]))
                return
            except Exception as e:
                pass

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

    from tools.AudioMetadataEditor import handle_audio_editor_menu

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

    from tools.FileConverter import handle_file_converter_menu

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

    from tools.ImageWatermarker import handle_watermarker_menu

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

    from tools.SubtitleExtractor import handle_subtitle_extractor_menu

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
                        [InlineKeyboardButton("📺 Dumb Channels Guide", callback_data="help_dumb_channels")],
                        [InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")],
                        [InlineKeyboardButton("🎞️ Formats & Codecs", callback_data="help_formats")],
                        [InlineKeyboardButton("📈 Quotas & Limits", callback_data="help_quotas")],
                        [InlineKeyboardButton("💎 Premium Plans", callback_data="help_premium")],
                        [InlineKeyboardButton("🔧 Troubleshooting", callback_data="help_troubleshooting")],
                        [InlineKeyboardButton("❌ Close", callback_data="help_close")],
                    ]
                ),
            )
        except MessageNotModified:
            pass

    elif data == "help_dumb_channels":
        try:
            await callback_query.message.edit_text(
                "**📺 Dumb Channels Guide**\n\n"
                "> Automate your forwarded files.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**How to Add a Dumb Channel:**\n"
                "1. Create a Channel or Group.\n"
                "2. Add me to the Channel as an **Administrator**.\n"
                "3. Open my menu and go to `Settings` > `Dumb Channels` > `Add New`.\n"
                "4. Forward a message from that channel to me.\n\n"
                "**Setting Defaults:**\n"
                "You can specify a channel to automatically receive Movies, Series, or Everything (Standard). Once setup, you can select these channels as destinations during processing.",
                reply_markup=InlineKeyboardMarkup(back_button),
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
                "Simply send any file to the bot. It will automatically scan the name and look up metadata.\n\n"
                "• **Auto-Detect:** Finds Series, Episode, Year, and Movie Posters.\n"
                "• **Custom Name:** Bypasses auto-detect for a custom filename.\n"
                "• **Shortcuts:** `/r` or `/rename`."
            )
        elif tool == "audio":
            text = (
                "**🎵 Audio Metadata Editor**\n\n"
                "> Perfect for your music collection.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Allows you to modify the ID3 tags of MP3, FLAC, and other audio files.\n\n"
                "• You can change the Title, Artist, Album, and embedded Cover Art.\n"
                "• **Shortcut:** `/a` or `/audio`."
            )
        elif tool == "convert":
            text = (
                "**🔀 File Converter**\n\n"
                "> Change formats instantly.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Converts media files from one format to another (e.g., MKV to MP4, WEBM to MP4).\n\n"
                "• Just send the file and select the format.\n"
                "• **Shortcut:** `/c` or `/convert`."
            )
        elif tool == "watermark":
            text = (
                "**© Image Watermarker**\n\n"
                "> Brand your media.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Adds a custom image watermark (like a logo) to your videos or images.\n\n"
                "• You can set the position and size.\n"
                "• **Shortcut:** `/w` or `/watermark`."
            )
        elif tool == "subtitle":
            text = (
                "**📝 Subtitle Extractor**\n\n"
                "> Pull subs from MKV files.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Extracts embedded subtitle tracks from video files and gives them to you as `.srt` or `.ass` files.\n\n"
                "• **Shortcut:** `/s` or `/subtitle`."
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

    elif data == "help_formats":
        try:
            await callback_query.message.edit_text(
                "**🎞️ Formats & Codecs**\n\n"
                "> Supported media formats.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Supported Video Formats:**\n"
                "• `.mp4`, `.mkv`, `.avi`, `.webm`, `.flv`\n\n"
                "**Supported Audio Formats:**\n"
                "• `.mp3`, `.flac`, `.m4a`, `.wav`, `.aac`\n\n"
                "**Supported Image Formats:**\n"
                "• `.jpg`, `.png`, `.webp`, `.jpeg`\n\n"
                "*(The bot can process any extension, but specific tools like the Converter or Audio Editor only work with media files!)*",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_quotas":
        try:
            await callback_query.message.edit_text(
                "**📈 Quotas & Limits**\n\n"
                "> Fair usage system.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "To keep the bot fast and stable, daily limits are applied. These reset every 24 hours.\n\n"
                "• **Daily Files:** The maximum number of files you can process per day.\n"
                "• **Daily Egress:** The maximum total bandwidth (in MB or GB) you can process per day.\n"
                "• **MyFiles Expiry:** Temporary files are deleted from your storage locker after a set number of days to free up space.\n\n"
                "Check your profile or use `/myfiles` to view your current usage.",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_premium":
        try:
            await callback_query.message.edit_text(
                "**💎 Premium Plans**\n\n"
                "> Upgrade your experience.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Premium users unlock a completely different tier of processing power.\n\n"
                "**Benefits:**\n"
                "• **Priority Queue:** Skip the wait times when the bot is under heavy load.\n"
                "• **Bigger Limits:** Huge increases to Daily Egress and Daily File limits.\n"
                "• **Permanent Storage:** Store significantly more files in your `/myfiles` locker forever.\n"
                "• **Access to Heavy Tools:** Exclusive access to CPU-intensive tools like the Subtitle Extractor or Video Converter (if restricted by the Admin).\n\n"
                "Use the Premium Dashboard on the `/start` menu to view available plans.",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_troubleshooting":
        try:
            await callback_query.message.edit_text(
                "**🔧 Troubleshooting & FAQ**\n\n"
                "> Common issues and solutions.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Select the issue you are experiencing below to see how to fix it:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🤖 Bot Not Responding", callback_data="help_ts_no_response"),
                         InlineKeyboardButton("❌ Wrong Metadata", callback_data="help_ts_wrong_meta")],
                        [InlineKeyboardButton("📦 File Too Large", callback_data="help_ts_file_size"),
                         InlineKeyboardButton("⏳ Stuck Processing", callback_data="help_ts_stuck")],
                        [InlineKeyboardButton("🎵 Missing Audio/Subs", callback_data="help_ts_missing_tracks"),
                         InlineKeyboardButton("📝 Subtitles Won't Extract", callback_data="help_ts_subs_fail")],
                        [InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_guide")]
                    ]
                )
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_ts_"):
        issue = data.replace("help_ts_", "")
        back_to_ts = [[InlineKeyboardButton("🔙 Back to Troubleshooting", callback_data="help_troubleshooting")]]

        if issue == "no_response":
            text = (
                "**🤖 Bot Not Responding**\n\n"
                "If the bot is completely ignoring your files or commands, it could be due to a few reasons:\n\n"
                "**1. Rate Limiting:** You might be sending files too quickly. The bot has an internal anti-spam system. Wait 10-15 seconds and try sending one file.\n"
                "**2. Active Session:** The bot might be stuck waiting for your input on a previous task. Type `/end` to completely reset your session and try again.\n"
                "**3. Global Maintenance:** Occasionally, the bot undergoes maintenance or restarts. Give it a couple of minutes."
            )
        elif issue == "wrong_meta":
            text = (
                "**❌ Wrong Metadata / Bad TMDb Match**\n\n"
                "Sometimes, the Auto-Detector grabs the wrong poster or movie name because the original filename was too messy.\n\n"
                "**How to fix it:**\n"
                "1. **Clean the Filename:** Rename the file on your phone/PC *before* sending it. Format it like `Movie Title (Year).mp4`. This gives the bot a 99% success rate.\n"
                "2. **Use Quick Rename:** If it's not a real movie, go to `/settings` and enable **Quick Rename Mode**. This skips TMDb entirely!\n"
                "3. **Manual Override:** When the bot asks you to confirm the TMDb details, just hit **Skip / Manual**."
            )
        elif issue == "file_size":
            text = (
                "**📦 File Too Large (2GB Limit)**\n\n"
                "Telegram enforces strict limits on bot uploads.\n\n"
                "**The Limits:**\n"
                "• **Free Users:** 2.0 GB maximum per file.\n"
                "• **Premium Users:** 4.0 GB maximum (if enabled by the Admin).\n\n"
                "**Workarounds:**\n"
                "If your file is 2.5GB, you must either compress it on your computer before sending it, or upgrade to a Premium Plan to unlock the 4GB bot capacity."
            )
        elif issue == "stuck":
            text = (
                "**⏳ Stuck Processing**\n\n"
                "If the progress bar seems completely frozen at a specific percentage for several minutes:\n\n"
                "**1. Cancel the Task:** Type the `/end` command. This forces the bot to abort whatever it is doing and clears your active state.\n"
                "**2. Corrupt File:** The file you uploaded might be broken or incomplete. Try playing it on your device to ensure it's not corrupted.\n"
                "**3. Telegram Server Lag:** Sometimes Telegram's upload servers experience severe delays. Cancel it and try again later."
            )
        elif issue == "missing_tracks":
            text = (
                "**🎵 Missing Audio or Subtitle Tracks**\n\n"
                "If you converted a file or extracted a track and something is missing:\n\n"
                "**1. Not Supported by Format:** If you converted an MKV to MP4, remember that MP4 does *not* support certain subtitle formats natively. The bot strips them to prevent file corruption.\n"
                "**2. Hardcoded Subs:** If the subtitles are 'burned in' (part of the actual video picture), the bot cannot extract them."
            )
        elif issue == "subs_fail":
            text = (
                "**📝 Subtitles Won't Extract**\n\n"
                "If the Subtitle Extractor fails to rip the `.srt` or `.ass` file:\n\n"
                "**1. Image-Based Subs:** Some subtitles (like PGS or VobSub/PGS) are actually *images*, not text. The bot cannot extract image-based subtitles yet.\n"
                "**2. No Embedded Tracks:** The video might not actually have embedded subtitle files; you might have just been playing it alongside a separate file on your PC."
            )

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_to_ts))
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
