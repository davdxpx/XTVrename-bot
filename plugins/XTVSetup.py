# --- Imports ---
import asyncio
import contextlib
import datetime
import random

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import (
    ApiIdInvalid,
    MessageNotModified,
    PasswordHashInvalid,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from tools.mirror_leech.UIChrome import frame_plain as frame
from utils.telegram.log import get_logger

logger = get_logger("plugins.XTVSetup")
pro_setup_sessions = {}
pro_change_sessions = {}  # user_id → {"action": "tunnel", "msg_id": ...}


# === Helper Functions ===
def get_pro_session_data(user_id):
    if user_id not in pro_setup_sessions:
        pro_setup_sessions[user_id] = {}
    return pro_setup_sessions[user_id]


def _cancel_kb(callback: str = "pro_setup_menu") -> InlineKeyboardMarkup:
    """Single-button `❌ Cancel` keyboard used across the wizard."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data=callback)]]
    )


def _back_kb(callback: str = "pro_setup_menu", label: str = "← Back") -> InlineKeyboardMarkup:
    """Single-button back keyboard with unified label."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=callback)]]
    )


async def _error_screen(msg, text: str, user_id: int | None = None) -> None:
    """Edit `msg` to show an error with a unified `← Back` button and drop
    any stashed wizard state for the given user."""
    with contextlib.suppress(MessageNotModified):
        await msg.edit_text(text, reply_markup=_back_kb())
    if user_id is not None:
        pro_setup_sessions.pop(user_id, None)


