from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message
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

    pro_session = await db.get_pro_session()
    pro_btn_text = "🚀 Manage 𝕏TV Pro™" if pro_session else "🚀 Setup 𝕏TV Pro™"

    if Config.PUBLIC_MODE:
        await message.reply_text(
            "🛠 **Public Mode Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for Public Mode.\n"
            "These settings apply globally to the bot, such as branding and rate limits.\n"
            "*(Use /settings to configure your personal renaming templates)*",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🤖 Edit Bot Name", callback_data="admin_public_bot_name"
                        ),
                        InlineKeyboardButton(
                            "👥 Edit Community Name",
                            callback_data="admin_public_community_name",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🔗 Edit Support Contact",
                            callback_data="admin_public_support_contact",
                        ),
                        InlineKeyboardButton(
                            "📢 Edit Force-Sub Channel",
                            callback_data="admin_public_force_sub",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "📦 Set Daily Egress Limit",
                            callback_data="admin_daily_egress",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "📄 Set Daily File Limit",
                            callback_data="admin_daily_files",
                        ),
                        InlineKeyboardButton(
                            "⏱ Edit Dumb Channel Timeout",
                            callback_data="admin_dumb_timeout",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "📊 Usage Dashboard",
                            callback_data="admin_usage_dashboard",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "👀 View Public Config", callback_data="admin_public_view"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            pro_btn_text, callback_data="pro_setup_menu"
                        )
                    ],
                ]
            ),
        )
    else:
        await message.reply_text(
            "🛠 **XTV Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for the XTV Rename Bot.\n"
            "These settings affect all files processed by the bot.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🖼 Manage Thumbnail", callback_data="admin_thumb_menu"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📝 Edit Metadata Templates",
                            callback_data="admin_templates",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📝 Edit Filename Templates",
                            callback_data="admin_filename_templates",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📝 Edit Caption Template", callback_data="admin_caption"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📺 Dumb Channels", callback_data="admin_dumb_channels"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⚙️ Settings", callback_data="admin_settings"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "👀 View Current Settings", callback_data="admin_view"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            pro_btn_text, callback_data="pro_setup_menu"
                        )
                    ],
                ]
            ),
        )


from pyrogram import ContinuePropagation


