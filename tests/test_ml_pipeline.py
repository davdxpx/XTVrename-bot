"""Mirror-Leech pipeline integration — fake downloader + uploader.

Verifies that `run_task`:
  - routes progress through the injected progress_cb
  - writes UploadResult rows for each uploader
  - transitions status through downloading → uploading → (done) and
    that the caller sees the right values on the MLTask.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tools.mirror_leech.Tasks import MLContext, MLTask, UploadResult
from tools.mirror_leech import downloaders, uploaders
from tools.mirror_leech.Runner import run_task


@pytest.fixture
def fake_provider_registry(monkeypatch):
    """Install a fake downloader + uploader, clear on teardown."""
    captured_progress: list[tuple[float, float, float]] = []

    class _FakeDown(downloaders.Downloader):
        id = "fake_down"
        display_name = "fake"

        @classmethod
        async def accepts(cls, source: str, context: dict) -> bool:
            return source.startswith("fake:")

        async def download(self, ctx: MLContext) -> Path:
            ctx.status("downloading")
            for done in (10.0, 50.0, 100.0):
                ctx.progress(done, 100.0, done)
            target = ctx.temp_dir / "artifact.bin"
            target.write_bytes(b"payload")
            return target

    class _FakeUp(uploaders.Uploader):
        id = "fake_up"
        display_name = "fake-up"
        needs_credentials = False

        async def is_configured(self, user_id: int) -> bool:
            return True

        async def test_connection(self, user_id: int) -> tuple[bool, str]:
            return True, "ok"

        async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
            captured_progress.extend([(0, 0, 0)])  # simple touchpoint
            return UploadResult("fake_up", ok=True, url="https://example/ok")

    # Inject into private registries; remove on teardown.
    downloaders._registry.append(_FakeDown)
    uploaders._registry.append(_FakeUp)
    yield captured_progress
    downloaders._registry.remove(_FakeDown)
    uploaders._registry.remove(_FakeUp)


@pytest.mark.asyncio
async def test_run_task_happy_path(tmp_path, fake_provider_registry, monkeypatch):
    # Redirect the runner's temp root into tmp_path so we don't pollute the
    # bot's real DOWNLOAD_DIR.
    import tools.mirror_leech.Runner as runner_mod
    monkeypatch.setattr(runner_mod, "_TEMP_ROOT", tmp_path)

    task = MLTask.new(
        user_id=42,
        source="fake:demo",
        downloader_id="fake_down",
        uploader_ids=["fake_up"],
    )
    seen: list[str] = []

    async def progress_cb(t: MLTask) -> None:
        seen.append(t.status)

    await run_task(task, client=None, progress_cb=progress_cb)
    # Let any fire-and-forget progress callbacks finish.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Final status when run_task returns is "uploading" — the worker pool
    # is what promotes it to "done" after run_task resolves cleanly.
    assert task.status == "uploading"
    # Progress callback must have been invoked at least once (the awaited
    # "uploading" transition always fires).
    assert "uploading" in seen
    # Upload landed a result row with the expected URL.
    assert any(r.ok and r.url == "https://example/ok" for r in task.results)
    # Download phase actually mutated the fraction all the way to 1.0.
    assert task.progress_fraction == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_run_task_uploader_missing_becomes_error(tmp_path, fake_provider_registry, monkeypatch):
    import tools.mirror_leech.Runner as runner_mod
    monkeypatch.setattr(runner_mod, "_TEMP_ROOT", tmp_path)

    task = MLTask.new(
        user_id=1,
        source="fake:demo",
        downloader_id="fake_down",
        uploader_ids=["nonexistent_up"],
    )
    await run_task(task, client=None)
    assert task.results and task.results[0].ok is False
    assert "unknown uploader" in task.results[0].message
