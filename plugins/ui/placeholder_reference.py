# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Shared Placeholder Reference and Preview screens.

Every template-edit screen in the admin and user menus links here so
there's one place to document what ``{Title}``, ``{Rating}``, etc.
resolve to. The module is scope-aware: open it on ``filename_series``
and you only see the groups that scope allows (BASIC, EPISODE,
TECHNICAL, SOURCE, TMDB).

Callback scheme
---------------
``ph_ref_{origin}_{scope}_{group_key}`` — show the reference for one
group within a scope. ``origin`` is ``a`` (admin) or ``u`` (user) so
the Back button can return to the right parent menu.

``tpl_preview_{origin}_{scope}_{field}`` — render the current template
against ``SAMPLE_MAPPING`` so the user sees what it produces without
uploading a real file. ``field`` is the DB key of the template being
previewed (``movies``, ``system_filename_series``, ``caption``, …).

Back targets
------------
Admin origin returns to ``edit_fn_template_{field}`` /
``edit_template_{field}``; user origin returns to
``edit_user_fn_template_{field}`` / ``edit_user_template_{field}``.
The caller decides which scope maps to which field key, so this module
stays dumb about that mapping.
"""

from __future__ import annotations

import contextlib
from typing import Optional, Tuple

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from db import db
from plugins.admin.core import is_admin
from utils.template import (
    CATALOG,
    SCOPE_GROUPS,
    groups_for,
    placeholders_for,
    render_preview,
)


DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


# Field-key ↔ scope bridging ------------------------------------------------
#
# The Templates UI stores templates under a "field key" (``movies``,
# ``subtitles_series``, ``system_filename_movies``, ``caption``,
# ``title``/``author``/…). Each field key maps to exactly one scope in
# ``utils.template``. Centralising the mapping here means admin and user
# UIs reference the same table.

FIELD_TO_SCOPE = {
    # Filename templates (stored under settings.filename_templates.<key>)
    "movies":              "filename_movies",
    "series":              "filename_series",
    "subtitles_movies":    "filename_subs_movies",
    "subtitles_series":    "filename_subs_series",
    "personal_video":      "filename_personal_video",
    "personal_photo":      "filename_personal_photo",
    "personal_file":       "filename_personal_file",
    # System filename (stored under settings.templates.<key>)
    "system_filename_movies": "system_filename_movies",
    "system_filename_series": "system_filename_series",
    # Caption (stored under settings.templates.caption)
    "caption": "caption",
    # Metadata templates (stored under settings.templates.<key>)
    "title":       "metadata_title",
    "author":      "metadata_author",
    "artist":      "metadata_artist",
    "video":       "metadata_video",
    "audio":       "metadata_audio",
    "subtitle":    "metadata_subtitle",
    "comment":     "metadata_comment",
    "copyright":   "metadata_copyright",
    "description": "metadata_description",
    "genre":       "metadata_genre",
    "date":        "metadata_date",
    "album":       "metadata_album",
    "show":        "metadata_show",
    "network":     "metadata_network",
}


# Back-target construction --------------------------------------------------
#
# The admin and user Templates UIs store field keys in two families:
# filename_templates.<key> and templates.<key>. We reuse whichever
# callback already exists in the parent module so Back behaves naturally.

_FILENAME_KEYS = {
    "movies", "series",
    "subtitles_movies", "subtitles_series",
    "personal_video", "personal_photo", "personal_file",
    "system_filename_movies", "system_filename_series",
    "caption",
}


def _parent_callback(origin: str, field: str) -> str:
    """Return the callback_data that opens the edit screen for ``field``
    in the caller's menu family. Both existing admin/user UIs expose
    ``edit_fn_template_{field}`` for filename-family keys and
    ``edit_template_{field}`` for metadata-family keys; the user UI
    prefixes with ``user_``."""
    prefix = "" if origin == "a" else "user_"
    if field in _FILENAME_KEYS:
        return f"{prefix}edit_fn_template_{field}"
    return f"{prefix}edit_template_{field}"


def _fmt_placeholder_line(ph) -> str:
    # Each placeholder rendered as: `{Name}` — description — `example`
    return f"`{{{ph.name}}}` — {ph.description} — `{ph.example}`"


def _build_group_row(scope: str, origin: str, field: str, active: str) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    for group in groups_for(scope):
        label = group.emoji + " " + group.title
        if group.key == active:
            label = f"· {label} ·"
        row.append(
            InlineKeyboardButton(
                label,
                callback_data=f"ph_ref_{origin}_{field}_{group.key}",
            )
        )
    return row


def _chunk_rows(buttons: list[InlineKeyboardButton], per_row: int = 3) -> list[list[InlineKeyboardButton]]:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def render_reference(field: str, group_key: str, origin: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Build the Placeholder Reference screen text + keyboard.

    Callers pass the DB ``field`` (e.g. ``"series"`` or ``"caption"``)
    rather than the internal scope name so they don't have to know the
    mapping.
    """
    scope = FIELD_TO_SCOPE.get(field)
    if scope is None:
        return "❌ Unknown template field.", InlineKeyboardMarkup([[
            InlineKeyboardButton("← Back", callback_data=_parent_callback(origin, field))
        ]])

    # Fall back to the first allowed group if the caller's group isn't
    # in scope (deep-link URLs can go stale after scope edits).
    allowed_groups = SCOPE_GROUPS[scope]
    if group_key not in allowed_groups:
        group_key = allowed_groups[0]

    group = CATALOG[group_key]
    phs = placeholders_for(scope, group_key)

    title_line = f"📖 **Placeholders — {group.title}**"
    body_lines = [_fmt_placeholder_line(p) for p in phs] or [
        "_No placeholders in this group for this template._"
    ]
    total = len(allowed_groups)
    current_idx = allowed_groups.index(group_key) + 1

    text_lines = [
        title_line,
        DIVIDER,
        "",
        *body_lines,
        "",
        f"> Placeholders resolve to an empty string when unavailable (e.g. no TMDb match, subtitle without probe).",
        "",
        f"Group {current_idx} of {total}",
    ]
    text = "\n".join(text_lines)

    group_buttons = _build_group_row(scope, origin, field, group_key)
    rows: list[list[InlineKeyboardButton]] = []
    rows.extend(_chunk_rows(group_buttons, per_row=3))
    rows.append([
        InlineKeyboardButton(
            "👁 Preview",
            callback_data=f"tpl_preview_{origin}_{field}",
        )
    ])
    rows.append([
        InlineKeyboardButton(
            "← Back to Edit Template",
            callback_data=_parent_callback(origin, field),
        )
    ])
    return text, InlineKeyboardMarkup(rows)


