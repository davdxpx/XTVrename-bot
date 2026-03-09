from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from utils.log import get_logger
import asyncio
import io
logger = get_logger("plugins.admin")
admin_sessions = {}
def is_admin(user_id):
    return user_id == Config.CEO_ID
@Client.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message):
    if not is_admin(message.from_user.id):
        return

    if Config.PUBLIC_MODE:
        await message.reply_text(
            "🛠 **Public Mode Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for Public Mode.\n"
            "These settings apply globally to the bot, such as branding and rate limits.\n"
            "*(Use /settings to configure your personal renaming templates)*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Edit Bot Name", callback_data="admin_public_bot_name"),
                 InlineKeyboardButton("👥 Edit Community Name", callback_data="admin_public_community_name")],
                [InlineKeyboardButton("🔗 Edit Support Contact", callback_data="admin_public_support_contact"),
                 InlineKeyboardButton("📢 Edit Force-Sub Channel", callback_data="admin_public_force_sub")],
                [InlineKeyboardButton("⏱ Edit Rate Limits", callback_data="admin_public_rate_limit"),
                 InlineKeyboardButton("⏱ Edit Dumb Channel Timeout", callback_data="admin_dumb_timeout")],
                [InlineKeyboardButton("👀 View Public Config", callback_data="admin_public_view")]
            ])
        )
    else:
        await message.reply_text(
            "🛠 **XTV Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for the XTV Rename Bot.\n"
            "These settings affect all files processed by the bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 Manage Thumbnail", callback_data="admin_thumb_menu")],
                [InlineKeyboardButton("📝 Edit Metadata Templates", callback_data="admin_templates")],
                [InlineKeyboardButton("📝 Edit Filename Templates", callback_data="admin_filename_templates")],
                [InlineKeyboardButton("📝 Edit Caption Template", callback_data="admin_caption")],
                [InlineKeyboardButton("📺 Dumb Channels", callback_data="admin_dumb_channels")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
                [InlineKeyboardButton("👀 View Current Settings", callback_data="admin_view")]
            ])
        )

from pyrogram import ContinuePropagation

