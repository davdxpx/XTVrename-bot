from pyrogram import Client, filters, StopPropagation, ContinuePropagation
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from database import db
from utils.log import get_logger
from plugins.admin import admin_sessions

logger = get_logger("plugins.admin_setup")

@Client.on_message(filters.regex(r"^/(start|new)") & filters.private, group=-1)
async def intercept_start_for_setup(client, message):
    user_id = message.from_user.id

    # Fast path: check cache for complete setup
    setup_complete = await db.get_setting("is_bot_setup_complete", default=False, user_id=Config.CEO_ID)
    if setup_complete:
        raise ContinuePropagation # Fall through to regular start handler

    if user_id != Config.CEO_ID:
        await message.reply_text("🚧 **Bot is currently being set up by the Admin.**\nPlease come back later.")
        raise StopPropagation

    # Check if there's a specific admin session going on that should intercept this instead
    if user_id in admin_sessions and admin_sessions[user_id] in ["awaiting_setup_bot_name", "awaiting_setup_community_name", "awaiting_setup_timeout", "awaiting_setup_free_limits", "awaiting_setup_trial_length"]:
        raise ContinuePropagation # Let the text handler deal with it

    # Initiate or resume CEO setup
    await send_ceo_setup_menu(client, message.chat.id)
    raise StopPropagation

async def send_ceo_setup_menu(client, chat_id, edit_message=None):
    state = await db.get_setting("setup_stage", default="1.0", user_id=Config.CEO_ID)

    # We will dispatch based on state
    if state == "1.0":
        await render_stage_1(client, chat_id, edit_message)

    elif state.startswith("2."):
        await render_stage_2(client, chat_id, state, edit_message)

    elif state.startswith("3."):
        await render_stage_3(client, chat_id, state, edit_message)

    elif state.startswith("4."):
        await render_stage_4(client, chat_id, state, edit_message)

async def render_stage_1(client, chat_id, edit_message=None):
    text = (
        "🚀 **Welcome to 𝕏TV MediaStudio™ Initial Setup!**\n\n"
        "**Stage 1: Basic Bot Info**\n"
        "Let's configure the basic visual elements of the bot.\n\n"
        "> __Tip: You can use the Skip button if you want to keep the defaults.__"
    )

    buttons = []

    if Config.PUBLIC_MODE:
        config = await db.get_public_config()
        bot_name = config.get("bot_name", "𝕏TV MediaStudio™")
        community = config.get("community_name", "Our Community")

        text += f"\n\n**Current Bot Name:** `{bot_name}`"
        text += f"\n**Current Community Name:** `{community}`"

        buttons.extend([
            [InlineKeyboardButton("✏️ Edit Bot Name", callback_data="setup_set_bot_name")],
            [InlineKeyboardButton("✏️ Edit Community Name", callback_data="setup_set_community_name")]
        ])
    else:
        text += "\n\n**(Note: Bot Name and Community Name customization are only available in Public Mode. You can skip this.)**"

    buttons.extend([
        [InlineKeyboardButton("🌐 Set Language (Coming Soon)", callback_data="setup_noop")],
        [InlineKeyboardButton("➡️ Next Stage", callback_data="setup_next_2.0")]
    ])

    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass
    else:
        await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

async def render_stage_2(client, chat_id, state, edit_message=None):
    if state == "2.0":
        # MyFiles enable/disable
        text = (
            "📁 **Stage 2: Storage & MyFiles™**\n\n"
            "Do you want to enable the **MyFiles™ Management System**?\n"
            "This allows users to browse their uploaded/processed files in a neat inline dashboard."
        )
        buttons = [
            [InlineKeyboardButton("✅ Yes, Enable MyFiles™", callback_data="setup_myfiles_on")],
            [InlineKeyboardButton("❌ No, Disable MyFiles™", callback_data="setup_myfiles_off")]
        ]
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                pass
        else:
            await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

    elif state == "2.1":
        # Storage Channels
        text = "📁 **Stage 2: Storage & MyFiles™**\n\n"
        if Config.PUBLIC_MODE:
            text += (
                "In **Public Mode**, each user sets up their own storage channels.\n"
                "You, as the CEO, don't need to configure global storage channels for users.\n\n"
                "Click Next to continue."
            )
            buttons = [[InlineKeyboardButton("➡️ Next Stage", callback_data="setup_next_3.0")]]
        else:
            text += (
                "In **Non-Public Mode**, you must configure the central 'Dumb Channels' where all media is stored.\n\n"
                "1. Create three private channels (Standard, Movie, Series).\n"
                "2. Add the bot to them as Admin.\n"
                "3. Forward a message from each channel to this chat to set them."
            )

            # Show current channels
            dumb_channels = await db.get_dumb_channels()
            def_ch = await db.get_default_dumb_channel()
            mov_ch = await db.get_movie_dumb_channel()
            ser_ch = await db.get_series_dumb_channel()

            text += "\n\n**Current Channels:**"
            text += f"\n🔸 Standard: `{def_ch if def_ch else 'Not Set'}`"
            text += f"\n🎬 Movie: `{mov_ch if mov_ch else 'Not Set'}`"
            text += f"\n📺 Series: `{ser_ch if ser_ch else 'Not Set'}`"

            buttons = [
                [InlineKeyboardButton("➡️ Next Stage", callback_data="setup_next_3.0")]
            ]
            if edit_message:
                try:
                    await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                except Exception:
                    pass
            else:
                await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

