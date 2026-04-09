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
                        owner_doc = await db.get_user(owner_id)
                        if owner_doc:
                            is_owner_premium = owner_doc.get("is_premium", False)

                        owner_settings = await db.get_settings(owner_id)
                        if owner_settings and "share_display_name" in owner_settings:
                            share_display_name = owner_settings["share_display_name"]
                        elif is_owner_premium:
                            # For premium users, disabled by default for privacy reasons
                            share_display_name = False

                        if share_display_name and owner_doc:
                            owner_name = owner_doc.get("first_name", "A user")

                        protect = False
                        if owner_settings and "hide_forward_tags" in owner_settings:
                            protect = owner_settings["hide_forward_tags"]

                    else:
                        protect = not is_owner_premium

                    await message.reply_text(f"📦 **Batch File Delivery**\n\nReceiving {len(file_ids)} files shared by: `{owner_name if share_display_name else 'Anonymous'}`")

                    # We could queue this or send them slowly
                    import asyncio
                    from pyrogram.errors import PeerIdInvalid
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
                            except PeerIdInvalid:
                                try:
                                    await client.get_chat(f["channel_id"])
                                    await client.copy_message(
                                        chat_id=user_id,
                                        from_chat_id=f["channel_id"],
                                        message_id=f["message_id"],
                                        protect_content=protect
                                    )
                                    count += 1
                                    await asyncio.sleep(0.5)
                                except Exception as inner_e:
                                    logger.error(f"Failed to copy group file {fid_str} (Peer fallback failed): {inner_e}")
                            except Exception as e:
                                logger.error(f"Failed to copy group file {fid_str}: {e}")

                    try:
                        await client.send_sticker(user_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
                    except Exception:
                        pass
                    await message.reply_text(f"✅ Delivered {count} files successfully.")

                    raise StopPropagation
            except Exception as e:
                if isinstance(e, StopPropagation):
                    raise
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
                [InlineKeyboardButton("🚀 Quick Start", callback_data="help_quickstart")],
                [InlineKeyboardButton("🛠 All Tools & Features", callback_data="help_tools")],
                [InlineKeyboardButton("📁 File Management", callback_data="help_file_management"),
                 InlineKeyboardButton("🤖 Auto-Detect", callback_data="help_auto_detect")],
                [InlineKeyboardButton("📄 Personal & General", callback_data="help_general"),
                 InlineKeyboardButton("🏷️ Templates", callback_data="help_templates")],
                [InlineKeyboardButton("📺 Dumb Channels", callback_data="help_dumb_channels"),
                 InlineKeyboardButton("🔗 Bot Commands", callback_data="help_commands")],
                [InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")],
                [InlineKeyboardButton("🎞️ Formats & Codecs", callback_data="help_formats"),
                 InlineKeyboardButton("📈 Quotas & Limits", callback_data="help_quotas")],
                [InlineKeyboardButton("💎 Premium Plans", callback_data="help_premium")],
                [InlineKeyboardButton("🔧 Troubleshooting", callback_data="help_troubleshooting")],
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
        [InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]
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
                        [InlineKeyboardButton("🚀 Quick Start", callback_data="help_quickstart")],
                        [InlineKeyboardButton("🛠 All Tools & Features", callback_data="help_tools")],
                        [InlineKeyboardButton("📁 File Management", callback_data="help_file_management"),
                         InlineKeyboardButton("🤖 Auto-Detect", callback_data="help_auto_detect")],
                        [InlineKeyboardButton("📄 Personal & General", callback_data="help_general"),
                         InlineKeyboardButton("🏷️ Templates", callback_data="help_templates")],
                        [InlineKeyboardButton("📺 Dumb Channels", callback_data="help_dumb_channels"),
                         InlineKeyboardButton("🔗 Bot Commands", callback_data="help_commands")],
                        [InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")],
                        [InlineKeyboardButton("🎞️ Formats & Codecs", callback_data="help_formats"),
                         InlineKeyboardButton("📈 Quotas & Limits", callback_data="help_quotas")],
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

    elif data == "help_quickstart":
        try:
            await callback_query.message.edit_text(
                "**🚀 Quick Start Guide**\n\n"
                "> Get started in seconds.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**3 Simple Steps:**\n"
                "1. **Send** any media file directly to this chat.\n"
                "2. **Confirm** the detected metadata or customize it.\n"
                "3. **Receive** your perfectly tagged and renamed file!\n\n"
                "That's it! For advanced features, explore the other topics in this guide.",
                reply_markup=InlineKeyboardMarkup(back_button),
            )
        except MessageNotModified:
            pass

    elif data == "help_templates":
        try:
            await callback_query.message.edit_text(
                "**🏷️ Templates & Variables**\n\n"
                "> Customize your output format.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Templates control how your files are named and captioned after processing. "
                "Select a topic below to learn more:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("📝 Filename Templates", callback_data="help_tpl_filename"),
                         InlineKeyboardButton("💬 Caption Templates", callback_data="help_tpl_caption")],
                        [InlineKeyboardButton("📋 Variable Reference", callback_data="help_tpl_variables"),
                         InlineKeyboardButton("🎯 Template Examples", callback_data="help_tpl_examples")],
                        [InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]
                    ]
                )
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_tpl_"):
        tpl = data.replace("help_tpl_", "")
        back_to_tpl = [[InlineKeyboardButton("← Back to Templates", callback_data="help_templates")]]

        if tpl == "filename":
            text = (
                "**📝 Filename Templates**\n\n"
                "> Control your output filenames.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Go to `/settings` > **Filename Template** to set your format.\n\n"
                "• Use variables like `{Title}`, `{Year}`, `{Quality}` to build dynamic names.\n"
                "• The file extension is always added automatically.\n"
                "• Example: `{Title} ({Year}) [{Quality}]` → `Inception (2010) [1080p].mkv`"
            )
        elif tpl == "caption":
            text = (
                "**💬 Caption Templates**\n\n"
                "> Customize file captions.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Captions appear below your file in Telegram.\n\n"
                "• Set via `/settings` > **Caption Template**.\n"
                "• Supports the same variables as filename templates.\n"
                "• You can use Telegram formatting: **bold**, __italic__, `code`."
            )
        elif tpl == "variables":
            text = (
                "**📋 Variable Reference**\n\n"
                "> All available template variables.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• `{Title}` — Detected movie/series title\n"
                "• `{Year}` — Release year\n"
                "• `{Quality}` — e.g. 1080p, 720p\n"
                "• `{Season_Episode}` — e.g. S01E01\n"
                "• `{filename}` — Original filename\n"
                "• `{extension}` — File extension\n"
                "• `{size}` — File size"
            )
        elif tpl == "examples":
            text = (
                "**🎯 Template Examples**\n\n"
                "> Ready-to-use templates.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Movies:**\n"
                "• `{Title} ({Year}) [{Quality}]`\n"
                "→ `Inception (2010) [1080p].mkv`\n\n"
                "**Series:**\n"
                "• `{Title} {Season_Episode} [{Quality}]`\n"
                "→ `Breaking Bad S01E01 [720p].mkv`\n\n"
                "**Simple:**\n"
                "• `{Title}` → `Inception.mkv`"
            )
        else:
            text = "Unknown template topic."

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_to_tpl))
        except MessageNotModified:
            pass

    elif data == "help_commands":
        try:
            await callback_query.message.edit_text(
                "**🔗 Bot Commands**\n\n"
                "> Quick reference for all commands.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Select a category to see available commands:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🎬 Media Commands", callback_data="help_cmd_media")],
                        [InlineKeyboardButton("📁 File & Mode Commands", callback_data="help_cmd_files")],
                        [InlineKeyboardButton("⚙️ System Commands", callback_data="help_cmd_system")],
                        [InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]
                    ]
                )
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_cmd_"):
        cmd = data.replace("help_cmd_", "")
        back_to_cmd = [[InlineKeyboardButton("← Back to Commands", callback_data="help_commands")]]

        if cmd == "media":
            text = (
                "**🎬 Media Commands**\n\n"
                "> Process and edit your media.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• `/rename` or `/r` — Start the rename & tag tool\n"
                "• `/audio` or `/a` — Open the audio metadata editor\n"
                "• `/convert` or `/c` — Convert file formats\n"
                "• `/watermark` or `/w` — Add image watermark\n"
                "• `/subtitle` or `/s` — Extract subtitles"
            )
        elif cmd == "files":
            text = (
                "**📁 File & Mode Commands**\n\n"
                "> Manage files and modes.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• `/myfiles` — Access your personal file storage\n"
                "• `/g` — Activate General Mode (no metadata)\n"
                "• Just send a file directly to start Auto-Detect Mode"
            )
        elif cmd == "system":
            text = (
                "**⚙️ System Commands**\n\n"
                "> Control the bot.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• `/start` — Main menu & dashboard\n"
                "• `/help` — Open this guide\n"
                "• `/end` — Cancel current task & reset session\n"
                "• `/settings` — Personal settings & templates\n"
                "• `/info` — Bot info & support contact"
            )
        else:
            text = "Unknown command category."

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_to_cmd))
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
                        [InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]
                    ]
                )
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_tool_"):
        tool = data.split("_")[-1]
        back_to_tools = [[InlineKeyboardButton("← Back to Tools", callback_data="help_tools")]]

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
                "__(Extensions are always added automatically)__",
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
                "__(The bot can process any extension, but specific tools like the Converter or Audio Editor only work with media files!)__",
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
                "Select the category that best matches your issue:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🔌 Connection & Access", callback_data="help_ts_cat_connect"),
                         InlineKeyboardButton("📤 Upload & Download", callback_data="help_ts_cat_upload")],
                        [InlineKeyboardButton("🏷️ Metadata & Detection", callback_data="help_ts_cat_meta"),
                         InlineKeyboardButton("⚙️ Processing Issues", callback_data="help_ts_cat_process")],
                        [InlineKeyboardButton("🎵 Audio & Subtitles", callback_data="help_ts_cat_audio"),
                         InlineKeyboardButton("📁 Files & Storage", callback_data="help_ts_cat_files")],
                        [InlineKeyboardButton("💎 Account & Premium", callback_data="help_ts_cat_account")],
                        [InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]
                    ]
                )
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_ts_cat_"):
        cat = data.replace("help_ts_cat_", "")
        back_to_ts = [[InlineKeyboardButton("← Back to Troubleshooting", callback_data="help_troubleshooting")]]

        if cat == "connect":
            text = "**🔌 Connection & Access**\n\n> Issues with reaching the bot.\n━━━━━━━━━━━━━━━━━━━━\nSelect your specific issue:"
            buttons = [
                [InlineKeyboardButton("🤖 Bot Not Responding", callback_data="help_ts_no_response"),
                 InlineKeyboardButton("🚫 Bot Seems Blocked", callback_data="help_ts_blocked")],
                [InlineKeyboardButton("⌨️ Commands Ignored", callback_data="help_ts_cmd_ignored"),
                 InlineKeyboardButton("🔒 Private Chat Error", callback_data="help_ts_private_only")],
            ]
        elif cat == "upload":
            text = "**📤 Upload & Download**\n\n> Issues with file transfers.\n━━━━━━━━━━━━━━━━━━━━\nSelect your specific issue:"
            buttons = [
                [InlineKeyboardButton("📦 File Too Large", callback_data="help_ts_file_size"),
                 InlineKeyboardButton("💥 Upload Fails", callback_data="help_ts_upload_fail")],
                [InlineKeyboardButton("🐌 Slow Transfer", callback_data="help_ts_slow_transfer"),
                 InlineKeyboardButton("🔨 File Corrupted", callback_data="help_ts_corrupted")],
            ]
        elif cat == "meta":
            text = "**🏷️ Metadata & Detection**\n\n> Issues with auto-detection.\n━━━━━━━━━━━━━━━━━━━━\nSelect your specific issue:"
            buttons = [
                [InlineKeyboardButton("❌ Wrong Metadata", callback_data="help_ts_wrong_meta"),
                 InlineKeyboardButton("🔍 TMDb No Results", callback_data="help_ts_tmdb_empty")],
                [InlineKeyboardButton("📺 Wrong Season/Ep", callback_data="help_ts_wrong_ep"),
                 InlineKeyboardButton("🖼 Poster Not Loading", callback_data="help_ts_poster_fail")],
            ]
        elif cat == "process":
            text = "**⚙️ Processing Issues**\n\n> Issues during file processing.\n━━━━━━━━━━━━━━━━━━━━\nSelect your specific issue:"
            buttons = [
                [InlineKeyboardButton("⏳ Stuck Processing", callback_data="help_ts_stuck"),
                 InlineKeyboardButton("💥 Conversion Fails", callback_data="help_ts_conv_fail")],
                [InlineKeyboardButton("📄 Output Empty", callback_data="help_ts_empty_output"),
                 InlineKeyboardButton("📉 Bad Quality", callback_data="help_ts_bad_quality")],
            ]
        elif cat == "audio":
            text = "**🎵 Audio & Subtitles**\n\n> Issues with audio and subtitle tracks.\n━━━━━━━━━━━━━━━━━━━━\nSelect your specific issue:"
            buttons = [
                [InlineKeyboardButton("🎵 Missing Tracks", callback_data="help_ts_missing_tracks"),
                 InlineKeyboardButton("📝 Subs Won't Extract", callback_data="help_ts_subs_fail")],
                [InlineKeyboardButton("🔊 Audio Out of Sync", callback_data="help_ts_audio_sync"),
                 InlineKeyboardButton("🗣 Wrong Language", callback_data="help_ts_wrong_lang")],
            ]
        elif cat == "files":
            text = "**📁 Files & Storage**\n\n> Issues with your stored files.\n━━━━━━━━━━━━━━━━━━━━\nSelect your specific issue:"
            buttons = [
                [InlineKeyboardButton("📂 MyFiles Not Loading", callback_data="help_ts_myfiles_fail"),
                 InlineKeyboardButton("⏰ Files Expired Early", callback_data="help_ts_expired")],
                [InlineKeyboardButton("🗑 Can't Delete Files", callback_data="help_ts_cant_delete"),
                 InlineKeyboardButton("💾 Storage Full", callback_data="help_ts_storage_full")],
            ]
        elif cat == "account":
            text = "**💎 Account & Premium**\n\n> Issues with your account or plan.\n━━━━━━━━━━━━━━━━━━━━\nSelect your specific issue:"
            buttons = [
                [InlineKeyboardButton("💎 Premium Not Active", callback_data="help_ts_prem_fail"),
                 InlineKeyboardButton("🔄 Quota Not Resetting", callback_data="help_ts_quota_reset")],
                [InlineKeyboardButton("⬆️ Upgrade Problems", callback_data="help_ts_upgrade_fail"),
                 InlineKeyboardButton("👤 Account Not Found", callback_data="help_ts_acc_missing")],
            ]
        else:
            text = "Unknown category."
            buttons = []

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons + back_to_ts)
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_ts_"):
        issue = data.replace("help_ts_", "")

        ts_categories = {
            "no_response": "connect", "blocked": "connect", "cmd_ignored": "connect", "private_only": "connect",
            "file_size": "upload", "upload_fail": "upload", "slow_transfer": "upload", "corrupted": "upload",
            "wrong_meta": "meta", "tmdb_empty": "meta", "wrong_ep": "meta", "poster_fail": "meta",
            "stuck": "process", "conv_fail": "process", "empty_output": "process", "bad_quality": "process",
            "missing_tracks": "audio", "subs_fail": "audio", "audio_sync": "audio", "wrong_lang": "audio",
            "myfiles_fail": "files", "expired": "files", "cant_delete": "files", "storage_full": "files",
            "prem_fail": "account", "quota_reset": "account", "upgrade_fail": "account", "acc_missing": "account",
        }
        cat_names = {
            "connect": "Connection", "upload": "Upload", "meta": "Metadata",
            "process": "Processing", "audio": "Audio & Subs", "files": "Files & Storage",
            "account": "Account"
        }
        cat = ts_categories.get(issue, "")
        back_label = cat_names.get(cat, "Troubleshooting")
        back_cb = f"help_ts_cat_{cat}" if cat else "help_troubleshooting"
        back_to_cat = [[InlineKeyboardButton(f"← Back to {back_label}", callback_data=back_cb)]]

        # --- Connection & Access ---
        if issue == "no_response":
            text = (
                "**🤖 Bot Not Responding**\n\n"
                "If the bot is completely ignoring your files or commands, it could be due to a few reasons:\n\n"
                "**1. Rate Limiting:** You might be sending files too quickly. The bot has an internal anti-spam system. Wait 10-15 seconds and try sending one file.\n"
                "**2. Active Session:** The bot might be stuck waiting for your input on a previous task. Type `/end` to completely reset your session and try again.\n"
                "**3. Global Maintenance:** Occasionally, the bot undergoes maintenance or restarts. Give it a couple of minutes."
            )
        elif issue == "blocked":
            text = (
                "**🚫 Bot Seems Blocked**\n\n"
                "If you can't start or interact with the bot at all:\n\n"
                "**1. Unblock the Bot:** Open the bot's profile in Telegram and check if you accidentally blocked it. Tap 'Unblock' if so.\n"
                "**2. Restart the Bot:** Send `/start` to re-initialize your session.\n"
                "**3. Access Restricted:** In Public Mode, the admin may have restricted access. Contact the bot owner."
            )
        elif issue == "cmd_ignored":
            text = (
                "**⌨️ Commands Ignored**\n\n"
                "If the bot doesn't react to your commands:\n\n"
                "**1. Private Chat Only:** Most commands only work in the bot's private chat, not in groups.\n"
                "**2. Typo in Command:** Ensure you're typing the exact command (e.g. `/rename`, not `/Rename`).\n"
                "**3. Active Session:** You may have a pending task. Type `/end` first, then retry your command."
            )
        elif issue == "private_only":
            text = (
                "**🔒 Private Chat Error**\n\n"
                "If you get a 'private chat only' error:\n\n"
                "**1. Open Private Chat:** Click on the bot's name and tap 'Message' to open a direct chat.\n"
                "**2. Group Limitations:** The bot processes files only in private chats. Groups are used for Dumb Channel routing only.\n"
                "**3. Start the Bot:** Send `/start` in the private chat to initialize."
            )
        # --- Upload & Download ---
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
        elif issue == "upload_fail":
            text = (
                "**💥 Upload Fails Midway**\n\n"
                "If your upload keeps failing or disconnecting:\n\n"
                "**1. Network Stability:** Ensure you have a stable internet connection. Switch from Wi-Fi to mobile data or vice versa.\n"
                "**2. File Size:** Verify the file isn't exceeding Telegram's upload limit for your account type.\n"
                "**3. Telegram Servers:** Telegram may be experiencing issues. Wait a few minutes and try again."
            )
        elif issue == "slow_transfer":
            text = (
                "**🐌 Slow Transfer Speed**\n\n"
                "If uploads or downloads are very slow:\n\n"
                "**1. Server Load:** During peak hours, Telegram's servers can be slower. Try again at a different time.\n"
                "**2. File Size:** Large files naturally take longer. A 1.5GB file can take several minutes.\n"
                "**3. Your Connection:** Test your internet speed. The bot can only transfer as fast as your connection allows."
            )
        elif issue == "corrupted":
            text = (
                "**🔨 File Corrupted After Download**\n\n"
                "If the file you received appears broken or won't play:\n\n"
                "**1. Re-Download:** Try downloading the file again from the bot's message. Telegram sometimes corrupts files during transfer.\n"
                "**2. Original File:** The source file may have been corrupted before processing. Test the original on your device.\n"
                "**3. Format Issue:** Some players can't handle certain codecs. Try opening the file with VLC."
            )
        # --- Metadata & Detection ---
        elif issue == "wrong_meta":
            text = (
                "**❌ Wrong Metadata / Bad TMDb Match**\n\n"
                "Sometimes, the Auto-Detector grabs the wrong poster or movie name because the original filename was too messy.\n\n"
                "**How to fix it:**\n"
                "1. **Clean the Filename:** Rename the file on your phone/PC *before* sending it. Format it like `Movie Title (Year).mp4`. This gives the bot a 99% success rate.\n"
                "2. **Use Quick Rename:** If it's not a real movie, go to `/settings` and enable **Quick Rename Mode**. This skips TMDb entirely!\n"
                "3. **Manual Override:** When the bot asks you to confirm the TMDb details, just hit **Skip / Manual**."
            )
        elif issue == "tmdb_empty":
            text = (
                "**🔍 TMDb No Results**\n\n"
                "If the bot can't find your movie or series on TMDb:\n\n"
                "**1. Clean the Filename:** Remove junk from the name. `Movie.2024.1080p.WEB-DL.x264` should become `Movie (2024).mp4`.\n"
                "**2. English Title:** TMDb works best with English titles. If your file has a foreign title, try the international name.\n"
                "**3. New Release:** Very new or obscure releases may not be on TMDb yet. Use **Skip / Manual** to set details yourself."
            )
        elif issue == "wrong_ep":
            text = (
                "**📺 Wrong Season/Episode**\n\n"
                "If the bot detects the wrong season or episode number:\n\n"
                "**1. Filename Format:** Ensure the file follows common naming: `Show S01E05.mkv` or `Show - 1x05.mkv`.\n"
                "**2. Absolute Numbering:** Some anime uses absolute episode numbers. The bot expects SxxExx format.\n"
                "**3. Manual Edit:** When the bot shows detected info, you can manually change the season and episode before confirming."
            )
        elif issue == "poster_fail":
            text = (
                "**🖼 Poster Not Loading**\n\n"
                "If the thumbnail or poster doesn't appear:\n\n"
                "**1. TMDb Availability:** Not all titles have poster images on TMDb. The bot can only use what's available.\n"
                "**2. Set a Custom Thumbnail:** Go to `/settings` > **Default Thumbnail** and upload your own.\n"
                "**3. Skip / Manual:** When in manual mode, you can send any image as the thumbnail."
            )
        # --- Processing Issues ---
        elif issue == "stuck":
            text = (
                "**⏳ Stuck Processing**\n\n"
                "If the progress bar seems completely frozen at a specific percentage for several minutes:\n\n"
                "**1. Cancel the Task:** Type the `/end` command. This forces the bot to abort whatever it is doing and clears your active state.\n"
                "**2. Corrupt File:** The file you uploaded might be broken or incomplete. Try playing it on your device to ensure it's not corrupted.\n"
                "**3. Telegram Server Lag:** Sometimes Telegram's upload servers experience severe delays. Cancel it and try again later."
            )
        elif issue == "conv_fail":
            text = (
                "**💥 Conversion Fails**\n\n"
                "If the File Converter returns an error:\n\n"
                "**1. Unsupported Codec:** The source file may use a codec the converter can't handle. Try a different format.\n"
                "**2. Corrupt Source:** The original file might be damaged. Test it on your device with VLC first.\n"
                "**3. File Too Large:** Very large files may time out during conversion. Try compressing the file before sending."
            )
        elif issue == "empty_output":
            text = (
                "**📄 Output File Empty**\n\n"
                "If the bot returns a file that's 0 bytes or won't open:\n\n"
                "**1. Source Issue:** The original file may have been corrupted or incomplete.\n"
                "**2. Format Mismatch:** Converting between incompatible formats can produce empty files. Stick to common formats like MP4/MKV.\n"
                "**3. Retry:** Cancel with `/end` and send the file again. Temporary server glitches can cause this."
            )
        elif issue == "bad_quality":
            text = (
                "**📉 Bad Output Quality**\n\n"
                "If the output looks worse than the original:\n\n"
                "**1. Renaming Doesn't Re-encode:** The Rename & Tag tool never changes video quality. If quality dropped, the issue is elsewhere.\n"
                "**2. Conversion Compression:** The File Converter may compress during format changes. This is normal for some conversions.\n"
                "**3. Telegram Compression:** Make sure you're sending files as **Documents**, not as 'Video'. Telegram compresses videos heavily."
            )
        # --- Audio & Subtitles ---
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
        elif issue == "audio_sync":
            text = (
                "**🔊 Audio Out of Sync**\n\n"
                "If the audio doesn't match the video after processing:\n\n"
                "**1. Original Sync:** Check if the original file already had sync issues. Play it on VLC to compare.\n"
                "**2. Conversion Artifact:** Format conversion can sometimes cause slight desync. Try a different output format.\n"
                "**3. Variable Frame Rate:** VFR videos are prone to sync issues. The bot processes them as-is."
            )
        elif issue == "wrong_lang":
            text = (
                "**🗣 Wrong Audio Language**\n\n"
                "If the bot picks the wrong audio track:\n\n"
                "**1. Default Track:** The bot uses the default audio track set in the file's metadata. This may not always be your preferred language.\n"
                "**2. MKV Multi-Audio:** MKV files can contain multiple audio tracks. The first one is usually selected.\n"
                "**3. Re-mux with MKVToolNix:** Use a tool on your PC to set the correct default audio track before sending."
            )
        # --- Files & Storage ---
        elif issue == "myfiles_fail":
            text = (
                "**📂 MyFiles Not Loading**\n\n"
                "If the `/myfiles` command isn't working:\n\n"
                "**1. Empty Storage:** You might not have any stored files yet. Process a file first and it will appear.\n"
                "**2. Session Conflict:** Type `/end` first to clear any active sessions, then try `/myfiles` again.\n"
                "**3. Server Restart:** After a bot restart, give it a minute to reconnect to the database."
            )
        elif issue == "expired":
            text = (
                "**⏰ Files Expired Too Early**\n\n"
                "If your temporary files disappeared sooner than expected:\n\n"
                "**1. Expiry Rules:** Temporary files have a plan-based expiry (e.g., 7 days for free users). Check your plan details.\n"
                "**2. Use Permanent Slots:** Pin important files to your permanent storage to keep them forever.\n"
                "**3. Storage Cleanup:** The admin may have triggered a manual cleanup. Contact support if this happens repeatedly."
            )
        elif issue == "cant_delete":
            text = (
                "**🗑 Can't Delete Files**\n\n"
                "If you're unable to remove files from your storage:\n\n"
                "**1. Use /myfiles:** Navigate to the file via `/myfiles` and use the delete button in the file's detail view.\n"
                "**2. Active Processing:** You can't delete a file that's currently being processed. Wait for completion or use `/end`.\n"
                "**3. Expired Files:** Already-expired files are removed automatically. They may just not be visible anymore."
            )
        elif issue == "storage_full":
            text = (
                "**💾 Storage Full**\n\n"
                "If you've hit your storage limit:\n\n"
                "**1. Delete Old Files:** Use `/myfiles` to remove files you no longer need.\n"
                "**2. Permanent Slot Limit:** Each plan has a fixed number of permanent slots. Free up slots by unpinning files.\n"
                "**3. Upgrade Plan:** Premium plans offer significantly more storage. Check the Premium Dashboard on `/start`."
            )
        # --- Account & Premium ---
        elif issue == "prem_fail":
            text = (
                "**💎 Premium Not Activating**\n\n"
                "If your Premium subscription isn't working:\n\n"
                "**1. Activation Delay:** Allow a few minutes after purchase for the system to process your payment.\n"
                "**2. Restart Session:** Send `/start` to refresh your profile. The bot caches user data briefly.\n"
                "**3. Contact Admin:** If it still doesn't work, use `/info` to find the support contact and send your payment receipt."
            )
        elif issue == "quota_reset":
            text = (
                "**🔄 Quota Not Resetting**\n\n"
                "If your daily limits haven't reset:\n\n"
                "**1. 24-Hour Cycle:** Quotas reset exactly 24 hours after your first usage of the day, not at midnight.\n"
                "**2. Check Usage:** Use `/myfiles` or your profile to see your current usage and when the reset is due.\n"
                "**3. Time Zone:** The reset timer is based on UTC. Your local time may differ."
            )
        elif issue == "upgrade_fail":
            text = (
                "**⬆️ Upgrade Problems**\n\n"
                "If you can't upgrade your plan:\n\n"
                "**1. Already Premium:** Check if you already have an active subscription via `/start`.\n"
                "**2. Payment Method:** Ensure the payment method configured by the admin is available in your region.\n"
                "**3. Contact Support:** Use `/info` to reach the bot admin for manual activation or alternative payment options."
            )
        elif issue == "acc_missing":
            text = (
                "**👤 Account Not Found**\n\n"
                "If the bot doesn't recognize your account:\n\n"
                "**1. First Time:** Send `/start` to register. The bot creates your profile on first interaction.\n"
                "**2. Database Reset:** The admin may have reset the database. Your data would need to be restored manually.\n"
                "**3. Different Account:** Ensure you're using the same Telegram account you originally registered with."
            )
        else:
            text = "Unknown issue. Please go back and select a valid topic."

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_to_cat))
        except MessageNotModified:
            pass

    elif data == "help_settings":
        try:
            await callback_query.message.edit_text(
                "**⚙️ Settings & Info**\n\n"
                "> Customize your experience.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Explore the different settings you can configure:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("📝 Filename Template", callback_data="help_set_filename"),
                         InlineKeyboardButton("💬 Caption Template", callback_data="help_set_caption")],
                        [InlineKeyboardButton("🖼 Default Thumbnail", callback_data="help_set_thumb"),
                         InlineKeyboardButton("⚡ Quick Rename", callback_data="help_set_quick")],
                        [InlineKeyboardButton("📺 Dumb Channels", callback_data="help_set_dumb"),
                         InlineKeyboardButton("ℹ️ Bot Info", callback_data="help_set_info")],
                        [InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]
                    ]
                )
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_set_"):
        setting = data.replace("help_set_", "")
        back_to_set = [[InlineKeyboardButton("← Back to Settings", callback_data="help_settings")]]

        if setting == "filename":
            text = (
                "**📝 Filename Template**\n\n"
                "> Control how output files are named.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Go to `/settings` > **Filename Template** to customize.\n\n"
                "• Use variables like `{Title}`, `{Year}`, `{Quality}`.\n"
                "• The file extension is always appended automatically.\n"
                "• Example: `{Title} ({Year}) [{Quality}]`"
            )
        elif setting == "caption":
            text = (
                "**💬 Caption Template**\n\n"
                "> Customize the text below your files.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Go to `/settings` > **Caption Template** to configure.\n\n"
                "• Captions appear directly below your uploaded files in Telegram.\n"
                "• Supports the same variables as filename templates.\n"
                "• You can also use Telegram formatting like **bold** and __italic__."
            )
        elif setting == "thumb":
            text = (
                "**🖼 Default Thumbnail**\n\n"
                "> Set a custom poster for all uploads.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Go to `/settings` > **Default Thumbnail**.\n\n"
                "• Upload any image to use as the default thumbnail for all processed files.\n"
                "• This overrides TMDb posters unless disabled per-file.\n"
                "• To remove it, go back and select **Remove Thumbnail**."
            )
        elif setting == "quick":
            text = (
                "**⚡ Quick Rename Mode**\n\n"
                "> Skip TMDb entirely.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Enable via `/settings` > **Quick Rename Mode**.\n\n"
                "• When enabled, the bot skips all TMDb lookups and metadata detection.\n"
                "• You'll be prompted for a custom filename immediately.\n"
                "• Perfect for personal files, documents, or non-media content."
            )
        elif setting == "dumb":
            text = (
                "**📺 Dumb Channels Setup**\n\n"
                "> Route processed files to channels.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Go to `/settings` > **Dumb Channels**.\n\n"
                "• Add the bot as an admin to your channel first.\n"
                "• Then forward a message from that channel to the bot.\n"
                "• Set the channel type: Movies, Series, or Standard (everything)."
            )
        elif setting == "info":
            text = (
                "**ℹ️ Bot Info & Contact**\n\n"
                "> Learn about the bot.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Use the `/info` command to view:\n\n"
                "• Bot version and uptime status.\n"
                "• The admin's contact details for support.\n"
                "• Links to the official channel or community group."
            )
        else:
            text = "Unknown setting."

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(back_to_set))
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
