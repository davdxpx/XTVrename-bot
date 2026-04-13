from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from config import Config
from utils.log import get_logger

logger = get_logger("plugins.user_setup")

async def send_user_tool_preferences_setup(client, user_id, message_or_query):
    # Retrieve toggles
    toggles = await db.get_feature_toggles()

    pf = {}
    if Config.PUBLIC_MODE:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                pf = plan_settings.get("features", {})

    available_tools = []
    # Always available
    available_tools.append({"id": "rename", "name": "📁 Rename / Tag Media"})

    # Feature available = global toggle ON AND (per-plan toggle ON or global default)
    def _is_available(feat_key):
        global_on = toggles.get(feat_key, True)
        plan_on = pf.get(feat_key, True) if pf else True
        return global_on and plan_on

    if _is_available("audio_editor"):
        available_tools.append({"id": "audio_editor", "name": "🎵 Audio Editor"})
    if _is_available("file_converter"):
        available_tools.append({"id": "file_converter", "name": "🔀 File Converter"})
    if _is_available("watermarker"):
        available_tools.append({"id": "watermarker", "name": "©️ Watermarker"})
    if _is_available("subtitle_extractor"):
        available_tools.append({"id": "subtitle_extractor", "name": "📝 Subtitle Extractor"})
    if _is_available("video_trimmer"):
        available_tools.append({"id": "video_trimmer", "name": "✂️ Video Trimmer"})
    if _is_available("media_info"):
        available_tools.append({"id": "media_info", "name": "ℹ️ Media Info"})
    if _is_available("voice_converter"):
        available_tools.append({"id": "voice_converter", "name": "🎙️ Voice Converter"})
    if _is_available("video_note_converter"):
        available_tools.append({"id": "video_note_converter", "name": "⭕ Video Note Converter"})

    user_settings = await db.get_settings(user_id)
    selected_tools = user_settings.get("start_menu_tools", ["rename"]) if user_settings else ["rename"]

    text = (
        "⚙️ **Personalize Your Menu**\n\n"
        "What tools do you plan to use the most?\n"
        "Select up to **3 features** to pin them directly to your `/start` menu for quick access.\n"
        "__(The rest will be inside the 'Other Features' button)__"
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

    buttons.append([InlineKeyboardButton("Finish Setup ➡️", callback_data="pref_finish")])

    if hasattr(message_or_query, "answer"):
        # Is callback query
        await message_or_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        # Is message
        await message_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^pref_"))
async def handle_user_preferences(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    user_settings = await db.get_settings(user_id)
    selected_tools = user_settings.get("start_menu_tools", ["rename"]) if user_settings else ["rename"]

    if data.startswith("pref_toggle_"):
        tool_id = data.replace("pref_toggle_", "")

        if tool_id in selected_tools:
            selected_tools.remove(tool_id)
        else:
            if len(selected_tools) >= 3:
                await callback_query.answer("You can only select up to 3 tools!", show_alert=True)
                return
            selected_tools.append(tool_id)

        await db.update_setting("start_menu_tools", selected_tools, user_id)
        await send_user_tool_preferences_setup(client, user_id, callback_query)

    elif data == "pref_finish":
        await db.update_setting("has_completed_preferences", True, user_id)
        await callback_query.answer("Preferences Saved!", show_alert=False)
        await callback_query.message.delete()
        # Trigger standard start menu by passing message-like object to start handler
        from plugins.start import handle_start_command_unique

        class FakeMessage:
            def __init__(self, from_user, text):
                self.from_user = from_user
                self.text = text

            async def reply_text(self, *args, **kwargs):
                return await client.send_message(user_id, *args, **kwargs)

        await handle_start_command_unique(client, FakeMessage(callback_query.from_user, "/start"))

    elif data == "pref_finish_return":
        await callback_query.answer("Preferences Saved!", show_alert=False)
        from plugins.public_cmds import user_settings_callback
        callback_query.data = "user_general_settings_menu"
        await user_settings_callback(client, callback_query)

async def track_tool_usage(user_id, tool_id):
    """
    Increments usage counter for a specific tool.
    Used for 'Smart Swap' logic.
    """
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

    # Unselected tools and their usage
    unselected_usage = {k: v for k, v in stats.items() if k not in selected}
    selected_usage = {k: v for k, v in stats.items() if k in selected}

    if not unselected_usage or not selected_usage:
        return

    # Find most used unselected tool
    most_used_unselected = max(unselected_usage, key=unselected_usage.get)
    max_unsel_count = unselected_usage[most_used_unselected]

    # Find least used selected tool
    least_used_selected = min(selected_usage, key=selected_usage.get)
    min_sel_count = selected_usage[least_used_selected]

    # Swap criteria: Unselected has been used more than 10 times, and is used at least 3 times more than the least used selected
    if max_unsel_count > 10 and max_unsel_count > (min_sel_count * 3):
        # Swap
        selected.remove(least_used_selected)
        selected.append(most_used_unselected)
        await db.update_setting("start_menu_tools", selected, user_id)
        logger.info(f"Smart swapped tools for {user_id}: {least_used_selected} -> {most_used_unselected}")
