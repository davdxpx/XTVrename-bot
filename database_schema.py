"""
MediaStudio layout routing tables.

Describes how legacy flat settings map onto the new per-concern documents
in `MediaStudio-Settings` and onto `MediaStudio-users.<uid>.personal_settings`.

Keys that are not in `GLOBAL_KEY_TO_DOC` and not in `PERSONAL_KEYS` fall
through to `LEGACY_MISC_DOC_ID` with a WARNING so an admin can spot drift.
"""

# --- Collection names ---

SETTINGS_COLLECTION = "MediaStudio-Settings"
USERS_COLLECTION = "MediaStudio-users"
FILES_COLLECTION = "MediaStudio-files"
FOLDERS_COLLECTION = "MediaStudio-folders"
DAILY_STATS_COLLECTION = "MediaStudio-daily-stats"
PENDING_PAYMENTS_COLLECTION = "MediaStudio-pending-payments"
FILE_GROUPS_COLLECTION = "MediaStudio-file-groups"
# MyFiles extras — audit/activity/quota/shares collections
MYFILES_AUDIT_COLLECTION = "MediaStudio-myfiles-audit"
MYFILES_ACTIVITY_COLLECTION = "MediaStudio-myfiles-activity"
MYFILES_QUOTAS_COLLECTION = "MediaStudio-myfiles-quotas"
MYFILES_SHARES_COLLECTION = "MediaStudio-myfiles-shares"

# Legacy names in MainDB prior to the mediastudio_layout migration.
LEGACY_COLLECTION_NAMES = {
    "user_settings": None,  # split across Settings + users.personal_settings
    "users": USERS_COLLECTION,
    "files": FILES_COLLECTION,
    "folders": FOLDERS_COLLECTION,
    "daily_stats": DAILY_STATS_COLLECTION,
    "pending_payments": PENDING_PAYMENTS_COLLECTION,
    "file_groups": FILE_GROUPS_COLLECTION,
}

# Suffix for pre-migration backup clones kept in MainDB.
BACKUP_SUFFIX = "_backup_legacy"

# --- Global settings doc IDs inside MediaStudio-Settings ---

DOC_BRANDING = "branding"
DOC_FORCE_SUB = "force_sub"
DOC_PAYMENTS = "payments"
DOC_PREMIUM_PLANS = "premium_plans"
DOC_MYFILES_CONFIG = "myfiles_config"
DOC_MYFILES_LIMITS = "myfiles_limits"
DOC_EGRESS_LIMITS = "egress_limits"
DOC_DATABASE_CHANNELS = "database_channels"
DOC_DUMB_CHANNELS_GLOBAL = "dumb_channels_global"
DOC_FEATURE_TOGGLES = "feature_toggles"
DOC_BLOCKED_USERS = "blocked_users"
DOC_XTV_PRO = "xtv_pro"
DOC_YOUTUBE_COOKIES = "youtube_cookies"
DOC_SCHEMA_MIGRATIONS = "schema_migrations"
DOC_MIRROR_LEECH_GLOBAL = "mirror_leech_global"
DOC_MYFILES_RETENTION = "myfiles_retention"
LEGACY_MISC_DOC_ID = "legacy_misc"

# --- Virtual doc IDs that the shim synthesises from multiple real docs ---

VIRTUAL_GLOBAL_SETTINGS = "global_settings"
VIRTUAL_PUBLIC_MODE_CONFIG = "public_mode_config"
VIRTUAL_DOC_IDS = {VIRTUAL_GLOBAL_SETTINGS, VIRTUAL_PUBLIC_MODE_CONFIG}

