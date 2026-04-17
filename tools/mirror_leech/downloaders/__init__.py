"""Downloader protocol and registry.

Each concrete downloader is a subclass of `Downloader` that decorates
itself with `@register_downloader`. The Controller iterates the registry
in registration order and picks the first downloader whose `accepts()`
returns True.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from tools.mirror_leech.Tasks import MLContext


class Downloader(ABC):
    #: short unique id used in callback_data and task records
    id: str = ""
    display_name: str = ""
    needs_credentials: bool = False

    @classmethod
    @abstractmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        """Return True iff this downloader can handle `source`."""

    @abstractmethod
    async def download(self, ctx: "MLContext") -> Path:
        """Fetch `ctx.source` into a file under `ctx.temp_dir` and return
        the resulting path. Report progress via `ctx.progress(...)`."""


_registry: list[Type[Downloader]] = []


def register_downloader(cls: Type[Downloader]) -> Type[Downloader]:
    """Class decorator — appends `cls` to the downloader registry in
    insertion order. The Controller picks the first matcher, so order
    providers by specificity (most specific first)."""
    if cls not in _registry:
        _registry.append(cls)
    return cls


def all_downloaders() -> list[Type[Downloader]]:
    return list(_registry)


def downloader_by_id(downloader_id: str) -> Type[Downloader] | None:
    for cls in _registry:
        if cls.id == downloader_id:
            return cls
    return None
