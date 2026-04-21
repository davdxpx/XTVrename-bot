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
from db import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin
from plugins.ui.placeholder_reference import (
    FIELD_TO_SCOPE,
    reference_and_preview_buttons,
)
from utils.template import (
    SCOPE_TOP_HINTS,
    allowed_fields_for,
    validate_template,
)

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"

# Which DB keys are filename-family (stored under settings.filename_templates)
# vs system-filename (stored under settings.templates.system_filename_*).
# Callback routing and text handlers branch on this set.
_FILENAME_FAMILY_KEYS = {
    "movies", "series",
    "subtitles_movies", "subtitles_series",
    "personal_video", "personal_photo", "personal_file",
}
_SYS_FILENAME_KEYS = {"system_filename_movies", "system_filename_series"}
_METADATA_KEYS = {
    "title", "author", "artist", "video", "audio", "subtitle",
    "comment", "copyright", "description", "genre", "date",
    "album", "show", "network",
}


def _vars_line(scope: str) -> str:
    """Build the compact `Variables:` line for an edit screen. Pulls
    the curated top hints from the catalogue so the scope sees its
    most-useful placeholders first."""
    hints = SCOPE_TOP_HINTS.get(scope, ())
    return ", ".join(f"`{{{h}}}`" for h in hints)


def _ref_and_preview(field: str):
    """Two-button row with 📖 Placeholder Reference + 👁 Preview for
    admin origin. Returns an empty list when the field has no scope."""
    return reference_and_preview_buttons(field, origin="a")