@Client.on_callback_query(
    filters.regex(
        r"^(admin_(?!usage_dashboard|dashboard_.*|unblock_|block_|reset_quota_|prompt_lookup)|edit_template_|edit_fn_template_|prompt_admin_|prompt_public_|prompt_daily_|prompt_fn_template_|prompt_template_|dumb_(?!user_))"
    )
)
async def admin_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data
    logger.info(f"Admin callback: {data} from user {user_id}")

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
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "➕ Add New Dumb Channel", callback_data="dumb_add"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "➖ Remove Dumb Channel", callback_data="dumb_remove"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⭐ Set Default", callback_data="dumb_set_default"
                            )
                        ],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                    ]
                ),
            )
            return
        elif data == "dumb_add":
            admin_sessions[user_id] = "awaiting_dumb_add"
            await callback_query.message.edit_text(
                "➕ **Add Dumb Channel**\n\n"
                "Please add me as an Administrator in the desired channel.\n"
                "Then, forward any message from that channel to me, OR send the Channel ID (e.g. `-100...`) or Public Username.\n\n"
                "*(Send `disable` to cancel)*",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]]
                ),
            )
            return
        elif data == "dumb_remove":
            channels = await db.get_dumb_channels()
            if not channels:
                await callback_query.answer("No channels configured.", show_alert=True)
                return
            buttons = []
            for ch_id, ch_name in channels.items():
                buttons.append(
                    [
                        InlineKeyboardButton(
                            f"❌ {ch_name}", callback_data=f"dumb_del_{ch_id}"
                        )
                    ]
                )
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="dumb_menu")])
            await callback_query.message.edit_text(
                "Select a channel to remove:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return
        elif data.startswith("dumb_del_"):
            ch_id = data.replace("dumb_del_", "")
            await db.remove_dumb_channel(ch_id)
            await callback_query.answer("Channel removed.", show_alert=True)
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
                buttons.append(
                    [
                        InlineKeyboardButton(
                            f"⭐ {ch_name}", callback_data=f"dumb_def_{ch_id}"
                        )
                    ]
                )
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="dumb_menu")])
            await callback_query.message.edit_text(
                "Select default auto-detect channel:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
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
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✏️ Change", callback_data="prompt_admin_dumb_timeout"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                ]
            ),
        )
        return

    if data == "prompt_admin_dumb_timeout":
        admin_sessions[user_id] = "awaiting_dumb_timeout"
        await callback_query.message.edit_text(
            "⏱ **Send the new timeout in seconds (e.g., 3600 for 1 hour):**",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]
            ),
        )
        return

    if Config.PUBLIC_MODE and (data.startswith("admin_public_") or data == "admin_daily_egress" or data == "admin_daily_files"):
        if data == "admin_public_view":
            config = await db.get_public_config()
            text = "👀 **Public Mode Config**\n\n"
            text += f"**Bot Name:** {config.get('bot_name', 'Not set')}\n"
            text += f"**Community Name:** {config.get('community_name', 'Not set')}\n"
            text += f"**Support Contact:** {config.get('support_contact', 'Not set')}\n"
            text += (
                f"**Force-Sub Channel:** {config.get('force_sub_channel', 'Not set')}\n"
            )
            text += (
                f"**Daily Egress Limit:** {config.get('daily_egress_mb', 0)} MB\n"
            )
            text += (
                f"**Daily File Limit:** {config.get('daily_file_count', 0)} files\n"
            )

            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]]
                ),
            )
            return

        elif data == "admin_public_bot_name":
            config = await db.get_public_config()
            current_val = config.get("bot_name", "Not set")
            await callback_query.message.edit_text(
                f"🤖 **Edit Bot Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_public_bot_name"
                            )
                        ],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                    ]
                ),
            )
            return

        elif data == "admin_public_community_name":
            config = await db.get_public_config()
            current_val = config.get("community_name", "Not set")
            await callback_query.message.edit_text(
                f"👥 **Edit Community Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change",
                                callback_data="prompt_public_community_name",
                            )
                        ],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                    ]
                ),
            )
            return

        elif data == "admin_public_support_contact":
            config = await db.get_public_config()
            current_val = config.get("support_contact", "Not set")
            await callback_query.message.edit_text(
                f"🔗 **Edit Support Contact**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change",
                                callback_data="prompt_public_support_contact",
                            )
                        ],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                    ]
                ),
            )
            return

        elif data == "admin_public_force_sub":
            config = await db.get_public_config()
            current_val = config.get("force_sub_channel", "Not set")
            await callback_query.message.edit_text(
                f"📢 **Edit Force-Sub Channel**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_public_force_sub"
                            )
                        ],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                    ]
                ),
            )
            return

        elif data == "admin_daily_egress":
            config = await db.get_public_config()
            current_val = config.get("daily_egress_mb", 0)
            await callback_query.message.edit_text(
                f"📦 **Edit Daily Egress Limit**\n\nCurrent: `{current_val}` MB\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_daily_egress"
                            )
                        ],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                    ]
                ),
            )
            return

        elif data == "admin_daily_files":
            config = await db.get_public_config()
            current_val = config.get("daily_file_count", 0)
            await callback_query.message.edit_text(
                f"📄 **Edit Daily File Limit**\n\nCurrent: `{current_val}` files\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_daily_files"
                            )
                        ],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                    ]
                ),
            )
            return

    if Config.PUBLIC_MODE and (data.startswith("prompt_public_") or data.startswith("prompt_daily_")):
        if data.startswith("prompt_daily_"):
            field = data.replace("prompt_", "")
        else:
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
        elif field == "daily_egress":
            text = "📦 **Send the new daily egress limit in MB (e.g., 2048).**\nSend `0` to disable."
        elif field == "daily_files":
            text = "📄 **Send the new daily file limit.**\nSend `0` to disable."
        else:
            text = "Send the new value:"

        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]
            ),
        )
        return
    if data == "admin_thumb_menu":
        await callback_query.message.edit_text(
            "🖼 **Manage Thumbnail**\n\n" "Select an action:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "👀 View Current", callback_data="admin_thumb_view"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📤 Set Default", callback_data="admin_thumb_set"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                ]
            ),
        )
    elif data == "admin_thumb_view":
        thumb_bin, _ = await db.get_thumbnail()
        if thumb_bin:
            try:
                f = io.BytesIO(thumb_bin)
                f.name = "thumbnail.jpg"
                await client.send_photo(
                    user_id, f, caption="**Current Default Thumbnail**"
                )
                await callback_query.message.edit_text(
                    "🖼 **Manage Thumbnail**\n\n" "Thumbnail sent above.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "👀 View Current", callback_data="admin_thumb_view"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "📤 Set Default", callback_data="admin_thumb_set"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "🔙 Back", callback_data="admin_main"
                                )
                            ],
                        ]
                    ),
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
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📤 Upload New", callback_data="prompt_admin_thumb_set"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_thumb_menu")],
                ]
            ),
        )
    elif data == "prompt_admin_thumb_set":
        admin_sessions[user_id] = "awaiting_thumb"
        await callback_query.message.edit_text(
            "🖼 **Send the new photo** to set as the default thumbnail:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_thumb_menu")]]
            ),
        )
    elif data == "admin_templates":
        await callback_query.message.edit_text(
            "📝 **Edit Metadata Templates**\n\n" "Select a field to edit:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Title", callback_data="edit_template_title"
                        ),
                        InlineKeyboardButton(
                            "Author", callback_data="edit_template_author"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "Artist", callback_data="edit_template_artist"
                        ),
                        InlineKeyboardButton(
                            "Video", callback_data="edit_template_video"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "Audio", callback_data="edit_template_audio"
                        ),
                        InlineKeyboardButton(
                            "Subtitle", callback_data="edit_template_subtitle"
                        ),
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                ]
            ),
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
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✏️ Change", callback_data="prompt_admin_caption"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                ]
            ),
        )
    elif data == "prompt_admin_caption":
        admin_sessions[user_id] = "awaiting_template_caption"
        await callback_query.message.edit_text(
            "📝 **Send the new caption text:**\n\n(Use `{random}` to use the default random text generator)",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]
            ),
        )
    elif data == "admin_view":
        settings = await db.get_settings()
        templates = settings.get("templates", {}) if settings else {}
        has_thumb = (
            "✅ Yes" if settings and settings.get("thumbnail_binary") else "❌ No"
        )
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
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]]
            ),
        )
    elif data == "admin_filename_templates":
        await callback_query.message.edit_text(
            "📝 **Edit Filename Templates**\n\n" "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Movies", callback_data="edit_fn_template_movies"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Series", callback_data="edit_fn_template_series"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Personal", callback_data="admin_fn_templates_personal"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Subtitles", callback_data="admin_fn_templates_subtitles"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                ]
            ),
        )
    elif data == "admin_fn_templates_personal":
        await callback_query.message.edit_text(
            "📝 **Edit Personal Filename Templates**\n\n" "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Personal Files",
                            callback_data="edit_fn_template_personal_file",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Personal Photos",
                            callback_data="edit_fn_template_personal_photo",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Personal Videos",
                            callback_data="edit_fn_template_personal_video",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔙 Back", callback_data="admin_filename_templates"
                        )
                    ],
                ]
            ),
        )
    elif data == "admin_fn_templates_subtitles":
        await callback_query.message.edit_text(
            "📝 **Edit Subtitles Filename Templates**\n\n" "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Movies", callback_data="edit_fn_template_subtitles_movies"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Series", callback_data="edit_fn_template_subtitles_series"
                        )
                    ],
                ]
            ),
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
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✏️ Change", callback_data=f"prompt_fn_template_{field}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔙 Back", callback_data="admin_filename_templates"
                        )
                    ],
                ]
            ),
        )
    elif data.startswith("prompt_fn_template_"):
        field = data.replace("prompt_fn_template_", "")
        admin_sessions[user_id] = f"awaiting_fn_template_{field}"
        await callback_query.message.edit_text(
            f"✏️ **Send the new filename template for {field.capitalize()}:**",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data="admin_filename_templates"
                        )
                    ]
                ]
            ),
        )
    elif data == "admin_settings":
        current_channel = await db.get_channel()
        await callback_query.message.edit_text(
            f"⚙️ **General Settings**\n\n"
            f"Current Channel Variable: `{current_channel}`\n\n"
            "Click below to change it.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✏️ Change", callback_data="prompt_admin_channel"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_main")],
                ]
            ),
        )
    elif data == "prompt_admin_channel":
        admin_sessions[user_id] = "awaiting_channel"
        await callback_query.message.edit_text(
            "⚙️ **Send the new Channel name (e.g. `@XTVglobal`):**",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]
            ),
        )
    elif data == "admin_main" or data == "admin_cancel":
        admin_sessions.pop(user_id, None)

        pro_session = await db.get_pro_session()
        pro_btn_text = "🚀 Manage 𝕏TV Pro™" if pro_session else "🚀 Setup 𝕏TV Pro™"

        if Config.PUBLIC_MODE:
            await callback_query.message.edit_text(
                "🛠 **Public Mode Admin Panel** 🛠\n\n"
                "Welcome, CEO.\n"
                "Manage global settings for Public Mode.\n"
                "These settings apply globally to the bot, such as branding and rate limits.\n"
                "*(Use /settings to configure your personal renaming templates)*",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🤖 Edit Bot Name",
                                callback_data="admin_public_bot_name",
                            ),
                            InlineKeyboardButton(
                                "👥 Edit Community Name",
                                callback_data="admin_public_community_name",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "🔗 Edit Support Contact",
                                callback_data="admin_public_support_contact",
                            ),
                            InlineKeyboardButton(
                                "📢 Edit Force-Sub Channel",
                                callback_data="admin_public_force_sub",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "⏱ Edit Rate Limits",
                                callback_data="admin_public_rate_limit",
                            ),
                            InlineKeyboardButton(
                                "⏱ Edit Dumb Channel Timeout",
                                callback_data="admin_dumb_timeout",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "👀 View Public Config",
                                callback_data="admin_public_view",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                pro_btn_text, callback_data="pro_setup_menu"
                            )
                        ],
                    ]
                ),
            )
        else:
            await callback_query.message.edit_text(
                "🛠 **XTV Admin Panel** 🛠\n\n"
                "Welcome, CEO.\n"
                "Manage global settings for the XTV Rename Bot.\n"
                "These settings affect all files processed by the bot.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🖼 Manage Thumbnail", callback_data="admin_thumb_menu"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📝 Edit Metadata Templates",
                                callback_data="admin_templates",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📝 Edit Filename Templates",
                                callback_data="admin_filename_templates",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📝 Edit Caption Template",
                                callback_data="admin_caption",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📺 Dumb Channels", callback_data="admin_dumb_channels"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⚙️ Settings", callback_data="admin_settings"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "👀 View Current Settings", callback_data="admin_view"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                pro_btn_text, callback_data="pro_setup_menu"
                            )
                        ],
                    ]
                ),
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
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✏️ Change", callback_data=f"prompt_template_{field}"
                        )
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_templates")],
                ]
            ),
        )
    elif data.startswith("prompt_template_"):
        field = data.replace("prompt_template_", "")
        admin_sessions[user_id] = f"awaiting_template_{field}"
        await callback_query.message.edit_text(
            f"✏️ **Send the new template text for {field.capitalize()}:**",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="admin_templates")]]
            ),
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
        await msg.edit_text(
            "✅ Thumbnail updated successfully!",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Menu", callback_data="admin_thumb_menu"
                        )
                    ]
                ]
            ),
        )
        admin_sessions.pop(user_id, None)
    except Exception as e:
        logger.error(f"Thumbnail upload failed: {e}")
        await msg.edit_text(f"❌ Error: {e}")


