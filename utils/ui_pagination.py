# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Reusable inline-keyboard pagination helper.

The rename-flow picker screens (codec / audio / specials) have grown
well past the point where every label fits on one screen, and the
myfiles list has had its own bespoke paginator for a while. This
module centralises the pattern so new pickers don't have to re-invent
it.

Typical use
-----------
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from utils.ui_pagination import paginate_kb, PAGE_THRESHOLD

    items = [("x264", "x264"), ("x265", "x265"), ...]
    rows = paginate_kb(
        items=items,
        page=current_page,
        per_page=9,
        per_row=3,
        label_for=lambda key, label, selected: f"✅ {label}" if selected else label,
        selected={current_codec},
        cb_template=lambda key: f"set_codec_{key}_{msg_id}",
        page_cb_template=lambda p: f"codec_pg_{p}_{msg_id}",
        extra_rows=[[InlineKeyboardButton("← Back", callback_data=f"back_confirm_{msg_id}")]],
    )
    keyboard = InlineKeyboardMarkup(rows)

Only dependency is `pyrogram.types.InlineKeyboardButton`. If the caller
already knows it has fewer than `PAGE_THRESHOLD` items, it can skip
the page nav row by passing `per_page=len(items)` (or just not using
the helper at all).
"""

from __future__ import annotations

from typing import Callable, Iterable

from pyrogram.types import InlineKeyboardButton

#: Items above this count should page; below it, everything fits on
#: one screen and the nav row can safely be omitted by the caller.
PAGE_THRESHOLD = 10


def paginate_kb(
    items: list[tuple[str, str]],
    *,
    page: int,
    per_page: int = 9,
    per_row: int = 3,
    selected: Iterable[str] | None = None,
    label_for: Callable[[str, str, bool], str] | None = None,
    cb_template: Callable[[str], str],
    page_cb_template: Callable[[int], str] | None = None,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
    noop_cb: str = "noop",
) -> list[list[InlineKeyboardButton]]:
    """Build a paginated inline keyboard.

    Parameters
    ----------
    items
        Ordered list of `(key, label)` tuples. `key` is what the
        callback_data ends up encoding; `label` is the default button
        text if `label_for` isn't supplied.
    page
        0-indexed page to render.
    per_page
        Items per page. Should be a multiple of `per_row` for a clean
        grid, but that's not enforced.
    per_row
        Buttons per row inside the item grid.
    selected
        Optional iterable of keys that should be rendered as "on".
        `label_for` sees the boolean as its third argument.
    label_for
        Optional callable `(key, label, selected) -> str`. Default
        prepends "✅ " when selected, otherwise returns the label
        untouched.
    cb_template
        Callable `(key) -> str` producing `callback_data` for each
        item button.
    page_cb_template
        Callable `(page_index) -> str` producing `callback_data` for
        the Prev/Next buttons. When None, no page-nav row is emitted.
    extra_rows
        Rows appended below the pagination row (e.g. Clear / Done /
        Back buttons). Passed through unchanged.
    noop_cb
        Callback_data for disabled Prev/Next placeholders. Defaults to
        "noop", which most handler suites already absorb.
    """
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    if per_row < 1:
        raise ValueError("per_row must be >= 1")

    total = len(items)
    if total == 0:
        return list(extra_rows or [])

    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = min(start + per_page, total)
    page_items = items[start:end]

    sel = set(selected or ())
    if label_for is None:
        def _default_label(key: str, label: str, is_sel: bool) -> str:
            return f"✅ {label}" if is_sel else label
        label_for = _default_label

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, label in page_items:
        row.append(
            InlineKeyboardButton(
                label_for(key, label, key in sel),
                callback_data=cb_template(key),
            )
        )
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if page_cb_template is not None and total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    "⬅️ Prev", callback_data=page_cb_template(page - 1)
                )
            )
        else:
            nav_row.append(InlineKeyboardButton(" ", callback_data=noop_cb))
        nav_row.append(
            InlineKeyboardButton(
                f"{page + 1}/{total_pages}", callback_data=noop_cb
            )
        )
        if page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton(
                    "Next ➡️", callback_data=page_cb_template(page + 1)
                )
            )
        else:
            nav_row.append(InlineKeyboardButton(" ", callback_data=noop_cb))
        rows.append(nav_row)

    if extra_rows:
        rows.extend(extra_rows)

    return rows


def needs_pagination(item_count: int, per_page: int = PAGE_THRESHOLD) -> bool:
    """Tiny predicate: tells callers whether it's worth paging at all."""
    return item_count > per_page


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
