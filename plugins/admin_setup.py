from pyrogram import Client, filters, StopPropagation
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from database import db
from utils.log import get_logger
from plugins.admin_legacy import admin_sessions

logger = get_logger("plugins.admin_setup")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _render_setup(client, chat_id, text, buttons, msg_id=None):
    """Send or edit the anchor setup message. Returns the message_id."""
    markup = InlineKeyboardMarkup(buttons)
    if msg_id:
        try:
            await client.edit_message_text(chat_id, msg_id, text, reply_markup=markup)
            return msg_id
        except MessageNotModified:
            return msg_id
        except Exception:
            pass
    msg = await client.send_message(chat_id, text, reply_markup=markup)
    return msg.id


def _build_progress_bar(current_stage: str) -> str:
    """Build a visual progress indicator for the setup wizard."""
    stages = [("1", "Bot Info"), ("2", "Storage"), ("3", "Features"), ("4", "Advanced")]
    current_num = int(current_stage.split(".")[0])
    parts = []
    for num_str, label in stages:
        num = int(num_str)
        if num < current_num:
            parts.append(f"● {label}")
        elif num == current_num:
            parts.append(f"◉ **{label}**")
        else:
            parts.append(f"○ {label}")
    return " ━ ".join(parts)


def _get_setup_msg_id():
    """Get the stored anchor message ID from admin_sessions."""
    state_obj = admin_sessions.get(Config.CEO_ID)
    if isinstance(state_obj, dict):
        return state_obj.get("msg_id")
    return None


def _store_setup_session(msg_id, state="setup_active"):
    """Store or update the setup session with anchor msg_id."""
    admin_sessions[Config.CEO_ID] = {
        "state": state,
        "msg_id": msg_id,
        "setup_context": True,
    }

@Client.on_message(filters.regex(r"^/(start|new)") & filters.private, group=-1)
async def intercept_start_for_setup(client, message):
    user_id = message.from_user.id

    # Fast path: check cache for complete setup
    setup_complete = await db.get_setting("is_bot_setup_complete", default=False, user_id=Config.CEO_ID)
    if setup_complete:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    if user_id != Config.CEO_ID:
        await message.reply_text("🚧 **Bot is currently being set up by the Admin.**\nPlease come back later.")
        raise StopPropagation

    # Check if there's a text-input session that should intercept
    state_obj = admin_sessions.get(user_id)
    if state_obj:
        state = state_obj if isinstance(state_obj, str) else state_obj.get("state", "")
        awaiting_states = [
            "awaiting_setup_bot_name", "awaiting_setup_community_name",
            "awaiting_setup_timeout", "awaiting_setup_free_limits",
            "awaiting_setup_trial_length",
        ]
        if state in awaiting_states:
            from pyrogram import ContinuePropagation
            raise ContinuePropagation

    # Initiate or resume CEO setup
    await send_ceo_setup_menu(client, message.chat.id)
    raise StopPropagation


async def send_ceo_setup_menu(client, chat_id, msg_id=None):
    """Main dispatcher — renders the current setup stage in the anchor message."""
    if msg_id is None:
        msg_id = _get_setup_msg_id()

    state = await db.get_setting("setup_stage", default="1.0", user_id=Config.CEO_ID)

    if state == "1.0":
        new_id = await render_stage_1(client, chat_id, msg_id)
    elif state.startswith("2."):
        new_id = await render_stage_2(client, chat_id, state, msg_id)
    elif state.startswith("3."):
        new_id = await render_stage_3(client, chat_id, state, msg_id)
    elif state.startswith("4."):
        new_id = await render_stage_4(client, chat_id, state, msg_id)
    else:
        new_id = await render_stage_1(client, chat_id, msg_id)

    _store_setup_session(new_id)
    return new_id