# Preview -------------------------------------------------------------------


async def _current_template(field: str, user_id: int, origin: str) -> Optional[str]:
    """Fetch the current template text for ``field``. Admin origin reads
    the global settings doc; user origin reads the caller's per-user
    doc. Returns ``None`` when nothing is set — the preview falls back
    to the scope's default.
    """
    # Admin = global scope (user_id=None); user = caller's id.
    scope_user = None if origin == "a" else user_id
    if field in {
        "movies", "series", "subtitles_movies", "subtitles_series",
        "personal_video", "personal_photo", "personal_file",
    }:
        fn_templates = await db.get_filename_templates(scope_user)
        return fn_templates.get(field) if fn_templates else None
    if field == "system_filename_movies":
        return await db.get_system_filename_template("movie", scope_user)
    if field == "system_filename_series":
        return await db.get_system_filename_template("series", scope_user)
    templates = await db.get_all_templates(scope_user)
    return templates.get(field)


def render_preview_screen(field: str, origin: str, current: Optional[str]) -> Tuple[str, InlineKeyboardMarkup]:
    scope = FIELD_TO_SCOPE.get(field)
    label = field.replace("_", " ").title()

    if scope is None or not current:
        text = (
            f"👁 **Preview — {label}**\n"
            f"{DIVIDER}\n\n"
            "_No template set — showing the default render._\n"
        )
        rendered = ""
    else:
        rendered = render_preview(scope, current)
        text = (
            f"👁 **Preview — {label}**\n"
            f"{DIVIDER}\n\n"
            f"Template:\n`{current}`\n\n"
            f"Result (sample: Fallout S01E01, 1080p):\n`{rendered or '—'}`\n\n"
            "> Placeholders that have no value for this sample resolve to empty."
        )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "← Back to Edit Template",
            callback_data=_parent_callback(origin, field),
        )
    ]])
    return text, kb


# Callback handlers ---------------------------------------------------------


@Client.on_callback_query(filters.regex(r"^ph_ref_[au]_"))
async def _reference_cb(client, callback_query: CallbackQuery):
    data = callback_query.data
    # ph_ref_{origin}_{field}_{group_key} — field may contain underscores.
    # Strip the prefix, split off origin and group_key, the rest is field.
    try:
        _, _, origin, rest = data.split("_", 3)
        field, _, group_key = rest.rpartition("_")
    except ValueError:
        await callback_query.answer("Invalid reference link.", show_alert=True)
        return
    if not field or not group_key:
        await callback_query.answer("Invalid reference link.", show_alert=True)
        return
    if origin == "a" and not is_admin(callback_query.from_user.id):
        raise ContinuePropagation
    await callback_query.answer()
    text, kb = render_reference(field, group_key, origin)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^tpl_preview_[au]_"))
async def _preview_cb(client, callback_query: CallbackQuery):
    data = callback_query.data
    try:
        _, _, origin, field = data.split("_", 3)
    except ValueError:
        await callback_query.answer("Invalid preview link.", show_alert=True)
        return
    if not field:
        await callback_query.answer("Invalid preview link.", show_alert=True)
        return
    if origin == "a" and not is_admin(callback_query.from_user.id):
        raise ContinuePropagation
    await callback_query.answer()
    current = await _current_template(field, callback_query.from_user.id, origin)
    text, kb = render_preview_screen(field, origin, current)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


def reference_and_preview_buttons(field: str, origin: str) -> list[list[InlineKeyboardButton]]:
    """Convenience for edit screens — two rows of action buttons pointing
    at this module's handlers. Caller is responsible for appending their
    own Back and Cancel buttons."""
    scope = FIELD_TO_SCOPE.get(field)
    if scope is None:
        return []
    first_group = SCOPE_GROUPS[scope][0]
    return [
        [
            InlineKeyboardButton(
                "📖 Placeholder Reference",
                callback_data=f"ph_ref_{origin}_{field}_{first_group}",
            ),
            InlineKeyboardButton(
                "👁 Preview",
                callback_data=f"tpl_preview_{origin}_{field}",
            ),
        ],
    ]
