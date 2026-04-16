"""Tests for the Mirror-Leech picker ContextStore."""

import time

from tools.mirror_leech import ContextStore


def test_put_then_get_roundtrip():
    ctx = ContextStore.PickerContext(user_id=1, source="https://x")
    cid = ContextStore.put(ctx)
    assert ContextStore.get(cid) is ctx


def test_get_unknown_returns_none():
    assert ContextStore.get("nope99") is None


def test_drop_removes_entry():
    ctx = ContextStore.PickerContext(user_id=1, source="https://x")
    cid = ContextStore.put(ctx)
    ContextStore.drop(cid)
    assert ContextStore.get(cid) is None


def test_expired_entry_returns_none(monkeypatch):
    ctx = ContextStore.PickerContext(user_id=1, source="https://x")
    cid = ContextStore.put(ctx)
    # Fast-forward the clock past the TTL.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + ContextStore._TTL_SECONDS + 1)
    assert ContextStore.get(cid) is None


def test_id_is_callback_data_sized():
    cid = ContextStore.new_id()
    # Callback_data is 64 bytes total. Our id is ≤8 chars, leaves tons of room.
    assert len(cid.encode()) <= 8