async def _legacy_sys_banner_line() -> str:
    """Return the one-line legacy-system-filename banner, or an empty
    string if the admin has already overridden at least one split key.
    Placed at the top of the Filename Templates submenu so operators
    know their old template still applies to both media types.
    """
    templates = await db.get_all_templates()
    legacy = templates.get("system_filename")
    has_new = bool(templates.get("system_filename_movies") or templates.get("system_filename_series"))
    if legacy and not has_new:
        return (
            "ℹ️ **System Filename was split into Movies/Series.**\n"
            "Your existing template still applies to both until you override either.\n\n"
        )
    return ""


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
        r"^(admin_templates_menu$|admin_templates$|admin_templates_meta2$|admin_caption$"
        r"|admin_filename_templates$|admin_fn_templates_(?:personal|subtitles|system)$"
        r"|admin_pref_separator$|admin_set_sep_"
        r"|edit_template_|edit_fn_template_|edit_sys_template_"
        r"|prompt_fn_template_|prompt_template_|prompt_sys_template_"
        r"|prompt_admin_caption$)"
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

    # --- Metadata templates list (page 1 of 2) ---
    if data == "admin_templates":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit Metadata Templates**\n"
                f"{DIVIDER}\n\n"
                "Select a field to edit.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✏️ Title",   callback_data="edit_template_title"),
                            InlineKeyboardButton("✏️ Author",  callback_data="edit_template_author"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Artist",  callback_data="edit_template_artist"),
                            InlineKeyboardButton("✏️ Video",   callback_data="edit_template_video"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Audio",   callback_data="edit_template_audio"),
                            InlineKeyboardButton("✏️ Subtitle",callback_data="edit_template_subtitle"),
                        ],
                        [
                            InlineKeyboardButton("➡ More metadata fields", callback_data="admin_templates_meta2"),
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

    # --- Metadata templates list (page 2 of 2) — new keys from the upgrade ---
    if data == "admin_templates_meta2":
        await callback_query.answer()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit Metadata Templates**\n"
                f"{DIVIDER}\n\n"
                "Extended metadata tags written to the output file.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✏️ Comment",    callback_data="edit_template_comment"),
                            InlineKeyboardButton("✏️ Copyright",  callback_data="edit_template_copyright"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Description",callback_data="edit_template_description"),
                            InlineKeyboardButton("✏️ Genre",      callback_data="edit_template_genre"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Date",       callback_data="edit_template_date"),
                            InlineKeyboardButton("✏️ Album",      callback_data="edit_template_album"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Show",       callback_data="edit_template_show"),
                            InlineKeyboardButton("✏️ Network",    callback_data="edit_template_network"),
                        ],
                        [
                            InlineKeyboardButton("← Back", callback_data="admin_templates"),
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
        vars_line = _vars_line("caption")
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data="prompt_admin_caption")],
        ]
        rows.extend(_ref_and_preview("caption"))
        rows.append([
            InlineKeyboardButton(
                "← Back to Templates", callback_data="admin_templates_menu"
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"🧾 **Edit Caption Template**\n"
                f"{DIVIDER}\n\n"
                f"Current: `{current_caption}`\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.\n\n"
                "> Send just `{random}` to keep the default anti-hash behaviour.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        return

    if data == "prompt_admin_caption":
        admin_sessions[user_id] = {
            "state": "awaiting_template_caption",
            "msg_id": callback_query.message.id,
        }
        vars_line = _vars_line("caption")
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new caption template:**\n"
                f"{DIVIDER}\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.\n\n"
                "> Use `{random}` alone to keep the default anti-hash text generator.",
                reply_markup=InlineKeyboardMarkup(
                    _ref_and_preview("caption")
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="admin_templates_menu")]]
                ),
            )
        return

    # --- Filename templates (flat layout with system split + caption) ---
    if data == "admin_filename_templates":
        await callback_query.answer()
        banner = await _legacy_sys_banner_line()
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Filename Templates**\n"
                f"{DIVIDER}\n\n"
                f"{banner}"
                "Select a template to edit.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🎬 Movies",      callback_data="edit_fn_template_movies"),
                            InlineKeyboardButton("📺 Series",      callback_data="edit_fn_template_series"),
                        ],
                        [
                            InlineKeyboardButton("🎬 Movies Subs", callback_data="edit_fn_template_subtitles_movies"),
                            InlineKeyboardButton("📺 Series Subs", callback_data="edit_fn_template_subtitles_series"),
                        ],
                        [
                            InlineKeyboardButton("🎞 Personal Video", callback_data="edit_fn_template_personal_video"),
                            InlineKeyboardButton("🖼 Personal Photo", callback_data="edit_fn_template_personal_photo"),
                            InlineKeyboardButton("📁 Personal File",  callback_data="edit_fn_template_personal_file"),
                        ],
                        [
                            InlineKeyboardButton("⚙️ System (Movies)", callback_data="edit_sys_template_movies"),
                            InlineKeyboardButton("⚙️ System (Series)", callback_data="edit_sys_template_series"),
                        ],
                        [
                            InlineKeyboardButton("🧾 Caption", callback_data="admin_caption"),
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

    # --- Individual filename template view ---
    if data.startswith("edit_fn_template_"):
        await callback_query.answer()
        field = data.replace("edit_fn_template_", "")
        scope = FIELD_TO_SCOPE.get(field)
        if scope is None:
            await callback_query.answer("Unknown template field.", show_alert=True)
            return
        # Invalidate so the admin view always reflects the latest DB state.
        db._invalidate_settings_cache()
        templates = await db.get_filename_templates()
        current_val = templates.get(field, "")
        default_val = Config.DEFAULT_FILENAME_TEMPLATES.get(field, "")
        stored_line = (
            f"Current: `{current_val}`"
            if current_val
            else f"Current: __not set — using default__ `{default_val}`"
        )
        vars_line = _vars_line(scope)
        label = field.replace("_", " ").title()
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_fn_template_{field}")],
        ]
        rows.extend(_ref_and_preview(field))
        rows.append([
            InlineKeyboardButton(
                "← Back to Filename Templates",
                callback_data="admin_filename_templates",
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit Filename Template — {label}**\n"
                f"{DIVIDER}\n\n"
                f"{stored_line}\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.\n\n"
                "Note: File extension is added automatically.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        return

    # --- Prompt for filename template text ---
    if data.startswith("prompt_fn_template_"):
        field = data.replace("prompt_fn_template_", "")
        scope = FIELD_TO_SCOPE.get(field)
        admin_sessions[user_id] = {
            "state": f"awaiting_fn_template_{field}",
            "msg_id": callback_query.message.id,
        }
        vars_line = _vars_line(scope) if scope else ""
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new filename template for {field.replace('_', ' ').title()}:**\n"
                f"{DIVIDER}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    (_ref_and_preview(field) if scope else [])
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="admin_filename_templates")]]
                ),
            )
        return

    # --- Individual system-filename template view ---
    if data.startswith("edit_sys_template_"):
        await callback_query.answer()
        sub = data.replace("edit_sys_template_", "")
        field = f"system_filename_{sub}" if sub in ("movies", "series") else sub
        scope = FIELD_TO_SCOPE.get(field)
        if scope is None:
            await callback_query.answer("Unknown system filename key.", show_alert=True)
            return
        db._invalidate_settings_cache()
        templates = await db.get_all_templates()
        current_val = templates.get(field) or templates.get("system_filename", "")
        default_val = (
            Config.DEFAULT_SYSTEM_FILENAME_SERIES
            if sub == "series"
            else Config.DEFAULT_SYSTEM_FILENAME_MOVIES
        )
        stored_line = (
            f"Current: `{current_val}`"
            if current_val
            else f"Current: __not set — using default__ `{default_val}`"
        )
        vars_line = _vars_line(scope)
        label = "System Filename — " + ("Series" if sub == "series" else "Movies")
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_sys_template_{sub}")],
        ]
        rows.extend(_ref_and_preview(field))
        rows.append([
            InlineKeyboardButton(
                "← Back to Filename Templates",
                callback_data="admin_filename_templates",
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"⚙️ **Edit {label}**\n"
                f"{DIVIDER}\n\n"
                f"{stored_line}\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        return

    if data.startswith("prompt_sys_template_"):
        sub = data.replace("prompt_sys_template_", "")
        if sub not in ("movies", "series"):
            return
        field = f"system_filename_{sub}"
        scope = FIELD_TO_SCOPE.get(field)
        admin_sessions[user_id] = {
            "state": f"awaiting_sys_template_{sub}",
            "msg_id": callback_query.message.id,
        }
        vars_line = _vars_line(scope) if scope else ""
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new system filename template for "
                f"{'Series' if sub == 'series' else 'Movies'}:**\n"
                f"{DIVIDER}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    (_ref_and_preview(field) if scope else [])
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="admin_filename_templates")]]
                ),
            )
        return

    # --- Individual metadata template view ---
    if data.startswith("edit_template_"):
        await callback_query.answer()
        field = data.replace("edit_template_", "")
        if field not in _METADATA_KEYS:
            await callback_query.answer("Unknown metadata template.", show_alert=True)
            return
        scope = FIELD_TO_SCOPE.get(field)
        templates = await db.get_all_templates()
        current_val = templates.get(field, "")
        default_val = Config.DEFAULT_TEMPLATES.get(field, "")
        stored_line = (
            f"Current: `{current_val}`"
            if current_val
            else f"Current: __not set — using default__ `{default_val}`"
        )
        vars_line = _vars_line(scope) if scope else ""
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_template_{field}")],
        ]
        rows.extend(_ref_and_preview(field))
        rows.append([
            InlineKeyboardButton(
                "← Back to Metadata Templates",
                callback_data="admin_templates",
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit {field.capitalize()} Metadata Template**\n"
                f"{DIVIDER}\n\n"
                f"{stored_line}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        return

    # --- Prompt for metadata template text ---
    if data.startswith("prompt_template_"):
        field = data.replace("prompt_template_", "")
        if field not in _METADATA_KEYS:
            return
        scope = FIELD_TO_SCOPE.get(field)
        admin_sessions[user_id] = {
            "state": f"awaiting_template_{field}",
            "msg_id": callback_query.message.id,
        }
        vars_line = _vars_line(scope) if scope else ""
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new template text for {field.capitalize()}:**\n"
                f"{DIVIDER}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    (_ref_and_preview(field) if scope else [])
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="admin_templates")]]
                ),
            )
        return


