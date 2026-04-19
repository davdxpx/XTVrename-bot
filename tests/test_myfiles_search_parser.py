"""MyFiles search DSL → MongoDB filter."""

import datetime

from utils.myfiles.search import build_query


def test_user_scope_and_soft_delete_filter_default():
    q = build_query("", user_id=42)
    assert q["user_id"] == 42
    assert q["is_deleted"] == {"$ne": True}


def test_tag_include_and_exclude():
    q = build_query("tag:urlaub -tag:alt", user_id=1)
    assert q["tags"]["$all"] == ["urlaub"]
    assert q["tags"]["$nin"] == ["alt"]


def test_extension_regex():
    q = build_query("ext:mp4", user_id=1)
    assert q["file_name"]["$regex"].endswith(r"\.mp4$")


def test_size_gt_and_lt_with_units():
    q = build_query("size:>500mb", user_id=1)
    assert q["size_bytes"]["$gt"] == 500 * 1024 ** 2
    q = build_query("size:<1gb", user_id=1)
    assert q["size_bytes"]["$lt"] == 1 * 1024 ** 3


def test_date_filters():
    q = build_query("before:2026-01 after:2025-06", user_id=1)
    assert q["created_at"]["$lt"] == datetime.datetime(2026, 1, 1)
    assert q["created_at"]["$gte"] == datetime.datetime(2025, 6, 1)


def test_freetext_becomes_filename_regex():
    q = build_query("beach photos", user_id=1)
    assert "file_name" in q
    pat = q["file_name"]["$regex"]
    assert "beach" in pat and "photos" in pat
    assert q["file_name"]["$options"] == "i"


def test_garbage_tokens_are_ignored_gracefully():
    # No crash, and user_id scope survives.
    q = build_query("???? tag: size:lol", user_id=7)
    assert q["user_id"] == 7
