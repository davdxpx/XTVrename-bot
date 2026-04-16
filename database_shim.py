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

from utils.log import get_logger

import database_schema as schema

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
    if any(k.startswith("$") for k in update.keys()):
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
    """

    def __init__(self, settings_collection, users_collection):
        self._settings = settings_collection  # AsyncIOMotorCollection (MediaStudio-Settings)
        self._users = users_collection  # AsyncIOMotorCollection (MediaStudio-users)
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

    async def _merge_global_docs(self) -> dict | None:
        """Merge all real Settings docs into a virtual flat dict matching the
        shape callers expect from {"_id": "global_settings"}.

        Returns None when no underlying docs exist, preserving the legacy
        "no settings yet, insert defaults" signal that bootstrap paths rely
        on for a fresh install.
        """
        merged: dict[str, Any] = {}
        count = 0
        async for doc in self._settings.find({"_id": {"$in": list(schema.MERGED_GLOBAL_DOCS)}}):
            count += 1
            doc.pop("_id", None)
            for key, value in doc.items():
                if key in schema.MERGE_EXCLUDE:
                    continue
                # Later docs win on collision — should not happen with a
                # well-maintained GLOBAL_KEY_TO_DOC but guard against it.
                merged[key] = value
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
        """Route a $set/$unset/etc. update targeting a virtual global doc."""
        set_fields = _extract_set_fields(update)
        unset_fields = _extract_unset_fields(update)
        other_ops = _extract_other_ops(update)

        # Group fields by target doc.
        targets_set: dict[str, dict] = collections.defaultdict(dict)
        for key, value in set_fields.items():
            target = schema.GLOBAL_KEY_TO_DOC.get(key)
            if target is None:
                target = schema.LEGACY_MISC_DOC_ID
                self._record_unknown("update/$set", schema.VIRTUAL_GLOBAL_SETTINGS, key)
            targets_set[target][key] = value

        targets_unset: dict[str, dict] = collections.defaultdict(dict)
        for key in unset_fields:
            target = schema.GLOBAL_KEY_TO_DOC.get(key, schema.LEGACY_MISC_DOC_ID)
            if target == schema.LEGACY_MISC_DOC_ID and key not in schema.GLOBAL_KEY_TO_DOC:
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