def _format_bytes(n) -> str:
    n = int(n or 0)
    units = [("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)]
    for unit, scale in units:
        if n >= scale:
            return f"{n / scale:.2f} {unit}"
    return f"{n} B"


def _format_dt(value) -> str:
    if not value:
        return "__never__"
    if isinstance(value, datetime.datetime):
        return value.strftime("%d %b %Y · %H:%M UTC")
    if isinstance(value, str):
        return f"`{value}`"
    return f"`{value}`"


def _mask_phone(phone) -> str:
    if not phone:
        return "__unknown__"
    s = str(phone)
    if len(s) <= 6:
        return f"`{s}`"
    return f"`{s[:3]} ••• ••• {s[-4:]}`"


@Client.on_callback_query(filters.regex(r"^pro_setup_menu$"))

# --- Handlers ---
async def pro_menu(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id != Config.CEO_ID:
        return await callback_query.answer("Not authorized.", show_alert=True)

    pro_setup_sessions.pop(user_id, None)
    pro_change_sessions.pop(user_id, None)

    session = await db.get_pro_session()

    if session:
        text, buttons = _render_active(session, getattr(client, "user_bot", None))
    else:
        text, buttons = _render_inactive()

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )


def _render_active(session: dict, user_bot) -> tuple[str, list]:
    name = session.get("userbot_first_name") or "__unknown__"
    if session.get("userbot_username"):
        name = f"{name} (@{session['userbot_username']})"
    uid = session.get("userbot_user_id") or "__unknown__"
    phone = _mask_phone(session.get("phone_number"))
    is_premium = session.get("is_premium")
    if is_premium is True:
        prem_line = "💎 Premium: `yes`"
        if session.get("premium_expires_at"):
            prem_line += f" · expires {_format_dt(session['premium_expires_at'])}"
    elif is_premium is False:
        prem_line = "💎 Premium: `no`"
    else:
        prem_line = "💎 Premium: _unknown_"
    auth_line = f"📅 Authorised: {_format_dt(session.get('authorised_at'))}"

    last_check = session.get("last_auth_check_at")
    last_status = session.get("last_auth_status")
    if last_check is None:
        health_line = "Health: ⚪ `not yet checked` — tap 🩺 Health Check"
    elif last_status == "ok":
        health_line = f"Health: 🟢 `connected` — last check {_format_dt(last_check)}"
    elif last_status == "error":
        health_line = f"Health: 🔴 `error` — last check {_format_dt(last_check)}"
    else:
        health_line = f"Health: 🟡 `{last_status or 'unknown'}` — last check {_format_dt(last_check)}"

    runtime = "🟢 `running`" if user_bot is not None else "🔴 `not started`"

    account_lines = [
        "> **Userbot Account**",
        f"> 👤 Name: `{name}`",
        f"> 🆔 ID: `{uid}`",
        f"> 📞 Phone: {phone}",
        f"> {prem_line}",
        f"> {auth_line}",
    ]
    runtime_lines = [
        "> **Runtime**",
        f"> ⚙️ Userbot process: {runtime}",
        f"> {health_line}",
    ]
    tunnel_lines = ["> **Tunnel Channel**"]
    if session.get("tunnel_id"):
        tunnel_lines.append(f"> 🆔 ID: `{session['tunnel_id']}`")
        link = session.get("tunnel_link")
        if link:
            tunnel_lines.append(f"> 🔗 Link: `{link}`")
        else:
            tunnel_lines.append("> 🔗 Link: _not set_")
    else:
        tunnel_lines.append("> __No tunnel configured yet.__")

    upload_count = int(session.get("upload_count_total") or 0)
    upload_bytes = int(session.get("upload_bytes_total") or 0)
    avg = (upload_bytes / upload_count) if upload_count else 0
    last_upload = _format_dt(session.get("last_upload_at"))
    stats_lines = [
        "> **Upload Stats — Lifetime**",
        f"> 📦 Files routed: `{upload_count}`",
        f"> 📊 Volume: `{_format_bytes(upload_bytes)}`",
        f"> ⚡ Avg per file: `{_format_bytes(avg)}`",
        f"> 🕒 Last upload: {last_upload}",
    ]

    body = "\n".join(
        [
            "Status: ✅ `Active`",
            "",
            *account_lines,
            "",
            *runtime_lines,
            "",
            *tunnel_lines,
            "",
            *stats_lines,
            "",
            "> Use Health Check before relying on the userbot.",
            "> Test Send proves the tunnel.",
        ]
    )
    text = frame("🚀 **𝕏TV Pro™ — Manage**", body)

    buttons = [
        [
            InlineKeyboardButton("🩺 Health Check", callback_data="pro_health_check"),
            InlineKeyboardButton("📤 Test Send", callback_data="pro_test_send"),
        ],
        [
            InlineKeyboardButton("🔁 Re-Authorise", callback_data="pro_re_auth"),
            InlineKeyboardButton("🆔 Change Tunnel", callback_data="pro_change_tunnel"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="pro_setup_menu"),
            InlineKeyboardButton("🗑 Delete Session", callback_data="pro_setup_delete_ask"),
        ],
        [InlineKeyboardButton("← Back", callback_data="admin_main")],
    ]
    return text, buttons


def _render_inactive() -> tuple[str, list]:
    body = "\n".join(
        [
            "> Pro extends Telegram's 4 GB cap by routing uploads through",
            "> a userbot session. You'll need:",
            ">",
            "> **1.** A spare Telegram account",
            "> **2.** Its `api_id` + `api_hash` from my.telegram.org",
            "> **3.** Access to receive its login code",
            "",
            "> 🔐 The session string is stored in your database — do not share it.",
        ]
    )
    text = frame("🚀 **𝕏TV Pro™ — Setup**", body)
    buttons = [
        [
            InlineKeyboardButton("🆕 Start Setup", callback_data="pro_setup_start"),
            InlineKeyboardButton("📖 What is 𝕏TV Pro?", callback_data="pro_setup_what"),
        ],
        [InlineKeyboardButton("← Back", callback_data="admin_main")],
    ]
    return text, buttons


@Client.on_callback_query(filters.regex(r"^pro_setup_what$"))
async def pro_setup_what(client, callback_query):
    if callback_query.from_user.id != Config.CEO_ID:
        return await callback_query.answer("Not authorized.", show_alert=True)
    await callback_query.answer()
    body = "\n".join(
        [
            "> Standard Telegram bots can only upload files up to **2 GB**.",
            "> Telegram **Premium** users can upload up to **4 GB**.",
            "",
            "> 𝕏TV Pro™ logs in a Premium **userbot** session and routes any",
            "> file >2 GB through it. The bot copies the file to a private",
            "> tunnel channel where the userbot picks it up and re-sends it",
            "> to the destination — all transparently.",
            "",
            "> Setup is one-time. After authorisation everything happens",
            "> automatically.",
        ]
    )
    text = frame("📖 **About 𝕏TV Pro™**", body)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=_back_kb())

@Client.on_callback_query(filters.regex(r"^pro_health_check$"))
async def pro_health_check(client, callback_query):
    if callback_query.from_user.id != Config.CEO_ID:
        return await callback_query.answer("Not authorized.", show_alert=True)
    await callback_query.answer("Pinging userbot…")

    user_bot = getattr(client, "user_bot", None)
    if user_bot is None:
        await db.update_pro_session(
            last_auth_check_at=datetime.datetime.utcnow(),
            last_auth_status="error",
        )
    else:
        try:
            await asyncio.wait_for(user_bot.get_me(), timeout=5)
            await db.update_pro_session(
                last_auth_check_at=datetime.datetime.utcnow(),
                last_auth_status="ok",
            )
        except Exception as e:
            logger.warning(f"Pro health check failed: {e}")
            await db.update_pro_session(
                last_auth_check_at=datetime.datetime.utcnow(),
                last_auth_status="error",
            )

    session = await db.get_pro_session()
    if session:
        text, buttons = _render_active(session, getattr(client, "user_bot", None))
    else:
        text, buttons = _render_inactive()
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )


