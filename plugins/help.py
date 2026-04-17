# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""`/help` command + every `help_*` callback page.

Previously lived inside plugins/start.py (~1600 lines at the tail of
the file) and the dedicated plugins/help_v22_guide.py. Consolidated
into a single module so the help system can evolve without touching
the start-command plugin.

Layout:
  1. `/help` command handler (handle_help_command_unique)
  2. Main callback router (handle_help_callbacks) covering every
     legacy help topic (Quick Start, Tools, File Management, ...)
  3. "✨ New in v2.2" submenu hub + per-topic pages
     (help_new_v22, help_v22_<topic>)
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import Config
from database import db
from utils.log import get_logger
from utils.logger import debug

logger = get_logger("plugins.help")


# --- /help command ---------------------------------------------------------

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
                [InlineKeyboardButton("✨ New in v2.2", callback_data="help_new_v22")],
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

# --- Main callback router --------------------------------------------------

debug("✅ Loaded handler: help_callback")

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
                        [InlineKeyboardButton("✨ New in v2.2", callback_data="help_new_v22")],
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
                "• `/subtitle` or `/s` — Extract subtitles\n"
                "• `/trim` or `/t` — Trim/cut video by timestamp\n"
                "• `/mediainfo` or `/mi` — Show detailed media file info\n"
                "• `/voice` or `/v` — Convert audio to voice note\n"
                "• `/videonote` or `/vn` — Convert video to round note\n"
                "• `/youtube` or `/yt` — Download from YouTube (video / audio / thumb / subs)"
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
                        [InlineKeyboardButton("✂️ Video Trimmer", callback_data="help_tool_trimmer"),
                         InlineKeyboardButton("ℹ️ Media Info", callback_data="help_tool_mediainfo")],
                        [InlineKeyboardButton("🎙️ Voice Converter", callback_data="help_tool_voice"),
                         InlineKeyboardButton("⭕ Video Note", callback_data="help_tool_videonote")],
                        [InlineKeyboardButton("▶️ YouTube Tool", callback_data="help_tool_youtube")],
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
            # File Converter has its own submenu — render it via the dedicated
            # router below so users don't drown in one massive wall of text.
            try:
                await callback_query.message.edit_text(
                    "**🔀 File Converter — Mega Edition**\n\n"
                    "> Your all-in-one media swiss-army knife.\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "The converter handles video, audio, and image files with "
                    "dozens of operations. Pick a topic below to learn more.\n\n"
                    "**Shortcut:** `/c` or `/convert`",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("🚀 How to Use", callback_data="help_fc_howto")],
                            [InlineKeyboardButton("🎬 Video", callback_data="help_fc_video"),
                             InlineKeyboardButton("🎵 Audio", callback_data="help_fc_audio")],
                            [InlineKeyboardButton("🖼 Image", callback_data="help_fc_image"),
                             InlineKeyboardButton("⚙️ Transform", callback_data="help_fc_transform")],
                            [InlineKeyboardButton("💡 Tips & Tricks", callback_data="help_fc_tips")],
                            [InlineKeyboardButton("← Back to Tools", callback_data="help_tools")],
                        ]
                    ),
                    disable_web_page_preview=True,
                )
            except MessageNotModified:
                pass
            return
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
        elif tool == "trimmer":
            text = (
                "**✂️ Video Trimmer**\n\n"
                "> Cut videos by timestamp.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Trims a video between a start and end timestamp using stream copy (no re-encoding).\n\n"
                "• Send a video, then provide start and end times.\n"
                "• **Format:** `HH:MM:SS` or `MM:SS`\n"
                "• **Shortcut:** `/t` or `/trim`."
            )
        elif tool == "mediainfo":
            text = (
                "**ℹ️ Media Info**\n\n"
                "> Inspect any media file.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Shows detailed technical information about a media file: codecs, resolution, bitrate, duration, and all streams.\n\n"
                "• **Shortcut:** `/mi` or `/mediainfo`."
            )
        elif tool == "voice":
            text = (
                "**🎙️ Voice Note Converter**\n\n"
                "> Turn audio into voice notes.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Converts any audio file to Telegram voice note format (OGG Opus).\n\n"
                "• Send an audio file and it will be converted and sent as a voice message.\n"
                "• **Shortcut:** `/v` or `/voice`."
            )
        elif tool == "videonote":
            text = (
                "**⭕ Video Note Converter**\n\n"
                "> Create round video messages.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What it does:**\n"
                "Converts a video into a Telegram round video note. The video is cropped to square, scaled to 384px, and limited to 60 seconds.\n\n"
                "• **Shortcut:** `/vn` or `/videonote`."
            )
        elif tool == "youtube":
            try:
                await callback_query.message.edit_text(
                    "**▶️ YouTube Tool**\n\n"
                    "> Professional YouTube downloader with anti-bot hardening.\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Paste any `youtube.com` / `youtu.be` link or use `/yt`. "
                    "Pick a topic below to explore what's possible.\n\n"
                    "**Shortcut:** `/yt` or `/youtube`",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("🚀 How to Use", callback_data="help_yt_howto")],
                            [InlineKeyboardButton("🎬 Video", callback_data="help_yt_video"),
                             InlineKeyboardButton("🎵 Audio", callback_data="help_yt_audio")],
                            [InlineKeyboardButton("🖼 Thumbnails", callback_data="help_yt_thumb"),
                             InlineKeyboardButton("📝 Subtitles", callback_data="help_yt_subs")],
                            [InlineKeyboardButton("ℹ️ Video Info", callback_data="help_yt_info"),
                             InlineKeyboardButton("🍪 Cookies (Admin)", callback_data="help_yt_cookies")],
                            [InlineKeyboardButton("🛡 Anti-Bot & Errors", callback_data="help_yt_errors"),
                             InlineKeyboardButton("💡 Tips", callback_data="help_yt_tips")],
                            [InlineKeyboardButton("← Back to Tools", callback_data="help_tools")],
                        ]
                    ),
                    disable_web_page_preview=True,
                )
            except MessageNotModified:
                pass
            return
        else:
            text = (
                "**🛠 Tool Info**\n\n"
                "Sorry, no detailed guide is available for this tool yet."
            )

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(back_to_tools),
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass

    elif data == "help_file_management":
        try:
            await callback_query.message.edit_text(
                "**📁 File Management — /myfiles**\n\n"
                "> Your personal cloud locker inside Telegram.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Everything you process with the bot flows through **MyFiles**. "
                "You get temporary history, permanent pinned slots, folders, "
                "search, quotas, and more. Pick a topic below:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🚀 Overview & Quick Start", callback_data="help_mf_overview")],
                        [InlineKeyboardButton("🕒 Temporary Files", callback_data="help_mf_temp"),
                         InlineKeyboardButton("📌 Permanent Slots", callback_data="help_mf_perm")],
                        [InlineKeyboardButton("📂 Folders", callback_data="help_mf_folders"),
                         InlineKeyboardButton("🔎 Search & Filters", callback_data="help_mf_search")],
                        [InlineKeyboardButton("📈 Quotas & Storage", callback_data="help_mf_quotas"),
                         InlineKeyboardButton("♻️ Actions & Sharing", callback_data="help_mf_actions")],
                        [InlineKeyboardButton("💡 Tips & FAQ", callback_data="help_mf_tips")],
                        [InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")],
                    ]
                ),
                disable_web_page_preview=True,
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
                "<blockquote expandable>**Supported Video Formats:**\n"
                "• `.mp4`, `.mkv`, `.avi`, `.webm`, `.flv`\n\n"
                "**Supported Audio Formats:**\n"
                "• `.mp3`, `.flac`, `.m4a`, `.wav`, `.aac`\n\n"
                "**Supported Image Formats:**\n"
                "• `.jpg`, `.png`, `.webp`, `.jpeg`\n\n"
                "__(The bot can process any extension, but specific tools like the Converter or Audio Editor only work with media files!)__</blockquote>",
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
                "<blockquote expandable>Welcome to the troubleshooting guide. Here you can find solutions to common problems.\n"
                "If you are experiencing issues with the bot, please select one of the categories below to see detailed help.</blockquote>\n\n"
                "Select the issue you are experiencing below to see how to fix it:",
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
            try:
                await callback_query.message.edit_text(
                    "**📺 Dumb Channels — Auto-Routing**\n\n"
                    "> Automatically push processed files into the right channel.\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Dumb Channels are Telegram channels the bot posts into on "
                    "your behalf — sorted by content type. Pick a topic below "
                    "to learn more.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("🚀 What is it?", callback_data="help_dumb_overview")],
                            [InlineKeyboardButton("🔧 Setup Step-by-Step", callback_data="help_dumb_setup")],
                            [InlineKeyboardButton("🏷 Channel Types", callback_data="help_dumb_types"),
                             InlineKeyboardButton("🗂 Multiple Channels", callback_data="help_dumb_multi")],
                            [InlineKeyboardButton("🧙 Channel Wizard", callback_data="help_dumb_wizard"),
                             InlineKeyboardButton("🔐 Permissions", callback_data="help_dumb_perms")],
                            [InlineKeyboardButton("💡 Tips & Troubleshooting", callback_data="help_dumb_tips")],
                            [InlineKeyboardButton("← Back to Settings", callback_data="help_settings")],
                        ]
                    ),
                    disable_web_page_preview=True,
                )
            except MessageNotModified:
                pass
            return
        elif setting == "info":
            try:
                public_cfg = await db.get_public_config()
            except Exception:
                public_cfg = {}
            bot_name = public_cfg.get("bot_name", "𝕏TV MediaStudio™")
            community_name = public_cfg.get("community_name", "𝕏TV Network")
            support_contact = public_cfg.get("support_contact", "@davdxpx")

            text = (
                f"**ℹ️ {bot_name} — Info & Contact**\n\n"
                f"> Everything about the bot, its makers, and where to find us.\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"**💡 About This Bot**\n"
                f"Your ultimate media processing tool. Easily rename, format, convert, and organize your files with professional metadata injection, custom thumbnails, and much more.\n\n"
                f"**📊 Quick Facts**\n"
                f"• **Bot Version:** `{Config.VERSION} (Public Edition)`\n"
                f"• **MyFiles Engine:** `{Config.MYFILES_VERSION}`\n"
                f"• **Community:** `{community_name}`\n\n"
                f"**🔍 See Live Stats**\n"
                f"Use the `/info` command to view the full live status:\n"
                f"• Bot version & uptime\n"
                f"• Live CPU / RAM load\n"
                f"• Python & Pyrofork versions\n"
                f"• Support contact & community link\n\n"
                f"**📞 Help & Support**\n"
                f"• **Support Contact:** {support_contact}\n"
                f"• **Bot Updates Channel:** [@XTVbots](https://t.me/XTVbots)\n"
                f"• **Backup Channel:** [@XTVhome](https://t.me/XTVhome)\n\n"
                f"**🧩 Source Code**\n"
                f"This bot is open source — explore, learn, or contribute:\n"
                f"• [github.com/davdxpx/XTV-MediaStudio](https://github.com/davdxpx/XTV-MediaStudio)\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"**⚡ Powered by:** [𝕏TV](https://t.me/XTVglobal)\n"
                f"**👨‍💻 Developed by:** [𝕏0L0™](https://t.me/davdxpx)\n"
                f"© 2026 𝕏TV Network Global"
            )
        else:
            text = "Unknown setting."

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(back_to_set),
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_fc_"):
        section = data.replace("help_fc_", "")
        back_to_fc = [[InlineKeyboardButton("← Back to File Converter", callback_data="help_tool_convert")]]

        if section == "howto":
            text = (
                "**🚀 File Converter — How to Use**\n\n"
                "> Three steps to any conversion.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**1️⃣ Send the file**\n"
                "Drop any video, audio or image into the chat — or hit `/c` / `/convert` on an existing file.\n\n"
                "**2️⃣ Pick a category**\n"
                "A menu appears with the categories available for that file type (Video / Audio / Image + Transform).\n\n"
                "**3️⃣ Pick an operation**\n"
                "Choose the target format or effect. The bot downloads, processes, and re-uploads the result.\n\n"
                "**⚡ Good to know**\n"
                "• Stream-copy is used whenever possible — most conversions finish in seconds.\n"
                "• The original filename and metadata title are preserved; a small suffix marks the new version.\n"
                "• Every submenu has a 🔙 Back button — no dead ends."
            )
        elif section == "video":
            text = (
                "**🎬 File Converter — Video**\n\n"
                "> Remux, re-encode, extract, and GIFify.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**📦 Container (remux, no quality loss)**\n"
                "• MP4, MKV, MOV, AVI, WEBM, FLV, 3GP, TS\n"
                "• Fast: streams are copied, not re-encoded.\n\n"
                "**🎞 Codec (re-encode)**\n"
                "• x264 (H.264) — universal compatibility\n"
                "• x265 (H.265) — smaller files, modern players\n"
                "• VP9 — ideal for WEBM / YouTube\n"
                "• AV1 — the new streaming standard\n\n"
                "**🎵 Extract Audio**\n"
                "• MP3, M4A (AAC), OGG, OPUS, FLAC, WAV\n\n"
                "**🖼 Extract Frame**\n"
                "• PNG, JPG, WEBP — grabs the first frame.\n\n"
                "**🎞 GIF**\n"
                "• Low / Medium / High quality presets.\n"
                "• Automatically caps dimensions for smooth playback."
            )
        elif section == "audio":
            text = (
                "**🎵 File Converter — Audio**\n\n"
                "> Re-encode, re-format, polish.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**📊 Bitrate**\n"
                "• 128 / 192 / 256 / 320 kbps\n\n"
                "**🔀 Format**\n"
                "• MP3 · M4A (AAC) · OGG · OPUS · FLAC · WAV · WMA\n\n"
                "**🔊 Audio FX**\n"
                "• Normalize — Evens out loud & quiet parts.\n"
                "• Boost +6dB — Louder output.\n"
                "• Mono Downmix — Fold stereo into mono.\n"
                "• Plus additional effect presets in-menu.\n\n"
                "**💡 Tip**\n"
                "Audio FX is also available on video files without re-encoding the picture."
            )
        elif section == "image":
            text = (
                "**🖼 File Converter — Image**\n\n"
                "> Format, size, orientation, filters, compression.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**🔀 Format**\n"
                "• JPG · PNG · WEBP · BMP · TIFF · GIF\n\n"
                "**📐 Resize**\n"
                "• HD, FHD, square and thumbnail presets.\n"
                "• Aspect ratio preserved.\n\n"
                "**🔄 Rotate / Flip**\n"
                "• 90° · 180° · 270°\n"
                "• Horizontal & vertical flip.\n\n"
                "**🎨 Filter**\n"
                "• Grayscale, sepia, invert, blur, sharpen, and more.\n\n"
                "**🗜 Compress**\n"
                "• Quality presets — shrink without visible loss."
            )
        elif section == "transform":
            text = (
                "**⚙️ File Converter — Transform (Video)**\n\n"
                "> Resize, speed, mute, reverse — without leaving the bot.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**📐 Resolution**\n"
                "• 480p · 720p · 1080p · 4K presets.\n\n"
                "**⚡ Speed**\n"
                "• 0.5× · 1.5× · 2× · and more.\n"
                "• Audio is automatically re-pitched to stay in sync.\n\n"
                "**🔇 Mute**\n"
                "• Strip the audio track completely.\n\n"
                "**⏪ Reverse**\n"
                "• Play the whole clip backwards (with reversed audio).\n\n"
                "**💡 Tip**\n"
                "Use Transform before Codec if you want maximum compression — lower resolution + new codec."
            )
        elif section == "tips":
            text = (
                "**💡 File Converter — Tips & Tricks**\n\n"
                "> Get the best results with the least waiting.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **Container before codec.** If you only need a different file extension, use Container — it's instant.\n"
                "• **Codec for size.** H.265 / AV1 can shrink a file by 40–60 % at the same visual quality.\n"
                "• **Extract Audio saves bandwidth.** Pulling the music out of a music-video is tiny vs. re-uploading the whole clip.\n"
                "• **Send as Document.** Telegram compresses 'Video' uploads. Always send as **File/Document** for best quality input.\n"
                "• **Preview frame.** Use Extract Frame to grab a poster image for thumbnails.\n"
                "• **Chain it.** Converter output lands in your MyFiles — run it through another tool next.\n"
                "• **Cancel anytime.** Type `/end` to abort a long conversion."
            )
        else:
            text = "Unknown File Converter topic."

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(back_to_fc),
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_yt_"):
        section = data.replace("help_yt_", "")
        back_to_yt = [[InlineKeyboardButton("← Back to YouTube Tool", callback_data="help_tool_youtube")]]

        if section == "howto":
            text = (
                "**🚀 YouTube Tool — How to Use**\n\n"
                "> Paste. Pick. Download.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**1️⃣ Open the tool**\n"
                "• Send `/yt` or `/youtube`, or just paste a `youtube.com` / `youtu.be` link anywhere in chat.\n"
                "• Auto-detect opens the menu instantly when a link is pasted.\n\n"
                "**2️⃣ Pick a mode**\n"
                "Video · Audio · Thumbnail · Subtitles · Video Info\n\n"
                "**3️⃣ Pick quality / options**\n"
                "The bot downloads via yt-dlp, rotates player clients if needed, and sends the file back.\n\n"
                "**Shortcut:** `/yt` or `/youtube`"
            )
        elif section == "video":
            text = (
                "**🎬 YouTube — Video Download**\n\n"
                "> Pick a resolution or let the bot grab the best.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Available qualities**\n"
                "• 360p — small, fast, data-friendly.\n"
                "• 480p — balanced for mobile.\n"
                "• 720p — HD for most content.\n"
                "• 1080p — full HD when offered.\n"
                "• **Best** — auto-picks the highest available video+audio.\n\n"
                "**Output**\n"
                "• MP4 container with best video + best audio merged via ffmpeg.\n"
                "• Progress updates while downloading & muxing.\n\n"
                "**💡 Tip**\n"
                "If a quality isn't listed on YouTube, the bot falls back to the closest available stream."
            )
        elif section == "audio":
            text = (
                "**🎵 YouTube — Audio Extraction**\n\n"
                "> MP3 out of any video.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Bitrates**\n"
                "• 128 kbps — podcasts, speech\n"
                "• 192 kbps — default music quality\n"
                "• 320 kbps — maximum MP3 fidelity\n\n"
                "**What you get**\n"
                "• `.mp3` file with the video title as filename.\n"
                "• Embedded thumbnail & basic ID3 tags where possible.\n\n"
                "**💡 Tip**\n"
                "For albums or music videos, combine with the Audio Metadata Editor (`/a`) afterwards to fine-tune tags."
            )
        elif section == "thumb":
            text = (
                "**🖼 YouTube — Thumbnails**\n\n"
                "> Grab the HD cover art in one click.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Pulls the highest-resolution thumbnail YouTube offers (`maxresdefault` when available, then `sddefault`, then `hqdefault`).\n"
                "• Returned as a real image — not a compressed preview.\n"
                "• Perfect for making your own video posters, social posts, or channel banners.\n\n"
                "**💡 Tip**\n"
                "Run the thumbnail through the Image Watermarker (`/w`) if you want to brand it with your logo before sharing."
            )
        elif section == "subs":
            text = (
                "**📝 YouTube — Subtitles**\n\n"
                "> Captions in dozens of languages.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What's supported**\n"
                "• Manual subtitles (when the uploader provided them).\n"
                "• Auto-generated captions (YouTube speech-to-text).\n"
                "• All languages YouTube lists for that video.\n\n"
                "**Output formats**\n"
                "• `.srt` — universal subtitle format.\n"
                "• `.vtt` — when requested / when SRT isn't available.\n\n"
                "**💡 Tip**\n"
                "If no language appears, the creator simply didn't enable captions on that video and auto-subs are disabled."
            )
        elif section == "info":
            text = (
                "**ℹ️ YouTube — Video Info**\n\n"
                "> Everything about the video without downloading it.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Displays:\n"
                "• 🎬 Title, uploader, channel link.\n"
                "• ⏱ Duration · 👁 Views · 👍 Likes.\n"
                "• 📅 Upload date · 🏷 Tags · 🌐 Language.\n"
                "• 📖 Description (truncated if huge).\n"
                "• 📑 Chapters — if the uploader set them.\n\n"
                "**💡 Tip**\n"
                "Use Video Info first to confirm you've got the right video before kicking off a download."
            )
        elif section == "cookies":
            text = (
                "**🍪 YouTube — Cookies (Admin)**\n\n"
                "> Bypass YouTube's anti-bot gate.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Why cookies?**\n"
                "YouTube increasingly blocks server IPs with \"Sign in to confirm you're not a bot\". A valid `cookies.txt` from a logged-in browser session solves this.\n\n"
                "**Admin commands**\n"
                "• `/ytcookies` — upload or refresh cookies.\n"
                "• `/ytcookies_remove` — wipe cookies from disk **and** DB.\n\n"
                "**How to export**\n"
                "1. Log into `youtube.com` in your browser.\n"
                "2. Use an extension like **Get cookies.txt LOCALLY**.\n"
                "3. Save as `cookies.txt` → send it to the bot as a document.\n\n"
                "**🛡 Persistence**\n"
                "Cookies are mirrored into MongoDB automatically — they survive container redeploys (no volume mount needed)."
            )
        elif section == "errors":
            text = (
                "**🛡 YouTube — Anti-Bot & Errors**\n\n"
                "> What the bot does when YouTube pushes back.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**🤖 Bot-check (Sign in to confirm...)**\n"
                "• The bot automatically rotates through multiple **player_client** profiles (android, ios, web, tv_embedded, mweb).\n"
                "• If all clients fail, you'll see a friendly screen with next-step guidance.\n"
                "• Fix: admin uploads fresh cookies via `/ytcookies`.\n\n"
                "**📉 \"Requested format is not available\"**\n"
                "• After all player clients fail, the bot retries once with `format=best` (no strict merge rules).\n"
                "• If it still fails, a dedicated help screen explains likely causes: live stream, DRM, region-locked, rate-limit.\n\n"
                "**🔁 Built-in retry chain**\n"
                "• Player-client rotation → cookie check → permissive format → typed error UI.\n"
                "• No more generic \"Unexpected error\" for known YouTube cases."
            )
        elif section == "tips":
            text = (
                "**💡 YouTube — Tips**\n\n"
                "> Get more out of the tool.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **Paste anywhere.** Any YouTube URL opens the menu, even mid-conversation.\n"
                "• **Playlist links** are auto-reduced to the current video — no accidental 500-file downloads.\n"
                "• **Shorts work too.** `youtube.com/shorts/…` URLs behave like normal videos.\n"
                "• **Restricted / age-gated.** Usually solved by uploading cookies (admin).\n"
                "• **Very long videos.** Prefer 720p or Audio to stay under Telegram's 2 GB / 4 GB limit.\n"
                "• **Quality not listed?** YouTube didn't publish that rendition — pick the next lower option or use Best.\n"
                "• **Output lands in MyFiles.** Pin it to permanent storage to keep it."
            )
        else:
            text = "Unknown YouTube topic."

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(back_to_yt),
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_mf_"):
        section = data.replace("help_mf_", "")
        back_to_mf = [[InlineKeyboardButton("← Back to File Management", callback_data="help_file_management")]]

        if section == "overview":
            text = (
                "**🚀 MyFiles — Overview & Quick Start**\n\n"
                "> Your personal media locker inside Telegram.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What is MyFiles?**\n"
                "Every file you process with the bot — renames, conversions, extracts, YouTube downloads — is saved to your private locker, so you can re-download, share, or re-process it without re-uploading.\n\n"
                "**Quick start**\n"
                "• Command: `/myfiles`\n"
                "• Opens a paginated gallery with inline buttons.\n"
                "• Two storage tiers: 🕒 **Temporary** (auto-expires) and 📌 **Permanent** (pinned forever).\n"
                "• Organise with 📂 **Folders** and find things with 🔎 **Search**.\n\n"
                "**Engine**\n"
                f"• MyFiles v`{Config.MYFILES_VERSION}` — production-grade async storage backed by MongoDB."
            )
        elif section == "temp":
            text = (
                "**🕒 MyFiles — Temporary Files**\n\n"
                "> Short-term history of everything you processed.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**How it works**\n"
                "• Every processed file is added automatically — no action needed.\n"
                "• Expires after a plan-based number of days (see /start profile).\n"
                "• Survives bot restarts: stored in DB, referenced by Telegram file_id.\n\n"
                "**What you can do**\n"
                "• ⬇ Re-download instantly — no re-upload.\n"
                "• 📌 Promote to **Permanent** with one tap.\n"
                "• 🔁 Re-run through another tool (converter, watermarker…).\n"
                "• 🗑 Delete manually if you want space back.\n\n"
                "**💡 Tip**\n"
                "If a file is important, pin it to Permanent before expiry — one click from the file view."
            )
        elif section == "perm":
            text = (
                "**📌 MyFiles — Permanent Slots**\n\n"
                "> Files that never expire.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**What are slots?**\n"
                "Each user has a plan-based number of **permanent slots**. A file placed in a slot is kept forever (until you remove it).\n\n"
                "**Slot limits**\n"
                "• **Free** — small slot pool (see /start).\n"
                "• **Premium** — significantly more slots.\n"
                "• **CEO** — unlimited.\n\n"
                "**Actions**\n"
                "• 📌 Pin — moves a temporary file into a permanent slot.\n"
                "• 🗑 Unpin — frees the slot; the file becomes temporary again.\n"
                "• ✏️ Rename — change the display name without re-uploading.\n\n"
                "**💡 Tip**\n"
                "If you're slot-limited, delete old pins you no longer need before adding new ones."
            )
        elif section == "folders":
            text = (
                "**📂 MyFiles — Folders**\n\n"
                "> Sort your locker your way.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Creating folders**\n"
                "• Use the ➕ New Folder button inside `/myfiles`.\n"
                "• Pick a name (emojis welcome).\n\n"
                "**Moving files**\n"
                "• Open any permanent file → **Move to folder**.\n"
                "• Files can live in one folder at a time.\n\n"
                "**Renaming & deleting folders**\n"
                "• Long-press a folder or open its menu.\n"
                "• Deleting a folder returns its files to the root.\n\n"
                "**💡 Tip**\n"
                "Great categories: `🎬 Movies`, `📺 Series`, `🎵 Music`, `📄 Docs`, `🖼 Images`, `✏️ Drafts`."
            )
        elif section == "search":
            text = (
                "**🔎 MyFiles — Search & Filters**\n\n"
                "> Find a file in a sea of files.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Search**\n"
                "• Hit the 🔎 button inside `/myfiles`.\n"
                "• Type part of the filename, title, or extension.\n"
                "• Matches across temporary **and** permanent files.\n\n"
                "**Filter by type**\n"
                "• 🎬 Video · 🎵 Audio · 🖼 Image · 📄 Document · 📝 Subtitle\n"
                "• Instantly narrows the gallery.\n\n"
                "**Sort options**\n"
                "• Newest first (default) · Oldest · Name A→Z · Size.\n\n"
                "**💡 Tip**\n"
                "Search is case-insensitive and works on partial words — typing `ep5` will match `Show.S01E05.mkv`."
            )
        elif section == "quotas":
            text = (
                "**📈 MyFiles — Quotas & Storage**\n\n"
                "> Fair usage, transparent limits.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Per-plan limits**\n"
                "• **Daily files** — how many files you can process per 24 h.\n"
                "• **Daily egress** — total MB/GB of upload+download per day.\n"
                "• **Temp expiry** — how long temporary files live.\n"
                "• **Permanent slots** — long-term storage cap.\n\n"
                "**Where to see them**\n"
                "• `/start` → your profile card shows today's usage.\n"
                "• `/myfiles` → footer shows temp/perm counts.\n\n"
                "**Resets**\n"
                "• Daily counters reset on a rolling 24 h window (UTC).\n"
                "• Expired temporary files are auto-cleaned every 6 hours.\n\n"
                "**💡 Tip**\n"
                "Hit a wall? Pin what matters, delete the rest, or upgrade via the Premium Dashboard."
            )
        elif section == "actions":
            text = (
                "**♻️ MyFiles — Actions & Sharing**\n\n"
                "> Everything you can do with a stored file.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Open any file in `/myfiles` to reveal its action panel:\n\n"
                "• **⬇ Re-send** — instantly re-delivers the file to your chat.\n"
                "• **📌 Pin / 🗑 Unpin** — toggle permanent status.\n"
                "• **📂 Move** — drop into a folder.\n"
                "• **✏️ Rename** — change display name.\n"
                "• **🔁 Re-process** — feed the file straight into another tool (converter, audio editor, watermarker, etc.).\n"
                "• **🗑 Delete** — permanently remove from storage.\n\n"
                "**🔗 Sharing**\n"
                "Re-send puts the file back in your chat — forward it to anyone like a normal Telegram file."
            )
        elif section == "tips":
            text = (
                "**💡 MyFiles — Tips & FAQ**\n\n"
                "> Shortcuts and common questions.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **Shortcut:** `/mf` works as a fast alias for `/myfiles`.\n"
                "• **Re-send is free.** Re-delivering a stored file doesn't count against daily egress.\n"
                "• **File IDs expire?** No — the bot caches a canonical reference that's refreshed automatically.\n"
                "• **Lost a file after restart?** Temporary files are in DB — hit `/myfiles` and they're still there.\n"
                "• **Can I nest folders?** Not yet — keep folders flat.\n"
                "• **Backup?** Pin important files as Permanent; admins can export DB if needed.\n"
                "• **Privacy.** Only *you* see *your* files. Even admins don't browse user lockers in the UI.\n\n"
                "**Need help?** Visit the Help menu → Troubleshooting → **Files & Storage**."
            )
        else:
            text = "Unknown MyFiles topic."

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(back_to_mf),
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass

    elif data.startswith("help_dumb_"):
        section = data.replace("help_dumb_", "")
        back_to_dumb = [[InlineKeyboardButton("← Back to Dumb Channels", callback_data="help_set_dumb")]]

        if section == "overview":
            text = (
                "**🚀 Dumb Channels — Overview**\n\n"
                "> Auto-post your processed files into the right place.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**The idea**\n"
                "Instead of re-forwarding every finished file into your library channels, just tell the bot where each **type** of content belongs once. From then on, processed files go there automatically.\n\n"
                "**Why \"dumb\"?**\n"
                "Because the bot doesn't need any setup *inside* the channel — it just posts. The channel is passive, the bot does the thinking.\n\n"
                "**Typical flow**\n"
                "1. You process a movie → it lands in the Movies channel.\n"
                "2. You process an episode → it lands in the Series channel.\n"
                "3. Random docs / audio → Standard channel."
            )
        elif section == "setup":
            text = (
                "**🔧 Dumb Channels — Setup**\n\n"
                "> Four steps, one-time configuration.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**1️⃣ Create or pick a channel**\n"
                "Private or public, both work. Give it a clear name (e.g. `🎬 My Movies`).\n\n"
                "**2️⃣ Add the bot as admin**\n"
                "Open the channel → Admins → Add admin → search for the bot → grant **Post Messages** (the only permission required).\n\n"
                "**3️⃣ Open settings**\n"
                "In the bot chat: `/settings` → **Dumb Channels** → **➕ Add channel**.\n\n"
                "**4️⃣ Link the channel**\n"
                "Forward any message from the target channel to the bot, or paste its `@username` / invite link. Then choose the **type** (Movies / Series / Standard)."
            )
        elif section == "types":
            text = (
                "**🏷 Dumb Channels — Channel Types**\n\n"
                "> Three tiers decide what lands where.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**🎬 Movies**\n"
                "Receives files the bot classifies as movies (TMDb match, no season/episode, movie-style filename).\n\n"
                "**📺 Series**\n"
                "Receives episodes (S01E05, 1x05, anime numbering, etc.). Respects auto-detected season/episode info in the caption.\n\n"
                "**📦 Standard**\n"
                "Catch-all for everything that isn't clearly a movie or a series: music, documents, images, personal files.\n\n"
                "**💡 Rule of thumb**\n"
                "Start with one Standard channel — you can always add a Movies / Series split later."
            )
        elif section == "multi":
            text = (
                "**🗂 Dumb Channels — Multiple Channels**\n\n"
                "> One channel per type — or many.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**How it works**\n"
                "• You can link more than one channel per type.\n"
                "• When multiple channels share a type, the bot posts to **all** of them (mirroring).\n"
                "• Great for: public + private library, main + backup, personal + shared.\n\n"
                "**Unlinking**\n"
                "`/settings` → **Dumb Channels** → pick a channel → **Remove**.\n\n"
                "**💡 Tip**\n"
                "Use mirroring to keep a private backup channel in sync with your public one — zero manual forwarding."
            )
        elif section == "wizard":
            text = (
                "**🧙 Dumb Channels — Channel Wizard**\n\n"
                "> Let the bot guide you through setup.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "The Channel Wizard is an interactive setup flow that walks you through every required step:\n\n"
                "• 🔍 Verifies the bot is an admin in your channel.\n"
                "• 🧪 Sends a test post and confirms it landed.\n"
                "• 🏷 Prompts you to pick a type (Movies / Series / Standard).\n"
                "• 💾 Saves the configuration to the DB.\n\n"
                "**Where to find it**\n"
                "`/settings` → **Dumb Channels** → **🧙 Channel Wizard**.\n\n"
                "**💡 Tip**\n"
                "If a normal Add flow fails with a permissions error, run the wizard — it pinpoints exactly what's missing."
            )
        elif section == "perms":
            text = (
                "**🔐 Dumb Channels — Permissions**\n\n"
                "> What the bot actually needs.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**Minimum required**\n"
                "• **Post Messages** ✅\n\n"
                "**Recommended**\n"
                "• **Edit Messages** — lets the bot update a processing-status post instead of spamming new ones.\n"
                "• **Delete Messages** — useful if a post needs to be pulled (e.g., wrong file).\n\n"
                "**Not needed**\n"
                "• Restrict/Promote users, invite members, change info — the bot never touches these.\n\n"
                "**Security**\n"
                "The bot stores only the channel ID / link — never its join link secrets. Revoking admin in Telegram instantly cuts off access."
            )
        elif section == "tips":
            text = (
                "**💡 Dumb Channels — Tips & Troubleshooting**\n\n"
                "> Make it work perfectly, every time.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **Chat not found / PEER error?** The bot hasn't seen the channel yet. Send one message from the channel (forwarded to the bot) or restart the bot.\n"
                "• **Post failed — bot is not admin.** Re-add the bot in the channel's admin list with **Post Messages** permission.\n"
                "• **Files go to wrong type?** Auto-detection was ambiguous — rename with a cleaner filename *before* sending, or switch the detected type in the confirmation step.\n"
                "• **Standard channel duplicates posts.** You probably have both a Standard and a typed channel — files match the typed one **and** fall through to Standard. Remove Standard if you want strict routing.\n"
                "• **Want captions customized?** See **Settings → Caption Template**.\n"
                "• **Revoking access.** Just remove the bot from the channel admins — no need to edit settings."
            )
        else:
            text = "Unknown Dumb Channels topic."

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(back_to_dumb),
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass

    elif data == "help_close":
        await callback_query.message.delete()

# --- ✨ New in v2.2 submenu ------------------------------------------------

# --- Hub ---------------------------------------------------------------------

def _hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔒 TMDb is now optional", callback_data="help_v22_tmdb")],
            [InlineKeyboardButton("☁️ Mirror-Leech overview", callback_data="help_v22_ml_intro")],
            [
                InlineKeyboardButton("📥 Sources", callback_data="help_v22_ml_sources"),
                InlineKeyboardButton("☁️ Destinations", callback_data="help_v22_ml_dests"),
            ],
            [InlineKeyboardButton("🔗 Linking a provider", callback_data="help_v22_ml_link")],
            [InlineKeyboardButton("🧩 MyFiles integration", callback_data="help_v22_ml_myfiles")],
            [InlineKeyboardButton("🎲 SECRETS_KEY one-click", callback_data="help_v22_secrets")],
            [InlineKeyboardButton("🩺 System Health panel", callback_data="help_v22_health")],
            [InlineKeyboardButton("🗃 DB layout migration", callback_data="help_v22_dblayout")],
            [InlineKeyboardButton("← Back to Guide", callback_data="help_guide")],
        ]
    )


