# --- Imports ---
from pyrogram import Client, filters, StopPropagation
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from database import db
from utils.state import set_state, get_state, get_data, update_data, clear_session
from utils.log import get_logger
from utils.dumb_channel import (
    resolve_channel,
    validate_bot_admin,
    already_configured,
    ValidationStatus,
    ValidationResult,
)

logger = get_logger("plugins.dumb_channel")

# ==========================================================================
# Unified Dumb-Channel wizard (v2)
# --------------------------------------------------------------------------
# A three-step add flow shared by the admin panel (global channels) and the
# user Settings panel (per-user channels in PUBLIC_MODE). Uses `utils.state`
# as single source of truth — no more admin_sessions/user_sessions drift.
#
# Callback namespace: `dumbv2_*`.
# State: `awaiting_dcv2_input` (only during Step 2; Steps 1/3 are stateless
# button-flows).
# ==========================================================================

# --- Session keys ---------------------------------------------------------
SK_MODE       = "dcv2_mode"         # "global" | "user"
SK_BACK_CB    = "dcv2_back_cb"      # callback to return to the list view
SK_MSG_ID     = "dcv2_msg_id"       # id of the wizard message (we edit in place)
SK_PENDING_ID = "dcv2_pending_id"
SK_PENDING_NM = "dcv2_pending_name"

# --- State --------------------------------------------------------------
S_INPUT = "awaiting_dcv2_input"

# --- Mode descriptors -----------------------------------------------------
ENTRY_MAP = {
    "global": {"back": "dumb_menu",      "label": "Global Dumb Channels"},
    "user":   {"back": "dumb_user_menu", "label": "Your Dumb Channels"},
}


# === Small helpers ========================================================
def _back_btn(back_cb: str):
    return [InlineKeyboardButton("← Back", callback_data=back_cb)]


def _cancel_btn(back_cb: str):
    return [InlineKeyboardButton("❌ Cancel", callback_data=back_cb)]


async def _safe_edit(client, user_id: int, msg_id: int, text: str, rows=None):
    """Edit the wizard message, tolerating MessageNotModified."""
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(rows) if rows else None,
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        pass
    except Exception as e:
        logger.warning(f"_safe_edit({user_id}, {msg_id}) failed: {e}")


# === Step 1: show the prompt ==============================================
async def _render_step1(client, base_message, user_id: int, mode: str, back_cb: str):
    me = await client.get_me()
    bot_uname = me.username or ""

    text_lines = [
        "➕ **Add Dumb Channel**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "**1️⃣ Make me admin** in the target channel with **Post Messages** permission.",
    ]
    if bot_uname:
        text_lines.append(f"   Bot: `@{bot_uname}`")
    text_lines += [
        "",
        "**2️⃣ Then send one of:**",
        "  • Forward any message from the channel",
        "  • `@username`",
        "  • `-100…` channel ID",
        "  • `t.me/<user>` or `t.me/c/<id>` link",
        "",
        "__Send `cancel` or `disable` to abort.__",
    ]
    text = "\n".join(text_lines)

    rows = []
    if bot_uname:
        # Telegram's built-in "Add to Channel as Admin" deep link.
        add_url = f"https://t.me/{bot_uname}?startchannel&admin=post_messages"
        rows.append([InlineKeyboardButton("➕ Add me as admin", url=add_url)])
    rows.append([_cancel_btn(back_cb)[0]])

    try:
        msg = await base_message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(rows),
            disable_web_page_preview=True,
        )
        # edit_text returns the edited message in pyrogram.
        update_data(user_id, SK_MSG_ID, getattr(msg, "id", base_message.id))
    except MessageNotModified:
        update_data(user_id, SK_MSG_ID, base_message.id)
    except Exception as e:
        logger.warning(f"Step1 edit failed, sending fresh: {e}")
        msg = await base_message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(rows),
            disable_web_page_preview=True,
        )
        update_data(user_id, SK_MSG_ID, msg.id)