@Client.on_callback_query(filters.regex(r"^pro_test_send$"))
async def pro_test_send(client, callback_query):
    if callback_query.from_user.id != Config.CEO_ID:
        return await callback_query.answer("Not authorized.", show_alert=True)
    await callback_query.answer("Sending test message…")

    session = await db.get_pro_session()
    user_bot = getattr(client, "user_bot", None)
    tunnel_id = (session or {}).get("tunnel_id")

    if user_bot is None or not tunnel_id:
        await callback_query.answer(
            "Userbot not running or tunnel not configured.", show_alert=True
        )
        return

    try:
        msg = await user_bot.send_message(
            tunnel_id, "🩺 𝕏TV Pro health check — auto-deleting", disable_notification=True
        )
        await asyncio.sleep(2)
        with contextlib.suppress(Exception):
            await msg.delete()
        await callback_query.answer("✅ Test send succeeded.", show_alert=True)
    except Exception as e:
        logger.warning(f"Pro test send failed: {e}")
        await callback_query.answer(f"❌ Test send failed: {e}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^pro_re_auth$"))
async def pro_re_auth(client, callback_query):
    if callback_query.from_user.id != Config.CEO_ID:
        return await callback_query.answer("Not authorized.", show_alert=True)
    await callback_query.answer()

    # Stop running userbot, clear stored session, then jump straight into the
    # setup wizard. We do not pre-fill anything to keep the wizard logic
    # straightforward — admins re-enter all three credentials.
    await db.delete_pro_session()
    if getattr(client, "user_bot", None):
        with contextlib.suppress(Exception):
            await client.user_bot.stop()
        client.user_bot = None

    pro_setup_sessions[callback_query.from_user.id] = {"state": "awaiting_api_id"}
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            frame(
                "🔁 **𝕏TV Pro™ — Re-Authorise**",
                "> Old session cleared. Send the new **API ID** to begin.",
            ),
            reply_markup=_cancel_kb(),
        )