# All real Settings docs that the shim merges when reading a virtual doc ID.
MERGED_GLOBAL_DOCS = (
    DOC_BRANDING,
    DOC_FORCE_SUB,
    DOC_PAYMENTS,
    DOC_PREMIUM_PLANS,
    DOC_MYFILES_CONFIG,
    DOC_MYFILES_LIMITS,
    DOC_MYFILES_RETENTION,
    DOC_EGRESS_LIMITS,
    DOC_DATABASE_CHANNELS,
    DOC_DUMB_CHANNELS_GLOBAL,
    DOC_FEATURE_TOGGLES,
    DOC_BLOCKED_USERS,
    LEGACY_MISC_DOC_ID,
)

# Heavy fields that must NOT be merged into virtual-doc reads (avoid blowing
# up callers that scan all of global_settings). Accessors hit the specific
# real doc directly instead.
MERGE_EXCLUDE = frozenset(
    {
        # placeholder — thumbnail_binary lives under per-user personal_settings
        # now, so it never appears in a global merge anyway. Keep the frozenset
        # available for future heavy-field exclusions.
    }
)

# --- Key -> doc routing for global settings writes ---
#
# When a caller does  db.settings.update_one({"_id": "global_settings"},
#                                            {"$set": {key: value}})
# the shim looks `key` up in GLOBAL_KEY_TO_DOC and rewrites the target doc.
# `public_mode_config` writes use the same table.
#
# Keys missing from this map (and not in PERSONAL_KEYS) land in
# LEGACY_MISC_DOC_ID and emit a WARNING so we can tighten the map over time.

GLOBAL_KEY_TO_DOC = {
    # branding
    "bot_name": DOC_BRANDING,
    "community_name": DOC_BRANDING,
    "support_contact": DOC_BRANDING,
    "default_channel": DOC_BRANDING,
    "default_templates": DOC_BRANDING,
    "default_filename_templates": DOC_BRANDING,
    # force-sub
    "force_sub_channel": DOC_FORCE_SUB,
    "force_sub_channels": DOC_FORCE_SUB,
    "force_sub_link": DOC_FORCE_SUB,
    "force_sub_username": DOC_FORCE_SUB,
    "force_sub_banner_file_id": DOC_FORCE_SUB,
    "force_sub_message_text": DOC_FORCE_SUB,
    "force_sub_button_label": DOC_FORCE_SUB,
    "force_sub_button_emoji": DOC_FORCE_SUB,
    "force_sub_welcome_text": DOC_FORCE_SUB,
    # payments
    "payment_methods": DOC_PAYMENTS,
    "discounts": DOC_PAYMENTS,
    "base_currency": DOC_PAYMENTS,
    "stars_payment_enabled": DOC_PAYMENTS,
    "currency_conversion_enabled": DOC_PAYMENTS,
    "rate_limit_delay": DOC_PAYMENTS,
    # premium plans
    "premium_system_enabled": DOC_PREMIUM_PLANS,
    "premium_trial_enabled": DOC_PREMIUM_PLANS,
    "premium_trial_days": DOC_PREMIUM_PLANS,
    "premium_trial_length_days": DOC_PREMIUM_PLANS,
    "premium_deluxe_enabled": DOC_PREMIUM_PLANS,
    "premium_standard": DOC_PREMIUM_PLANS,
    "premium_deluxe": DOC_PREMIUM_PLANS,
    "xtv_pro_4gb_access": DOC_PREMIUM_PLANS,
    # myfiles
    "myfiles_enabled": DOC_MYFILES_CONFIG,
    "myfiles_limits": DOC_MYFILES_LIMITS,
    # myfiles extras — retention / quotas
    "myfiles_trash_retention_days": DOC_MYFILES_RETENTION,
    "myfiles_audit_retention_days": DOC_MYFILES_RETENTION,
    "myfiles_activity_retention_days": DOC_MYFILES_RETENTION,
    "myfiles_max_versions": DOC_MYFILES_RETENTION,
    "myfiles_default_quotas": DOC_MYFILES_RETENTION,
    # egress / rate limits
    "daily_egress_mb": DOC_EGRESS_LIMITS,
    "daily_file_count": DOC_EGRESS_LIMITS,
    "global_daily_egress_mb": DOC_EGRESS_LIMITS,
    "dumb_channel_timeout": DOC_EGRESS_LIMITS,
    # channels
    "database_channels": DOC_DATABASE_CHANNELS,
    "dumb_channels": DOC_DUMB_CHANNELS_GLOBAL,
    "dumb_channel_links": DOC_DUMB_CHANNELS_GLOBAL,
    "default_dumb_channel": DOC_DUMB_CHANNELS_GLOBAL,
    "movie_dumb_channel": DOC_DUMB_CHANNELS_GLOBAL,
    "series_dumb_channel": DOC_DUMB_CHANNELS_GLOBAL,
    # feature toggles
    "feature_toggles": DOC_FEATURE_TOGGLES,
    "global_feature_toggles": DOC_FEATURE_TOGGLES,
    # blocked users
    "blocked_users": DOC_BLOCKED_USERS,
    # migration bookkeeping — kept readable via the virtual doc
    "migration_to_users_done": DOC_SCHEMA_MIGRATIONS,
    "dumb_channels_migrated_to_ceo": DOC_SCHEMA_MIGRATIONS,
    "myfiles_extras_v1_applied_at": DOC_SCHEMA_MIGRATIONS,
}