def _hub_text() -> str:
    return (
        "**✨ What's new in v2.2**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bite-sized pages covering everything MyFiles 2.2 added on top of "
        "the original bot. Tap a topic; each page is one screen of copy "
        "with a back button.\n\n"
        "> __Tip:__ If you're just starting out, read **☁️ Mirror-Leech "
        "overview** first — it ties most of the other pages together."
    )


@Client.on_callback_query(filters.regex(r"^help_new_v22$"))
async def help_v22_hub(client: Client, callback_query: CallbackQuery) -> None:
    try:
        await callback_query.message.edit_text(_hub_text(), reply_markup=_hub_keyboard())
    except MessageNotModified:
        pass
    try:
        await callback_query.answer()
    except Exception:
        pass


# --- Individual pages --------------------------------------------------------

_PAGES: dict[str, tuple[str, str]] = {
    "tmdb": (
        "🔒 TMDb is now optional",
        "**🔒 TMDb is now optional**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "The bot runs fine without a TMDb API key — only the features "
        "that actually need TMDb show a 🔒 badge until you add one.\n\n"
        "**Keeps working without TMDb**\n"
        "> • General Mode renaming\n"
        "> • File Converter, YouTube Tool, MyFiles, all other Tools\n\n"
        "**Unlocks with a key**\n"
        "> • Auto-match of uploads to Movie / Series\n"
        "> • Posters on MyFiles + rename previews\n"
        "> • Auto-route between Movie / Series dumb channels\n\n"
        "Check `/admin → 🩺 System Health → 🎬 TMDb Status` to see the "
        "current state and grab a free key if you want to light it up.",
    ),
    "ml_intro": (
        "☁️ Mirror-Leech overview",
        "**☁️ Mirror-Leech overview**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Mirror-Leech takes any supported source and fans it out to every "
        "cloud destination you've linked.\n\n"
        "> 🔗 One URL in → many destinations out\n"
        "> 🧩 Deep fusion with MyFiles (single + batch)\n"
        "> 📊 `/mlqueue` tracks jobs with inline cancel\n"
        "> 🔐 Credentials encrypted at rest (Fernet)\n\n"
        "**Entry points**\n"
        "> • `/ml <url>` — pick destinations, hit Start\n"
        "> • `/settings → ☁️ Mirror-Leech` — link providers\n"
        "> • MyFiles `☁️ Mirror-Leech Options` on any file\n\n"
        "Admins flip the feature toggle at `/admin → 🩺 System Health "
        "→ ☁️ Mirror-Leech Config`.",
    ),
    "ml_sources": (
        "📥 Mirror-Leech sources",
        "**📥 Mirror-Leech sources**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "What `/ml` accepts:\n\n"
        "> • **Direct HTTP(S) URL** — aiohttp streaming with resume\n"
        "> • **yt-dlp page** — any URL a yt-dlp extractor recognises "
        "(YouTube, social video, etc.)\n"
        "> • **Telegram file** — automatically used when you tap "
        "☁️ Mirror-Leech on a MyFiles entry\n"
        "> • **RSS feed** — first enclosure is handed to HTTP\n\n"
        "The Controller picks the right downloader on its own — you "
        "just paste the URL.\n\n"
        "__Heads-up:__ peer-to-peer links aren't supported on the main "
        "branch; use the torrent-edition build for that.",
    ),
    "ml_dests": (
        "☁️ Mirror-Leech destinations",
        "**☁️ Mirror-Leech destinations**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Every registered uploader can be fanned to in parallel:\n\n"
        "> • **Google Drive** — OAuth refresh-token flow\n"
        "> • **Rclone** — covers 70+ backends via your rclone.conf\n"
        "> • **MEGA.nz** — email + password\n"
        "> • **GoFile** — anonymous by default, optional token\n"
        "> • **Pixeldrain** — anonymous by default, optional key\n"
        "> • **Telegram** — DM fallback, userbot for >2 GB\n"
        "> • **DDL** — one-time signed URLs served from the host\n\n"
        "Availability depends on what's installed — unavailable "
        "providers are hidden automatically in the picker.",
    ),
    "ml_link": (
        "🔗 Linking a provider",
        "**🔗 Linking a provider**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "1. Open `/settings → ☁️ Mirror-Leech`.\n"
        "2. Tap the provider you want to link.\n"
        "3. Hit **📝 Paste / update credentials**, then send the token "
        "(or email+password, or rclone.conf) as your next message.\n"
        "4. The bot encrypts it with Fernet, deletes your paste "
        "message, and confirms.\n"
        "5. Tap **🔌 Test connection** to verify.\n\n"
        "**Clearing a provider**\n"
        "> Same screen → **🗑 Clear credential**. Removes every field "
        "for that provider so you can re-link cleanly.",
    ),
    "ml_myfiles": (
        "🧩 MyFiles integration",
        "**🧩 MyFiles integration**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Every MyFiles entry now has a **☁️ Mirror-Leech Options** "
        "button alongside Send / Rename / Move.\n\n"
        "**Single file**\n"
        "> Tap the button → pick destinations → **🚀 Start**.\n\n"
        "**Multi-select**\n"
        "> Tick the files you want, then the bottom bar shows "
        "`☁️ Mirror-Leech Selected (N)`. The picker queues one "
        "MLTask per file × destination so everything runs in parallel.\n\n"
        "Each task gets its own progress message with a cancel button, "
        "and `/mlqueue` lists them all at once.",
    ),
    "secrets": (
        "🎲 SECRETS_KEY one-click",
        "**🎲 SECRETS_KEY one-click generator**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Mirror-Leech encrypts every provider credential with Fernet. "
        "The key lives in the `SECRETS_KEY` env var and can be generated "
        "in-bot:\n\n"
        "1. `/admin → 🩺 System Health → ☁️ Mirror-Leech Config`\n"
        "2. Tap **🎲 Generate SECRETS_KEY**\n"
        "3. Copy the posted key + follow the per-host install block\n"
        "4. Restart the bot → tap **✅ Enable Mirror-Leech**\n\n"
        "__⚠️ Back the key up.__ Losing it means every user has to "
        "re-link their providers.",
    ),
    "health": (
        "🩺 System Health panel",
        "**🩺 System Health & Statuses**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "One admin entry gathering every operator-facing diagnostics "
        "page. Open via `/admin → 🩺 System Health & Statuses`.\n\n"
        "> 🩺 **DB Schema Health** — collection counts, migration state, "
        "recent unknown-key writes\n"
        "> 🎬 **TMDb Status** — is the key configured, what unlocks\n"
        "> ☁️ **Mirror-Leech Config** — master toggle, provider "
        "availability, SECRETS_KEY state\n\n"
        "All three pages switch between compact (when configured) and "
        "full-onboarding copy (when something is missing).",
    ),
    "dblayout": (
        "🗃 DB layout migration",
        "**🗃 DB layout migration**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "v2.2 renames every MongoDB collection to the **`MediaStudio-*`** "
        "scheme and splits the monolithic settings doc into per-concern "
        "docs (branding, payments, premium_plans, ...).\n\n"
        "> ✅ Runs once automatically at startup\n"
        "> 🛡 Idempotent, advisory-locked, safe to restart mid-run\n"
        "> 💾 Every legacy collection is copied to `<name>_backup_legacy` "
        "before the split\n\n"
        "**Operator actions** at `/admin → 🩺 System Health → 🩺 DB "
        "Schema Health`:\n"
        "> • **🔁 Re-run migration (dry-run)** — plan-only, no writes\n"
        "> • **🗑 Drop legacy backups** — reclaim disk once you're sure",
    ),
}


def _page_keyboard(topic_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("← Back to New in v2.2", callback_data="help_new_v22")],
            [InlineKeyboardButton("❌ Close", callback_data="help_close")],
        ]
    )


@Client.on_callback_query(filters.regex(r"^help_v22_(tmdb|ml_intro|ml_sources|ml_dests|ml_link|ml_myfiles|secrets|health|dblayout)$"))
async def help_v22_page(client: Client, callback_query: CallbackQuery) -> None:
    topic_id = callback_query.data.removeprefix("help_v22_")
    page = _PAGES.get(topic_id)
    if not page:
        await callback_query.answer("Unknown page.", show_alert=True)
        return
    _, body = page
    try:
        await callback_query.message.edit_text(body, reply_markup=_page_keyboard(topic_id))
    except MessageNotModified:
        pass
    try:
        await callback_query.answer()
    except Exception:
        pass
