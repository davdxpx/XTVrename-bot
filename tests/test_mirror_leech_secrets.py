"""Tests for Mirror-Leech Fernet-based credential encryption."""

import pytest

from config import Config
from tools.mirror_leech import Secrets


@pytest.fixture
def fresh_key():
    original = Config.SECRETS_KEY
    Config.SECRETS_KEY = Secrets.generate_key()
    yield Config.SECRETS_KEY
    Config.SECRETS_KEY = original


@pytest.fixture
def no_key():
    original = Config.SECRETS_KEY
    Config.SECRETS_KEY = None
    yield
    Config.SECRETS_KEY = original


@pytest.fixture
def bad_key():
    original = Config.SECRETS_KEY
    Config.SECRETS_KEY = "not-a-fernet-key"
    yield
    Config.SECRETS_KEY = original


def test_encrypt_decrypt_roundtrip(fresh_key):
    token = Secrets.encrypt("s3cret-refresh-token")
    assert token != "s3cret-refresh-token"
    assert Secrets.decrypt(token) == "s3cret-refresh-token"


def test_is_available_flipflop(fresh_key, no_key, bad_key):
    # fresh_key fixture already left the module in a usable state, but the
    # chained fixtures teach pytest to run each one in isolation: we just
    # re-read the current state here.
    Config.SECRETS_KEY = Secrets.generate_key()
    assert Secrets.is_available() is True
    Config.SECRETS_KEY = ""
    assert Secrets.is_available() is False
    Config.SECRETS_KEY = "not-a-fernet-key"
    assert Secrets.is_available() is False


def test_encrypt_without_key_raises(no_key):
    with pytest.raises(RuntimeError):
        Secrets.encrypt("whatever")


def test_decrypt_without_key_returns_none(no_key):
    assert Secrets.decrypt("any") is None


def test_decrypt_corrupt_token_returns_none(fresh_key):
    assert Secrets.decrypt("this-is-not-a-fernet-token") is None


def test_generate_key_is_valid_fernet_key():
    key = Secrets.generate_key()
    assert isinstance(key, str)
    # A Fernet key is 44-char base64 (32 bytes + '=' padding)
    assert len(key) == 44