# ---------------------------------------------------------------------------
# Text-input state handlers (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def _handle_template_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_template_* and awaiting_caption states."""
    user_id = message.from_user.id
    field = state.replace("awaiting_template_", "")
    new_template = message.text or ""

    # Resolve the scope once so validation, error messages, and the
    # Placeholder Reference button all speak the same language.
    scope = FIELD_TO_SCOPE.get(field)
    if scope is None:
        await message.reply_text(f"❌ Unknown template field: `{field}`.")
        return

    allowed = set(allowed_fields_for(scope))
    ok, err = validate_template(new_template, allowed_fields=allowed)
    if not ok:
        await message.reply_text(
            f"❌ **Invalid template**\n"
            f"{DIVIDER}\n\n{err}\n\n"
            f"You sent:\n`{new_template}`\n\n"
            "Tap 📖 below for the full list.",
            reply_markup=InlineKeyboardMarkup(
                reference_and_preview_buttons(field, origin="a")
                + [[InlineKeyboardButton("❌ Cancel", callback_data="admin_templates")]]
            ),
        )
        return

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
        f"✅ **Template for {field.capitalize()} updated**\n"
        f"{DIVIDER}\n\n`{new_template}`",
        reply_markup=reply_markup,
    )
    admin_sessions.pop(user_id, None)