@Client.on_callback_query(filters.regex(r"^dumbv2_start:(global|user)$"))
async def handle_dumbv2_start(client, callback_query):
    user_id = callback_query.from_user.id
    mode = callback_query.data.split(":", 1)[1]

    # Gate: 'global' is only intended for the admin panel. If a non-admin
    # somehow triggers it in PUBLIC_MODE, fall back to 'user'.
    if mode == "global" and Config.PUBLIC_MODE:
        ceo_id = getattr(Config, "CEO_ID", None)
        admin_ids = getattr(Config, "ADMIN_IDS", set()) or set()
        if user_id != ceo_id and user_id not in admin_ids:
            mode = "user"

    cfg = ENTRY_MAP.get(mode, ENTRY_MAP["user"])
    back_cb = cfg["back"]

    await callback_query.answer()
    update_data(user_id, SK_MODE, mode)
    update_data(user_id, SK_BACK_CB, back_cb)
    set_state(user_id, S_INPUT)

    await _render_step1(client, callback_query.message, user_id, mode, back_cb)


# === Step 2: user sends input =============================================
@Client.on_message(
    (filters.text | filters.forwarded) & filters.private & ~filters.regex(r"^/"),
    group=1,
)
async def handle_dcv2_input(client, message):
    # Early bail-out when we're not actively collecting input.
    try:
        user_id = message.from_user.id
    except AttributeError:
        return

    if get_state(user_id) != S_INPUT:
        return  # not ours — let other groups handle

    sess = get_data(user_id) or {}
    mode = sess.get(SK_MODE, "user")
    back_cb = sess.get(SK_BACK_CB, ENTRY_MAP[mode]["back"])
    wizard_msg_id = sess.get(SK_MSG_ID)

    raw_text = (message.text or "").strip()

    # Cancel token.
    if raw_text.lower() in ("cancel", "disable", "abort", "stop"):
        set_state(user_id, None)
        try:
            await message.delete()
        except Exception:
            pass
        if wizard_msg_id:
            await _safe_edit(
                client, user_id, wizard_msg_id,
                "❌ **Cancelled.**",
                rows=[_back_btn(back_cb)],
            )
        raise StopPropagation

    # Delete the user's input message to keep the chat tidy.
    try:
        await message.delete()
    except Exception:
        pass

    # Step 2a: resolving the channel reference.
    if wizard_msg_id:
        await _safe_edit(
            client, user_id, wizard_msg_id,
            "🔍 **Resolving channel…**",
        )

    ch_id, ch_name, err = await resolve_channel(client, message)
    if not ch_id:
        await _render_resolve_error(client, user_id, wizard_msg_id, mode, back_cb, err)
        raise StopPropagation

    # Step 2b: validate the bot's permissions.
    if wizard_msg_id:
        await _safe_edit(
            client, user_id, wizard_msg_id,
            f"🔍 **Validating bot permissions in** `{ch_name}`**…**",
        )

    result = await validate_bot_admin(client, ch_id)
    # Prefer the freshly-resolved name if validator didn't carry it.
    if not result.channel_name:
        result.channel_name = ch_name

    await _render_validation(client, user_id, wizard_msg_id, mode, back_cb, result)
    raise StopPropagation


async def _render_resolve_error(client, user_id, msg_id, mode, back_cb, err):
    rows = [
        [InlineKeyboardButton("🔄 Try again", callback_data=f"dumbv2_start:{mode}")],
        [InlineKeyboardButton("← Back", callback_data=back_cb)],
    ]
    await _safe_edit(
        client, user_id, msg_id,
        "❌ **Couldn't resolve channel**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{err}",
        rows=rows,
    )
    set_state(user_id, None)