async def render_stage_1(client, chat_id, msg_id=None):
    progress = _build_progress_bar("1.0")
    config = await db.get_public_config() if Config.PUBLIC_MODE else {}
    bot_name = config.get("bot_name", "𝕏TV MediaStudio™") if Config.PUBLIC_MODE else "𝕏TV MediaStudio™"
    community = config.get("community_name", "Our Community") if Config.PUBLIC_MODE else "official XTV"

    text = (
        f"**🚀 𝕏TV MediaStudio™ Setup**\n\n"
        f"> Stage 1: Basic Bot Info\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{progress}\n\n"
        f"Configure the basic visual elements of the bot.\n\n"
        f"**Bot Name:** `{bot_name}`\n"
        f"**Community:** `{community}`\n\n"
        f"__Tip: Skip to keep the defaults.__"
    )

    buttons = [
        [InlineKeyboardButton("✏️ Edit Bot Name", callback_data="setup_set_bot_name")],
        [InlineKeyboardButton("✏️ Edit Community Name", callback_data="setup_set_community_name")],
        [InlineKeyboardButton("➡️ Next Stage", callback_data="setup_next_2.0")],
    ]
    return await _render_setup(client, chat_id, text, buttons, msg_id)

async def render_stage_2(client, chat_id, state, msg_id=None):
    progress = _build_progress_bar("2.0")

    if state == "2.0":
        text = (
            f"**📁 𝕏TV MediaStudio™ Setup**\n\n"
            f"> Stage 2: Storage & MyFiles™\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress}\n\n"
            f"Do you want to enable the **MyFiles™ Management System**?\n"
            f"This allows users to browse their uploaded/processed files in a neat inline dashboard."
        )
        buttons = [
            [InlineKeyboardButton("✅ Yes, Enable MyFiles™", callback_data="setup_myfiles_on")],
            [InlineKeyboardButton("❌ No, Disable MyFiles™", callback_data="setup_myfiles_off")],
        ]
        return await _render_setup(client, chat_id, text, buttons, msg_id)

    elif state == "2.1":
        text = (
            f"**📁 𝕏TV MediaStudio™ Setup**\n\n"
            f"> Stage 2: Storage Channels\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress}\n\n"
        )
        if Config.PUBLIC_MODE:
            text += (
                "In **Public Mode**, each user sets up their own storage channels.\n"
                "You don't need to configure global storage channels.\n\n"
                "Click Next to continue."
            )
        else:
            text += (
                "Configure the central **Dumb Channels** where all media is stored.\n\n"
                "1. Create three private channels (Standard, Movie, Series).\n"
                "2. Add the bot to them as Admin.\n"
                "3. Forward a message from each channel to this chat.\n"
            )
            def_ch = await db.get_default_dumb_channel()
            mov_ch = await db.get_movie_dumb_channel()
            ser_ch = await db.get_series_dumb_channel()
            text += (
                f"\n**Current Channels:**\n"
                f"🔸 Standard: `{def_ch or 'Not Set'}`\n"
                f"🎬 Movie: `{mov_ch or 'Not Set'}`\n"
                f"📺 Series: `{ser_ch or 'Not Set'}`"
            )

        buttons = [[InlineKeyboardButton("➡️ Next Stage", callback_data="setup_next_3.0")]]
        return await _render_setup(client, chat_id, text, buttons, msg_id)