async def _handle_fn_template_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_fn_template_* states."""
    user_id = message.from_user.id
    field = state.replace("awaiting_fn_template_", "")
    new_template = message.text or ""

    scope = FIELD_TO_SCOPE.get(field)
    if scope is None:
        await message.reply_text(f"❌ Unknown filename template field: `{field}`.")
        return

    allowed = set(allowed_fields_for(scope))
    ok, err = validate_template(new_template, allowed_fields=allowed)
    if not ok:
        await message.reply_text(
            f"❌ **Invalid filename template**\n"
            f"{DIVIDER}\n\n{err}\n\n"
            f"You sent:\n`{new_template}`\n\n"
            "Tap 📖 below for the full list.",
            reply_markup=InlineKeyboardMarkup(
                reference_and_preview_buttons(field, origin="a")
                + [[InlineKeyboardButton("❌ Cancel", callback_data="admin_filename_templates")]]
            ),
        )
        return

    await db.update_filename_template(field, new_template)
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back to Filename Templates", callback_data="admin_filename_templates")]]
    )
    await edit_or_reply(client, message, msg_id,
        f"✅ **Filename template for {field.replace('_', ' ').title()} updated**\n"
        f"{DIVIDER}\n\n`{new_template}`",
        reply_markup=reply_markup,
    )
    admin_sessions.pop(user_id, None)


async def _handle_sys_template_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_sys_template_{movies,series} — writes to
    settings.templates.system_filename_{movies,series}.
    """
    user_id = message.from_user.id
    sub = state.replace("awaiting_sys_template_", "")
    if sub not in ("movies", "series"):
        return
    field = f"system_filename_{sub}"
    new_template = message.text or ""

    scope = FIELD_TO_SCOPE[field]
    allowed = set(allowed_fields_for(scope))
    ok, err = validate_template(new_template, allowed_fields=allowed)
    if not ok:
        await message.reply_text(
            f"❌ **Invalid system filename template**\n"
            f"{DIVIDER}\n\n{err}\n\n"
            f"You sent:\n`{new_template}`\n\n"
            "Tap 📖 below for the full list.",
            reply_markup=InlineKeyboardMarkup(
                reference_and_preview_buttons(field, origin="a")
                + [[InlineKeyboardButton("❌ Cancel", callback_data="admin_filename_templates")]]
            ),
        )
        return

    await db.update_template(field, new_template)
    label = "Series" if sub == "series" else "Movies"
    await edit_or_reply(client, message, msg_id,
        f"✅ **System Filename ({label}) updated**\n"
        f"{DIVIDER}\n\n`{new_template}`",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to Filename Templates", callback_data="admin_filename_templates")]]
        ),
    )
    admin_sessions.pop(user_id, None)


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_template_", _handle_template_text)
_register("awaiting_fn_template_", _handle_fn_template_text)
_register("awaiting_sys_template_", _handle_sys_template_text)
