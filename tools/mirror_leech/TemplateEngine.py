"""Safe folder-template renderer.

Expands user-supplied templates like `/MirrorLeech/{year}/{month:02d}/`
into concrete paths at upload time. Only `str.format_map` is used —
no Jinja, no eval, no attribute access. Unknown variables silently
resolve to an empty string so a typo can't crash the whole upload.

Supported variables (set by `MLContext.template_vars`):

    {year}            YYYY from server time
    {month}           raw int; pair with `{month:02d}` for zero-padding
    {day}             same
    {hour}/{minute}   server-time clock
    {source_kind}     id of the downloader that produced the file
                      ("http" / "yt" / "telegram" / "rss" / …)
    {user_id}         numeric Telegram user id
    {task_id}         Mirror-Leech task id (12 hex chars)
    {original_name}   filename stem (no extension, no path)
    {ext}             extension with no leading dot, lowercased
"""

from __future__ import annotations

from datetime import datetime


class _SafeDict(dict):
    """Dict variant that returns `""` for any missing key instead of
    raising KeyError — so a template that references {missing_var} just
    leaves it blank instead of blowing up the upload."""

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return ""


def _flatten_slashes(path: str) -> str:
    while "//" in path:
        path = path.replace("//", "/")
    return path


def render_template(template: str, variables: dict) -> str:
    """Expand `template` with `variables`. Missing vars become "".

    Never raises on unknown keys. Raises `ValueError` only on truly
    malformed templates (unclosed braces, etc.) so the UI can surface
    the error before saving.
    """
    if not template:
        return ""
    safe = _SafeDict(variables)
    try:
        rendered = template.format_map(safe)
    except (IndexError, ValueError) as exc:
        raise ValueError(f"template error: {exc}") from exc
    return _flatten_slashes(rendered)


def now_vars() -> dict:
    """Return the time-dependent variables. Kept separate so tests can
    pass a frozen datetime."""
    now = datetime.now()
    return {
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute,
    }
