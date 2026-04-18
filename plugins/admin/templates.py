# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Templates admin domain.

Covers metadata templates, filename templates, caption template,
preferred separator — every callback reachable from the Templates
submenu in the admin panel.

The menu builder `get_admin_templates_menu` also lives here so layout
stays close to its handlers.

Text-input flows (`awaiting_template_*`, `awaiting_fn_template_*`,
`awaiting_caption`) are registered with the shared ``text_dispatcher``
and routed here at runtime.
"""

import contextlib

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin


def get_admin_templates_menu():
    return InlineKeyboardMarkup(
        [
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
                    "📝 Edit Metadata Templates", callback_data="admin_templates"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔤 Preferred Separator", callback_data="admin_pref_separator"
                )
            ],
            [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
        ]
    )


@Client.on_callback_query(
    filters.regex(
        r"^(admin_templates_menu$|admin_templates$|admin_caption$"
        r"|admin_filename_templates$|admin_fn_templates_(?:personal|subtitles)$"
        r"|admin_pref_separator$|admin_set_sep_"
        r"|edit_template_|edit_fn_template_"
        r"|prompt_fn_template_|prompt_template_|prompt_admin_caption$)"
    )
)
async def templates_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    # --- Templates menu ---
    if data == "admin_templates_menu":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📋 **Templates Menu**\n\nSelect a template category to edit:",
                reply_markup=get_admin_templates_menu(),
            )
        return

    # --- Preferred separator ---
    if data == "admin_pref_separator":
        await callback_query.answer()
        try:
            current_sep = await db.get_preferred_separator(user_id)
            sep_display = "Space" if current_sep == " " else current_sep
            await callback_query.message.edit_text(
                f"🔤 **Preferred Separator**\n\n"
                f"Choose the separator used when cleaning up filename templates.\n"
                f"Current: **{sep_display}**\n\n"
                f"Select your preferred separator below:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Dot (.)", callback_data="admin_set_sep_."),
                            InlineKeyboardButton("Underscore (_)", callback_data="admin_set_sep__"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="admin_set_sep_space"),
                        ],
                        [InlineKeyboardButton("← Back to Templates", callback_data="admin_templates_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data.startswith("admin_set_sep_"):
        try:
            new_sep = data.split("_set_sep_")[1]
            if new_sep == "space":
                new_sep = " "
            await db.update_preferred_separator(new_sep, user_id)
            sep_display = "Space" if new_sep == " " else new_sep
            await callback_query.answer(f"Separator set to: {sep_display}", show_alert=True)
            await callback_query.message.edit_text(
                f"🔤 **Preferred Separator**\n\n"
                f"Choose the separator used when cleaning up filename templates.\n"
                f"Current: **{sep_display}**\n\n"
                f"Select your preferred separator below:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Dot (.)", callback_data="admin_set_sep_."),
                            InlineKeyboardButton("Underscore (_)", callback_data="admin_set_sep__"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="admin_set_sep_space"),
                        ],
                        [InlineKeyboardButton("← Back to Templates", callback_data="admin_templates_menu")],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Metadata templates list ---
    if data == "admin_templates":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📝 **Edit Metadata Templates**\n\nSelect a field to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Title", callback_data="edit_template_title"),
                            InlineKeyboardButton("Author", callback_data="edit_template_author"),
                        ],
                        [
                            InlineKeyboardButton("Artist", callback_data="edit_template_artist"),
                            InlineKeyboardButton("Video", callback_data="edit_template_video"),
                        ],
                        [
                            InlineKeyboardButton("Audio", callback_data="edit_template_audio"),
                            InlineKeyboardButton("Subtitle", callback_data="edit_template_subtitle"),
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Templates", callback_data="admin_templates_menu"
                            )
                        ],
                    ]
                ),
            )
        return

    # --- Caption template ---
    if data == "admin_caption":
        await callback_query.answer()
        templates = await db.get_all_templates()
        current_caption = templates.get("caption", "{random}")
        with contextlib.suppress(MessageNotModified):
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
                        [
                            InlineKeyboardButton(
                                "← Back to Templates", callback_data="admin_templates_menu"
                            )
                        ],
                    ]
                ),
            )
        return

    if data == "prompt_admin_caption":
        admin_sessions[user_id] = {
            "state": "awaiting_template_caption",
            "msg_id": callback_query.message.id,
        }
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📝 **Send the new caption text:**\n\n"
                "(Use `{random}` to use the default random text generator)",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="admin_templates_menu"
                            )
                        ]
                    ]
                ),
            )
        return

    # --- Filename templates ---
    if data == "admin_filename_templates":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📝 **Edit Filename Templates**\n\nSelect media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Movies", callback_data="edit_fn_template_movies")],
                        [InlineKeyboardButton("Series", callback_data="edit_fn_template_series")],
                        [InlineKeyboardButton("Personal", callback_data="admin_fn_templates_personal")],
                        [InlineKeyboardButton("Subtitles", callback_data="admin_fn_templates_subtitles")],
                        [
                            InlineKeyboardButton(
                                "← Back to Templates", callback_data="admin_templates_menu"
                            )
                        ],
                    ]
                ),
            )
        return

    if data == "admin_fn_templates_personal":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📝 **Edit Personal Filename Templates**\n\nSelect media type to edit:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Personal Files", callback_data="edit_fn_template_personal_file"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal Photos", callback_data="edit_fn_template_personal_photo"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Personal Videos", callback_data="edit_fn_template_personal_video"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Filename Templates",
                                callback_data="admin_filename_templates",
                            )
                        ],
                    ]
                ),
            )
        return

    if data == "admin_fn_templates_subtitles":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📝 **Edit Subtitles Filename Templates**\n\nSelect media type to edit:",
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
        return

    # --- Individual filename template view ---
    if data.startswith("edit_fn_template_"):
        await callback_query.answer()
        field = data.replace("edit_fn_template_", "")
        # Invalidate so the admin view always reflects the latest DB state,
        # not a stale 60s-cache value. Cheap no-op when cache is empty.
        db._invalidate_settings_cache()
        templates = await db.get_filename_templates()
        current_val = templates.get(field, "")
        # Config default for this key — shown when nothing custom is stored,
        # so the user can see "this is the fallback" vs. "this is really saved".
        default_val = Config.DEFAULT_FILENAME_TEMPLATES.get(field, "")
        try:
            if field.lower() in {"movies", "series", "subtitles_movies", "subtitles_series"}:
                vars_text = (
                    "`{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, "
                    "`{Season_Episode}`, `{Language}`, `{Channel}`, `{Specials}`, "
                    "`{Codec}`, `{Audio}`"
                )
            else:
                vars_text = (
                    "`{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, "
                    "`{Season_Episode}`, `{Language}`, `{Channel}`"
                )
            stored_line = (
                f"Current: `{current_val}`"
                if current_val
                else f"Current: _not set — using default_ `{default_val}`"
            )
            await callback_query.message.edit_text(
                f"✏️ **Edit Filename Template ({field.capitalize()})**\n\n"
                f"{stored_line}\n\n"
                f"Variables: {vars_text}\n"
                "Note: File extension will be added automatically.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data=f"prompt_fn_template_{field}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Filename Templates",
                                callback_data="admin_filename_templates",
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Prompt for filename template text ---
    if data.startswith("prompt_fn_template_"):
        field = data.replace("prompt_fn_template_", "")
        admin_sessions[user_id] = {
            "state": f"awaiting_fn_template_{field}",
            "msg_id": callback_query.message.id,
        }
        try:
            if field.lower() in {"movies", "series", "subtitles_movies", "subtitles_series"}:
                vars_text = (
                    "\n\nVariables: `{Title}`, `{Year}`, `{Quality}`, `{Season}`, "
                    "`{Episode}`, `{Season_Episode}`, `{Language}`, `{Channel}`, "
                    "`{Specials}`, `{Codec}`, `{Audio}`"
                )
            else:
                vars_text = (
                    "\n\nVariables: `{Title}`, `{Year}`, `{Quality}`, `{Season}`, "
                    "`{Episode}`, `{Season_Episode}`, `{Language}`, `{Channel}`"
                )
            await callback_query.message.edit_text(
                f"✏️ **Send the new filename template for {field.capitalize()}:**{vars_text}",
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
        except MessageNotModified:
            pass
        return

    # --- Individual metadata template view ---
    if data.startswith("edit_template_"):
        await callback_query.answer()
        field = data.split("_")[-1]
        templates = await db.get_all_templates()
        current_val = templates.get(field, "")
        with contextlib.suppress(MessageNotModified):
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
                        [
                            InlineKeyboardButton(
                                "← Back to Metadata Templates",
                                callback_data="admin_templates",
                            )
                        ],
                    ]
                ),
            )
        return

    # --- Prompt for metadata template text ---
    if data.startswith("prompt_template_"):
        field = data.replace("prompt_template_", "")
        admin_sessions[user_id] = {
            "state": f"awaiting_template_{field}",
            "msg_id": callback_query.message.id,
        }
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new template text for {field.capitalize()}:**",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="admin_templates"
                            )
                        ]
                    ]
                ),
            )
        return


# ---------------------------------------------------------------------------
# Text-input state handlers (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def _handle_template_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_template_* and awaiting_caption states."""
    user_id = message.from_user.id
    field = state.split("_")[-1]
    new_template = message.text
    await db.update_template(field, new_template)
    if field == "caption":
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to Templates", callback_data="admin_templates_menu")]]
        )
    else:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to Metadata Templates", callback_data="admin_templates")]]
        )
    await edit_or_reply(client, message, msg_id,
        f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`",
        reply_markup=reply_markup,
    )
    admin_sessions.pop(user_id, None)


async def _handle_fn_template_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_fn_template_* states."""
    user_id = message.from_user.id
    field = state.replace("awaiting_fn_template_", "")
    new_template = message.text
    await db.update_filename_template(field, new_template)
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back to Filename Templates", callback_data="admin_filename_templates")]]
    )
    await edit_or_reply(client, message, msg_id,
        f"✅ Filename template for **{field.capitalize()}** updated to:\n`{new_template}`",
        reply_markup=reply_markup,
    )
    admin_sessions.pop(user_id, None)


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_template_", _handle_template_text)
_register("awaiting_fn_template_", _handle_fn_template_text)
