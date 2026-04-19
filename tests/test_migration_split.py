"""Tests for db_migrations.split.split_user_settings_doc."""

from db import schema as schema
from db.migrations.split import split_user_settings_doc


def test_public_mode_config_splits_into_per_concern_docs():
    doc = {
        "_id": "public_mode_config",
        "bot_name": "PublicBot",
        "community_name": "XTV",
        "base_currency": "USD",
        "premium_system_enabled": True,
        "payment_methods": {"paypal_enabled": True},
        "myfiles_limits": {"free": {}},
    }
    result = split_user_settings_doc(doc, public_mode=True, ceo_id=1)
    assert result.global_docs[schema.DOC_BRANDING]["bot_name"] == "PublicBot"
    assert result.global_docs[schema.DOC_BRANDING]["community_name"] == "XTV"
    assert result.global_docs[schema.DOC_PAYMENTS]["base_currency"] == "USD"
    assert (
        result.global_docs[schema.DOC_PREMIUM_PLANS]["premium_system_enabled"] is True
    )
    assert "myfiles_limits" in result.global_docs[schema.DOC_MYFILES_LIMITS]
    assert not result.user_updates
    assert not result.unknown_keys


def test_global_settings_in_non_public_mode_routes_personal_keys_to_ceo():
    doc = {
        "_id": "global_settings",
        "dumb_channel_timeout": 30,
        "thumbnail_file_id": "ABC",
        "templates": {"title": "{title}"},
        "myfiles_enabled": True,
    }
    result = split_user_settings_doc(doc, public_mode=False, ceo_id=999)

    # Global fields
    assert (
        result.global_docs[schema.DOC_EGRESS_LIMITS]["dumb_channel_timeout"] == 30
    )
    assert result.global_docs[schema.DOC_MYFILES_CONFIG]["myfiles_enabled"] is True

    # CEO personal fields
    ceo = result.user_updates[999]
    assert ceo["personal_settings"]["thumbnail_file_id"] == "ABC"
    assert ceo["personal_settings"]["templates"] == {"title": "{title}"}


def test_global_settings_in_public_mode_keeps_personal_looking_keys_global():
    # In public mode, non-user-id-addressed personal keys are admin defaults,
    # not CEO personal settings — they go to the global per-concern docs via
    # the key routing table (no PERSONAL_KEYS override).
    doc = {
        "_id": "global_settings",
        "default_dumb_channel": -100,
    }
    result = split_user_settings_doc(doc, public_mode=True, ceo_id=1)
    assert (
        result.global_docs[schema.DOC_DUMB_CHANNELS_GLOBAL]["default_dumb_channel"]
        == -100
    )
    assert not result.user_updates


def test_user_doc_routes_everything_to_personal_settings_plus_usage():
    doc = {
        "_id": "user_42",
        "thumbnail_file_id": "XYZ",
        "preferred_language": "de",
        "usage": {"date": "2025-01-01", "egress_mb": 123},
    }
    result = split_user_settings_doc(doc, public_mode=True, ceo_id=1)
    user = result.user_updates[42]
    assert user["personal_settings"]["thumbnail_file_id"] == "XYZ"
    assert user["personal_settings"]["preferred_language"] == "de"
    assert user["usage"] == {"date": "2025-01-01", "egress_mb": 123}
    # usage is NOT double-written into personal_settings
    assert "usage" not in user["personal_settings"]


def test_xtv_pro_settings_maps_to_xtv_pro_doc():
    doc = {
        "_id": "xtv_pro_settings",
        "session_string": "deadbeef",
        "tunnel_id": 123,
    }
    result = split_user_settings_doc(doc, public_mode=True, ceo_id=1)
    assert result.global_docs[schema.DOC_XTV_PRO]["session_string"] == "deadbeef"
    assert result.global_docs[schema.DOC_XTV_PRO]["tunnel_id"] == 123


def test_youtube_cookies_maps_to_youtube_cookies_doc():
    doc = {"_id": "youtube_cookies", "cookies": "COOKIEBLOB"}
    result = split_user_settings_doc(doc, public_mode=True, ceo_id=1)
    assert result.global_docs[schema.DOC_YOUTUBE_COOKIES]["cookies"] == "COOKIEBLOB"


def test_unknown_key_lands_in_legacy_misc():
    doc = {"_id": "public_mode_config", "never_seen_key_zzz": 7}
    result = split_user_settings_doc(doc, public_mode=True, ceo_id=1)
    assert (
        result.global_docs[schema.LEGACY_MISC_DOC_ID]["never_seen_key_zzz"] == 7
    )
    assert ("public_mode_config", "never_seen_key_zzz") in result.unknown_keys


def test_unknown_doc_shape_preserved_verbatim():
    doc = {"_id": "totally_random", "blob": {"a": 1}}
    result = split_user_settings_doc(doc, public_mode=True, ceo_id=1)
    assert result.verbatim_legacy["legacy_totally_random"] == {"blob": {"a": 1}}
    assert not result.global_docs
    assert not result.user_updates


def test_tangled_realworld_snapshot():
    # Mixed doc: non-public CEO with templates + global feature toggles in
    # the same document, the way older deployments ended up.
    doc = {
        "_id": "global_settings",
        "bot_name": "OldBot",
        "thumbnail_file_id": "PIC",
        "myfiles_enabled": True,
        "global_daily_egress_mb": 500,
        "dumb_channels": {"-100": "Movies"},
        "ghost_field": "keep me anyway",
    }
    result = split_user_settings_doc(doc, public_mode=False, ceo_id=123)
    assert result.global_docs[schema.DOC_BRANDING]["bot_name"] == "OldBot"
    assert result.global_docs[schema.DOC_EGRESS_LIMITS][
        "global_daily_egress_mb"
    ] == 500
    assert result.global_docs[schema.DOC_MYFILES_CONFIG]["myfiles_enabled"] is True
    assert result.user_updates[123]["personal_settings"]["thumbnail_file_id"] == "PIC"
    assert result.user_updates[123]["personal_settings"]["dumb_channels"] == {
        "-100": "Movies"
    }
    assert ("global_settings", "ghost_field") in result.unknown_keys
    assert (
        result.global_docs[schema.LEGACY_MISC_DOC_ID]["ghost_field"]
        == "keep me anyway"
    )
