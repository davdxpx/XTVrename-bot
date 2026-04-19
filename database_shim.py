"""
CollectionShim — back-compat wrapper around the MediaStudio-layout.

The 115 call sites in the codebase access settings via the old pattern:
  - db.settings.find_one({"_id": "global_settings"})
  - db.settings.update_one({"_id": "global_settings"}, {"$set": {k: v}})
  - db.settings.find_one({"_id": "public_mode_config"})
  - db.settings.find_one({"_id": f"user_{uid}"})
  - db.settings.find_one({"_id": "xtv_pro_settings" | "youtube_cookies"})

After the mediastudio_layout migration the underlying storage is:
  - MediaStudio-Settings: one doc per logical concern (branding, payments, ...)
  - MediaStudio-users.<uid>.personal_settings: per-user fields

`SettingsCollectionShim` presents the legacy surface and transparently
routes each read / write to the right place.

Unknown global keys fall through to the `legacy_misc` doc with a WARNING
so drift is observable in the /admin → DB Schema Health panel.
"""

from __future__ import annotations

import collections
import time
from typing import Any

import database_schema as schema
from utils.log import get_logger

logger = get_logger("database.shim")

# The shim keeps a bounded deque of recent unknown-key writes so the admin
# health panel can surface them. Entries: {ts, op, doc_id, key, source}.
_UNKNOWN_KEY_LOG_MAX = 50


def _extract_set_fields(update: dict) -> dict:
    """Return the `$set` fields of a Mongo update doc, or the doc itself if
    it's a plain replace. Leaves `$unset` / `$inc` / other operators untouched
    for the caller to forward verbatim."""
    if not isinstance(update, dict):
        return {}
    if any(k.startswith("$") for k in update):
        return dict(update.get("$set", {}))
    return dict(update)


def _extract_unset_fields(update: dict) -> list[str]:
    if not isinstance(update, dict):
        return []
    return list(update.get("$unset", {}).keys())


def _extract_other_ops(update: dict) -> dict:
    """Return the update operators we don't rewrite (e.g. $inc, $push, $addToSet)
    so they can be forwarded to the target doc(s) unchanged."""
    if not isinstance(update, dict):
        return {}
    return {k: v for k, v in update.items() if k.startswith("$") and k not in ("$set", "$unset")}