@Client.on_message(
    (filters.text | filters.forwarded) & filters.private & ~filters.regex(r"^/"),
    group=1,
)
async def handle_admin_text(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state = admin_sessions.get(user_id)
    if not state:
        raise ContinuePropagation

    if state == "awaiting_user_lookup":
        val = message.text.strip()
        from utils.state import clear_session

        # Check if they provided an ID directly
        if val.isdigit():
            user_id = int(val)
        else:
            # Maybe they provided a username
            try:
                user = await client.get_users(val)
                user_id = user.id
            except Exception:
                await message.reply_text("❌ Could not find a user with that ID or username. Please make sure the ID is correct.",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_usage_dashboard")]]))
                clear_session(message.from_user.id)
                return

        await show_user_lookup(client, message, user_id)
        clear_session(message.from_user.id)
        return

    if state == "awaiting_dumb_timeout":
        val = message.text.strip() if message.text else ""
        if not val.isdigit():
            await message.reply_text(
                "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_main")]]
                ),
            )
            return
        await db.update_dumb_channel_timeout(int(val))
        await message.reply_text(
            f"✅ Dumb channel timeout updated to `{val}` seconds.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]
            ),
        )
        admin_sessions.pop(user_id, None)
        return

    if state == "awaiting_dumb_add" and not Config.PUBLIC_MODE:
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            admin_sessions.pop(user_id, None)
            await message.reply_text(
                "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="dumb_menu"
                            )
                        ]
                    ]
                ),
            )
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
                await message.reply_text(
                    f"❌ Error finding channel: {e}\nTry forwarding a message instead.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ Cancel", callback_data="dumb_menu")]]
                    ),
                )
                return

        if ch_id:
            invite_link = None
            try:
                invite_link = await client.export_chat_invite_link(ch_id)
            except Exception as e:
                logger.warning(f"Could not export invite link for {ch_id}: {e}")

            await db.add_dumb_channel(ch_id, ch_name, invite_link=invite_link)
            await message.reply_text(
                f"✅ Added Dumb Channel: **{ch_name}** (`{ch_id}`)",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="dumb_menu"
                            )
                        ]
                    ]
                ),
            )
            admin_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_public_"):
        field = state.replace("awaiting_public_", "")

        val = message.text.strip() if message.text else ""
        if not val:
            raise ContinuePropagation

        if field == "bot_name":
            await db.update_public_config("bot_name", val)
            await message.reply_text(
                f"✅ Bot Name updated to `{val}`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "community_name":
            await db.update_public_config("community_name", val)
            await message.reply_text(
                f"✅ Community Name updated to `{val}`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "support_contact":
            await db.update_public_config("support_contact", val)
            await message.reply_text(
                f"✅ Support Contact updated to `{val}`",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )
        elif field == "force_sub":
            if val.lower() == "disable":
                await db.update_public_config("force_sub_channel", None)
                await db.update_public_config("force_sub_link", None)
                await message.reply_text(
                    "✅ Force-Sub disabled.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🔙 Back to Menu", callback_data="admin_main"
                                )
                            ]
                        ]
                    ),
                )
                admin_sessions.pop(user_id, None)
            else:
                await message.reply_text(
                    "⏳ **Still Waiting...**\n\nPlease add me as an Admin to the channel, or type `disable` to cancel.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "❌ Cancel", callback_data="admin_main"
                                )
                            ]
                        ]
                    ),
                )
            return
        elif field == "rate_limit":
            if not val.isdigit():
                await message.reply_text(
                    "❌ Invalid number. Try again.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "❌ Cancel", callback_data="admin_main"
                                )
                            ]
                        ]
                    ),
                )
                return
            await db.update_public_config("rate_limit_delay", int(val))
            await message.reply_text(
                f"✅ Rate limit updated to `{val}` seconds.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Menu", callback_data="admin_main"
                            )
                        ]
                    ]
                ),
            )

        admin_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_template_"):
        field = state.split("_")[-1]
        new_template = message.text
        await db.update_template(field, new_template)
        if field == "caption":
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]
            )
        else:
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Templates", callback_data="admin_templates"
                        )
                    ]
                ]
            )
        await message.reply_text(
            f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)
    elif state.startswith("awaiting_fn_template_"):
        field = state.replace("awaiting_fn_template_", "")
        new_template = message.text
        await db.update_filename_template(field, new_template)
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Back to Filename Templates",
                        callback_data="admin_filename_templates",
                    )
                ]
            ]
        )
        await message.reply_text(
            f"✅ Filename template for **{field.capitalize()}** updated to:\n`{new_template}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)
    elif state == "awaiting_channel":
        new_channel = message.text
        await db.update_channel(new_channel)
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]]
        )
        await message.reply_text(
            f"✅ Channel variable updated to:\n`{new_channel}`",
            reply_markup=reply_markup,
        )
        admin_sessions.pop(user_id, None)


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------

