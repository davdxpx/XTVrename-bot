"""Uploader protocol and registry.

Each concrete uploader is a subclass of `Uploader` that decorates itself
with `@register_uploader`. The config UI and MyFiles pickers iterate the
registry to render destination buttons.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Type

if TYPE_CHECKING:
    from tools.mirror_leech.Tasks import MLContext, UploadResult


@dataclass(frozen=True)
class QuotaInfo:
    """Per-destination storage usage snapshot.

    `total_bytes` and `free_bytes` may be None for providers that expose
    only one of the two (e.g. an S3-like endpoint might surface
    used_bytes without a hard cap). Callers should handle every field
    being None gracefully and render only what's available.
    """

    used_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    free_bytes: Optional[int] = None

    @property
    def fraction_used(self) -> Optional[float]:
        if self.total_bytes and self.total_bytes > 0 and self.used_bytes is not None:
            return max(0.0, min(1.0, self.used_bytes / self.total_bytes))
        return None


class Uploader(ABC):
    #: short unique id used in callback_data, registry lookups, and task records
    id: str = ""
    display_name: str = ""
    #: True when the uploader needs per-user credentials (OAuth, API key, ...)
    needs_credentials: bool = True
    #: required system binary; if missing, the uploader is skipped in menus
    binary_required: str | None = None
    #: optional python package that must import for the uploader to run
    python_import_required: str | None = None

    @classmethod
    def available(cls) -> bool:
        """System / library precondition. False → hidden from menus."""
        if cls.binary_required:
            import shutil
            if shutil.which(cls.binary_required) is None:
                return False
        if cls.python_import_required:
            try:
                __import__(cls.python_import_required)
            except ImportError:
                return False
        return True

    @abstractmethod
    async def is_configured(self, user_id: int) -> bool:
        """True when the current user has working credentials stored."""

    @abstractmethod
    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        """Return (ok, human_message) after a live probe."""

    @abstractmethod
    async def upload(
        self, ctx: "MLContext", local_path: Path
    ) -> "UploadResult":
        """Upload `local_path` to the user's configured destination."""

    async def get_quota(self, user_id: int) -> Optional[QuotaInfo]:
        """Return storage usage for this destination, or None when the
        provider doesn't expose a quota API (S3-like, generic WebDAV
        without DAV:quota, ...). Default is None so uploaders opt in."""
        return None


_registry: list[Type[Uploader]] = []


def register_uploader(cls: Type[Uploader]) -> Type[Uploader]:
    if cls not in _registry:
        _registry.append(cls)
    return cls


def all_uploaders() -> list[Type[Uploader]]:
    return list(_registry)


def uploader_by_id(uploader_id: str) -> Type[Uploader] | None:
    for cls in _registry:
        if cls.id == uploader_id:
            return cls
    return None


def available_uploaders() -> list[Type[Uploader]]:
    return [cls for cls in _registry if cls.available()]