# --- Per-user personal settings ---
#
# When a caller writes `{"_id": "user_<uid>"}` the shim stores the field under
# MediaStudio-users.<uid>.personal_settings.<key>. Reads go through
# the same translation. Every key that is user-scoped should appear here.
# Unknown per-user keys are still accepted (forward-compat for v1.6.x
# features), just logged at DEBUG.

PERSONAL_KEYS = frozenset(
    {
        # thumbnails & templates
        "thumbnail_file_id",
        "thumbnail_binary",
        "thumbnail_mode",
        "templates",
        "filename_templates",
        # workflow / general prefs
        "channel",
        "preferred_language",
        "preferred_separator",
        "workflow_mode",
        "setup_completed",
        "setup_stage",
        "is_bot_setup_complete",
        "has_completed_preferences",
        "start_menu_tools",
        "tool_usage_stats",
        "default_quality",
        "auto_tmdb_match",
        "default_media_type",
        "preserve_original_filename",
        # MyFiles prefs
        "myfiles_auto_permanent",
        "myfiles_default_sort",
        "myfiles_files_per_page",
        "display_show_poster",
        "group_series_by_season",
        "link_anonymity",
        "share_display_name",
        "hide_forward_tags",
        # per-user dumb channels (public mode)
        "dumb_channels",
        "dumb_channel_links",
        "default_dumb_channel",
        "movie_dumb_channel",
        "series_dumb_channel",
        # Phase D (Mirror-Leech)
        "mirror_leech_accounts",
    }
)

# --- Whole-doc upsert routing ---
#
# Some legacy code writes whole sub-documents at top-level IDs (e.g.
# xtv_pro_settings, youtube_cookies). The migration maps them to new single-
# purpose docs; the shim routes direct writes by the legacy _id here.

LEGACY_WHOLE_DOC_ROUTING = {
    "xtv_pro_settings": DOC_XTV_PRO,
    "youtube_cookies": DOC_YOUTUBE_COOKIES,
}


def classify_global_key(key: str) -> str:
    """Return the target doc _id for a global-settings key.

    Unknown keys are routed to LEGACY_MISC_DOC_ID so the shim can still
    accept the write; callers should log a WARNING in that case.
    """
    return GLOBAL_KEY_TO_DOC.get(key, LEGACY_MISC_DOC_ID)


def is_virtual_doc_id(doc_id) -> bool:
    return isinstance(doc_id, str) and doc_id in VIRTUAL_DOC_IDS


def parse_user_doc_id(doc_id) -> int | None:
    """Return the user id encoded in `user_<id>`, or None if not a user doc."""
    if not isinstance(doc_id, str) or not doc_id.startswith("user_"):
        return None
    try:
        return int(doc_id[5:])
    except ValueError:
        return None