@Client.on_callback_query(filters.regex(r"^(admin_|edit_template_|edit_fn_template_|prompt_admin_|prompt_public_|prompt_fn_template_|prompt_template_|dumb_)"))
async def admin_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data
    logger.info(f"Admin callback: {data} from user {user_id}")

    # Handle Dumb Channel Callbacks for non-public mode
    if not Config.PUBLIC_MODE and data.startswith("dumb_"):
        if data == "dumb_menu":
            channels = await db.get_dumb_channels()
            default_ch = await db.get_default_dumb_channel()
            text = "📺 **Manage Dumb Channels**\n\n"
            text += "These channels can be used to forward processed files automatically.\n\n"
            text += "**Configured Channels:**\n"
            if not channels:
                text += "- None\n"
            else:
                for ch_id, ch_name in channels.items():
                    marker = " (Default)" if str(ch_id) == default_ch else ""
                    text += f"- {ch_name} `{ch_id}`{marker}\n"

            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add New Dumb Channel", callback_data="dumb_add")],
                    [InlineKeyboardButton("➖ Remove Dumb Channel", callback_data="dumb_remove")],
                    [InlineKeyboardButton("⭐ Set Default", callback_data="dumb_set_default")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                ])
            )
            return
        elif data == "dumb_add":
            admin_sessions[user_id] = "awaiting_dumb_add"
            await callback_query.message.edit_text(
                "➕ **Add Dumb Channel**\n\n"
                "Please add me as an Administrator in the desired channel.\n"
                "Then, forward any message from that channel to me, OR send the Channel ID (e.g. `-100...`) or Public Username.\n\n"
                "*(Send `disable` to cancel)*",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]])
            )
            return
        elif data == "dumb_remove":
            channels = await db.get_dumb_channels()
            if not channels:
                await callback_query.answer("No channels configured.", show_alert=True)
                return
            buttons = []
            for ch_id, ch_name in channels.items():
                buttons.append([InlineKeyboardButton(f"❌ {ch_name}", callback_data=f"dumb_del_{ch_id}")])
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="dumb_menu")])
            await callback_query.message.edit_text("Select a channel to remove:", reply_markup=InlineKeyboardMarkup(buttons))
            return
        elif data.startswith("dumb_del_"):
            ch_id = data.replace("dumb_del_", "")
            await db.remove_dumb_channel(ch_id)
            await callback_query.answer("Channel removed.", show_alert=True)
            # go back
            callback_query.data = "dumb_menu"
            await admin_callback(client, callback_query)
            return
        elif data == "dumb_set_default":
            channels = await db.get_dumb_channels()
            if not channels:
                await callback_query.answer("No channels configured.", show_alert=True)
                return
            buttons = []
            for ch_id, ch_name in channels.items():
                buttons.append([InlineKeyboardButton(f"⭐ {ch_name}", callback_data=f"dumb_def_{ch_id}")])
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="dumb_menu")])
            await callback_query.message.edit_text("Select default auto-detect channel:", reply_markup=InlineKeyboardMarkup(buttons))
            return
        elif data.startswith("dumb_def_"):
            ch_id = data.replace("dumb_def_", "")
            await db.set_default_dumb_channel(ch_id)
            await callback_query.answer("Default channel set.", show_alert=True)
            callback_query.data = "dumb_menu"
            await admin_callback(client, callback_query)
            return

    if data == "admin_dumb_channels":
        callback_query.data = "dumb_menu"
        await admin_callback(client, callback_query)
        return

    if data == "admin_dumb_timeout":
        current_val = await db.get_dumb_channel_timeout()
        await callback_query.message.edit_text(
            f"⏱ **Edit Dumb Channel Timeout**\n\n"
            f"This is the max time (in seconds) the bot will wait for earlier files before uploading to the Dumb Channel.\n\n"
            f"Current: `{current_val}` seconds\n\nClick below to change it.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Change", callback_data="prompt_admin_dumb_timeout")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
        return

    if data == "prompt_admin_dumb_timeout":
        admin_sessions[user_id] = "awaiting_dumb_timeout"
        await callback_query.message.edit_text(
            "⏱ **Send the new timeout in seconds (e.g., 3600 for 1 hour):**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]])
        )
        return

    # Handle Public Mode Callbacks first
    if Config.PUBLIC_MODE and data.startswith("admin_public_"):
        if data == "admin_public_view":
            config = await db.get_public_config()
            text = "👀 **Public Mode Config**\n\n"
            text += f"**Bot Name:** {config.get('bot_name', 'Not set')}\n"
            text += f"**Community Name:** {config.get('community_name', 'Not set')}\n"
            text += f"**Support Contact:** {config.get('support_contact', 'Not set')}\n"
            text += f"**Force-Sub Channel:** {config.get('force_sub_channel', 'Not set')}\n"
            text += f"**Rate Limit Delay:** {config.get('rate_limit_delay', 0)} seconds\n"

            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
            )
            return

        elif data == "admin_public_bot_name":
            config = await db.get_public_config()
            current_val = config.get("bot_name", "Not set")
            await callback_query.message.edit_text(
                f"🤖 **Edit Bot Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change", callback_data="prompt_public_bot_name")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                ])
            )
            return

        elif data == "admin_public_community_name":
            config = await db.get_public_config()
            current_val = config.get("community_name", "Not set")
            await callback_query.message.edit_text(
                f"👥 **Edit Community Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change", callback_data="prompt_public_community_name")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                ])
            )
            return

        elif data == "admin_public_support_contact":
            config = await db.get_public_config()
            current_val = config.get("support_contact", "Not set")
            await callback_query.message.edit_text(
                f"🔗 **Edit Support Contact**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change", callback_data="prompt_public_support_contact")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                ])
            )
            return

        elif data == "admin_public_force_sub":
            config = await db.get_public_config()
            current_val = config.get("force_sub_channel", "Not set")
            await callback_query.message.edit_text(
                f"📢 **Edit Force-Sub Channel**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change", callback_data="prompt_public_force_sub")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                ])
            )
            return

        elif data == "admin_public_rate_limit":
            config = await db.get_public_config()
            current_val = config.get("rate_limit_delay", 0)
            await callback_query.message.edit_text(
                f"⏱ **Edit Rate Limit**\n\nCurrent: `{current_val}` seconds\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change", callback_data="prompt_public_rate_limit")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                ])
            )
            return

    # Handle "Change" prompts for Public Config
    if Config.PUBLIC_MODE and data.startswith("prompt_public_"):
        field = data.replace("prompt_public_", "")
        admin_sessions[user_id] = f"awaiting_public_{field}"

        if field == "bot_name":
            text = "🤖 **Send the new bot name:**"
        elif field == "community_name":
            text = "👥 **Send the new community name:**"
        elif field == "support_contact":
            text = "🔗 **Send the new support contact (e.g., @username or link):**"
        elif field == "force_sub":
            text = (
                "📢 **Setup Force-Sub Channel**\n\n"
                "⏳ **I am waiting...**\n\n"
                "Simply **add me as an Administrator** to your desired channel right now!\n"
                "Make sure I have the 'Invite Users via Link' permission.\n\n"
                "I will automatically detect the channel and set it up instantly.\n\n"
                "*Send `disable` to cancel and turn off Force-Sub.*"
            )
        elif field == "rate_limit":
            text = "⏱ **Send the delay in seconds (e.g., 60).**\nSend `0` to disable."
        else:
            text = "Send the new value:"

        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]])
        )
        return
    if data == "admin_thumb_menu":
        await callback_query.message.edit_text(
            "🖼 **Manage Thumbnail**\n\n"
            "Select an action:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👀 View Current", callback_data="admin_thumb_view")],
                [InlineKeyboardButton("📤 Set Default", callback_data="admin_thumb_set")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "admin_thumb_view":
        thumb_bin, _ = await db.get_thumbnail()
        if thumb_bin:
            try:
                f = io.BytesIO(thumb_bin)
                f.name = "thumbnail.jpg"
                await client.send_photo(user_id, f, caption="**Current Default Thumbnail**")
                await callback_query.message.edit_text(
                    "🖼 **Manage Thumbnail**\n\n"
                    "Thumbnail sent above.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("👀 View Current", callback_data="admin_thumb_view")],
                        [InlineKeyboardButton("📤 Set Default", callback_data="admin_thumb_set")],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to send thumbnail: {e}")
                await callback_query.answer("Error sending thumbnail!", show_alert=True)
        else:
            await callback_query.answer("No thumbnail set in DB!", show_alert=True)
    elif data == "admin_thumb_set":
        await callback_query.message.edit_text(
            "📤 **Set Default Thumbnail**\n\n"
            "Click below to upload a new thumbnail. "
            "This will be embedded into every video processed.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Upload New", callback_data="prompt_admin_thumb_set")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_thumb_menu")]
            ])
        )
    elif data == "prompt_admin_thumb_set":
        admin_sessions[user_id] = "awaiting_thumb"
        await callback_query.message.edit_text(
            "🖼 **Send the new photo** to set as the default thumbnail:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_thumb_menu")]])
        )
    elif data == "admin_templates":
        await callback_query.message.edit_text(
            "📝 **Edit Metadata Templates**\n\n"
            "Select a field to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Title", callback_data="edit_template_title"),
                 InlineKeyboardButton("Author", callback_data="edit_template_author")],
                [InlineKeyboardButton("Artist", callback_data="edit_template_artist"),
                 InlineKeyboardButton("Video", callback_data="edit_template_video")],
                [InlineKeyboardButton("Audio", callback_data="edit_template_audio"),
                 InlineKeyboardButton("Subtitle", callback_data="edit_template_subtitle")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "admin_caption":
        templates = await db.get_all_templates()
        current_caption = templates.get("caption", "{random}")
        await callback_query.message.edit_text(
            f"📝 **Edit Caption Template**\n\n"
            f"Current: `{current_caption}`\n\n"
            "**Variables:**\n"
            "- `{filename}` : The final filename\n"
            "- `{size}` : File size (e.g. 1.5 GB)\n"
            "- `{duration}` : Video duration\n"
            "- `{random}` : Random string (Anti-Hash)\n\n"
            "Click below to change it.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Change", callback_data="prompt_admin_caption")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "prompt_admin_caption":
        admin_sessions[user_id] = "awaiting_template_caption"
        await callback_query.message.edit_text(
            "📝 **Send the new caption text:**\n\n(Use `{random}` to use the default random text generator)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]])
        )
    elif data == "admin_view":
        settings = await db.get_settings()
        templates = settings.get("templates", {}) if settings else {}
        has_thumb = "✅ Yes" if settings and settings.get("thumbnail_binary") else "❌ No"
        text = f"👀 **Current Settings**\n\n"
        text += f"**Thumbnail Set:** {has_thumb}\n\n"
        text += "**Metadata Templates:**\n"
        if templates:
            for k, v in templates.items():
                if k == "caption":
                    text += f"- **Caption:** `{v}`\n"
                else:
                    text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No templates set.\n"
        text += "\n**Filename Templates:**\n"
        fn_templates = settings.get("filename_templates", {}) if settings else {}
        if fn_templates:
            for k, v in fn_templates.items():
                text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No filename templates set.\n"
        text += f"\n**Channel Variable:** `{settings.get('channel', Config.DEFAULT_CHANNEL) if settings else Config.DEFAULT_CHANNEL}`\n"
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
        )
    elif data == "admin_filename_templates":
        await callback_query.message.edit_text(
            "📝 **Edit Filename Templates**\n\n"
            "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Movies", callback_data="edit_fn_template_movies")],
                [InlineKeyboardButton("Series", callback_data="edit_fn_template_series")],
                [InlineKeyboardButton("Personal", callback_data="admin_fn_templates_personal")],
                [InlineKeyboardButton("Subtitles", callback_data="admin_fn_templates_subtitles")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "admin_fn_templates_personal":
        await callback_query.message.edit_text(
            "📝 **Edit Personal Filename Templates**\n\n"
            "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Personal Files", callback_data="edit_fn_template_personal_file")],
                [InlineKeyboardButton("Personal Photos", callback_data="edit_fn_template_personal_photo")],
                [InlineKeyboardButton("Personal Videos", callback_data="edit_fn_template_personal_video")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_filename_templates")]
            ])
        )
    elif data == "admin_fn_templates_subtitles":
        await callback_query.message.edit_text(
            "📝 **Edit Subtitles Filename Templates**\n\n"
            "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Movies", callback_data="edit_fn_template_subtitles_movies")],
                [InlineKeyboardButton("Series", callback_data="edit_fn_template_subtitles_series")],
            ])
        )
    elif data.startswith("edit_fn_template_"):
        field = data.replace("edit_fn_template_", "")
        templates = await db.get_filename_templates()
        current_val = templates.get(field, "")
        await callback_query.message.edit_text(
            f"✏️ **Edit Filename Template ({field.capitalize()})**\n\n"
            f"Current: `{current_val}`\n\n"
            f"Variables: `{{Title}}`, `{{Year}}`, `{{Quality}}`, `{{Season}}`, `{{Episode}}`, `{{Season_Episode}}`, `{{Language}}`, `{{Channel}}`\n"
            f"Note: File extension will be added automatically.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_fn_template_{field}")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_filename_templates")]
            ])
        )
    elif data.startswith("prompt_fn_template_"):
        field = data.replace("prompt_fn_template_", "")
        admin_sessions[user_id] = f"awaiting_fn_template_{field}"
        await callback_query.message.edit_text(
            f"✏️ **Send the new filename template for {field.capitalize()}:**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_filename_templates")]])
        )
    elif data == "admin_settings":
        current_channel = await db.get_channel()
        await callback_query.message.edit_text(
            f"⚙️ **General Settings**\n\n"
            f"Current Channel Variable: `{current_channel}`\n\n"
            "Click below to change it.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Change", callback_data="prompt_admin_channel")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "prompt_admin_channel":
        admin_sessions[user_id] = "awaiting_channel"
        await callback_query.message.edit_text(
            "⚙️ **Send the new Channel name (e.g. `@XTVglobal`):**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]])
        )
    elif data == "admin_main" or data == "admin_cancel":
        admin_sessions.pop(user_id, None)
        if Config.PUBLIC_MODE:
            await callback_query.message.edit_text(
                "🛠 **Public Mode Admin Panel** 🛠\n\n"
                "Welcome, CEO.\n"
                "Manage global settings for Public Mode.\n"
                "These settings apply globally to the bot, such as branding and rate limits.\n"
                "*(Use /settings to configure your personal renaming templates)*",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Edit Bot Name", callback_data="admin_public_bot_name"),
                     InlineKeyboardButton("👥 Edit Community Name", callback_data="admin_public_community_name")],
                    [InlineKeyboardButton("🔗 Edit Support Contact", callback_data="admin_public_support_contact"),
                     InlineKeyboardButton("📢 Edit Force-Sub Channel", callback_data="admin_public_force_sub")],
                    [InlineKeyboardButton("⏱ Edit Rate Limits", callback_data="admin_public_rate_limit"),
                     InlineKeyboardButton("⏱ Edit Dumb Channel Timeout", callback_data="admin_dumb_timeout")],
                    [InlineKeyboardButton("👀 View Public Config", callback_data="admin_public_view")]
                ])
            )
        else:
            await callback_query.message.edit_text(
                "🛠 **XTV Admin Panel** 🛠\n\n"
                "Welcome, CEO.\n"
                "Manage global settings for the XTV Rename Bot.\n"
                "These settings affect all files processed by the bot.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖼 Manage Thumbnail", callback_data="admin_thumb_menu")],
                    [InlineKeyboardButton("📝 Edit Metadata Templates", callback_data="admin_templates")],
                    [InlineKeyboardButton("📝 Edit Filename Templates", callback_data="admin_filename_templates")],
                    [InlineKeyboardButton("📝 Edit Caption Template", callback_data="admin_caption")],
                    [InlineKeyboardButton("📺 Dumb Channels", callback_data="admin_dumb_channels")],
                    [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
                    [InlineKeyboardButton("👀 View Current Settings", callback_data="admin_view")]
                ])
            )
    elif data.startswith("edit_template_"):
        field = data.split("_")[-1]
        templates = await db.get_all_templates()
        current_val = templates.get(field, "")
        await callback_query.message.edit_text(
            f"✏️ **Edit {field.capitalize()} Template**\n\n"
            f"Current: `{current_val}`\n\n"
            f"Variables: `{{title}}`, `{{season_episode}}`, `{{lang}}` (for audio/subtitle)\n\n"
            "Click below to change it.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_template_{field}")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_templates")]
            ])
        )
    elif data.startswith("prompt_template_"):
        field = data.replace("prompt_template_", "")
        admin_sessions[user_id] = f"awaiting_template_{field}"
        await callback_query.message.edit_text(
            f"✏️ **Send the new template text for {field.capitalize()}:**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_templates")]])
        )