async def render_stage_3(client, chat_id, state, edit_message=None):
    if state == "3.0":
        text = (
            "⚙️ **Stage 3: Features & Premium (1/3)**\n\n"
            "Let's configure the base features available to **ALL users** (Free Plan)."
        )
        toggles = await db.get_feature_toggles()

        def emoji(s): return "✅" if s else "❌"
        buttons = [
            [InlineKeyboardButton(f"{emoji(toggles.get('audio_editor', True))} Audio Editor", callback_data="setup_tog_audio")],
            [InlineKeyboardButton(f"{emoji(toggles.get('file_converter', True))} File Converter", callback_data="setup_tog_conv")],
            [InlineKeyboardButton(f"{emoji(toggles.get('watermarker', True))} Watermarker", callback_data="setup_tog_water")],
            [InlineKeyboardButton(f"{emoji(toggles.get('subtitle_extractor', True))} Subtitle Extractor", callback_data="setup_tog_sub")],
            [InlineKeyboardButton("➡️ Next Step", callback_data="setup_next_3.1")]
        ]
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                pass
        else:
            await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

    elif state == "3.1":
        text = (
            "💎 **Stage 3: Features & Premium (2/3)**\n\n"
            "Do you want to enable the **Premium System**?\n"
            "This will activate premium plans, limits, trials, and payment systems."
        )
        if not Config.PUBLIC_MODE:
            text += "\n\n__(Note: Premium System is only relevant in Public Mode)__"
            buttons = [[InlineKeyboardButton("➡️ Skip (Non-Public Mode)", callback_data="setup_next_4.0")]]
        else:
            buttons = [
                [InlineKeyboardButton("✅ Yes, Enable Premium", callback_data="setup_prem_on")],
                [InlineKeyboardButton("❌ No, Disable Premium", callback_data="setup_prem_off")]
            ]
            if edit_message:
                try:
                    await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                except Exception:
                    pass
            else:
                await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

    elif state == "3.2":
        text = (
            "💎 **Stage 3: Features & Premium (3/3)**\n\n"
            "Premium System is Enabled.\n"
            "Do you want to enable the **Deluxe Plan** (a higher tier above Standard)?\n"
            "Do you want to enable the **Trial System** for new users?"
        )
        config = await db.get_public_config()
        deluxe_enabled = config.get("premium_deluxe_enabled", True)
        trial_enabled = config.get("premium_trial_enabled", True)

        def emoji(s): return "✅" if s else "❌"
        buttons = [
            [InlineKeyboardButton(f"{emoji(deluxe_enabled)} Deluxe Plan", callback_data="setup_tog_deluxe")],
            [InlineKeyboardButton(f"{emoji(trial_enabled)} Trial System", callback_data="setup_tog_trial")],
            [InlineKeyboardButton("⚙️ Configure Trial Length", callback_data="setup_set_trial_len")],
            [InlineKeyboardButton("➡️ Next Stage", callback_data="setup_next_4.0")]
        ]
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                pass
        else:
            await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