@Client.on_callback_query(filters.regex(r"^pro_change_tunnel$"))
async def pro_change_tunnel(client, callback_query):
    if callback_query.from_user.id != Config.CEO_ID:
        return await callback_query.answer("Not authorized.", show_alert=True)
    await callback_query.answer()

    pro_change_sessions[callback_query.from_user.id] = {
        "action": "tunnel",
        "msg_id": callback_query.message.id,
    }
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            frame(
                "🆔 **𝕏TV Pro™ — Change Tunnel Channel**",
                "> Send the new tunnel as `@username`, numeric ID (`-100…`),\n"
                "> or send `none` to clear.\n"
                ">\n"
                "> __The userbot must already be a member with post "
                "permissions.__",
            ),
            reply_markup=_cancel_kb(),
        )


@Client.on_callback_query(filters.regex(r"^pro_setup_delete(_ask)?$"))
async def delete_setup_ask(client, callback_query):
    """Confirm screen before destroying the Pro session.

    Both the new `pro_setup_delete_ask` callback and the legacy
    `pro_setup_delete` callback land here, so any stale inline keyboard
    still goes through confirmation instead of nuking the session.
    """
    await callback_query.answer()
    if callback_query.from_user.id != Config.CEO_ID:
        return
    text = frame(
        "🗑 **𝕏TV Pro™ — Delete Session?**",
        "> This will:\n"
        ">\n"
        "> • Stop the running userbot\n"
        "> • Erase the session string and credentials from the database\n"
        "> • Reset all upload telemetry counters\n"
        ">\n"
        "> The 4 GB tunnel will stop working immediately. Re-Setup is\n"
        "> the only way back.\n"
        "> __This cannot be undone.__",
    )
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data="pro_setup_menu"
                        ),
                        InlineKeyboardButton(
                            "🗑 Yes, delete it",
                            callback_data="pro_setup_delete_confirm",
                        ),
                    ]
                ]
            ),
        )