from pyrogram import ContinuePropagation

@Client.on_message(filters.photo & filters.private, group=1)
async def handle_admin_photo(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id) or admin_sessions.get(user_id) != "awaiting_thumb":
        raise ContinuePropagation

    msg = await message.reply_text("Processing thumbnail...")
    try:
        file_id = message.photo.file_id
        path = await client.download_media(message, file_name=Config.THUMB_PATH)
        with open(path, "rb") as f:
            binary_data = f.read()
        await db.update_thumbnail(file_id, binary_data)
        await msg.edit_text("✅ Thumbnail updated successfully!",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_thumb_menu")]]))
        admin_sessions.pop(user_id, None)
    except Exception as e:
        logger.error(f"Thumbnail upload failed: {e}")
        await msg.edit_text(f"❌ Error: {e}")
@Client.on_message((filters.text | filters.forwarded) & filters.private & ~filters.regex(r"^/"), group=1)
async def handle_admin_text(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state = admin_sessions.get(user_id)
    if not state:
        raise ContinuePropagation

    if state == "awaiting_dumb_timeout":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await message.reply_text("❌ Invalid number. Try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]))
            return
        await db.update_dumb_channel_timeout(int(val))
        await message.reply_text(f"✅ Dumb channel timeout updated to `{val}` seconds.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]))
        admin_sessions.pop(user_id, None)
        return

    if state == "awaiting_dumb_add" and not Config.PUBLIC_MODE:
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            admin_sessions.pop(user_id, None)
            await message.reply_text("Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="dumb_menu")]]))
            return

        ch_id = None
        ch_name = "Custom Channel"
        if message.forward_from_chat:
            ch_id = message.forward_from_chat.id
            ch_name = message.forward_from_chat.title
        elif val:
            try:
                chat = await client.get_chat(val)
                ch_id = chat.id
                ch_name = chat.title or "Channel"
            except Exception as e:
                await message.reply_text(f"❌ Error finding channel: {e}\nTry forwarding a message instead.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]]))
                return

        if ch_id:
            await db.add_dumb_channel(ch_id, ch_name)
            await message.reply_text(f"✅ Added Dumb Channel: **{ch_name}** (`{ch_id}`)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="dumb_menu")]]))
            admin_sessions.pop(user_id, None)
        return

    # Handle Public Mode settings
    if state.startswith("awaiting_public_"):
        field = state.replace("awaiting_public_", "")

        val = message.text.strip() if message.text else ""
        if not val:
            raise ContinuePropagation

        if field == "bot_name":
            await db.update_public_config("bot_name", val)
            await message.reply_text(f"✅ Bot Name updated to `{val}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]))
        elif field == "community_name":
            await db.update_public_config("community_name", val)
            await message.reply_text(f"✅ Community Name updated to `{val}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]))
        elif field == "support_contact":
            await db.update_public_config("support_contact", val)
            await message.reply_text(f"✅ Support Contact updated to `{val}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]))
        elif field == "force_sub":
            if val.lower() == "disable":
                await db.update_public_config("force_sub_channel", None)
                await db.update_public_config("force_sub_link", None)
                await message.reply_text("✅ Force-Sub disabled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]))
                admin_sessions.pop(user_id, None)
            else:
                await message.reply_text("⏳ **Still Waiting...**\n\nPlease add me as an Admin to the channel, or type `disable` to cancel.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]))
            return
        elif field == "rate_limit":
            if not val.isdigit():
                await message.reply_text("❌ Invalid number. Try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]))
                return
            await db.update_public_config("rate_limit_delay", int(val))
            await message.reply_text(f"✅ Rate limit updated to `{val}` seconds.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]))

        admin_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_template_"):
        field = state.split("_")[-1]
        new_template = message.text
        await db.update_template(field, new_template)
        if field == "caption":
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]])
        else:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Templates", callback_data="admin_templates")]])
        await message.reply_text(f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`",
                                 reply_markup=reply_markup)
        admin_sessions.pop(user_id, None)
    elif state.startswith("awaiting_fn_template_"):
        field = state.replace("awaiting_fn_template_", "")
        new_template = message.text
        await db.update_filename_template(field, new_template)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Filename Templates", callback_data="admin_filename_templates")]])
        await message.reply_text(f"✅ Filename template for **{field.capitalize()}** updated to:\n`{new_template}`",
                                 reply_markup=reply_markup)
        admin_sessions.pop(user_id, None)
    elif state == "awaiting_channel":
        new_channel = message.text
        await db.update_channel(new_channel)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]])
        await message.reply_text(f"✅ Channel variable updated to:\n`{new_channel}`",
                                 reply_markup=reply_markup)
        admin_sessions.pop(user_id, None)
# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
