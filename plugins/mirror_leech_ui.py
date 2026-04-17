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
    ml_cfg                       → user config root
    ml_cfg_up_<provider>         → per-provider config screen
    ml_cfg_test_<provider>       → test connection
    ml_cfg_clr_<provider>        → clear stored credential
    ml_cfg_paste_<provider>      → prompt user to paste token
    ml_opt_single_<file_id>      → MyFiles single-file entry
    ml_opt_multi_<state_key>     → MyFiles multi-select entry
    ml_prov_<uploader>_<ctx_id>  → pick uploader for picker context
    ml_go_<ctx_id>               → start task(s)
    ml_cancel_<task_id>          → cancel running task
    ml_queue                     → user queue
    ml_admin                     → CEO admin screen
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from tools.mirror_leech import ContextStore
from tools.mirror_leech.Controller import (
    UnsupportedSourceError,
    pick_downloader,
)
from tools.mirror_leech.UIChrome import frame
from tools.mirror_leech.uploaders import available_uploaders
from utils.log import get_logger

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
    from tools.mirror_leech.uploaders import uploader_by_id

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
    from database import db

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
    try:
        await callback_query.message.edit_text(
            frame(
                "🚫 **Mirror-Leech — Cancelled**",
                "> Picker dismissed. Run `/ml <url>` again when you're ready.",
            )
        )
    except Exception:
        pass
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
            f"> 📤 " + ", ".join(f"`{u}`" for u in ctx.selected_uploaders),
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
                await run_task(
                    t,
                    client,
                    progress_cb=lambda current: update_progress_message(client, current),
                )
                await update_progress_message(client, t)

            try:
                ml_worker_pool.enqueue(task, _runner)
            except Exception as exc:
                logger.exception(
                    "enqueue failed for batch task %s", task.id
                )
                summary_lines.append(
                    f"  ⚠️ `{task.id}` konnte nicht gestartet werden: {exc}"
                )

        ContextStore.drop(cid)
        # Replace the picker with a batch-summary header.
        try:
            await client.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.id,
                text=frame(
                    "☁️ **Mirror-Leech — Batch Queued**",
                    "\n".join(summary_lines),
                ),
            )
        except Exception:
            pass
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
    try:
        await callback_query.message.edit_text(
            render_task_text(task),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⏹ Cancel", callback_data=f"ml_cancel_{task.id}")]]
            ),
        )
    except Exception:
        pass

    ContextStore.drop(cid)

    async def _runner(t: MLTask) -> None:
        await run_task(
            t,
            client,
            progress_cb=lambda current: update_progress_message(client, current),
        )
        # Final render — terminal states always flush.
        await update_progress_message(client, t)

    try:
        ml_worker_pool.enqueue(task, _runner)
        logger.info(
            "ml_start_task queued single task %s for user %s",
            task.id, ctx.user_id,
        )
    except Exception as exc:
        logger.exception("enqueue failed for task %s", task.id)
        try:
            await callback_query.message.edit_text(
                f"❌ Konnte Task nicht starten: `{exc}`"
            )
        except Exception:
            pass


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
    for cls in all_uploaders():
        avail = cls.available()
        try:
            configured = avail and await cls().is_configured(user_id)
        except Exception:
            configured = False
        if not avail:
            badge = "🚫"
            suffix = "unavailable on this host"
        elif configured:
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
    try:
        await callback_query.message.edit_text(
            frame(
                "☁️ **Mirror-Leech — Config Closed**",
                "> Open `/ml` or `/mlqueue` whenever you're ready.",
            )
        )
    except Exception:
        pass
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
    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(rows),
        )
    except Exception:
        pass


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
}

# In-memory waiting state: user_id -> {"provider": str, "step": str, "tmp": ...}
_paste_state: dict[int, dict] = {}


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
    try:
        await callback_query.message.edit_text(
            f"✏️ **Link {provider}**\n\n" + fmt["prompt"] + "\n\n__Send the next message in this chat.__",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data=f"ml_cfg_up_{provider}")]]
            ),
        )
    except Exception:
        pass


@Client.on_message(filters.text & filters.private, group=4)
async def _ml_paste_text(client: Client, message: Message) -> None:
    state = _paste_state.get(message.from_user.id)
    if not state:
        return  # not a ML paste message; let other handlers run

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
            for field, value in zip(fields, parts):
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
    try:
        await message.delete()
    except Exception:
        pass
    await message.reply_text(f"✅ `{provider}` linked. Use **Test connection** to verify.")


# ---------------------------------------------------------------------------
# MyFiles entry points — single-file and multi-select Mirror-Leech Options
# ---------------------------------------------------------------------------

async def _tg_ref_for_myfile(file_id: str) -> str | None:
    """Turn a MyFiles file _id into a `tg:<chat>:<message>` source string
    TelegramDownloader understands. Returns None when the file is gone."""
    from bson import ObjectId  # type: ignore
    from database import db

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

    from database import db

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
