# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Filename-template helpers.

Admin filename templates, per-user rename templates, and the caption
template all go through Python's ``str.format()``. A single stray brace
(``"Title}.{Quality}"``) raises ``ValueError: Single '}' encountered in
format string`` deep inside the rename pipeline, and until now that
bubbled up as an unrecoverable task failure.

These helpers validate templates up-front at the input boundary and
provide a drop-in ``safe_format`` that never raises — if the template
is malformed, we return the raw template string untouched so the
caller can surface a clear error or fall back to a default.
"""

from __future__ import annotations

import string
from typing import Any, Dict, Optional, Tuple

_FORMATTER = string.Formatter()


def validate_template(
    template: str,
    allowed_fields: Optional[set[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Return ``(ok, error)`` for a user-supplied format template.

    ``ok`` is ``True`` iff ``str.format()`` would accept the template
    without raising ``ValueError`` / ``IndexError`` / ``KeyError`` for
    structural reasons (unbalanced braces, numeric positional fields,
    unknown placeholders when ``allowed_fields`` is provided).

    ``error`` is a short, user-facing message when ``ok`` is ``False``.
    """
    if not isinstance(template, str):
        return False, "Template must be a string."

    if not template.strip():
        return False, "Template cannot be empty."

    try:
        parsed = list(_FORMATTER.parse(template))
    except ValueError as exc:
        return False, f"Malformed template: {exc}. Use `{{Field}}` and escape literal braces as `{{{{` / `}}}}`."

    unknown: list[str] = []
    for _literal, field_name, _format_spec, _conversion in parsed:
        if field_name is None:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0].strip()
        if not root:
            return False, "Positional placeholders like `{}` are not supported. Use named fields, e.g. `{Title}`."
        if root.isdigit():
            return False, "Numeric placeholders like `{0}` are not supported. Use named fields, e.g. `{Title}`."
        if allowed_fields is not None and root not in allowed_fields:
            unknown.append(root)

    if unknown:
        joined = ", ".join(f"`{{{name}}}`" for name in sorted(set(unknown)))
        return False, f"Unknown placeholder(s): {joined}."

    return True, None


def safe_format(template: str, mapping: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Format ``template`` with ``mapping`` without raising.

    Returns ``(result, error)``. On success ``error`` is ``None`` and
    ``result`` is the formatted string. On failure ``error`` describes
    the problem and ``result`` is the original ``template`` so callers
    can log the failure and fall back to a known-good default.
    """
    ok, err = validate_template(template)
    if not ok:
        return template, err

    try:
        return template.format(**mapping), None
    except (KeyError, IndexError, ValueError) as exc:
        return template, f"Template formatting failed: {exc}."