async def render_stage_4(client, chat_id, state, edit_message=None):
    if state == "4.0":
        text = (
            "🔐 **Stage 4: Advanced & 𝕏TV Pro™ (1/2)**\n\n"
            "Configure Force-Sub & Timeout limits."
        )
        timeout = await db.get_dumb_channel_timeout()
        text += f"\n\n**Dumb Channel Timeout:** `{timeout} seconds`"

        buttons = [
            [InlineKeyboardButton("⚙️ Force-Sub Settings", callback_data="setup_force_sub")],
            [InlineKeyboardButton("⏱️ Edit Timeout", callback_data="setup_edit_timeout")],
            [InlineKeyboardButton("💳 Manage Payments", callback_data="setup_payments")] if Config.PUBLIC_MODE else [],
            [InlineKeyboardButton("➡️ Next Step", callback_data="setup_next_4.1")]
        ]
        buttons = [b for b in buttons if b] # Remove empty
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                pass
        else:
            await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

    elif state == "4.1":
        text = (
            "🚀 **Stage 4: Advanced & 𝕏TV Pro™ (2/2)**\n\n"
            "Do you want to set up the **𝕏TV Pro™ 4GB Userbot** now?\n"
            "This allows bypassing the 2GB Telegram limit."
        )
        buttons = [
            [InlineKeyboardButton("✅ Setup 4GB Userbot", callback_data="setup_pro_bot")],
            [InlineKeyboardButton("⏩ Skip & Finish Setup", callback_data="setup_finish")]
        ]
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                pass
        else:
            await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^setup_"))
async def handle_setup_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if user_id != Config.CEO_ID:
        await callback_query.answer("Unauthorized", show_alert=True)
        return

    if data == "setup_noop":
        await callback_query.answer("Coming soon!", show_alert=True)

    elif data.startswith("setup_next_"):
        next_stage = data.split("_")[2]
        await db.update_setting("setup_stage", next_stage, user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

    elif data == "setup_set_bot_name":
        if not Config.PUBLIC_MODE:
            await callback_query.answer("Only available in Public Mode.", show_alert=True)
            return
        admin_sessions[user_id] = "awaiting_setup_bot_name"
        await callback_query.message.reply_text("Please send the new **Bot Name**:\n\n__(Send /cancel to abort)__")

    elif data == "setup_set_community_name":
        if not Config.PUBLIC_MODE:
            await callback_query.answer("Only available in Public Mode.", show_alert=True)
            return
        admin_sessions[user_id] = "awaiting_setup_community_name"
        await callback_query.message.reply_text("Please send the new **Community Name**:\n\n__(Send /cancel to abort)__")

    elif data == "setup_myfiles_on":
        await db.update_setting("myfiles_enabled", True)
        await db.update_setting("setup_stage", "2.1", user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

    elif data == "setup_myfiles_off":
        await db.update_setting("myfiles_enabled", False)
        await db.update_setting("setup_stage", "2.1", user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

    elif data.startswith("setup_tog_"):
        tog = data.split("_")[2]
        if tog in ["audio", "conv", "water", "sub"]:
            map_dict = {"audio": "audio_editor", "conv": "file_converter", "water": "watermarker", "sub": "subtitle_extractor"}
            feature = map_dict[tog]
            toggles = await db.get_feature_toggles()
            current = toggles.get(feature, True)
            toggles[feature] = not current
            await db.update_setting("global_feature_toggles", toggles)
            await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

        elif tog == "deluxe":
            config = await db.get_public_config()
            current = config.get("premium_deluxe_enabled", True)
            await db.update_public_config("premium_deluxe_enabled", not current)
            await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

        elif tog == "trial":
            config = await db.get_public_config()
            current = config.get("premium_trial_enabled", True)
            await db.update_public_config("premium_trial_enabled", not current)
            await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

    elif data == "setup_prem_on":
        await db.update_public_config("premium_system_enabled", True)
        await db.update_setting("setup_stage", "3.2", user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

    elif data == "setup_prem_off":
        await db.update_public_config("premium_system_enabled", False)
        await db.update_setting("setup_stage", "4.0", user_id=Config.CEO_ID)
        await send_ceo_setup_menu(client, callback_query.message.chat.id, edit_message=callback_query.message)

    elif data == "setup_set_trial_len":
        admin_sessions[user_id] = "awaiting_setup_trial_length"
        await callback_query.message.reply_text("Please send the **Trial Length** in days (e.g., 7):\n\n__(Send /cancel to abort)__")

    elif data == "setup_edit_timeout":
        admin_sessions[user_id] = "awaiting_setup_timeout"
        await callback_query.message.reply_text("Please send the new **Timeout** in seconds (e.g., 60):\n\n__(Send /cancel to abort)__")

    elif data == "setup_force_sub":
        # Launch existing force sub menu
        from plugins.admin import get_admin_force_sub_menu
        msg, kb = await get_admin_force_sub_menu()
        try:
            await callback_query.message.edit_text(msg, reply_markup=kb)
        except Exception:
            pass

    elif data == "setup_payments":
        await callback_query.answer("Open Admin Panel -> Premium Systems -> Setup Payments to configure.", show_alert=True)

    elif data == "setup_pro_bot":
        # Launch pro bot setup
        from plugins.admin import admin_sessions
        admin_sessions[user_id] = "awaiting_pro_api_id"
        await callback_query.message.reply_text(
            "⚡ **𝕏TV Pro™ 4GB Userbot Setup**\n\n"
            "Please send your **API ID**.\n"
            "You can get it from https://my.telegram.org\n\n"
            "__(Send /cancel to abort)__"
        )

    elif data == "setup_finish":
        await db.update_setting("is_bot_setup_complete", True, user_id=Config.CEO_ID)
        await db.update_setting("setup_stage", "done", user_id=Config.CEO_ID)
        try:
            await callback_query.message.edit_text(
                "🎉 **Setup Complete!**\n\nThe bot is now fully configured and ready to use.\n"
                "You can always change these settings in the `/admin` panel.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Enter Bot", callback_data="help_close")]])
            )
        except Exception:
            pass

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "new", "cancel"]), group=1)
async def handle_setup_text_inputs(client, message):
    user_id = message.from_user.id
    if user_id not in admin_sessions:
        raise ContinuePropagation

    state = admin_sessions[user_id]

    if state == "awaiting_setup_bot_name":
        await db.update_public_config("bot_name", message.text.strip())
        admin_sessions.pop(user_id, None)
        await message.reply_text("✅ Bot Name updated!")
        await send_ceo_setup_menu(client, message.chat.id)
        raise StopPropagation

    elif state == "awaiting_setup_community_name":
        await db.update_public_config("community_name", message.text.strip())
        admin_sessions.pop(user_id, None)
        await message.reply_text("✅ Community Name updated!")
        await send_ceo_setup_menu(client, message.chat.id)
        raise StopPropagation

    elif state == "awaiting_setup_trial_length":
        try:
            days = int(message.text.strip())
            await db.update_public_config("premium_trial_length_days", days)
            admin_sessions.pop(user_id, None)
            await message.reply_text("✅ Trial Length updated!")
            await send_ceo_setup_menu(client, message.chat.id)
        except ValueError:
            await message.reply_text("❌ Please enter a valid number.")
        raise StopPropagation

    elif state == "awaiting_setup_timeout":
        try:
            val = int(message.text.strip())
            await db.update_setting("dumb_channel_timeout", val)
            admin_sessions.pop(user_id, None)
            await message.reply_text("✅ Timeout updated!")
            await send_ceo_setup_menu(client, message.chat.id)
        except ValueError:
            await message.reply_text("❌ Please enter a valid number.")
        raise StopPropagation