@Client.on_callback_query(filters.regex("^admin_usage_dashboard$") & filters.user(Config.CEO_ID))
async def admin_dashboard_overview_cb(client: Client, callback_query: CallbackQuery):
    stats = await db.get_dashboard_stats()

    # Active slots logic using semaphores in process.py
    from plugins.process import _SEMAPHORES

    active_slots = 0
    for phase in ["download", "process", "upload"]:
        if _SEMAPHORES.get(phase):
            # value of semaphore is internal counter. Max is 3. So acquired = 3 - value
            active_slots += (3 - _SEMAPHORES[phase]._value)

    # Format egress strings
    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb:.2f} MB"

    import datetime
    current_time_str = datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    start_date_obj = datetime.datetime.strptime(stats.get("bot_start_date"), "%Y-%m-%d")
    start_date_str = start_date_obj.strftime("%d %b %Y")

    # Build text
    text = (
        f"📊 **𝕏TV Usage Dashboard**\n"
        f"Updated: {current_time_str}\n"
        f"═════════════════════════\n"
        f"👥 Total Users: `{stats.get('total_users')}`\n"
        f"📁 Files Processed Today: `{stats.get('files_today')}`\n"
        f"📦 Egress Today: `{format_egress(stats.get('egress_today_mb'))}`\n"
    )

    if Config.PUBLIC_MODE:
        text += f"⚡ Active Right Now: `{active_slots}`\n"

    text += (
        f"─────────────────────────\n"
        f"📈 **All-Time**\n"
        f"─────────────────────────\n"
        f"📁 Total Files: `{stats.get('total_files')}`\n"
        f"📦 Total Egress: `{format_egress(stats.get('total_egress_mb'))}`\n"
        f"🗓️ Bot Running Since: `{start_date_str}`\n"
    )

    if Config.PUBLIC_MODE:
        text += (
            f"─────────────────────────\n"
            f"⚠️ Quota Hits Today: `{stats.get('quota_hits_today')}`\n"
            f"🚫 Blocked Users: `{stats.get('blocked_users')}`\n"
        )

    text += f"─────────────────────────"

    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔝 Top Users", callback_data="admin_dashboard_top_0"),
                    InlineKeyboardButton("📅 Daily Breakdown", callback_data="admin_dashboard_daily")
                ],
                [
                    InlineKeyboardButton("🔍 User Lookup", callback_data="prompt_user_lookup"),
                ],
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]
            ]
        )
    )

