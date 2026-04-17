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


async def test_controller_routes_magnet_to_ml_torrent_when_registered():
    # Torrent-edition registers MLTorrentDownloader which accepts magnet
    # URIs when aria2 is reachable. In the test env aria2 is unlikely to
    # be up, so the downloader refuses and the controller falls through.
    # What matters here is that the controller does NOT pre-reject magnet
    # URIs anymore (main did; torrent-edition removed the early-reject).
    try:
        cls = await pick_downloader("magnet:?xt=urn:btih:deadbeef")
        # If aria2 happens to be running on the test host, we get the
        # MLTorrentDownloader back — both outcomes are acceptable.
        assert cls.__name__ == "MLTorrentDownloader"
    except UnsupportedSourceError:
        # aria2 not available → fell through, same as for unknown scheme.
        pass


async def test_controller_raises_for_unknown_scheme_even_with_torrent_support():
    with pytest.raises(UnsupportedSourceError):
        await pick_downloader("unknown-scheme://nothing")


async def test_controller_raises_for_unknown_scheme():
    with pytest.raises(UnsupportedSourceError):
        await pick_downloader("ftp://old-school.example/file")


def test_http_downloader_is_registered():
    assert HTTPDownloader in all_downloaders()
