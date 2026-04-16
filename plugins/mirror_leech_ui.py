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
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "No destinations configured yet.\n\n"
                "Open `/settings → ☁️ Mirror-Leech` (public mode) or\n"
                "`/admin → ☁️ Mirror-Leech Config` (non-public) to link a "
                "provider, then run /ml again."
            ),
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

    await client.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"☁️ **Mirror-Leech**\n\n"
            f"📥 `{dl_line}`\n"
            f"🔗 `{preview}`\n\n"
            "Tap to toggle destinations, then **Start**."
        ),
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
            "🚧 **Mirror-Leech is not enabled on this bot yet.**\n\n"
            "An admin needs to flip `feature_toggles.mirror_leech` on from the "
            "`/admin → Mirror-Leech Config` panel."
        )
        return

    parts = (message.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "Usage: `/ml <url>`\n\n"
            "Supported: direct HTTP(S), YouTube / social video (yt-dlp),\n"
            "Telegram file refs, and RSS feeds. "
            "Torrents / magnets are out of scope on this branch.",
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
        f"📥 Using **{dl_cls.display_name}**. Building picker…",
        reply_markup=_cancel_kb(),
    )
    await _render_uploader_picker(
        client, message.chat.id, prompt.id, cid, message.from_user.id
    )


@Client.on_callback_query(filters.regex(r"^ml_cancel_picker$"))
async def ml_cancel_picker(client: Client, callback_query: CallbackQuery) -> None:
    """Best-effort dismiss of an in-progress picker message."""
    try:
        await callback_query.message.edit_text("🚫 Mirror-Leech picker cancelled.")
    except Exception:
        pass
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_go_([A-Za-z0-9_-]{4,10})$"))
async def ml_start_task(client: Client, callback_query: CallbackQuery) -> None:
    """Resolve the picker context and schedule one MLTask per selected uploader."""
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

    ml_worker_pool.enqueue(task, _runner)


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
    if not tasks:
        body = "📭 **Your Mirror-Leech queue is empty.**"
        rows: list[list[InlineKeyboardButton]] = []
    else:
        icon = {
            "queued": "⏳",
            "downloading": "⬇️",
            "uploading": "☁️",
            "done": "✅",
            "failed": "❌",
            "cancelled": "🚫",
        }
        lines = ["🗂 **Your last Mirror-Leech tasks**", ""]
        rows = []
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

    markup = InlineKeyboardMarkup(rows)
    if message_id:
        try:
            await client.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=body, reply_markup=markup
            )
            return
        except Exception:
            pass
    await client.send_message(chat_id, body, reply_markup=markup)