async def render_stage_3(client, chat_id, state, msg_id=None):
    progress = _build_progress_bar("3.0")

    def _e(val): return "✅" if val else "❌"

    if state == "3.0":
        toggles = await db.get_feature_toggles()
        text = (
            f"**⚙️ 𝕏TV MediaStudio™ Setup**\n\n"
            f"> Stage 3: Features & Premium (1/3)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress}\n\n"
            f"Configure the base features available to **all users**."
        )
        buttons = [
            [InlineKeyboardButton(f"{_e(toggles.get('audio_editor', True))} Audio Editor", callback_data="setup_tog_audio")],
            [InlineKeyboardButton(f"{_e(toggles.get('file_converter', True))} File Converter", callback_data="setup_tog_conv")],
            [InlineKeyboardButton(f"{_e(toggles.get('watermarker', True))} Watermarker", callback_data="setup_tog_water")],
            [InlineKeyboardButton(f"{_e(toggles.get('subtitle_extractor', True))} Subtitle Extractor", callback_data="setup_tog_sub")],
            [InlineKeyboardButton("➡️ Next Step", callback_data="setup_next_3.1")],
        ]
        return await _render_setup(client, chat_id, text, buttons, msg_id)

    elif state == "3.1":
        text = (
            f"**💎 𝕏TV MediaStudio™ Setup**\n\n"
            f"> Stage 3: Features & Premium (2/3)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress}\n\n"
            f"Do you want to enable the **Premium System**?\n"
            f"This activates premium plans, limits, trials, and payments."
        )
        if not Config.PUBLIC_MODE:
            text += "\n\n__Premium System is only relevant in Public Mode.__"
            buttons = [[InlineKeyboardButton("➡️ Skip (Non-Public Mode)", callback_data="setup_next_4.0")]]
        else:
            buttons = [
                [InlineKeyboardButton("✅ Yes, Enable Premium", callback_data="setup_prem_on")],
                [InlineKeyboardButton("❌ No, Disable Premium", callback_data="setup_prem_off")],
            ]
        return await _render_setup(client, chat_id, text, buttons, msg_id)

    elif state == "3.2":
        config = await db.get_public_config()
        deluxe_enabled = config.get("premium_deluxe_enabled", True)
        trial_enabled = config.get("premium_trial_enabled", True)
        text = (
            f"**💎 𝕏TV MediaStudio™ Setup**\n\n"
            f"> Stage 3: Features & Premium (3/3)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress}\n\n"
            f"Premium System is **Enabled**.\n\n"
            f"**Deluxe Plan:** {_e(deluxe_enabled)}  ·  **Trial System:** {_e(trial_enabled)}"
        )
        buttons = [
            [InlineKeyboardButton(f"{_e(deluxe_enabled)} Deluxe Plan", callback_data="setup_tog_deluxe")],
            [InlineKeyboardButton(f"{_e(trial_enabled)} Trial System", callback_data="setup_tog_trial")],
            [InlineKeyboardButton("⚙️ Configure Trial Length", callback_data="setup_set_trial_len")],
            [InlineKeyboardButton("➡️ Next Stage", callback_data="setup_next_4.0")],
        ]
        return await _render_setup(client, chat_id, text, buttons, msg_id)

async def render_stage_4(client, chat_id, state, msg_id=None):
    progress = _build_progress_bar("4.0")

    if state == "4.0":
        timeout = await db.get_dumb_channel_timeout()
        text = (
            f"**🔐 𝕏TV MediaStudio™ Setup**\n\n"
            f"> Stage 4: Advanced & 𝕏TV Pro™ (1/2)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress}\n\n"
            f"Configure Force-Sub & Timeout limits.\n\n"
            f"**Dumb Channel Timeout:** `{timeout} seconds`"
        )
        buttons = [
            [InlineKeyboardButton("⚙️ Force-Sub Settings", callback_data="setup_force_sub")],
            [InlineKeyboardButton("⏱️ Edit Timeout", callback_data="setup_edit_timeout")],
        ]
        if Config.PUBLIC_MODE:
            buttons.append([InlineKeyboardButton("💳 Manage Payments", callback_data="setup_payments")])
        buttons.append([InlineKeyboardButton("➡️ Next Step", callback_data="setup_next_4.1")])
        return await _render_setup(client, chat_id, text, buttons, msg_id)

    elif state == "4.1":
        text = (
            f"**🚀 𝕏TV MediaStudio™ Setup**\n\n"
            f"> Stage 4: Advanced & 𝕏TV Pro™ (2/2)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress}\n\n"
            f"Do you want to set up the **𝕏TV Pro™ 4GB Userbot** now?\n"
            f"This allows bypassing the 2GB Telegram limit."
        )
        buttons = [
            [InlineKeyboardButton("✅ Setup 4GB Userbot", callback_data="setup_pro_bot")],
            [InlineKeyboardButton("⏩ Skip & Finish Setup", callback_data="setup_finish")],
        ]
        return await _render_setup(client, chat_id, text, buttons, msg_id)

