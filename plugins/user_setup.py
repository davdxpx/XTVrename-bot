from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from config import Config
from utils.log import get_logger

logger = get_logger("plugins.user_setup")

# ---------------------------------------------------------------------------
# Available languages for TMDb preference
# ---------------------------------------------------------------------------
LANGUAGES = [
    ("en-US", "English"),
    ("de-DE", "Deutsch"),
    ("es-ES", "Español"),
    ("fr-FR", "Français"),
    ("hi-IN", "Hindi"),
    ("ja-JP", "日本語"),
    ("ko-KR", "한국어"),
    ("zh-CN", "中文"),
    ("ru-RU", "Русский"),
    ("it-IT", "Italiano"),
    ("pt-BR", "Português"),
    ("ta-IN", "Tamil"),
]

THUMB_MODES = [
    ("none", "❌ None"),
    ("auto", "🤖 Auto (TMDb)"),
    ("custom", "🖼️ Custom"),
]


# ---------------------------------------------------------------------------
# Core render function — always edits an existing message
# ---------------------------------------------------------------------------

async def render_user_preferences_inline(client, user_id, message):
    """Edit the given message to show tool preferences + language + thumbnail.

    Args:
        client: Pyrogram Client
        user_id: User ID
        message: The Message object to edit in-place
    """
    toggles = await db.get_feature_toggles()

    # Check premium features
    pf = {}
    if Config.PUBLIC_MODE:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                pf = plan_settings.get("features", {})

    def _is_available(feat_key):
        global_on = toggles.get(feat_key, True)
        plan_on = pf.get(feat_key, True) if pf else True
        return global_on and plan_on

    available_tools = [{"id": "rename", "name": "📁 Rename / Tag Media"}]
    tool_defs = [
        ("audio_editor", "🎵 Audio Editor"),
        ("file_converter", "🔀 File Converter"),
        ("watermarker", "©️ Watermarker"),
        ("subtitle_extractor", "📝 Subtitle Extractor"),
        ("video_trimmer", "✂️ Video Trimmer"),
        ("media_info", "ℹ️ Media Info"),
        ("voice_converter", "🎙️ Voice Converter"),
        ("video_note_converter", "⭕ Video Note Converter"),
    ]
    for tid, tname in tool_defs:
        if _is_available(tid):
            available_tools.append({"id": tid, "name": tname})

    user_settings = await db.get_settings(user_id)
    selected_tools = user_settings.get("start_menu_tools", ["rename"]) if user_settings else ["rename"]
    current_lang = user_settings.get("preferred_language", "en-US") if user_settings else "en-US"
    current_thumb = user_settings.get("thumbnail_mode", "none") if user_settings else "none"

    # Find display names
    lang_display = next((name for code, name in LANGUAGES if code == current_lang), current_lang)
    thumb_display = next((name for code, name in THUMB_MODES if code == current_thumb), current_thumb)

    text = (
        "**⚙️ Personalize Your Experience**\n\n"
        "> Select up to 3 tools to pin to your start menu.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "The rest will be inside the 'Other Features' button.\n\n"
        f"**Language:** `{lang_display}`  ·  **Thumbnail:** `{thumb_display}`\n\n"
        "__You can always change this later in /settings.__"
    )

    buttons = []
    row = []
    for tool in available_tools:
        is_selected = tool["id"] in selected_tools
        mark = "✅ " if is_selected else ""
        row.append(InlineKeyboardButton(f"{mark}{tool['name']}", callback_data=f"pref_toggle_{tool['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(f"🌐 {lang_display}", callback_data="pref_lang_menu"),
        InlineKeyboardButton(f"🖼️ {thumb_display}", callback_data="pref_thumb_menu"),
    ])
    buttons.append([InlineKeyboardButton("Done ➡️", callback_data="pref_finish")])

    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except MessageNotModified:
        pass
    except Exception:
        pass


