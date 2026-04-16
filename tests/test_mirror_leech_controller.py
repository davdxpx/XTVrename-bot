"""Tests for the Mirror-Leech Controller routing."""

import pytest

from tools.mirror_leech.Controller import (
    UnsupportedSourceError,
    pick_downloader,
)
from tools.mirror_leech.downloaders import all_downloaders
from tools.mirror_leech.downloaders.HTTPDownloader import HTTPDownloader


async def test_controller_routes_http_to_http_downloader():
    cls = await pick_downloader("https://example.com/file.mkv")
    assert cls is HTTPDownloader


async def test_controller_routes_http_with_query():
    cls = await pick_downloader("http://example.com/get?id=7")
    assert cls is HTTPDownloader


async def test_controller_rejects_magnet_with_user_message():
    with pytest.raises(UnsupportedSourceError) as exc:
        await pick_downloader("magnet:?xt=urn:btih:deadbeef")
    assert "torrent" in str(exc.value).lower()


async def test_controller_rejects_torrent_file_with_user_message():
    with pytest.raises(UnsupportedSourceError) as exc:
        await pick_downloader("https://tracker.example/release.torrent")
    assert "torrent" in str(exc.value).lower()


async def test_controller_raises_for_unknown_scheme():
    with pytest.raises(UnsupportedSourceError):
        await pick_downloader("ftp://old-school.example/file")


def test_http_downloader_is_registered():
    assert HTTPDownloader in all_downloaders()