@Client.on_callback_query(filters.regex(r"^pro_setup_delete_confirm$"))
async def delete_setup_confirm(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if user_id != Config.CEO_ID:
        return

    await db.delete_pro_session()

    if getattr(client, "user_bot", None):
        with contextlib.suppress(Exception):
            await client.user_bot.stop()
        client.user_bot = None

    await callback_query.message.edit_text(
        frame(
            "✅ **𝕏TV Pro™ — Session Deleted**",
            "> Disabled. The userbot session was securely deleted from\n"
            "> the database.",
        ),
        reply_markup=_back_kb(),
    )

@Client.on_callback_query(filters.regex(r"^pro_setup_start$"))
async def start_setup(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if user_id != Config.CEO_ID:
        return

    pro_setup_sessions[user_id] = {"state": "awaiting_api_id"}
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            frame(
                "🚀 **𝕏TV Pro™ — Setup Wizard**",
                "> Let's configure the Userbot tunnel for 4 GB files.\n"
                ">\n"
                "> **Step 1 / 3** — send your **API ID** (e.g. `1234567`).",
            ),
            reply_markup=_cancel_kb(),
        )

@Client.on_message(filters.private & filters.user(Config.CEO_ID), group=0)
async def pro_setup_handler(client, message):
    user_id = message.from_user.id

    # --- Change-tunnel one-shot text capture (independent of the wizard) ---
    if user_id in pro_change_sessions:
        info = pro_change_sessions[user_id]
        if info.get("action") == "tunnel":
            await _handle_change_tunnel_text(client, message, info)
        from pyrogram import StopPropagation
        raise StopPropagation

    if user_id not in pro_setup_sessions:
        raise ContinuePropagation

    data = pro_setup_sessions[user_id]
    state = data.get("state")
    if not state:
        raise ContinuePropagation

    # Crucial Fix: If public mode is enabled, general catch-all handlers might intercept this
    # We must explicitly raise StopPropagation so it doesn't fall through to other handlers.

    text = message.text.strip() if message.text else ""
    if not text:
        await message.reply_text("Please provide text.", reply_markup=_cancel_kb())
        from pyrogram import StopPropagation
        raise StopPropagation

    if state == "awaiting_api_id":
        if not text.isdigit():
            await message.reply_text(
                "API ID must be numeric. Try again.",
                reply_markup=_cancel_kb(),
            )
            from pyrogram import StopPropagation
            raise StopPropagation

        data["api_id"] = int(text)
        data["state"] = "awaiting_api_hash"
        await message.reply_text(
            "✅ Got API ID.\n\n**Step 2 / 3** — send your **API Hash**:",
            reply_markup=_cancel_kb(),
        )
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state == "awaiting_api_hash":
        data["api_hash"] = text
        data["state"] = "awaiting_phone"
        await message.reply_text(
            "✅ Got API Hash.\n\n**Step 3 / 3** — send your **Phone Number**\n"
            "in international format (e.g. `+1234567890`):",
            reply_markup=_cancel_kb(),
        )
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state == "awaiting_phone":
        data["phone"] = text
        msg = await message.reply_text(
            "⏳ Generating session and requesting code from Telegram…"
        )

        try:
            session_name = f"temp_session_{user_id}_{random.randint(1000, 9999)}"
            data["client"] = Client(
                session_name,
                api_id=data["api_id"],
                api_hash=data["api_hash"],
                in_memory=True,
            )
            await data["client"].connect()
            sent_code = await data["client"].send_code(data["phone"])
            data["phone_code_hash"] = sent_code.phone_code_hash
            data["state"] = "awaiting_code"

            with contextlib.suppress(MessageNotModified):
                await msg.edit_text(
                    "✅ **Verification Code Sent!**\n\n"
                    "Check your Telegram app for the login code.\n"
                    "**IMPORTANT:** Enter the code with spaces to avoid "
                    "Telegram's security triggers.\n"
                    "Example: if your code is `12345`, enter `1 2 3 4 5`.",
                    reply_markup=_cancel_kb(),
                )
        except ApiIdInvalid:
            await _error_screen(msg, "❌ **Invalid API ID / Hash.** Setup failed.", user_id)
        except PhoneNumberInvalid:
            await _error_screen(msg, "❌ **Invalid Phone Number.** Setup failed.", user_id)
        except Exception as e:
            await _error_screen(msg, f"❌ **Error requesting code:** {e}", user_id)
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state == "awaiting_code":
        code = text.replace(" ", "")
        msg = await message.reply_text("⏳ Verifying code…")

        userbot = data.get("client")
        try:
            await userbot.sign_in(data["phone"], data["phone_code_hash"], code)
            await finalize_setup(userbot, user_id, msg)
        except SessionPasswordNeeded:
            data["state"] = "awaiting_password"
            await msg.edit_text(
                "🔐 **Two-Step Verification Enabled**\n\n"
                "Please enter your 2FA password:",
                reply_markup=_cancel_kb(),
            )
        except PhoneCodeInvalid:
            with contextlib.suppress(MessageNotModified):
                await msg.edit_text(
                    "❌ **Invalid Code.** Try again or restart setup.",
                    reply_markup=_cancel_kb(),
                )
        except Exception as e:
            await _error_screen(msg, f"❌ **Sign In Error:** {e}", user_id)
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state == "awaiting_password":
        msg = await message.reply_text("⏳ Verifying password…")
        userbot = data.get("client")
        try:
            await userbot.check_password(text)
            await finalize_setup(userbot, user_id, msg)
        except PasswordHashInvalid:
            await msg.edit_text(
                "❌ **Invalid Password.** Try again.",
                reply_markup=_cancel_kb(),
            )
        except Exception as e:
            await _error_screen(msg, f"❌ **Error:** {e}", user_id)
        from pyrogram import StopPropagation
        raise StopPropagation

async def finalize_setup(userbot, user_id, msg):
    try:
        me = await userbot.get_me()
        if not me.is_premium:
            await msg.edit_text(
                frame(
                    "❌ **𝕏TV Pro™ — Premium Account Required**",
                    "> Your account doesn't have Telegram Premium.\n"
                    "> Buy it or complete the setup with an account that has\n"
                    "> Premium to unlock 4 GB uploads.",
                ),
                reply_markup=_back_kb(),
            )
            await userbot.disconnect()
            del pro_setup_sessions[user_id]
            return

        session_string = await userbot.export_session_string()
        data = pro_setup_sessions[user_id]

        # Capture rich userbot metadata so the Manage screen can show real
        # account details instead of a generic "Active" line.
        prem_expires = getattr(me, "premium_expire_date", None) or getattr(
            me, "premium_expires_date", None
        )
        await db.save_pro_session(
            session_string,
            data["api_id"],
            data["api_hash"],
            phone_number=data.get("phone"),
            userbot_user_id=getattr(me, "id", None),
            userbot_first_name=getattr(me, "first_name", None),
            userbot_username=getattr(me, "username", None),
            is_premium=bool(getattr(me, "is_premium", False)),
            premium_expires_at=prem_expires,
        )

        main_app = msg._client
        if not getattr(main_app, "user_bot", None):
            main_app.user_bot = Client(
                "xtv_user_bot",
                api_id=data["api_id"],
                api_hash=data["api_hash"],
                session_string=session_string,
                workers=50,
                max_concurrent_transmissions=10,
            )
            await main_app.user_bot.start()
            logger.info("𝕏TV Pro™ Premium Userbot Hot-Started Successfully!")

        with contextlib.suppress(MessageNotModified):
            await msg.edit_text(
                frame(
                    "✅ **𝕏TV Pro™ — Setup Complete**",
                    f"> Successfully authenticated as **{me.first_name}**.\n"
                    "> Session string and credentials saved to the database.\n"
                    "> 𝕏TV Pro™ is now active and ready to process >2 GB files.",
                ),
                reply_markup=_back_kb("admin_main"),
            )
        await userbot.disconnect()
        del pro_setup_sessions[user_id]
    except Exception as e:
        await _error_screen(msg, f"❌ **Failed to finalize setup:** {e}", user_id)

async def _handle_change_tunnel_text(client, message, info):
    """Resolve admin's reply for `🆔 Change Tunnel` and persist the new id."""
    user_id = message.from_user.id
    val = (message.text or "").strip()

    if not val:
        await message.reply_text("Send a channel `@username`, numeric ID, `none`, or `cancel`.")
        return

    if val.lower() in ("cancel", "/cancel"):
        pro_change_sessions.pop(user_id, None)
        await message.reply_text("Cancelled.", reply_markup=_back_kb())
        return

    if val.lower() == "none":
        await db.update_pro_session(tunnel_id=None, tunnel_link=None)
        pro_change_sessions.pop(user_id, None)
        await message.reply_text("✅ Tunnel cleared.", reply_markup=_back_kb())
        return

    # Resolve the channel via the userbot — it has to be a member to post,
    # so resolution from the userbot is the authoritative check.
    user_bot = getattr(client, "user_bot", None)
    if user_bot is None:
        await message.reply_text(
            "❌ Userbot not running. Run a Health Check first.",
            reply_markup=_back_kb(),
        )
        pro_change_sessions.pop(user_id, None)
        return

    target = val
    if val.lstrip("-").isdigit():
        target = int(val)

    try:
        chat = await user_bot.get_chat(target)
        link = getattr(chat, "invite_link", None) or (
            f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
        )
        await db.save_pro_tunnel(chat.id, link)
        pro_change_sessions.pop(user_id, None)
        title = chat.title or chat.username or str(chat.id)
        await message.reply_text(
            f"✅ Tunnel set to **{title}** (`{chat.id}`).",
            reply_markup=_back_kb(),
        )
    except Exception as e:
        logger.warning(f"Change tunnel failed for {val}: {e}")
        await message.reply_text(
            f"❌ Could not resolve `{val}`: {e}\nMake sure the userbot is a member.",
            reply_markup=_cancel_kb(),
        )


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
