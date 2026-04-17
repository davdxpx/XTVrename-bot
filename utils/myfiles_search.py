# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Tiny query-DSL parser for MyFiles advanced search.

Supported tokens (AND-combined):
    tag:<name>          — file carries tag
    -tag:<name>         — file does NOT carry tag
    ext:<ext>           — file extension (without dot)
    before:YYYY-MM-DD   — created before date
    after:YYYY-MM-DD    — created after date
    size:>500mb         — size above value (supports kb/mb/gb)
    size:<500mb         — size below value
    anything-else       — treated as a case-insensitive substring match on
                          file_name

The return value is a MongoDB filter dict ready for `db.files.find(...)`
with the user scope added.
"""

from __future__ import annotations

import datetime
import re
from typing import Any


_SIZE = re.compile(r"^(?P<op>[<>])(?P<num>[0-9]+)(?P<unit>[kmg]?b)?$", re.I)
_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}


def _parse_size(raw: str) -> tuple[str, int] | None:
    m = _SIZE.match(raw.strip())
    if not m:
        return None
    unit = (m.group("unit") or "b").lower()
    factor = _UNITS.get(unit, 1)
    return m.group("op"), int(m.group("num")) * factor


def _parse_date(raw: str) -> datetime.datetime | None:
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def build_query(query: str, *, user_id: int | None = None) -> dict[str, Any]:
    """Parse the user query and return a Mongo filter. Unknown tokens
    degrade gracefully to a filename regex."""
    q: dict[str, Any] = {"is_deleted": {"$ne": True}}
    if user_id is not None:
        q["user_id"] = user_id

    name_parts: list[str] = []
    include_tags: list[str] = []
    exclude_tags: list[str] = []

    for token in (query or "").split():
        low = token.lower()
        if low.startswith("tag:"):
            val = low[4:].lstrip("#")
            if val:
                include_tags.append(val)
            continue
        if low.startswith("-tag:"):
            val = low[5:].lstrip("#")
            if val:
                exclude_tags.append(val)
            continue
        if low.startswith("ext:"):
            ext = low[4:].lstrip(".")
            if ext:
                q["file_name"] = {
                    **(q.get("file_name") or {}),
                    "$regex": rf"\.{re.escape(ext)}$",
                    "$options": "i",
                }
            continue
        if low.startswith("before:"):
            d = _parse_date(low[7:])
            if d:
                q.setdefault("created_at", {})["$lt"] = d
            continue
        if low.startswith("after:"):
            d = _parse_date(low[6:])
            if d:
                q.setdefault("created_at", {})["$gte"] = d
            continue
        if low.startswith("size:"):
            parsed = _parse_size(low[5:])
            if parsed:
                op, val = parsed
                key = "$gt" if op == ">" else "$lt"
                q.setdefault("size_bytes", {})[key] = val
            continue
        name_parts.append(token)

    if include_tags:
        q["tags"] = {
            **(q.get("tags") or {}),
            "$all": include_tags,
        }
    if exclude_tags:
        q["tags"] = {
            **(q.get("tags") or {}),
            "$nin": exclude_tags,
        }
    if name_parts:
        existing = q.get("file_name") or {}
        existing["$regex"] = ".*".join(re.escape(p) for p in name_parts)
        existing["$options"] = "i"
        q["file_name"] = existing

    return q