@Client.on_callback_query(filters.regex(r"^admin_dashboard_top_(\d+)$") & filters.user(Config.CEO_ID))
async def admin_dashboard_top_cb(client: Client, callback_query: CallbackQuery):
    page = int(callback_query.matches[0].group(1))
    limit = 10
    skip = page * limit

    users, total = await db.get_top_users_today(limit=limit, skip=skip)

    import datetime
    current_date = datetime.datetime.utcnow().strftime("%d %b")

    text = f"🏆 **Top Users — Today ({current_date})**\n\n"

    if not users:
        text += "No usage tracked today."
    else:
        for i, user in enumerate(users):
            rank = skip + i + 1
            user_id = user["_id"].replace("user_", "")

            # Try to get user info if possible (fallback to ID)
            try:
                user_obj = await client.get_users(int(user_id))
                display_name = f"@{user_obj.username}" if user_obj.username else f"{user_obj.first_name}"
            except Exception:
                display_name = f"User {user_id}"

            usage = user.get("usage", {})
            files = usage.get("file_count", 0)
            mb = usage.get("egress_mb", 0.0)

            if mb >= 1024:
                mb_str = f"{mb / 1024:.2f} GB"
            else:
                mb_str = f"{mb:.2f} MB"

            text += f"**#{rank}** {display_name} — {files} files · {mb_str}\n"

    # Pagination
    buttons = []
    nav_row = []

    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_dashboard_top_{page-1}"))

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages}", callback_data="ignore"))

    if skip + limit < total:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_dashboard_top_{page+1}"))

    if len(nav_row) > 1:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_usage_dashboard")])

    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^admin_dashboard_daily$") & filters.user(Config.CEO_ID))