async def _render_validation(client, user_id, msg_id, mode, back_cb, result: ValidationResult):
    me = await client.get_me()
    bot_uname = me.username or ""

    # Dedup check (only meaningful when we have a confirmed channel id).
    if result.channel_id:
        target_uid = user_id if mode == "user" else None
        try:
            existing = await db.get_dumb_channels(target_uid)
        except Exception:
            existing = {}
        if already_configured(existing, result.channel_id):
            rows = [
                [InlineKeyboardButton("➕ Add another", callback_data=f"dumbv2_start:{mode}")],
                [InlineKeyboardButton("← Back to list", callback_data=back_cb)],
            ]
            await _safe_edit(
                client, user_id, msg_id,
                "ℹ️ **Already in your list**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"**{result.channel_name}** (`{result.channel_id}`)\n\n"
                "No changes made.",
                rows=rows,
            )
            set_state(user_id, None)
            return

    if result.status == ValidationStatus.OK_ADMIN_POST:
        update_data(user_id, SK_PENDING_ID, result.channel_id)
        update_data(user_id, SK_PENDING_NM, result.channel_name)
        rows = [
            [InlineKeyboardButton("💾 Save", callback_data="dumbv2_save")],
            [InlineKeyboardButton("🔄 Try again", callback_data=f"dumbv2_start:{mode}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=back_cb)],
        ]
        await _safe_edit(
            client, user_id, msg_id,
            "✅ **Channel verified**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"**Channel:** {result.channel_name}\n"
            f"**ID:** `{result.channel_id}`\n"
            f"**Bot:** admin with post rights ✅\n\n"
            "Save this channel?",
            rows=rows,
        )
        set_state(user_id, None)
        return

    # Everything below is a failure/warning path.
    if result.channel_id:
        update_data(user_id, SK_PENDING_ID, result.channel_id)
        update_data(user_id, SK_PENDING_NM, result.channel_name or "Channel")

    if result.status == ValidationStatus.OK_ADMIN_NO_POST:
        text = (
            "⚠️ **Admin — but no post rights**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"**Channel:** {result.channel_name}\n\n"
            "I'm an admin here but I'm missing the **Post Messages** "
            "permission. Open the channel → admins list → tap me → enable "
            "**Post Messages**, then tap Retry."
        )
    elif result.status == ValidationStatus.MEMBER_NO_ADMIN:
        text = (
            "⚠️ **Not an admin yet**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"**Channel:** {result.channel_name}\n\n"
            "I'm in the channel but not an admin. Promote me to admin with "
            "**Post Messages** permission, then tap Retry."
        )
    elif result.status == ValidationStatus.NOT_MEMBER:
        text = (
            "⚠️ **Bot is not in the channel**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"**Channel:** {result.channel_name or 'Unknown'}\n\n"
            f"Add `@{bot_uname}` as admin in this channel, then tap Retry."
        )
    else:  # INVALID
        text = (
            "❌ **Couldn't access channel**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{result.error_detail or 'Unknown error.'}"
        )

    rows = []
    if bot_uname and result.status in (
        ValidationStatus.NOT_MEMBER, ValidationStatus.MEMBER_NO_ADMIN,
    ):
        add_url = f"https://t.me/{bot_uname}?startchannel&admin=post_messages"
        rows.append([InlineKeyboardButton("➕ Add me as admin", url=add_url)])
    if result.channel_id and result.status != ValidationStatus.INVALID:
        rows.append([InlineKeyboardButton("🔄 Retry validation", callback_data="dumbv2_retry")])
    rows.append([InlineKeyboardButton("✏️ Enter different channel", callback_data=f"dumbv2_start:{mode}")])
    rows.append([InlineKeyboardButton("← Back", callback_data=back_cb)])

    await _safe_edit(client, user_id, msg_id, text, rows=rows)
    set_state(user_id, None)


# === Step 3: retry + save ================================================
@Client.on_callback_query(filters.regex(r"^dumbv2_retry$"))
async def handle_dumbv2_retry(client, callback_query):
    user_id = callback_query.from_user.id
    sess = get_data(user_id) or {}
    ch_id = sess.get(SK_PENDING_ID)
    mode = sess.get(SK_MODE, "user")
    back_cb = sess.get(SK_BACK_CB, ENTRY_MAP[mode]["back"])
    msg_id = sess.get(SK_MSG_ID) or callback_query.message.id

    if not ch_id:
        return await callback_query.answer("Nothing to retry — start over.", show_alert=True)

    await callback_query.answer()
    await _safe_edit(
        client, user_id, msg_id,
        "🔍 **Re-checking permissions…**",
    )
    result = await validate_bot_admin(client, ch_id)
    if not result.channel_name:
        result.channel_name = sess.get(SK_PENDING_NM) or "Channel"
    await _render_validation(client, user_id, msg_id, mode, back_cb, result)


@Client.on_callback_query(filters.regex(r"^dumbv2_save$"))
async def handle_dumbv2_save(client, callback_query):
    user_id = callback_query.from_user.id
    sess = get_data(user_id) or {}
    ch_id = sess.get(SK_PENDING_ID)
    ch_name = sess.get(SK_PENDING_NM) or "Channel"
    mode = sess.get(SK_MODE, "user")
    back_cb = sess.get(SK_BACK_CB, ENTRY_MAP[mode]["back"])

    if not ch_id:
        return await callback_query.answer(
            "Session expired — please start over.", show_alert=True
        )

    await callback_query.answer("Saving…")

    # Invite link export is best-effort.
    invite_link = None
    try:
        invite_link = await client.export_chat_invite_link(ch_id)
    except Exception as e:
        logger.warning(f"export_chat_invite_link({ch_id}) failed: {e}")

    target_user_id = user_id if mode == "user" else None
    try:
        await db.add_dumb_channel(
            ch_id, ch_name, invite_link=invite_link, user_id=target_user_id,
        )
    except Exception as e:
        logger.error(f"add_dumb_channel({ch_id}) failed: {e}")
        return await _safe_edit(
            client, user_id, callback_query.message.id,
            f"❌ **Save failed**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"`{e}`",
            rows=[_back_btn(back_cb)],
        )

    # Build a success message with quick-default shortcuts.
    opt_cb_prefix = "dumb_def_" if mode == "global" else "dumb_user_def_"
    rows = [
        [InlineKeyboardButton("⭐ Set as Standard default",
                              callback_data=f"{opt_cb_prefix}std_{ch_id}")],
        [InlineKeyboardButton("🎬 Set as Movie default",
                              callback_data=f"{opt_cb_prefix}mov_{ch_id}"),
         InlineKeyboardButton("📺 Set as Series default",
                              callback_data=f"{opt_cb_prefix}ser_{ch_id}")],
        [InlineKeyboardButton("➕ Add another", callback_data=f"dumbv2_start:{mode}")],
        [InlineKeyboardButton("← Back to list", callback_data=back_cb)],
    ]

    # Clean up session scratch fields (keep mode for "Add another").
    update_data(user_id, SK_PENDING_ID, None)
    update_data(user_id, SK_PENDING_NM, None)
    set_state(user_id, None)

    await _safe_edit(
        client, user_id, callback_query.message.id,
        "✅ **Saved**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"**{ch_name}** (`{ch_id}`)\n\n"
        "You can now route files to this Dumb Channel.",
        rows=rows,
    )


# === Legacy callback compatibility ========================================
# Older pinned menus may still emit the pre-refactor callbacks. Forward them
# into the new wizard so users don't end up in a dead state.
@Client.on_callback_query(filters.regex(r"^dumb_add$"))
async def _legacy_dumb_add(client, callback_query):
    callback_query.data = "dumbv2_start:global"
    await handle_dumbv2_start(client, callback_query)


@Client.on_callback_query(filters.regex(r"^dumb_user_add$"))
async def _legacy_dumb_user_add(client, callback_query):
    callback_query.data = "dumbv2_start:user"
    await handle_dumbv2_start(client, callback_query)


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
