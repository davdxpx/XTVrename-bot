# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""Mirror-Leech Pyrogram plugin.

Registers commands (`/ml`, `/mirror`, `/leech`) and every `ml_*`
callback query handler. Heavy logic lives in tools/mirror_leech/*;
this file is the wiring layer that knows about Pyrogram.

Callback-data grammar (see Phase D plan for the full table):
    ml_cfg                         → user config root
    ml_cfg_up_<provider>           → per-provider config screen
    ml_cfg_test_<provider>         → test connection
    ml_cfg_clr_<provider>          → clear stored credential
    ml_cfg_paste_<provider>        → prompt user to paste token
    ml_cfg_guide_<provider>        → open guide page 1 for provider
    ml_cfg_guide_<provider>_<page> → jump to page N (1-indexed)
    ml_opt_single_<file_id>        → MyFiles single-file entry
    ml_opt_multi_<state_key>       → MyFiles multi-select entry
    ml_prov_<uploader>_<ctx_id>    → pick uploader for picker context
    ml_go_<ctx_id>                 → start task(s)
    ml_cancel_<task_id>            → cancel running task
    ml_queue                       → user queue
    ml_admin                       → CEO admin screen
    ml_preset_list                 → list / manage destination presets
    ml_preset_new                  → start "new preset" wizard (label first)
    ml_preset_edit_<slug>          → open edit draft for existing preset
    ml_preset_delete_<slug>        → delete-with-confirm
    ml_preset_delconf_<slug>       → confirm delete
    ml_preset_tgl_<provider>       → toggle provider in current draft
    ml_preset_save                 → commit current draft
    ml_preset_cancel               → discard current draft
    ml_preset_use_<slug>_<ctx_id>  → apply preset to active /ml picker
"""

from __future__ import annotations

import contextlib

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from plugins.help.mirror_leech_guides import get_guide
from tools.mirror_leech import ContextStore
from tools.mirror_leech.Controller import (
    UnsupportedSourceError,
    pick_downloader,
)
from tools.mirror_leech.UIChrome import frame_plain as frame
from tools.mirror_leech.uploaders import available_uploaders
from utils.telegram.log import get_logger

logger = get_logger("plugins.mirror_leech_ui")


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="ml_cancel_picker")]]
    )


async def _configured_uploader_ids(user_id: int) -> list[str]:
    """Return the uploader ids the user has credentials for AND the bot
    supports (binary / python import present)."""
    configured: list[str] = []
    for cls in available_uploaders():
        try:
            if await cls().is_configured(user_id):
                configured.append(cls.id)
        except Exception:
            continue
    return configured


async def _render_uploader_picker(
    client: Client,
    chat_id: int,
    message_id: int,
    cid: str,
    user_id: int,
) -> None:
    """Edit / send the "pick a destination" keyboard for picker ctx `cid`."""
    ctx = ContextStore.get(cid)
    if not ctx:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="⌛ Mirror-Leech picker expired — run /ml again to retry.",
        )
        return

    configured = await _configured_uploader_ids(user_id)

    if not configured:
        body = (
            "> No destinations configured yet.\n"
            "> Open `/settings → ☁️ Mirror-Leech` (public mode) or\n"
            "> `/admin → ☁️ Mirror-Leech Config` (non-public) to link a\n"
            "> provider, then run /ml again."
        )
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=frame("☁️ **Mirror-Leech — Setup Required**", body),
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("⚙️ Open config", callback_data="ml_cfg")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="ml_cancel_picker")],
                ]
            ),
        )
        return

    rows: list[list[InlineKeyboardButton]] = []
    from tools.mirror_leech import Presets
    from tools.mirror_leech.uploaders import uploader_by_id

    # Preset quick-select row(s): only show presets that reference at
    # least one provider this user has actually configured — an "archive"
    # preset that lists s3+b2 is pointless while s3 is unlinked.
    presets = await Presets.get_presets(user_id)
    configured_set = set(configured)
    for preset in presets.values():
        usable = [p for p in preset.providers if p in configured_set]
        if not usable:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    f"🎯 {preset.label} ({len(usable)})",
                    callback_data=f"ml_preset_use_{preset.slug}_{cid}",
                )
            ]
        )

    selected = set(ctx.selected_uploaders)
    for up_id in configured:
        cls = uploader_by_id(up_id)
        if cls is None:
            continue
        marker = "✅ " if up_id in selected else "▫️ "
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker}{cls.display_name}",
                    callback_data=f"ml_prov_{up_id}_{cid}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                f"🚀 Start ({len(selected)})", callback_data=f"ml_go_{cid}"
            ),
            InlineKeyboardButton("❌ Cancel", callback_data="ml_cancel_picker"),
        ]
    )

    from tools.mirror_leech.downloaders import downloader_by_id

    dl_cls = downloader_by_id(ctx.candidate_downloader or "")
    dl_line = dl_cls.display_name if dl_cls else "auto"
    preview = ctx.source
    if len(preview) > 60:
        preview = preview[:57] + "…"

    body = (
        f"> 📥 `{dl_line}`\n"
        f"> 🔗 `{preview}`\n"
        f"\n"
        f"Tap to toggle destinations, then **Start**."
    )
    await client.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=frame("☁️ **Mirror-Leech — Pick Destinations**", body),
        reply_markup=InlineKeyboardMarkup(rows),
    )


@Client.on_callback_query(filters.regex(r"^ml_prov_([a-z0-9_]+)_([A-Za-z0-9_-]{4,10})$"))
async def ml_toggle_uploader(client: Client, callback_query: CallbackQuery) -> None:
    """Toggle a destination on/off inside the picker for ctx_id."""
    _, _, rest = callback_query.data.partition("ml_prov_")
    up_id, _, cid = rest.rpartition("_")
    ctx = ContextStore.get(cid)
    if not ctx:
        await callback_query.answer("Picker expired — run /ml again.", show_alert=True)
        return
    if ctx.user_id != callback_query.from_user.id:
        await callback_query.answer("This picker belongs to another user.", show_alert=True)
        return

    if up_id in ctx.selected_uploaders:
        ctx.selected_uploaders.remove(up_id)
    else:
        ctx.selected_uploaders.append(up_id)

    await callback_query.answer()
    await _render_uploader_picker(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        cid,
        callback_query.from_user.id,
    )


async def _feature_enabled() -> bool:
    from db import db

    toggles = await db.get_setting("feature_toggles", {}) if db else {}
    if isinstance(toggles, dict):
        return bool(toggles.get("mirror_leech", False))
    return False


@Client.on_message(filters.command(["ml", "mirror", "leech"]) & filters.private)
async def ml_command(client: Client, message: Message) -> None:
    """Entry-point for `/ml <url>` / `/mirror <url>` / `/leech <url>`."""
    if not await _feature_enabled():
        await message.reply_text(
            frame(
                "🚧 **Mirror-Leech — Disabled**",
                "> Mirror-Leech is not enabled on this bot yet.\n"
                "> An admin needs to flip `feature_toggles.mirror_leech`\n"
                "> on from the `/admin → Mirror-Leech Config` panel.",
            )
        )
        return

    parts = (message.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "Usage: `/ml <url>`\n\n"
            "Supported: direct HTTP(S), YouTube / social video (yt-dlp),\n"
            "Telegram file refs, and RSS feeds.",
        )
        return

    source = parts[1].strip()
    try:
        dl_cls = await pick_downloader(source)
    except UnsupportedSourceError as exc:
        await message.reply_text(str(exc))
        return

    # Stash picker state so the uploader-pick keyboard can reference it via
    # a short ctx_id (callback_data is limited to 64 bytes).
    cid = ContextStore.put(
        ContextStore.PickerContext(
            user_id=message.from_user.id,
            source=source,
            candidate_downloader=dl_cls.id,
            origin_chat_id=message.chat.id,
            origin_msg_id=message.id,
        )
    )

    prompt = await message.reply_text(
        frame(
            "⏳ **Mirror-Leech — Preparing**",
            f"> 📥 Using **{dl_cls.display_name}**\n"
            f"> Building destination picker…",
        ),
        reply_markup=_cancel_kb(),
    )
    await _render_uploader_picker(
        client, message.chat.id, prompt.id, cid, message.from_user.id
    )


@Client.on_callback_query(filters.regex(r"^ml_cancel_picker$"))
async def ml_cancel_picker(client: Client, callback_query: CallbackQuery) -> None:
    """Best-effort dismiss of an in-progress picker message."""
    with contextlib.suppress(Exception):
        await callback_query.message.edit_text(
            frame(
                "🚫 **Mirror-Leech — Cancelled**",
                "> Picker dismissed. Run `/ml <url>` again when you're ready.",
            )
        )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_go_([A-Za-z0-9_-]{4,10})$"))
async def ml_start_task(client: Client, callback_query: CallbackQuery) -> None:
    """Resolve the picker context and schedule MLTask(s).

    Single-source pickers (`/ml <url>` or MyFiles single-file) queue one
    task whose uploader_ids is the whole selection, running downloads +
    uploads once. Multi-file pickers (MyFiles multi-select) fan out one
    task per file — each task itself still fans out over the selected
    uploaders, so `N files × M destinations = N tasks × M uploads`.
    """
    from tools.mirror_leech.ProgressRender import (
        render_task_text,
        update_progress_message,
    )
    from tools.mirror_leech.Runner import run_task
    from tools.mirror_leech.Tasks import MLTask, ml_worker_pool

    cid = callback_query.data.removeprefix("ml_go_")
    ctx = ContextStore.get(cid)
    if not ctx:
        await callback_query.answer("Picker expired — run /ml again.", show_alert=True)
        return
    if ctx.user_id != callback_query.from_user.id:
        await callback_query.answer("This picker belongs to another user.", show_alert=True)
        return
    if not ctx.selected_uploaders:
        await callback_query.answer("Pick at least one destination first.", show_alert=True)
        return

    await callback_query.answer("Queued.")

    # Multi-file fan-out: resolve per-file sources now, queue one MLTask
    # per file. Single-source path falls through the same code with a
    # single dummy entry.
    if ctx.file_ids:
        sources: list[tuple[str, str | None]] = []
        for fid in ctx.file_ids:
            ref = await _tg_ref_for_myfile(fid)
            if ref:
                sources.append((fid, ref))
        if not sources:
            await callback_query.answer(
                "Selected files are no longer accessible.", show_alert=True
            )
            return
        summary_lines = [
            f"> 🗃 Queued **{len(sources)}** file(s) →",
            "> 📤 " + ", ".join(f"`{u}`" for u in ctx.selected_uploaders),
            "",
        ]
        first_task_id: str | None = None
        for idx, (_, source) in enumerate(sources, start=1):
            task = MLTask.new(
                user_id=ctx.user_id,
                source=source,
                downloader_id="telegram",
                uploader_ids=list(ctx.selected_uploaders),
            )
            task.message_chat_id = callback_query.message.chat.id
            # Only the first task edits the picker message; the rest
            # spawn fresh progress messages below to avoid overwriting
            # each other.
            if first_task_id is None:
                task.message_id = callback_query.message.id
                first_task_id = task.id
            else:
                fresh = await client.send_message(
                    callback_query.message.chat.id,
                    f"⏳ Queued task `{task.id}` ({idx}/{len(sources)})",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⏹ Cancel", callback_data=f"ml_cancel_{task.id}")]]
                    ),
                )
                task.message_id = fresh.id
            summary_lines.append(f"• `{task.id}` — queued")

            async def _runner(t: MLTask) -> None:
                try:
                    await run_task(
                        t,
                        client,
                        progress_cb=lambda current: update_progress_message(client, current),
                    )
                except Exception as exc:
                    t.status = "failed"
                    t.error = str(exc)
                    await update_progress_message(client, t)
                    raise
                await update_progress_message(client, t)

            try:
                ml_worker_pool.enqueue(task, _runner)
            except Exception as exc:
                logger.exception(
                    "enqueue failed for batch task %s", task.id
                )
                summary_lines.append(
                    f"  ⚠️ `{task.id}` could not be started: {exc}"
                )

        ContextStore.drop(cid)
        # Replace the picker with a batch-summary header.
        with contextlib.suppress(Exception):
            await client.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.id,
                text=frame(
                    "☁️ **Mirror-Leech — Batch Queued**",
                    "\n".join(summary_lines),
                ),
            )
        return

    # Single-source path (either /ml url or MyFiles single-file).
    task = MLTask.new(
        user_id=ctx.user_id,
        source=ctx.source,
        downloader_id=ctx.candidate_downloader or "",
        uploader_ids=list(ctx.selected_uploaders),
    )
    task.message_chat_id = callback_query.message.chat.id
    task.message_id = callback_query.message.id

    # Prime the progress message so the user sees something immediately.
    with contextlib.suppress(Exception):
        await callback_query.message.edit_text(
            render_task_text(task),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⏹ Cancel", callback_data=f"ml_cancel_{task.id}")]]
            ),
        )

    ContextStore.drop(cid)

    async def _runner(t: MLTask) -> None:
        # Always flush the UI with the real terminal state — run_task
        # propagates downloader / uploader exceptions without mutating
        # `status`, so we set it here before the final edit. Otherwise
        # the message stays stuck at "Downloading" forever.
        try:
            await run_task(
                t,
                client,
                progress_cb=lambda current: update_progress_message(client, current),
            )
        except Exception as exc:
            t.status = "failed"
            t.error = str(exc)
            await update_progress_message(client, t)
            raise
        await update_progress_message(client, t)

    try:
        ml_worker_pool.enqueue(task, _runner)
        logger.info(
            "ml_start_task queued single task %s for user %s",
            task.id, ctx.user_id,
        )
    except Exception as exc:
        logger.exception("enqueue failed for task %s", task.id)
        with contextlib.suppress(Exception):
            await callback_query.message.edit_text(
                f"❌ Could not start task: `{exc}`"
            )


@Client.on_callback_query(filters.regex(r"^ml_cancel_([0-9a-f]{6,16})$"))
async def ml_cancel_running(client: Client, callback_query: CallbackQuery) -> None:
    """Signal cancel on a running task and ack the user."""
    from tools.mirror_leech.Tasks import ml_worker_pool

    task_id = callback_query.data.removeprefix("ml_cancel_")
    task = ml_worker_pool.get(task_id)
    if not task:
        await callback_query.answer("Task already done or unknown.", show_alert=True)
        return
    if task.user_id != callback_query.from_user.id:
        await callback_query.answer("Not your task.", show_alert=True)
        return
    ml_worker_pool.cancel(task_id)
    await callback_query.answer("Cancel requested.")


@Client.on_message(filters.command("mlqueue") & filters.private)
async def ml_queue_command(client: Client, message: Message) -> None:
    await _render_queue(client, message.chat.id, None, message.from_user.id)


@Client.on_callback_query(filters.regex(r"^ml_queue$"))
async def ml_queue_callback(client: Client, callback_query: CallbackQuery) -> None:
    await _render_queue(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        callback_query.from_user.id,
    )
    await callback_query.answer()


async def _render_queue(
    client: Client,
    chat_id: int,
    message_id: int | None,
    user_id: int,
) -> None:
    from tools.mirror_leech.Tasks import ml_worker_pool

    tasks = ml_worker_pool.list_for_user(user_id)[:20]
    rows: list[list[InlineKeyboardButton]] = []
    if not tasks:
        body = "> 📭 Your Mirror-Leech queue is empty."
    else:
        icon = {
            "queued": "⏳",
            "downloading": "⬇️",
            "uploading": "☁️",
            "done": "✅",
            "failed": "❌",
            "cancelled": "🚫",
        }
        lines: list[str] = []
        for t in tasks:
            lines.append(
                f"{icon.get(t.status, '•')} `{t.id}` · {t.status} · "
                f"{t.progress_fraction * 100:.0f}%  ·  `{t.source[:50]}`"
            )
            if t.status in ("queued", "downloading", "uploading"):
                rows.append(
                    [
                        InlineKeyboardButton(
                            f"⏹ Cancel `{t.id}`",
                            callback_data=f"ml_cancel_{t.id}",
                        )
                    ]
                )
        body = "\n".join(lines)
    rows.append([InlineKeyboardButton("↻ Refresh", callback_data="ml_queue")])

    text = frame("🗂 **Mirror-Leech — Your Queue**", body)
    markup = InlineKeyboardMarkup(rows)
    if message_id:
        try:
            await client.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup
            )
            return
        except Exception:
            pass
    await client.send_message(chat_id, text, reply_markup=markup)


# ---------------------------------------------------------------------------
# ml_cfg — per-user provider configuration root
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^ml_cfg$"))
async def ml_cfg_root(client: Client, callback_query: CallbackQuery) -> None:
    await _render_cfg_root(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        callback_query.from_user.id,
    )
    await callback_query.answer()


async def _render_cfg_root(
    client: Client,
    chat_id: int,
    message_id: int,
    user_id: int,
) -> None:
    from tools.mirror_leech import Secrets
    from tools.mirror_leech.uploaders import all_uploaders

    lines: list[str] = []
    if not Secrets.is_available():
        lines.append(
            "> 🚨 `SECRETS_KEY` is **not configured** — credentials cannot\n"
            "> be stored until you set it."
        )
        lines.append("")

    rows: list[list[InlineKeyboardButton]] = []
    visible_count = 0
    for cls in all_uploaders():
        if not cls.available():
            # Hide providers the host hasn't enabled (missing binary, missing
            # Python package, missing env var). Admin panel at /admin →
            # Mirror-Leech Config still lists everything for diagnostics.
            continue
        visible_count += 1
        try:
            configured = await cls().is_configured(user_id)
        except Exception:
            configured = False
        if configured:
            badge = "✅"
            suffix = "linked"
        elif cls.needs_credentials:
            badge = "🔑"
            suffix = "link to enable"
        else:
            badge = "▫️"
            suffix = "anonymous OK"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{badge} {cls.display_name} — {suffix}",
                    callback_data=f"ml_cfg_up_{cls.id}",
                )
            ]
        )

    if visible_count == 0:
        body = (
            "> 🚧 No destinations have been enabled by the host admin yet.\n"
            "> Please ask the admin to configure Mirror-Leech providers\n"
            "> (Google Drive, Rclone, MEGA, …) before using this feature."
        )
        rows = [[InlineKeyboardButton("❌ Close", callback_data="ml_cfg_close")]]
        text = frame("☁️ **Mirror-Leech — Destinations**", body)
    else:
        # Presets entry only makes sense once the user has at least 2
        # configured providers — otherwise a "group" is just the provider.
        from tools.mirror_leech import Presets

        preset_count = len(await Presets.get_presets(user_id))
        preset_label = (
            f"🎯 Presets ({preset_count}/{Presets.MAX_PRESETS_PER_USER})"
            if preset_count
            else "🎯 Presets"
        )
        rows.append(
            [InlineKeyboardButton(preset_label, callback_data="ml_preset_list")]
        )
        rows.append([InlineKeyboardButton("🗂 My Queue", callback_data="ml_queue")])
        rows.append([InlineKeyboardButton("❌ Close", callback_data="ml_cfg_close")])

        body = ("\n".join(lines) + "\n"
                if lines else "") + "> Tap a provider to link, test, or clear."
        text = frame("☁️ **Mirror-Leech — Destinations**", body)
    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(rows),
        )
    except Exception:
        await client.send_message(
            chat_id, text, reply_markup=InlineKeyboardMarkup(rows)
        )


@Client.on_callback_query(filters.regex(r"^ml_cfg_close$"))
async def ml_cfg_close(client: Client, callback_query: CallbackQuery) -> None:
    with contextlib.suppress(Exception):
        await callback_query.message.edit_text(
            frame(
                "☁️ **Mirror-Leech — Config Closed**",
                "> Open `/ml` or `/mlqueue` whenever you're ready.",
            )
        )
    await callback_query.answer()


# ---------------------------------------------------------------------------
# ml_cfg_up_<provider> — per-provider drilldown
# ---------------------------------------------------------------------------

# Short hints shown under the provider name so the user knows what to paste.
_PROVIDER_HINTS: dict[str, str] = {
    "gdrive": (
        "Needs an OAuth refresh token + client_id + client_secret. Generate "
        "one via Google's OAuth playground or `rclone config`."
    ),
    "rclone": (
        "Paste your `rclone.conf` body, then set a default remote name "
        "(e.g. `gdrive:XTVBot`)."
    ),
    "mega": "Paste your MEGA email + password.",
    "gofile": "Optional token — anonymous upload works without linking.",
    "pixeldrain": "Optional API key — anonymous upload works without linking.",
    "telegram": "Defaults to DM. Paste a channel id to override.",
    "ddl": "Set DDL_BASE_URL on the bot host to enable one-time download links.",
    "dropbox": (
        "Needs a refresh token + app_key + app_secret from a scoped Dropbox "
        "app at dropbox.com/developers/apps."
    ),
    "onedrive": (
        "Needs a refresh token + client_id + tenant from an Azure/Entra app "
        "registration with Files.ReadWrite + offline_access."
    ),
    "box": (
        "Needs a refresh token + client_id + client_secret from a Box custom "
        "app with Read/Write-all-files scopes."
    ),
    "s3": (
        "Generic S3-compatible destination. Works with AWS, Wasabi, Cloudflare "
        "R2, MinIO, iDrive e2, Storj, and anything else speaking the S3 API."
    ),
    "b2": (
        "Native Backblaze B2 — use this over the S3 endpoint when you want "
        "B2-specific features (capability info, hash verification)."
    ),
    "webdav": (
        "Generic WebDAV — covers Nextcloud, ownCloud, Synology, QNAP, and "
        "any server speaking WebDAV with Basic auth."
    ),
    "seafile": (
        "Seafile via its native REST API. Needs an API token from your "
        "Seafile profile plus the target library's UUID."
    ),
}


@Client.on_callback_query(filters.regex(r"^ml_cfg_up_([a-z0-9_]+)$"))
async def ml_cfg_provider(client: Client, callback_query: CallbackQuery) -> None:
    provider = callback_query.data.removeprefix("ml_cfg_up_")
    await _render_provider_screen(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        callback_query.from_user.id,
        provider,
    )
    await callback_query.answer()


async def _render_provider_screen(
    client: Client,
    chat_id: int,
    message_id: int,
    user_id: int,
    provider: str,
) -> None:
    from tools.mirror_leech import Secrets
    from tools.mirror_leech.uploaders import uploader_by_id

    cls = uploader_by_id(provider)
    if cls is None:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=frame(
                "❓ **Mirror-Leech — Unknown Provider**",
                f"> No provider matches `{provider}` on this host.",
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back", callback_data="ml_cfg")]]
            ),
        )
        return

    try:
        configured = cls.available() and await cls().is_configured(user_id)
    except Exception:
        configured = False

    secrets_ok = Secrets.is_available()
    hint = _PROVIDER_HINTS.get(provider, "")
    status = "✅ Linked" if configured else (
        "🚫 Unavailable on this host" if not cls.available() else "🔑 Not linked"
    )
    body_lines = [f"> **Status:** {status}"]
    if hint:
        body_lines.append("")
        body_lines.append(f"> {hint}")
    if not secrets_ok:
        body_lines.append("")
        body_lines.append(
            "> 🚨 `SECRETS_KEY` is not set — paste-to-link is disabled\n"
            "> until an admin configures it. Test / anonymous flows\n"
            "> still work."
        )

    rows: list[list[InlineKeyboardButton]] = []
    if get_guide(provider) is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    "📖 Setup Guide", callback_data=f"ml_cfg_guide_{provider}"
                )
            ]
        )
    if cls.available():
        rows.append(
            [
                InlineKeyboardButton(
                    "🔌 Test connection", callback_data=f"ml_cfg_test_{provider}"
                )
            ]
        )
        if cls.needs_credentials or provider in {"gofile", "pixeldrain", "telegram"}:
            paste_label = "📝 Paste / update credentials"
            rows.append(
                [InlineKeyboardButton(paste_label, callback_data=f"ml_cfg_paste_{provider}")]
            )
        if configured:
            rows.append(
                [
                    InlineKeyboardButton(
                        "🗑 Clear credential", callback_data=f"ml_cfg_clr_{provider}"
                    )
                ]
            )
    rows.append([InlineKeyboardButton("← Back", callback_data="ml_cfg")])

    text = frame(f"☁️ **{cls.display_name}**", "\n".join(body_lines))
    with contextlib.suppress(Exception):
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(rows),
        )


@Client.on_callback_query(
    filters.regex(r"^ml_cfg_guide_([a-z0-9]+)(?:_(\d+))?$")
)
async def ml_cfg_guide(client: Client, callback_query: CallbackQuery) -> None:
    """Multi-page setup-guide viewer for a destination."""
    match = callback_query.matches[0]
    provider = match.group(1)
    page_arg = match.group(2)

    guide = get_guide(provider)
    if guide is None:
        await callback_query.answer("No guide available.", show_alert=True)
        return

    try:
        page_idx = int(page_arg) if page_arg else 1
    except ValueError:
        page_idx = 1
    page_idx = max(1, min(page_idx, guide.page_count))
    page = guide.pages[page_idx - 1]

    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page_idx > 1:
        nav.append(
            InlineKeyboardButton(
                "← Prev",
                callback_data=f"ml_cfg_guide_{provider}_{page_idx - 1}",
            )
        )
    nav.append(
        InlineKeyboardButton(
            f"Page {page_idx}/{guide.page_count}",
            callback_data=f"ml_cfg_guide_{provider}_{page_idx}",
        )
    )
    if page_idx < guide.page_count:
        nav.append(
            InlineKeyboardButton(
                "Next →",
                callback_data=f"ml_cfg_guide_{provider}_{page_idx + 1}",
            )
        )
    rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                "📝 Paste now", callback_data=f"ml_cfg_paste_{provider}"
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                f"← Back to {guide.display_name}",
                callback_data=f"ml_cfg_up_{provider}",
            )
        ]
    )

    text = frame(
        f"📖 **{guide.display_name} — {page.title}**",
        page.body,
    )
    with contextlib.suppress(Exception):
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(rows),
            disable_web_page_preview=True,
        )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_cfg_test_([a-z0-9_]+)$"))
async def ml_cfg_test(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech.uploaders import uploader_by_id

    provider = callback_query.data.removeprefix("ml_cfg_test_")
    cls = uploader_by_id(provider)
    if cls is None:
        await callback_query.answer("Unknown provider.", show_alert=True)
        return
    try:
        ok, message = await cls().test_connection(callback_query.from_user.id)
    except Exception as exc:
        ok, message = False, f"crashed: {exc}"
    prefix = "✅" if ok else "❌"
    await callback_query.answer(f"{prefix} {message}"[:200], show_alert=True)


@Client.on_callback_query(filters.regex(r"^ml_cfg_clr_([a-z0-9_]+)$"))
async def ml_cfg_clear(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech import Accounts

    provider = callback_query.data.removeprefix("ml_cfg_clr_")
    await Accounts.clear_account(callback_query.from_user.id, provider)
    await callback_query.answer("Credential cleared.")
    await _render_provider_screen(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        callback_query.from_user.id,
        provider,
    )


# ---------------------------------------------------------------------------
# ml_cfg_paste_<provider> — text-input flow for pasting tokens
# ---------------------------------------------------------------------------

# What each provider expects the user to send as plain text. The dicts
# map free-text arriving from the user to the stored fields; anything
# more structured (multi-field forms) would need a multi-step flow which
# is deferred to v1.6.x.
_PROVIDER_PASTE_FORMAT: dict[str, dict[str, str]] = {
    "gdrive": {
        "prompt": (
            "Send your Google OAuth credentials as three lines:\n"
            "```\n<refresh_token>\n<client_id>\n<client_secret>\n```"
        ),
        "mode": "three_secrets:refresh_token,client_id,client_secret",
    },
    "rclone": {
        "prompt": (
            "Paste your rclone.conf contents as a single message, then "
            "reply again with the default remote name in the format "
            "`remote:path`."
        ),
        "mode": "rclone_conf",
    },
    "mega": {
        "prompt": "Send `email password` as one message separated by a space.",
        "mode": "email_password",
    },
    "gofile": {
        "prompt": "Paste your GoFile account token (leave empty to unlink).",
        "mode": "single_secret:token",
    },
    "pixeldrain": {
        "prompt": "Paste your Pixeldrain API key (leave empty to unlink).",
        "mode": "single_secret:api_key",
    },
    "telegram": {
        "prompt": (
            "Send the destination: `dm` (default) or a channel id like "
            "`-1001234567890`."
        ),
        "mode": "plain:destination",
    },
    "ddl": {
        "prompt": "DDL is host-configured via `DDL_BASE_URL`. Nothing to paste.",
        "mode": "noop",
    },
    "dropbox": {
        "prompt": (
            "Send your Dropbox credentials as three lines:\n"
            "```\n<refresh_token>\n<app_key>\n<app_secret>\n```"
        ),
        "mode": "three_secrets:refresh_token,app_key,app_secret",
    },
    "onedrive": {
        "prompt": (
            "Send your OneDrive credentials as three lines:\n"
            "```\n<refresh_token>\n<client_id>\n<tenant>\n```\n"
            "Use `common` as tenant for personal Microsoft accounts."
        ),
        "mode": "three_secrets:refresh_token,client_id,tenant",
    },
    "box": {
        "prompt": (
            "Send your Box credentials as three lines:\n"
            "```\n<refresh_token>\n<client_id>\n<client_secret>\n```"
        ),
        "mode": "three_secrets:refresh_token,client_id,client_secret",
    },
    "s3": {
        "prompt": (
            "Send your S3 config as `key: value` lines. Required:\n"
            "```\n"
            "endpoint: https://s3.eu-central-1.wasabisys.com\n"
            "region: eu-central-1\n"
            "bucket: mybucket\n"
            "access_key: AKIA...\n"
            "secret_key: wJalrXUt...\n"
            "prefix: optional/sub/path\n"
            "```\n"
            "`endpoint` is optional for AWS (default endpoint inferred from "
            "region). `prefix` is optional."
        ),
        "mode": "s3_config",
    },
    "b2": {
        "prompt": (
            "Send your Backblaze B2 config as `key: value` lines:\n"
            "```\n"
            "app_key_id: 005a1b2c3d...\n"
            "app_key: K005f6g7h...\n"
            "bucket: mybucket\n"
            "prefix: optional/sub/path\n"
            "```\n"
            "Create the app key at secure.backblaze.com → App Keys."
        ),
        "mode": "b2_config",
    },
    "webdav": {
        "prompt": (
            "Send your WebDAV config as `key: value` lines. Required:\n"
            "```\n"
            "url: https://cloud.example.com/remote.php/dav/files/alice/\n"
            "username: alice\n"
            "password: <app-password-NOT-account-password>\n"
            "folder: MirrorLeech\n"
            "```\n"
            "`folder` is optional and relative to the WebDAV root. For "
            "Nextcloud / ownCloud, create an **app password** under "
            "Settings → Security instead of pasting your account password."
        ),
        "mode": "webdav_config",
    },
    "seafile": {
        "prompt": (
            "Send your Seafile config as `key: value` lines:\n"
            "```\n"
            "server_url: https://cloud.example.com\n"
            "library_id: 11111111-2222-3333-4444-555555555555\n"
            "api_token: <token from Profile → Settings → API Token>\n"
            "parent_dir: /MirrorLeech\n"
            "```\n"
            "`parent_dir` is optional and defaults to the library root. "
            "The library UUID appears in the URL when you open a library "
            "in the Seafile web UI."
        ),
        "mode": "seafile_config",
    },
}

# In-memory waiting state: user_id -> {"provider": str, "step": str, "tmp": ...}
_paste_state: dict[int, dict] = {}


# Multiline `key: value` paste modes. Each entry declares which keys are
# treated as secrets (Fernet-encrypted) vs plain config fields, plus the
# minimum set required before we accept the submission.
_KEY_VALUE_CONFIG_SCHEMAS: dict[str, dict[str, tuple[str, ...]]] = {
    "s3_config": {
        "secrets": ("access_key", "secret_key"),
        "plain": ("endpoint_url", "region", "bucket", "prefix"),
        "required": ("access_key", "secret_key", "bucket"),
    },
    "b2_config": {
        "secrets": ("app_key_id", "app_key"),
        "plain": ("bucket", "prefix"),
        "required": ("app_key_id", "app_key", "bucket"),
    },
    "webdav_config": {
        "secrets": ("password",),
        "plain": ("url", "username", "folder"),
        "required": ("url", "username", "password"),
    },
    "seafile_config": {
        "secrets": ("api_token",),
        "plain": ("server_url", "library_id", "parent_dir"),
        "required": ("server_url", "library_id", "api_token"),
    },
}


def _parse_key_value_paste(raw: str) -> dict[str, str]:
    """Parse `key: value` lines into a flat dict.

    Comments (`#` prefix), blank lines, and malformed lines are skipped.
    Keys are lowercased and trimmed; the alias `endpoint` normalises to
    `endpoint_url` so users can paste either form interchangeably.
    """
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower()
        v = v.strip()
        if not k or not v:
            continue
        if k == "endpoint":
            k = "endpoint_url"
        out[k] = v
    return out


@Client.on_callback_query(filters.regex(r"^ml_cfg_paste_([a-z0-9_]+)$"))
async def ml_cfg_paste_start(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech import Secrets

    provider = callback_query.data.removeprefix("ml_cfg_paste_")
    fmt = _PROVIDER_PASTE_FORMAT.get(provider)
    if not fmt or fmt["mode"] == "noop":
        await callback_query.answer(
            "Nothing to paste for this provider.", show_alert=True
        )
        return

    needs_secret = fmt["mode"] != "plain:destination"
    if needs_secret and not Secrets.is_available():
        await callback_query.answer(
            "SECRETS_KEY is not configured — admin must set it first.",
            show_alert=True,
        )
        return

    _paste_state[callback_query.from_user.id] = {
        "provider": provider,
        "step": "await_paste",
        "tmp": {},
    }
    await callback_query.answer()
    with contextlib.suppress(Exception):
        await callback_query.message.edit_text(
            f"✏️ **Link {provider}**\n\n" + fmt["prompt"] + "\n\n__Send the next message in this chat.__",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data=f"ml_cfg_up_{provider}")]]
            ),
        )


@Client.on_message(filters.text & filters.private, group=4)
async def _ml_paste_text(client: Client, message: Message) -> None:
    state = _paste_state.get(message.from_user.id)
    if not state:
        return  # not a ML paste message; let other handlers run

    # Preset wizards hijack the paste-state dispatcher — they only need a
    # single free-text line (the label).
    if state.get("provider") == "__preset__":
        await _ml_preset_label_text(client, message, state)
        return

    provider = state["provider"]
    fmt = _PROVIDER_PASTE_FORMAT.get(provider, {})
    mode = fmt.get("mode", "")
    raw = (message.text or "").strip()

    from tools.mirror_leech import Accounts

    try:
        if mode.startswith("single_secret:"):
            field = mode.split(":", 1)[1]
            if raw:
                await Accounts.set_secret(message.from_user.id, provider, field, raw)
            else:
                await Accounts.clear_account(message.from_user.id, provider)
        elif mode.startswith("three_secrets:"):
            fields = mode.split(":", 1)[1].split(",")
            parts = [p for p in raw.splitlines() if p.strip()]
            if len(parts) != len(fields):
                await message.reply_text(
                    f"⚠️ Need {len(fields)} lines; got {len(parts)}. Try again."
                )
                return
            for field, value in zip(fields, parts, strict=True):
                await Accounts.set_secret(
                    message.from_user.id, provider, field, value.strip()
                )
        elif mode == "email_password":
            parts = raw.split(None, 1)
            if len(parts) != 2:
                await message.reply_text(
                    "⚠️ Send `email password` separated by a space."
                )
                return
            email, password = parts
            await Accounts.set_plain(
                message.from_user.id, provider, "email", email.strip()
            )
            await Accounts.set_secret(
                message.from_user.id, provider, "password", password.strip()
            )
        elif mode == "rclone_conf":
            if state["step"] == "await_paste":
                await Accounts.set_secret(
                    message.from_user.id, provider, "conf", raw
                )
                state["step"] = "await_remote"
                await message.reply_text(
                    "✅ Config stored. Now send the default remote name, "
                    "e.g. `gdrive:MediaStudio`."
                )
                return
            if state["step"] == "await_remote":
                await Accounts.set_plain(
                    message.from_user.id, provider, "remote", raw
                )
        elif mode == "plain:destination":
            await Accounts.set_plain(
                message.from_user.id, provider, "destination", raw
            )
        elif mode in _KEY_VALUE_CONFIG_SCHEMAS:
            schema = _KEY_VALUE_CONFIG_SCHEMAS[mode]
            entries = _parse_key_value_paste(raw)
            missing = [f for f in schema["required"] if f not in entries]
            if missing:
                await message.reply_text(
                    "⚠️ Missing required keys: " + ", ".join(missing)
                )
                return
            for key, value in entries.items():
                if key in schema["secrets"]:
                    await Accounts.set_secret(
                        message.from_user.id, provider, key, value
                    )
                elif key in schema["plain"]:
                    await Accounts.set_plain(
                        message.from_user.id, provider, key, value
                    )
                # Unknown keys are ignored so pasting rclone-style configs
                # with extra fields doesn't reject valid credentials.
        else:
            await message.reply_text(f"⚠️ Unsupported paste mode `{mode}`.")
            return
    except RuntimeError as exc:
        await message.reply_text(f"❌ {exc}")
        _paste_state.pop(message.from_user.id, None)
        return
    except Exception as exc:
        await message.reply_text(f"❌ Failed to store credentials: {exc}")
        _paste_state.pop(message.from_user.id, None)
        return

    _paste_state.pop(message.from_user.id, None)
    # Best-effort: delete the user's secret-containing message.
    with contextlib.suppress(Exception):
        await message.delete()
    await message.reply_text(f"✅ `{provider}` linked. Use **Test connection** to verify.")


# ---------------------------------------------------------------------------
# Destination presets — user-defined fan-out groups
# ---------------------------------------------------------------------------
#
# Drafts live in memory while the user is editing — they only reach Mongo
# once the user taps "💾 Save preset". That way we never persist an
# invalid state (zero providers, unresolved rename, etc.).
_preset_drafts: dict[int, dict] = {}  # user_id -> {slug, label, providers, existing}


def _slugify_label(label: str) -> str:
    """Turn a human label into a preset slug. Lowercase, strip non-alnum,
    collapse runs of `_`. Callers must still ensure uniqueness."""
    cleaned = "".join(
        (c.lower() if c.isalnum() else "_") for c in label.strip()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "preset"


async def _unique_slug(user_id: int, base: str) -> str:
    """Return `base` if free, else `base_2`, `base_3`, …"""
    from tools.mirror_leech import Presets

    existing = await Presets.get_presets(user_id)
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


async def _render_preset_list(
    client: Client, chat_id: int, message_id: int, user_id: int
) -> None:
    from tools.mirror_leech import Presets

    presets = await Presets.get_presets(user_id)
    rows: list[list[InlineKeyboardButton]] = []
    if presets:
        for slug, preset in presets.items():
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🎯 {preset.label} ({len(preset.providers)})",
                        callback_data=f"ml_preset_edit_{slug}",
                    ),
                    InlineKeyboardButton(
                        "🗑", callback_data=f"ml_preset_delete_{slug}"
                    ),
                ]
            )

    if len(presets) < Presets.MAX_PRESETS_PER_USER:
        rows.append(
            [InlineKeyboardButton("➕ New preset", callback_data="ml_preset_new")]
        )
    rows.append([InlineKeyboardButton("← Back", callback_data="ml_cfg")])

    if presets:
        body = (
            "> Group your destinations so one tap in `/ml` fans out to all\n"
            "> of them at once. Up to "
            f"{Presets.MAX_PRESETS_PER_USER} presets, "
            f"{Presets.MAX_PROVIDERS_PER_PRESET} providers each."
        )
    else:
        body = (
            "> No presets yet. A preset is a named group of destinations —\n"
            "> tap it in `/ml` to fan a single file out to every provider\n"
            "> in the group without toggling checkboxes each time."
        )

    text = frame("🎯 **Mirror-Leech — Presets**", body)
    with contextlib.suppress(Exception):
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(rows),
        )


@Client.on_callback_query(filters.regex(r"^ml_preset_list$"))
async def ml_preset_list(client: Client, callback_query: CallbackQuery) -> None:
    await _render_preset_list(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        callback_query.from_user.id,
    )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_preset_new$"))
async def ml_preset_new(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech import Presets

    user_id = callback_query.from_user.id
    existing = await Presets.get_presets(user_id)
    if len(existing) >= Presets.MAX_PRESETS_PER_USER:
        await callback_query.answer(
            f"Preset limit reached ({Presets.MAX_PRESETS_PER_USER}). "
            "Delete one first.",
            show_alert=True,
        )
        return

    _paste_state[user_id] = {
        "provider": "__preset__",
        "step": "await_label",
        "tmp": {},
    }
    await callback_query.answer()
    with contextlib.suppress(Exception):
        await callback_query.message.edit_text(
            "🎯 **New preset — label**\n\n"
            "Send a short label for this preset (e.g. `Media Hosts`, "
            "`Cold Storage`). Max 40 characters.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="ml_preset_cancel")]]
            ),
        )


async def _ml_preset_label_text(
    client: Client, message: Message, state: dict
) -> None:
    user_id = message.from_user.id
    label = (message.text or "").strip()
    if not label:
        await message.reply_text("⚠️ Label can't be empty.")
        return
    if len(label) > 40:
        await message.reply_text("⚠️ Label too long (max 40 chars).")
        return

    base_slug = _slugify_label(label)
    slug = await _unique_slug(user_id, base_slug)
    _preset_drafts[user_id] = {
        "slug": slug,
        "label": label,
        "providers": [],
        "existing": False,
    }
    _paste_state.pop(user_id, None)
    with contextlib.suppress(Exception):
        await message.delete()
    sent = await message.reply_text("✅ Label stored. Now pick providers.")
    await _render_preset_edit(client, sent.chat.id, sent.id, user_id)


async def _render_preset_edit(
    client: Client, chat_id: int, message_id: int, user_id: int
) -> None:
    from tools.mirror_leech import Presets

    draft = _preset_drafts.get(user_id)
    if not draft:
        await _render_preset_list(client, chat_id, message_id, user_id)
        return

    configured = await _configured_uploader_ids(user_id)
    if not configured:
        body = (
            "> ⚠️ You need at least one configured destination before\n"
            "> building a preset. Link providers first, then come back."
        )
        rows = [[InlineKeyboardButton("← Back", callback_data="ml_preset_cancel")]]
        text = frame("🎯 **Preset — no destinations**", body)
        with contextlib.suppress(Exception):
            await client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(rows),
            )
        return

    from tools.mirror_leech.uploaders import uploader_by_id

    rows: list[list[InlineKeyboardButton]] = []
    selected = set(draft["providers"])
    for pid in configured:
        cls = uploader_by_id(pid)
        display = cls.display_name if cls else pid
        mark = "✅" if pid in selected else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {display}",
                    callback_data=f"ml_preset_tgl_{pid}",
                )
            ]
        )

    max_p = Presets.MAX_PROVIDERS_PER_PRESET
    rows.append(
        [
            InlineKeyboardButton(
                "💾 Save preset" if selected else "💾 (pick ≥1 provider)",
                callback_data="ml_preset_save",
            ),
            InlineKeyboardButton("❌ Cancel", callback_data="ml_preset_cancel"),
        ]
    )

    body = (
        f"> **Label:** {draft['label']}\n"
        f"> **Selected:** {len(selected)}/{max_p}\n\n"
        "> Tap providers to toggle. Save when you're done."
    )
    text = frame("🎯 **Preset — edit**", body)
    with contextlib.suppress(Exception):
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(rows),
        )


@Client.on_callback_query(filters.regex(r"^ml_preset_edit_([a-z0-9_-]+)$"))
async def ml_preset_edit(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech import Presets

    slug = callback_query.data.removeprefix("ml_preset_edit_")
    user_id = callback_query.from_user.id
    preset = await Presets.get_preset(user_id, slug)
    if not preset:
        await callback_query.answer("Preset not found.", show_alert=True)
        return
    _preset_drafts[user_id] = {
        "slug": preset.slug,
        "label": preset.label,
        "providers": list(preset.providers),
        "existing": True,
    }
    await _render_preset_edit(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        user_id,
    )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_preset_tgl_([a-z0-9_]+)$"))
async def ml_preset_toggle(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech import Presets

    provider = callback_query.data.removeprefix("ml_preset_tgl_")
    user_id = callback_query.from_user.id
    draft = _preset_drafts.get(user_id)
    if not draft:
        await callback_query.answer("Draft expired — start again.", show_alert=True)
        return

    if provider in draft["providers"]:
        draft["providers"].remove(provider)
    else:
        if len(draft["providers"]) >= Presets.MAX_PROVIDERS_PER_PRESET:
            await callback_query.answer(
                f"Max {Presets.MAX_PROVIDERS_PER_PRESET} providers per preset.",
                show_alert=True,
            )
            return
        draft["providers"].append(provider)

    await _render_preset_edit(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        user_id,
    )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_preset_save$"))
async def ml_preset_save(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech import Presets

    user_id = callback_query.from_user.id
    draft = _preset_drafts.get(user_id)
    if not draft:
        await callback_query.answer("No draft to save.", show_alert=True)
        return
    if not draft["providers"]:
        await callback_query.answer(
            "Pick at least one provider first.", show_alert=True
        )
        return

    try:
        await Presets.set_preset(
            user_id, draft["slug"], draft["label"], draft["providers"]
        )
    except ValueError as exc:
        await callback_query.answer(f"Save failed: {exc}", show_alert=True)
        return

    _preset_drafts.pop(user_id, None)
    await callback_query.answer("Saved.")
    await _render_preset_list(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        user_id,
    )


@Client.on_callback_query(filters.regex(r"^ml_preset_cancel$"))
async def ml_preset_cancel(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    _preset_drafts.pop(user_id, None)
    _paste_state.pop(user_id, None)
    await _render_preset_list(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        user_id,
    )
    await callback_query.answer()


@Client.on_callback_query(
    filters.regex(r"^ml_preset_use_([a-z0-9_-]+)_([A-Za-z0-9_-]{4,10})$")
)
async def ml_preset_use(client: Client, callback_query: CallbackQuery) -> None:
    """Apply a preset to the current /ml picker: set the provider
    selection to every preset provider the user has configured, then
    re-render the picker so the user can still tweak before Start."""
    from tools.mirror_leech import Presets

    match = callback_query.matches[0]
    slug = match.group(1)
    cid = match.group(2)

    ctx = ContextStore.get(cid)
    if not ctx:
        await callback_query.answer(
            "Picker expired — run /ml again.", show_alert=True
        )
        return
    if ctx.user_id != callback_query.from_user.id:
        await callback_query.answer(
            "This picker belongs to another user.", show_alert=True
        )
        return

    preset = await Presets.get_preset(callback_query.from_user.id, slug)
    if not preset:
        await callback_query.answer("Preset not found.", show_alert=True)
        return

    configured = set(await _configured_uploader_ids(ctx.user_id))
    ctx.selected_uploaders = [p for p in preset.providers if p in configured]
    await callback_query.answer(
        f"🎯 {preset.label}: {len(ctx.selected_uploaders)} selected"
    )
    await _render_uploader_picker(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        cid,
        ctx.user_id,
    )


@Client.on_callback_query(filters.regex(r"^ml_preset_delete_([a-z0-9_-]+)$"))
async def ml_preset_delete(client: Client, callback_query: CallbackQuery) -> None:
    from tools.mirror_leech import Presets

    slug = callback_query.data.removeprefix("ml_preset_delete_")
    preset = await Presets.get_preset(callback_query.from_user.id, slug)
    if not preset:
        await callback_query.answer("Preset not found.", show_alert=True)
        return

    body = (
        f"> Delete preset **{preset.label}** ({len(preset.providers)} "
        "providers)?\n\n> This cannot be undone."
    )
    rows = [
        [
            InlineKeyboardButton(
                "🗑 Delete", callback_data=f"ml_preset_delconf_{slug}"
            ),
            InlineKeyboardButton("← Back", callback_data="ml_preset_list"),
        ]
    ]
    with contextlib.suppress(Exception):
        await callback_query.message.edit_text(
            frame("🎯 **Preset — confirm delete**", body),
            reply_markup=InlineKeyboardMarkup(rows),
        )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_preset_delconf_([a-z0-9_-]+)$"))
async def ml_preset_delete_confirm(
    client: Client, callback_query: CallbackQuery
) -> None:
    from tools.mirror_leech import Presets

    slug = callback_query.data.removeprefix("ml_preset_delconf_")
    await Presets.delete_preset(callback_query.from_user.id, slug)
    await callback_query.answer("Deleted.")
    await _render_preset_list(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        callback_query.from_user.id,
    )


# ---------------------------------------------------------------------------
# MyFiles entry points — single-file and multi-select Mirror-Leech Options
# ---------------------------------------------------------------------------

async def _tg_ref_for_myfile(file_id: str) -> str | None:
    """Turn a MyFiles file _id into a `tg:<chat>:<message>` source string
    TelegramDownloader understands. Returns None when the file is gone."""
    from bson import ObjectId  # type: ignore

    from db import db

    try:
        record = await db.files.find_one({"_id": ObjectId(file_id)})
    except Exception:
        return None
    if not record:
        return None
    chat = record.get("channel_id")
    message_id = record.get("message_id")
    if not chat or not message_id:
        return None
    return f"tg:{chat}:{message_id}"


@Client.on_callback_query(filters.regex(r"^ml_opt_single_([A-Fa-f0-9]{24})$"))
async def ml_opt_single(client: Client, callback_query: CallbackQuery) -> None:
    """Open the uploader picker for one MyFiles file."""
    if not await _feature_enabled():
        await callback_query.answer("Mirror-Leech is disabled.", show_alert=True)
        return

    file_id = callback_query.data.removeprefix("ml_opt_single_")
    source = await _tg_ref_for_myfile(file_id)
    if source is None:
        await callback_query.answer("File not found.", show_alert=True)
        return

    cid = ContextStore.put(
        ContextStore.PickerContext(
            user_id=callback_query.from_user.id,
            source=source,
            candidate_downloader="telegram",
            origin_chat_id=callback_query.message.chat.id,
            origin_msg_id=callback_query.message.id,
            file_ids=[file_id],
        )
    )
    await callback_query.answer()
    await _render_uploader_picker(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        cid,
        callback_query.from_user.id,
    )


@Client.on_callback_query(filters.regex(r"^ml_opt_multi$"))
async def ml_opt_multi(client: Client, callback_query: CallbackQuery) -> None:
    """Open the uploader picker for the user's current multi-select."""
    if not await _feature_enabled():
        await callback_query.answer("Mirror-Leech is disabled.", show_alert=True)
        return

    from db import db

    user_id = callback_query.from_user.id
    user = await db.users.find_one({"user_id": user_id})
    state = (user or {}).get("myfiles_state") or {}
    file_ids = list(state.get("selected_files") or [])
    if not file_ids:
        await callback_query.answer("No files selected.", show_alert=True)
        return

    # Resolve each file's tg ref up front; drop missing rows.
    sources: list[tuple[str, str]] = []  # (file_id, tg-ref)
    for fid in file_ids:
        ref = await _tg_ref_for_myfile(fid)
        if ref:
            sources.append((fid, ref))

    if not sources:
        await callback_query.answer("None of the selected files resolved.", show_alert=True)
        return

    # For the picker UI we only need one "source" label; actual batch
    # fan-out happens in ml_go when it sees file_ids populated.
    cid = ContextStore.put(
        ContextStore.PickerContext(
            user_id=user_id,
            source=f"{len(sources)} selected files",
            candidate_downloader="telegram",
            origin_chat_id=callback_query.message.chat.id,
            origin_msg_id=callback_query.message.id,
            file_ids=[fid for fid, _ in sources],
        )
    )
    await callback_query.answer()
    await _render_uploader_picker(
        client,
        callback_query.message.chat.id,
        callback_query.message.id,
        cid,
        user_id,
    )