class SettingsCollectionShim:
    """Legacy `db.settings` facade over the new MediaStudio layout.

    Writes that target a virtual doc id (`global_settings`, `public_mode_config`,
    `user_<id>`) are rewritten to the real MediaStudio-Settings / MediaStudio-users
    documents. Writes that target an unrecognised doc id pass through verbatim
    so the shim never swallows data.

    In non-public mode, keys listed in ``schema.PERSONAL_KEYS`` (templates,
    dumb_channels, thumbnails, channel, …) that are written to or read from
    the virtual ``global_settings`` doc are transparently routed to the CEO's
    ``MediaStudio-users.<ceo_id>.personal_settings``. This matches the
    ``mediastudio_layout`` migration, which moves exactly those keys from
    the legacy ``global_settings`` doc to the CEO's user doc; without this
    routing, handlers that legitimately write to the virtual global doc
    would land their values in ``legacy_misc`` or ``dumb_channels_global``
    while the migrated truth sits in the user doc — so the bot would appear
    to have "lost" templates, dumb channels, default channel, thumbnails,
    etc. right after the migration.
    """

    def __init__(
        self,
        settings_collection,
        users_collection,
        *,
        ceo_id: int | None = None,
        public_mode: bool = False,
    ):
        self._settings = settings_collection  # AsyncIOMotorCollection (MediaStudio-Settings)
        self._users = users_collection  # AsyncIOMotorCollection (MediaStudio-users)
        self._ceo_id = int(ceo_id) if ceo_id else None
        self._public_mode = bool(public_mode)
        self._unknown_key_log: collections.deque = collections.deque(maxlen=_UNKNOWN_KEY_LOG_MAX)

    # ------------------------------------------------------------------ helpers

    @property
    def name(self) -> str:
        return getattr(self._settings, "name", schema.SETTINGS_COLLECTION)

    @property
    def real(self):
        """Escape hatch for code that truly needs the raw MediaStudio-Settings
        Motor collection (migration tooling, admin panels)."""
        return self._settings

    def recent_unknown_writes(self) -> list[dict]:
        return list(self._unknown_key_log)

    def _record_unknown(self, op: str, doc_id: str, key: str) -> None:
        self._unknown_key_log.append(
            {"ts": time.time(), "op": op, "doc_id": doc_id, "key": key}
        )
        logger.warning(
            "SettingsCollectionShim: unknown key '%s' on %s (%s) -> %s",
            key,
            doc_id,
            op,
            schema.LEGACY_MISC_DOC_ID,
        )

    def _ceo_personal_routing_enabled(self) -> bool:
        """Personal-key routing on virtual global_settings is only active in
        non-public, single-tenant deployments with a configured CEO."""
        return (not self._public_mode) and bool(self._ceo_id)

    async def _read_ceo_personal(self) -> dict:
        """Return the CEO's personal_settings dict (or {})."""
        if not self._ceo_id:
            return {}
        doc = await self._users.find_one({"user_id": self._ceo_id})
        if not doc:
            return {}
        return doc.get("personal_settings") or {}

    @staticmethod
    def _is_personal_key(key: str) -> bool:
        top = key.partition(".")[0]
        return top in schema.PERSONAL_KEYS

    async def _merge_global_docs(self) -> dict | None:
        """Merge all real Settings docs into a virtual flat dict matching the
        shape callers expect from {"_id": "global_settings"}.

        Returns None when no underlying docs exist, preserving the legacy
        "no settings yet, insert defaults" signal that bootstrap paths rely
        on for a fresh install.

        Iterates MERGED_GLOBAL_DOCS in tuple order (not via `$in` which
        gives implementation-defined ordering) so collisions resolve
        deterministically: later tuple entries overwrite earlier ones.

        In non-public mode, the CEO's personal_settings is merged on top so
        PERSONAL_KEYS (templates, dumb_channels, channel, thumbnail_*, …)
        migrated there by the mediastudio_layout migration remain visible
        under the virtual global_settings doc used by every handler.
        """
        merged: dict[str, Any] = {}
        count = 0
        for doc_id in schema.MERGED_GLOBAL_DOCS:
            doc = await self._settings.find_one({"_id": doc_id})
            if doc is None:
                continue
            count += 1
            doc.pop("_id", None)
            for key, value in doc.items():
                if key in schema.MERGE_EXCLUDE:
                    continue
                existing = merged.get(key)
                if isinstance(existing, dict) and isinstance(value, dict):
                    # Deep-merge dict values so legacy leftovers from
                    # `legacy_misc` (pre-routing writes) stay visible
                    # alongside values from the authoritative doc.
                    combined = dict(existing)
                    combined.update(value)
                    merged[key] = combined
                else:
                    merged[key] = value

        ceo_personal: dict = {}
        if self._ceo_personal_routing_enabled():
            ceo_personal = await self._read_ceo_personal()
            for key, value in ceo_personal.items():
                existing = merged.get(key)
                if isinstance(existing, dict) and isinstance(value, dict):
                    combined = dict(existing)
                    combined.update(value)
                    merged[key] = combined
                else:
                    merged[key] = value
            if ceo_personal:
                count += 1

        if count == 0:
            return None
        merged["_id"] = schema.VIRTUAL_GLOBAL_SETTINGS
        return merged

    async def _read_personal(self, uid: int) -> dict | None:
        user_doc = await self._users.find_one({"user_id": uid})
        if not user_doc:
            return None
        personal = user_doc.get("personal_settings") or {}
        # Emulate the legacy shape: doc with _id="user_<uid>" and keys flat.
        flat = {"_id": f"user_{uid}"}
        flat.update(personal)
        return flat

    async def _apply_global_update(self, update: dict, upsert: bool) -> Any:
        """Route a $set/$unset/etc. update targeting a virtual global doc.

        In non-public mode with a configured CEO, PERSONAL_KEYS (templates,
        dumb_channels, channel, thumbnail_*, …) are siphoned off into the
        CEO's personal_settings so they stay aligned with the data layout
        produced by the mediastudio_layout migration.
        """
        set_fields = _extract_set_fields(update)
        unset_fields = _extract_unset_fields(update)
        other_ops = _extract_other_ops(update)

        # Siphon off personal-key writes (non-public mode only) and apply
        # them to the CEO's user doc — preserving dotted subpaths so e.g.
        # `dumb_channels.-100123` lands under personal_settings.dumb_channels.
        ceo_route = self._ceo_personal_routing_enabled()
        ceo_set: dict = {}
        ceo_unset: list[str] = []
        ceo_other: dict = {}
        if ceo_route:
            for k in list(set_fields.keys()):
                if self._is_personal_key(k):
                    ceo_set[k] = set_fields.pop(k)
            for k in list(unset_fields):
                if self._is_personal_key(k):
                    ceo_unset.append(k)
                    unset_fields.remove(k)
            for op, body in list(other_ops.items()):
                if isinstance(body, dict):
                    moved = {
                        k: body[k] for k in list(body.keys()) if self._is_personal_key(k)
                    }
                    for k in moved:
                        body.pop(k)
                    if moved:
                        ceo_other[op] = moved
                    if not body:
                        other_ops.pop(op)

        # Group remaining fields by target doc. Support Mongo's dotted nested-key
        # syntax (`feature_toggles.mirror_leech_gallery_dl`): the routing table
        # is keyed by the top-level name, so we look up the prefix before
        # the first dot and keep the full dotted key in the rewritten
        # update so Mongo writes the nested field.
        def _lookup(key: str) -> str | None:
            if key in schema.GLOBAL_KEY_TO_DOC:
                return schema.GLOBAL_KEY_TO_DOC[key]
            top, _, _ = key.partition(".")
            if top and top in schema.GLOBAL_KEY_TO_DOC:
                return schema.GLOBAL_KEY_TO_DOC[top]
            return None

        targets_set: dict[str, dict] = collections.defaultdict(dict)
        for key, value in set_fields.items():
            target = _lookup(key)
            if target is None:
                target = schema.LEGACY_MISC_DOC_ID
                self._record_unknown("update/$set", schema.VIRTUAL_GLOBAL_SETTINGS, key)
            targets_set[target][key] = value

        targets_unset: dict[str, dict] = collections.defaultdict(dict)
        for key in unset_fields:
            target = _lookup(key) or schema.LEGACY_MISC_DOC_ID
            if target == schema.LEGACY_MISC_DOC_ID:
                self._record_unknown("update/$unset", schema.VIRTUAL_GLOBAL_SETTINGS, key)
            targets_unset[target][key] = ""

        last_result = None
        touched = set(targets_set.keys()) | set(targets_unset.keys())
        if other_ops:
            # Forward unknown operators to legacy_misc so we never drop data.
            touched.add(schema.LEGACY_MISC_DOC_ID)

        for target in touched:
            sub_update: dict = {}
            if target in targets_set:
                sub_update["$set"] = targets_set[target]
            if target in targets_unset:
                sub_update["$unset"] = targets_unset[target]
            if other_ops and target == schema.LEGACY_MISC_DOC_ID:
                sub_update.update(other_ops)
            if sub_update:
                last_result = await self._settings.update_one(
                    {"_id": target}, sub_update, upsert=upsert
                )

        if ceo_route and (ceo_set or ceo_unset or ceo_other):
            ceo_update: dict = {}
            if ceo_set:
                ceo_update["$set"] = ceo_set
            if ceo_unset:
                ceo_update["$unset"] = {k: "" for k in ceo_unset}
            if ceo_other:
                ceo_update.update(ceo_other)
            last_result = await self._apply_personal_update(
                self._ceo_id, ceo_update, upsert=True
            )

        return last_result

    async def _apply_personal_update(self, uid: int, update: dict, upsert: bool) -> Any:
        set_fields = _extract_set_fields(update)
        unset_fields = _extract_unset_fields(update)
        other_ops = _extract_other_ops(update)

        rewritten: dict = {}
        if set_fields:
            rewritten["$set"] = {f"personal_settings.{k}": v for k, v in set_fields.items()}
        if unset_fields:
            rewritten["$unset"] = {f"personal_settings.{k}": "" for k in unset_fields}
        if other_ops:
            # For operators like $inc on personal settings: rewrite path too.
            for op, body in other_ops.items():
                if isinstance(body, dict):
                    rewritten[op] = {f"personal_settings.{k}": v for k, v in body.items()}
                else:
                    rewritten[op] = body

        if upsert:
            # Ensure the user doc exists; upsert handles the insert side.
            rewritten.setdefault("$setOnInsert", {"user_id": uid})

        return await self._users.update_one(
            {"user_id": uid}, rewritten, upsert=upsert
        )

    # ------------------------------------------------------------------ public API

    async def find_one(self, filter_=None, *args, **kwargs):
        if isinstance(filter_, dict):
            doc_id = filter_.get("_id")
            if doc_id in schema.VIRTUAL_DOC_IDS:
                return await self._merge_global_docs()
            uid = schema.parse_user_doc_id(doc_id)
            if uid is not None:
                return await self._read_personal(uid)
            if doc_id in schema.LEGACY_WHOLE_DOC_ROUTING:
                target = schema.LEGACY_WHOLE_DOC_ROUTING[doc_id]
                doc = await self._settings.find_one({"_id": target})
                if doc is None:
                    return None
                aliased = dict(doc)
                aliased["_id"] = doc_id  # preserve the legacy _id
                return aliased
        return await self._settings.find_one(filter_, *args, **kwargs)

    def find(self, *args, **kwargs):
        """Pass-through cursor. Virtual-doc filtering is rare on find() so we
        don't rewrite — callers that iterate everything get the real docs."""
        return self._settings.find(*args, **kwargs)

    async def count_documents(self, *args, **kwargs):
        return await self._settings.count_documents(*args, **kwargs)

    def aggregate(self, *args, **kwargs):
        return self._settings.aggregate(*args, **kwargs)

    async def create_index(self, *args, **kwargs):
        return await self._settings.create_index(*args, **kwargs)

    async def update_one(self, filter_, update, upsert=False, **kwargs):
        if isinstance(filter_, dict):
            doc_id = filter_.get("_id")
            if doc_id in schema.VIRTUAL_DOC_IDS:
                return await self._apply_global_update(update, upsert)
            uid = schema.parse_user_doc_id(doc_id)
            if uid is not None:
                return await self._apply_personal_update(uid, update, upsert)
            if doc_id in schema.LEGACY_WHOLE_DOC_ROUTING:
                target = schema.LEGACY_WHOLE_DOC_ROUTING[doc_id]
                return await self._settings.update_one(
                    {"_id": target}, update, upsert=upsert, **kwargs
                )
        return await self._settings.update_one(filter_, update, upsert=upsert, **kwargs)

    async def update_many(self, filter_, update, **kwargs):
        return await self._settings.update_many(filter_, update, **kwargs)

    async def insert_one(self, document, **kwargs):
        if isinstance(document, dict):
            doc_id = document.get("_id")
            if doc_id in schema.VIRTUAL_DOC_IDS:
                # Rewrite to an upsert-style $set covering every field.
                payload = {k: v for k, v in document.items() if k != "_id"}
                return await self._apply_global_update({"$set": payload}, upsert=True)
            uid = schema.parse_user_doc_id(doc_id)
            if uid is not None:
                payload = {k: v for k, v in document.items() if k != "_id"}
                return await self._apply_personal_update(uid, {"$set": payload}, upsert=True)
            if doc_id in schema.LEGACY_WHOLE_DOC_ROUTING:
                target = schema.LEGACY_WHOLE_DOC_ROUTING[doc_id]
                rewritten = dict(document)
                rewritten["_id"] = target
                return await self._settings.insert_one(rewritten, **kwargs)
        return await self._settings.insert_one(document, **kwargs)

    async def insert_many(self, documents, **kwargs):
        return await self._settings.insert_many(documents, **kwargs)

    async def delete_one(self, filter_, **kwargs):
        if isinstance(filter_, dict):
            doc_id = filter_.get("_id")
            uid = schema.parse_user_doc_id(doc_id)
            if uid is not None:
                return await self._users.update_one(
                    {"user_id": uid}, {"$unset": {"personal_settings": ""}}
                )
            if doc_id in schema.LEGACY_WHOLE_DOC_ROUTING:
                target = schema.LEGACY_WHOLE_DOC_ROUTING[doc_id]
                return await self._settings.delete_one({"_id": target})
        return await self._settings.delete_one(filter_, **kwargs)

    async def delete_many(self, filter_, **kwargs):
        return await self._settings.delete_many(filter_, **kwargs)

    async def replace_one(self, filter_, replacement, upsert=False, **kwargs):
        # Replace semantics on a virtual doc is effectively $set of every field
        # plus clearing any field not present. Callers rarely need this; we
        # approximate as an upsert-style $set over the replacement.
        if isinstance(filter_, dict):
            doc_id = filter_.get("_id")
            if doc_id in schema.VIRTUAL_DOC_IDS:
                payload = {k: v for k, v in replacement.items() if k != "_id"}
                return await self._apply_global_update({"$set": payload}, upsert=upsert)
            uid = schema.parse_user_doc_id(doc_id)
            if uid is not None:
                payload = {k: v for k, v in replacement.items() if k != "_id"}
                return await self._apply_personal_update(uid, {"$set": payload}, upsert=upsert)
            if doc_id in schema.LEGACY_WHOLE_DOC_ROUTING:
                target = schema.LEGACY_WHOLE_DOC_ROUTING[doc_id]
                return await self._settings.replace_one(
                    {"_id": target}, replacement, upsert=upsert, **kwargs
                )
        return await self._settings.replace_one(filter_, replacement, upsert=upsert, **kwargs)
