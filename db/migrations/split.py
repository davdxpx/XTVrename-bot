"""Pure transformation: splitting a legacy user_settings document into the
new MediaStudio layout.

No I/O — given an input doc and the runtime mode flags, returns a plan
describing which fields land in which global docs / which user docs.
Makes the transformation easy to unit-test with fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from db import schema


@dataclass
class SplitResult:
    """Planned writes derived from one input user_settings doc.

    - global_docs: {doc_id: {field: value, ...}} for MediaStudio-Settings upserts.
    - user_updates: {user_id: {"personal_settings": {...}, "usage": {...}}}.
    - unknown_keys: list of (source_doc_id, key) routed to legacy_misc.
    - verbatim_legacy: {legacy_<original_id>: full_doc_body} for docs that
      don't match any known shape — the migration preserves them so nothing
      is dropped.
    """

    global_docs: dict[str, dict] = field(default_factory=dict)
    user_updates: dict[int, dict] = field(default_factory=dict)
    unknown_keys: list[tuple[str, str]] = field(default_factory=list)
    verbatim_legacy: dict[str, dict] = field(default_factory=dict)

    def _add_global(self, target: str, key: str, value) -> None:
        self.global_docs.setdefault(target, {})[key] = value

    def _add_personal(self, user_id: int, key: str, value) -> None:
        entry = self.user_updates.setdefault(
            user_id, {"personal_settings": {}, "usage": {}}
        )
        entry["personal_settings"][key] = value

    def _add_usage(self, user_id: int, usage: dict) -> None:
        entry = self.user_updates.setdefault(
            user_id, {"personal_settings": {}, "usage": {}}
        )
        entry["usage"].update(usage)


def _route_global_field(
    result: SplitResult,
    source_doc_id: str,
    key: str,
    value,
) -> None:
    target = schema.GLOBAL_KEY_TO_DOC.get(key)
    if target is None:
        result.unknown_keys.append((source_doc_id, key))
        target = schema.LEGACY_MISC_DOC_ID
    result._add_global(target, key, value)


def split_user_settings_doc(
    doc: dict,
    *,
    public_mode: bool,
    ceo_id: int,
) -> SplitResult:
    """Classify a single legacy user_settings document.

    Expected input _id values:
      - "global_settings"    — non-public mode config + (historically) CEO personal.
      - "public_mode_config" — public mode defaults.
      - "xtv_pro_settings"   — XTV Pro session config.
      - "youtube_cookies"    — persisted YT cookies blob.
      - "user_<int>"         — per-user personal settings.
      - anything else        — preserved verbatim under legacy_<_id>.
    """
    result = SplitResult()
    doc_id = doc.get("_id")
    if doc_id is None:
        return result

    body = {k: v for k, v in doc.items() if k != "_id"}

    if doc_id == schema.VIRTUAL_GLOBAL_SETTINGS:
        # In non-public mode the CEO's personal settings were written here
        # because _get_doc_id ignored user_id. Route PERSONAL_KEYS to CEO.
        for key, value in body.items():
            if key in schema.PERSONAL_KEYS and not public_mode:
                result._add_personal(ceo_id, key, value)
            else:
                _route_global_field(result, doc_id, key, value)
        return result

    if doc_id == schema.VIRTUAL_PUBLIC_MODE_CONFIG:
        for key, value in body.items():
            _route_global_field(result, doc_id, key, value)
        return result

    if doc_id in schema.LEGACY_WHOLE_DOC_ROUTING:
        target = schema.LEGACY_WHOLE_DOC_ROUTING[doc_id]
        result.global_docs.setdefault(target, {}).update(body)
        return result

    uid = schema.parse_user_doc_id(doc_id)
    if uid is not None:
        for key, value in body.items():
            if key == "usage" and isinstance(value, dict):
                result._add_usage(uid, value)
            else:
                result._add_personal(uid, key, value)
        return result

    # Unknown doc shape: preserve verbatim so it's visible to operators and
    # recoverable from the backup if anything depends on it.
    legacy_id = f"legacy_{doc_id}"
    result.verbatim_legacy[legacy_id] = body
    return result