@Client.on_callback_query(filters.regex(r"^setup_"))
async def handle_setup_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    msg_id = callback_query.message.id
    chat_id = callback_query.message.chat.id

    if user_id != Config.CEO_ID:
        await callback_query.answer("Unauthorized", show_alert=True)
        return

    await callback_query.answer()

    # --- Navigation ---
    if data.startswith("setup_next_"):
        next_stage = data.removeprefix("setup_next_")
        await db.update_setting("setup_stage", next_stage, user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, chat_id, msg_id=msg_id)

    # --- Cancel text input prompt, go back to current stage ---
    elif data == "setup_cancel_input":
        _store_setup_session(msg_id)
        await send_ceo_setup_menu(client, chat_id, msg_id=msg_id)

    # --- Text input prompts (shown inline in the anchor message) ---
    elif data == "setup_set_bot_name":
        if not Config.PUBLIC_MODE:
            await callback_query.answer("Only available in Public Mode.", show_alert=True)
            return
        _store_setup_session(msg_id, state="awaiting_setup_bot_name")
        text = (
            "**✏️ Edit Bot Name**\n\n"
            "> Send the new bot name as a text message.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "__Send /cancel to abort.__"
        )
        buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel_input")]]
        await _render_setup(client, chat_id, text, buttons, msg_id)

    elif data == "setup_set_community_name":
        if not Config.PUBLIC_MODE:
            await callback_query.answer("Only available in Public Mode.", show_alert=True)
            return
        _store_setup_session(msg_id, state="awaiting_setup_community_name")
        text = (
            "**✏️ Edit Community Name**\n\n"
            "> Send the new community name as a text message.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "__Send /cancel to abort.__"
        )
        buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel_input")]]
        await _render_setup(client, chat_id, text, buttons, msg_id)

    elif data == "setup_set_trial_len":
        _store_setup_session(msg_id, state="awaiting_setup_trial_length")
        text = (
            "**⚙️ Configure Trial Length**\n\n"
            "> Send the trial length in days (e.g. `7`).\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "__Send /cancel to abort.__"
        )
        buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel_input")]]
        await _render_setup(client, chat_id, text, buttons, msg_id)

    elif data == "setup_edit_timeout":
        _store_setup_session(msg_id, state="awaiting_setup_timeout")
        text = (
            "**⏱️ Edit Timeout**\n\n"
            "> Send the new timeout in seconds (e.g. `60`).\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "__Send /cancel to abort.__"
        )
        buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel_input")]]
        await _render_setup(client, chat_id, text, buttons, msg_id)

    # --- MyFiles toggle ---
    elif data in ("setup_myfiles_on", "setup_myfiles_off"):
        await db.update_setting("myfiles_enabled", data == "setup_myfiles_on")
        await db.update_setting("setup_stage", "2.1", user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, chat_id, msg_id=msg_id)

    # --- Feature toggles ---
    elif data.startswith("setup_tog_"):
        tog = data.removeprefix("setup_tog_")
        feat_map = {"audio": "audio_editor", "conv": "file_converter", "water": "watermarker", "sub": "subtitle_extractor"}
        if tog in feat_map:
            feature = feat_map[tog]
            toggles = await db.get_feature_toggles()
            toggles[feature] = not toggles.get(feature, True)
            await db.update_setting("global_feature_toggles", toggles)
        elif tog == "deluxe":
            config = await db.get_public_config()
            await db.update_public_config("premium_deluxe_enabled", not config.get("premium_deluxe_enabled", True))
        elif tog == "trial":
            config = await db.get_public_config()
            await db.update_public_config("premium_trial_enabled", not config.get("premium_trial_enabled", True))
        await send_ceo_setup_menu(client, chat_id, msg_id=msg_id)

    # --- Premium on/off ---
    elif data == "setup_prem_on":
        await db.update_public_config("premium_system_enabled", True)
        await db.update_setting("setup_stage", "3.2", user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, chat_id, msg_id=msg_id)

    elif data == "setup_prem_off":
        await db.update_public_config("premium_system_enabled", False)
        await db.update_setting("setup_stage", "4.0", user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, chat_id, msg_id=msg_id)

    # --- Force-Sub settings ---
    elif data == "setup_force_sub":
        from plugins.admin_legacy import get_admin_force_sub_menu
        msg, kb = await get_admin_force_sub_menu()
        try:
            await callback_query.message.edit_text(msg, reply_markup=kb)
        except Exception:
            pass

    # --- Payments ---
    elif data == "setup_payments":
        await callback_query.answer("Open Admin Panel -> Premium Systems -> Setup Payments to configure.", show_alert=True)

    # --- XTV Pro Bot setup ---
    elif data == "setup_pro_bot":
        admin_sessions[user_id] = "awaiting_pro_api_id"
        text = (
            "**⚡ 𝕏TV Pro™ 4GB Userbot Setup**\n\n"
            "> Send your **API ID** from https://my.telegram.org\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "__Send /cancel to abort.__"
        )
        buttons = [[InlineKeyboardButton("⏩ Skip & Finish", callback_data="setup_finish")]]
        await _render_setup(client, chat_id, text, buttons, msg_id)

    # --- Finish setup ---
    elif data == "setup_finish":
        await db.update_setting("is_bot_setup_complete", True, user_id=Config.CEO_ID)
        await db.update_setting("setup_stage", "done", user_id=Config.CEO_ID)
        admin_sessions.pop(Config.CEO_ID, None)
        text = (
            "**🎉 Setup Complete!**\n\n"
            "> The bot is now fully configured and ready to use.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "You can always change these settings in the `/admin` panel."
        )
        buttons = [[InlineKeyboardButton("🚀 Enter Bot", callback_data="help_close")]]
        await _render_setup(client, chat_id, text, buttons, msg_id)

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "new", "cancel"]), group=1)
async def handle_setup_text_inputs(client, message):
    user_id = message.from_user.id
    if user_id != Config.CEO_ID:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    state_obj = admin_sessions.get(user_id)
    if not state_obj:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    state = state_obj if isinstance(state_obj, str) else state_obj.get("state", "")
    msg_id = state_obj.get("msg_id") if isinstance(state_obj, dict) else None

    # Only handle setup-specific awaiting states here
    setup_states = {
        "awaiting_setup_bot_name", "awaiting_setup_community_name",
        "awaiting_setup_trial_length", "awaiting_setup_timeout",
    }
    if state not in setup_states:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    # Delete the user's message to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    if state == "awaiting_setup_bot_name":
        await db.update_public_config("bot_name", message.text.strip())
        _store_setup_session(msg_id)
        await send_ceo_setup_menu(client, message.chat.id, msg_id=msg_id)
        raise StopPropagation

    elif state == "awaiting_setup_community_name":
        await db.update_public_config("community_name", message.text.strip())
        _store_setup_session(msg_id)
        await send_ceo_setup_menu(client, message.chat.id, msg_id=msg_id)
        raise StopPropagation

    elif state == "awaiting_setup_trial_length":
        try:
            days = int(message.text.strip())
            await db.update_public_config("premium_trial_length_days", days)
            _store_setup_session(msg_id)
            await send_ceo_setup_menu(client, message.chat.id, msg_id=msg_id)
        except ValueError:
            pass  # Invalid input — just ignore, anchor message still shows prompt
        raise StopPropagation

    elif state == "awaiting_setup_timeout":
        try:
            val = int(message.text.strip())
            await db.update_setting("dumb_channel_timeout", val)
            _store_setup_session(msg_id)
            await send_ceo_setup_menu(client, message.chat.id, msg_id=msg_id)
        except ValueError:
            pass
        raise StopPropagation

@Client.on_message(filters.forwarded & filters.private, group=1)
async def handle_setup_forwarded_channels(client, message):
    user_id = message.from_user.id
    if user_id != Config.CEO_ID:
        return

    state = await db.get_setting("setup_stage", default="1.0", user_id=Config.CEO_ID)
    if state != "2.1" or Config.PUBLIC_MODE:
        return

    msg_id = _get_setup_msg_id()

    channel_id = message.forward_from_chat.id if message.forward_from_chat else None
    if not channel_id:
        # Can't detect channel — delete and ignore
        try:
            await message.delete()
        except Exception:
            pass
        raise StopPropagation

    # Delete the forwarded message to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    def_ch = await db.get_default_dumb_channel()
    mov_ch = await db.get_movie_dumb_channel()
    ser_ch = await db.get_series_dumb_channel()

    if not def_ch:
        await db.set_default_dumb_channel(channel_id)
    elif not mov_ch:
        await db.set_movie_dumb_channel(channel_id)
    elif not ser_ch:
        await db.set_series_dumb_channel(channel_id)

    # Re-render stage 2.1 in the anchor message
    await send_ceo_setup_menu(client, message.chat.id, msg_id=msg_id)
    raise StopPropagation
