"""Unit tests for utils.tmdb.gate.is_tmdb_available / tmdb_required_message."""

import pytest

from config import Config
from utils.tmdb.gate import is_tmdb_available, tmdb_required_message


@pytest.fixture
def reset_tmdb_key():
    original = Config.TMDB_API_KEY
    yield
    Config.TMDB_API_KEY = original


def test_is_tmdb_available_when_key_set(reset_tmdb_key):
    Config.TMDB_API_KEY = "abc123"
    assert is_tmdb_available() is True


def test_is_tmdb_available_when_key_none(reset_tmdb_key):
    Config.TMDB_API_KEY = None
    assert is_tmdb_available() is False


def test_is_tmdb_available_when_key_blank(reset_tmdb_key):
    Config.TMDB_API_KEY = ""
    assert is_tmdb_available() is False


def test_is_tmdb_available_when_key_whitespace(reset_tmdb_key):
    Config.TMDB_API_KEY = "   "
    assert is_tmdb_available() is False


def test_tmdb_required_message_mentions_feature_name():
    msg = tmdb_required_message("Movie poster lookup")
    assert "Movie poster lookup" in msg
    assert "TMDb" in msg
    assert "TMDB_API_KEY" in msg