@Client.on_message(filters.forwarded & filters.private, group=1)
async def handle_setup_forwarded_channels(client, message):
    user_id = message.from_user.id
    if user_id != Config.CEO_ID:
        return

    state = await db.get_setting("setup_stage", default="1.0", user_id=Config.CEO_ID)
    if state == "2.1" and not Config.PUBLIC_MODE:
        chat_id = message.forward_from_chat.id if message.forward_from_chat else None
        if not chat_id:
            await message.reply_text("❌ Could not detect channel. Ensure the channel isn't restricting forwards.")
            raise StopPropagation

        def_ch = await db.get_default_dumb_channel()
        mov_ch = await db.get_movie_dumb_channel()
        ser_ch = await db.get_series_dumb_channel()

        if not def_ch:
            await db.set_default_dumb_channel(chat_id)
            await message.reply_text("✅ Standard Channel set!")
        elif not mov_ch:
            await db.set_movie_dumb_channel(chat_id)
            await message.reply_text("✅ Movie Channel set!")
        elif not ser_ch:
            await db.set_series_dumb_channel(chat_id)
            await message.reply_text("✅ Series Channel set!")
        else:
            await message.reply_text("⚠️ All 3 channels are already set! Click Next Stage.")

        await send_ceo_setup_menu(client, message.chat.id)
        raise StopPropagation