async def send_user_tool_preferences_setup(client, user_id, message_or_query):
    """Backward-compatible wrapper used from /settings and start.py.

    If called with a CallbackQuery, edits the callback message.
    If called with a Message, sends a new message then edits it.
    """
    if hasattr(message_or_query, "answer"):
        # CallbackQuery
        await render_user_preferences_inline(client, user_id, message_or_query.message)
    else:
        # Message — send a new message first, then we have an anchor to edit
        msg = await message_or_query.reply_text("⏳ Loading preferences...")
        await render_user_preferences_inline(client, user_id, msg)


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^pref_"))
async def handle_user_preferences(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    user_settings = await db.get_settings(user_id)
    selected_tools = user_settings.get("start_menu_tools", ["rename"]) if user_settings else ["rename"]

    # --- Tool toggles ---
    if data.startswith("pref_toggle_"):
        tool_id = data.removeprefix("pref_toggle_")
        if tool_id in selected_tools:
            selected_tools.remove(tool_id)
        else:
            if len(selected_tools) >= 3:
                await callback_query.answer("You can only select up to 3 tools!", show_alert=True)
                return
            selected_tools.append(tool_id)
        await db.update_setting("start_menu_tools", selected_tools, user_id)
        await callback_query.answer()
        await render_user_preferences_inline(client, user_id, callback_query.message)

    # --- Finish setup (onboarding flow) ---
    elif data == "pref_finish":
        await db.update_setting("has_completed_preferences", True, user_id)
        await callback_query.answer("Preferences Saved!")
        # Render start menu in the SAME message
        from plugins.start import render_start_menu
        await render_start_menu(client, user_id, message_to_edit=callback_query.message, first_name=callback_query.from_user.first_name)

    # --- Finish and return to settings menu ---
    elif data == "pref_finish_return":
        await callback_query.answer("Preferences Saved!")
        from plugins.public_cmds import user_settings_callback
        callback_query.data = "user_general_settings_menu"
        await user_settings_callback(client, callback_query)

    # --- Language selection menu ---
    elif data == "pref_lang_menu":
        await callback_query.answer()
        current_lang = user_settings.get("preferred_language", "en-US") if user_settings else "en-US"
        text = (
            "**🌐 Select TMDb Language**\n\n"
            "> This language is used for movie/series metadata.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Current:** `{current_lang}`"
        )
        buttons = []
        row = []
        for code, name in LANGUAGES:
            mark = "✅ " if code == current_lang else ""
            row.append(InlineKeyboardButton(f"{mark}{name}", callback_data=f"pref_set_lang_{code}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("← Back", callback_data="pref_back")])
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass

    # --- Language selection ---
    elif data.startswith("pref_set_lang_"):
        lang_code = data.removeprefix("pref_set_lang_")
        await db.update_preferred_language(lang_code, user_id)
        await callback_query.answer("Language updated!")
        await render_user_preferences_inline(client, user_id, callback_query.message)

    # --- Thumbnail mode menu ---
    elif data == "pref_thumb_menu":
        await callback_query.answer()
        current_thumb = user_settings.get("thumbnail_mode", "none") if user_settings else "none"
        text = (
            "**🖼️ Default Thumbnail Mode**\n\n"
            "> Choose how thumbnails are handled.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "**❌ None** — No thumbnail attached\n"
            "**🤖 Auto** — Auto-fetch from TMDb\n"
            "**🖼️ Custom** — Use your uploaded thumbnail"
        )
        buttons = []
        for code, name in THUMB_MODES:
            mark = "✅ " if code == current_thumb else ""
            buttons.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"pref_set_thumb_{code}")])
        buttons.append([InlineKeyboardButton("← Back", callback_data="pref_back")])
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass

    # --- Thumbnail mode selection ---
    elif data.startswith("pref_set_thumb_"):
        mode = data.removeprefix("pref_set_thumb_")
        await db.update_setting("thumbnail_mode", mode, user_id)
        await callback_query.answer("Thumbnail mode updated!")
        await render_user_preferences_inline(client, user_id, callback_query.message)

    # --- Back to main preferences view ---
    elif data == "pref_back":
        await callback_query.answer()
        await render_user_preferences_inline(client, user_id, callback_query.message)


# ---------------------------------------------------------------------------
# Smart Swap (unchanged logic)
# ---------------------------------------------------------------------------

async def track_tool_usage(user_id, tool_id):
    """Increments usage counter for a specific tool. Used for Smart Swap."""
    user_settings = await db.get_settings(user_id)
    if not user_settings:
        return
    usage_stats = user_settings.get("tool_usage_stats", {})
    usage_stats[tool_id] = usage_stats.get(tool_id, 0) + 1
    await db.update_setting("tool_usage_stats", usage_stats, user_id)


async def perform_smart_swap_if_needed(user_id):
    user_settings = await db.get_settings(user_id)
    if not user_settings:
        return

    stats = user_settings.get("tool_usage_stats", {})
    selected = user_settings.get("start_menu_tools", ["rename"])

    if not stats or not selected:
        return

    unselected_usage = {k: v for k, v in stats.items() if k not in selected}
    selected_usage = {k: v for k, v in stats.items() if k in selected}

    if not unselected_usage or not selected_usage:
        return

    most_used_unselected = max(unselected_usage, key=unselected_usage.get)
    max_unsel_count = unselected_usage[most_used_unselected]

    least_used_selected = min(selected_usage, key=selected_usage.get)
    min_sel_count = selected_usage[least_used_selected]

    if max_unsel_count > 10 and max_unsel_count > (min_sel_count * 3):
        selected.remove(least_used_selected)
        selected.append(most_used_unselected)
        await db.update_setting("start_menu_tools", selected, user_id)
        logger.info(f"Smart swapped tools for {user_id}: {least_used_selected} -> {most_used_unselected}")