async def admin_dashboard_daily_cb(client: Client, callback_query: CallbackQuery):
    daily_stats = await db.get_daily_stats(limit=7)

    text = "📅 **Last 7 Days Breakdown**\n\n"
    text += "`Date          Files    Egress`\n"
    text += "`──────────────────────────────`\n"

    if not daily_stats:
        text += "No history available."
    else:
        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        for stat in daily_stats:
            date_obj = datetime.datetime.strptime(stat["date"], "%Y-%m-%d")
            date_str = date_obj.strftime("%d %b %Y")

            files = stat.get("file_count", 0)
            mb = stat.get("egress_mb", 0.0)

            if mb >= 1048576:
                egress_str = f"{mb / 1048576:.2f} TB"
            elif mb >= 1024:
                egress_str = f"{mb / 1024:.2f} GB"
            else:
                egress_str = f"{mb:.2f} MB"

            is_today = " ← today" if stat["date"] == current_utc_date else ""

            # Format columns
            text += f"`{date_str:<13} {files:<7} {egress_str:>7}`{is_today}\n"

    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_usage_dashboard")]])
    )

@Client.on_message(filters.regex(r"^/lookup (\d+)$") & filters.user(Config.CEO_ID))
async def admin_lookup_user(client: Client, message: Message):
    user_id = int(message.matches[0].group(1))
    await show_user_lookup(client, message, user_id)

