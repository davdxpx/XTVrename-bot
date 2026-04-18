"""Guard-rail test: some One-Click hosters (Render / Koyeb / Railway)
scan the repository for the word `torrent` and ban the app on sight.

The torrent-capable build lives on a separate branch; this branch must
stay word-clean under tools/, plugins/, utils/, main.py, config.py.

Readme / license / docs are exempt because those files describe
*absence* of the feature.
"""

from __future__ import annotations

import pathlib
import re

_BANNED = re.compile(r"(?i)\b(torrent|magnet|qbittorrent|qbit)\b")
_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCOPE = ("tools", "plugins", "utils")
_SINGLE_FILES = ("main.py", "config.py")


def _iter_python_files():
    for bucket in _SCOPE:
        root = _REPO / bucket
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            yield path
    for single in _SINGLE_FILES:
        p = _REPO / single
        if p.exists():
            yield p


def test_no_banned_hoster_keywords():
    offenders: list[tuple[str, int, str]] = []
    for path in _iter_python_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _BANNED.search(line):
                offenders.append((str(path.relative_to(_REPO)), lineno, line))
    assert not offenders, (
        "Banned hoster keywords found (move those code paths to the "
        "separate torrent-edition branch):\n"
        + "\n".join(f"  {p}:{ln}: {src}" for p, ln, src in offenders[:25])
    )