async def show_user_lookup(client: Client, message: Message, user_id: int):
    usage = await db.get_user_usage(user_id)
    is_blocked = await db.is_user_blocked(user_id)

    import datetime
    current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    current_date_display = datetime.datetime.utcnow().strftime("%d %b")

    files_today = 0
    egress_today_mb = 0.0
    quota_hits_today = 0

    if usage.get("date") == current_utc_date:
        files_today = usage.get("file_count", 0)
        egress_today_mb = usage.get("egress_mb", 0.0)
        quota_hits_today = usage.get("quota_hits", 0)

    files_alltime = usage.get("file_count_alltime", 0)
    egress_alltime_mb = usage.get("egress_mb_alltime", 0.0)

    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb:.2f} MB"

    # Try to get user profile info
    try:
        user_obj = await client.get_users(user_id)
        name = user_obj.first_name
        username = f"@{user_obj.username}" if user_obj.username else "N/A"
    except Exception:
        name = "Unknown User"
        username = "N/A"

    user_settings = await db.get_settings(user_id)
    joined_date = "Unknown"

    # Check if there is a document at all
    has_thumb = "No"
    current_template = "Default"

    if user_settings:
        if user_settings.get("thumbnail_file_id") or user_settings.get("thumbnail_binary"):
            has_thumb = "Yes"

        templates = user_settings.get("templates", {})
        if templates and templates.get("caption") != "{random}":
            current_template = "Custom"

        # Try to extract joined date from ObjectID if available, else from usage.date
        _id = user_settings.get("_id")
        if _id:
            try:
                # ObjectId contains a timestamp
                import bson
                if isinstance(_id, bson.ObjectId):
                    joined_date = _id.generation_time.strftime("%d %b %Y")
                else:
                    joined_date = usage.get("date", "Unknown")
            except Exception:
                joined_date = usage.get("date", "Unknown")

    text = (
        f"👤 **User Lookup**\n\n"
        f"**ID:** `{user_id}`\n"
        f"**Name:** {name}\n"
        f"**Username:** {username}\n"
        f"**Joined:** {joined_date}\n"
        f"**Template:** {current_template}\n"
        f"**Custom Thumb:** {has_thumb}\n"
        f"──────────────────────────\n"
        f"📊 **Today ({current_date_display})**\n"
        f"Files: `{files_today}`\n"
        f"Egress: `{format_egress(egress_today_mb)}`\n"
        f"Quota hits: `{quota_hits_today}`\n\n"
        f"📈 **All-Time**\n"
        f"Files: `{files_alltime}`\n"
        f"Egress: `{format_egress(egress_alltime_mb)}`\n"
        f"──────────────────────────\n"
    )

    if is_blocked:
        text += "🔴 **Status: BLOCKED**\n"

    buttons = []

    if is_blocked:
        buttons.append([InlineKeyboardButton("✅ Unblock User", callback_data=f"admin_unblock_{user_id}")])
    else:
        buttons.append([InlineKeyboardButton("🚫 Block User", callback_data=f"admin_block_{user_id}")])

    buttons.append([InlineKeyboardButton("🗑️ Reset Today's Quota", callback_data=f"admin_reset_quota_{user_id}")])
    buttons.append([InlineKeyboardButton("🔙 Dashboard", callback_data="admin_usage_dashboard")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^admin_block_(\d+)$") & filters.user(Config.CEO_ID))
async def admin_block_user_cb(client: Client, callback_query: CallbackQuery):
    user_id = int(callback_query.matches[0].group(1))
    await db.block_user(user_id)
    await callback_query.answer("User Blocked", show_alert=True)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

@Client.on_callback_query(filters.regex(r"^admin_unblock_(\d+)$") & filters.user(Config.CEO_ID))
async def admin_unblock_user_cb(client: Client, callback_query: CallbackQuery):
    user_id = int(callback_query.matches[0].group(1))
    await db.unblock_user(user_id)
    await callback_query.answer("User Unblocked", show_alert=True)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

@Client.on_callback_query(filters.regex(r"^admin_reset_quota_(\d+)$") & filters.user(Config.CEO_ID))
async def admin_reset_quota_cb(client: Client, callback_query: CallbackQuery):
    user_id = int(callback_query.matches[0].group(1))
    await db.reset_user_quota(user_id)
    await callback_query.answer("Quota Reset", show_alert=True)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

@Client.on_callback_query(filters.regex("^prompt_user_lookup$") & filters.user(Config.CEO_ID))
async def admin_prompt_lookup_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "🔍 **User Lookup**\n\n"
        "Please send the user's Telegram ID (e.g., 123456789) to view their profile.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_usage_dashboard")]])
    )
    from utils.state import set_state
    set_state(callback_query.from_user.id, "awaiting_user_lookup")


@Client.on_message(filters.text & filters.private & filters.user(Config.CEO_ID), group=2)
async def admin_handle_user_lookup_text(client: Client, message: Message):
    from utils.state import get_state, clear_session
    state = get_state(message.from_user.id)

    if state == "awaiting_user_lookup":
        val = message.text.strip()

        # Check if they provided an ID directly
        if val.isdigit():
            user_id = int(val)
        else:
            # Maybe they provided a username
            try:
                user = await client.get_users(val)
                user_id = user.id
            except Exception:
                await message.reply_text("❌ Could not find a user with that ID or username. Please make sure the ID is correct.",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_usage_dashboard")]]))
                clear_session(message.from_user.id)
                return

        await show_user_lookup(client, message, user_id)
        clear_session(message.from_user.id)
        raise ContinuePropagation
