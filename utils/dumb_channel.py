# --- Imports ---
import re
import enum
from dataclasses import dataclass
from typing import Optional, Tuple, Any

from utils.log import get_logger

logger = get_logger("utils.dumb_channel")

# ==========================================================================
# Unified Dumb-Channel resolver & validator
# --------------------------------------------------------------------------
# Two public coroutines:
#   resolve_channel(client, message_or_text) -> (ch_id, ch_name, error)
#   validate_bot_admin(client, ch_id)        -> ValidationResult
#
# Accepts forwarded messages (both the legacy forward_from_chat API and the
# newer forward_origin API), numeric `-100…` IDs, `@username`, bare usernames,
# and `t.me/<user>` / `t.me/c/<internal_id>` links. Rejects invite links
# (`t.me/+…`) with a helpful hint because the bot must be promoted before
# it can access a channel.
# ==========================================================================


class ValidationStatus(enum.Enum):
    OK_ADMIN_POST = "ok_admin_post"        # Admin with post rights (or creator).
    OK_ADMIN_NO_POST = "ok_admin_no_post"  # Admin but missing post rights.
    MEMBER_NO_ADMIN = "member_no_admin"    # Bot is a member but not admin.
    NOT_MEMBER = "not_member"              # Bot not in channel.
    INVALID = "invalid"                    # Chat unreachable / wrong type.


@dataclass
class ValidationResult:
    status: ValidationStatus
    channel_id: Optional[int] = None
    channel_name: Optional[str] = None
    channel_type: Optional[str] = None
    error_detail: Optional[str] = None


# --- Regex patterns for link parsing ---------------------------------------

_TME_PRIVATE = re.compile(
    r"(?:https?://)?t\.me/c/(\d+)(?:/\d+)?/?$", re.IGNORECASE
)
_TME_INVITE = re.compile(
    r"(?:https?://)?t\.me/(?:joinchat/)?(\+[A-Za-z0-9_\-]+)/?$", re.IGNORECASE
)
_TME_PUBLIC = re.compile(
    r"(?:https?://)?t\.me/([A-Za-z][A-Za-z0-9_]{3,})/?$", re.IGNORECASE
)
_USERNAME = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,})$")
_NUMERIC_CHANNEL = re.compile(r"^-?100\d{6,}$")


def _extract_forward_chat(message: Any) -> Optional[Tuple[int, str]]:
    """Pull (chat_id, title) from a forwarded message, supporting both the
    legacy `forward_from_chat` and the newer `forward_origin.chat` APIs."""
    if message is None:
        return None
    # Legacy API (pyrogram < forward_origin).
    fwd_chat = getattr(message, "forward_from_chat", None)
    if fwd_chat:
        return fwd_chat.id, (fwd_chat.title or "Channel")
    # New API (forward_origin.chat for channel forwards).
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        chat = getattr(origin, "chat", None)
        if chat:
            return chat.id, (getattr(chat, "title", None) or "Channel")
        # sender_chat fallback (some clients expose it here)
        sender_chat = getattr(origin, "sender_chat", None)
        if sender_chat:
            return sender_chat.id, (getattr(sender_chat, "title", None) or "Channel")
    return None


def _parse_input(text: str) -> Tuple[Optional[Any], Optional[str]]:
    """Convert free-form text into a resolver target usable by
    `Client.get_chat()`. Returns `(target, error)`."""
    text = (text or "").strip()
    if not text:
        return None, "No input provided."

    # Reject invite links — the bot would have to join first.
    if _TME_INVITE.match(text):
        return None, (
            "Invite links aren't supported — first add me to the channel as "
            "admin, then send a forward, @username or -100… ID."
        )

    # Private channel link (t.me/c/<internal>).
    m = _TME_PRIVATE.match(text)
    if m:
        try:
            return int(f"-100{m.group(1)}"), None
        except ValueError:
            return None, "Malformed private channel link."

    # Public link (t.me/<user>). Skip reserved paths like 'joinchat', 'c'.
    m = _TME_PUBLIC.match(text)
    if m:
        uname = m.group(1)
        if uname.lower() not in ("c", "joinchat", "share", "proxy", "iv"):
            return uname, None

    # Bare -100… numeric id, or a bare 100… (user forgot the minus).
    if _NUMERIC_CHANNEL.match(text):
        try:
            cid = int(text) if text.startswith("-") else int(f"-{text}")
            return cid, None
        except ValueError:
            pass

    # @username / bare username.
    m = _USERNAME.match(text)
    if m:
        return m.group(1), None

    return None, (
        "Couldn't parse input. Send a forwarded message, an @username, "
        "a `-100…` ID, or a `t.me/…` link."
    )


async def resolve_channel(
    client, message_or_text: Any
) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """Resolve a channel from either a pyrogram Message or a plain string.

    Returns: `(channel_id, channel_name, error)`.
      - on success → `(id, name, None)`
      - on failure → `(None, None, "human-readable reason")`
    """
    # Step 1: forwarded-message fast path.
    if not isinstance(message_or_text, str):
        fwd = _extract_forward_chat(message_or_text)
        if fwd is not None:
            ch_id, ch_name = fwd
            return ch_id, ch_name, None
        text = (getattr(message_or_text, "text", None) or "").strip()
    else:
        text = message_or_text

    target, err = _parse_input(text)
    if target is None:
        return None, None, err

    # Step 2: hit Telegram to resolve.
    try:
        chat = await client.get_chat(target)
    except Exception as e:
        # Keep the exception type in the message to help users debug.
        return None, None, f"Telegram couldn't find that channel ({type(e).__name__}: {e})."

    return chat.id, (chat.title or "Channel"), None


def _status_str(member) -> str:
    """Normalize the member status across pyrogram versions (enum vs string)."""
    st = getattr(member, "status", None)
    if st is None:
        return ""
    return getattr(st, "value", str(st)).lower()


async def validate_bot_admin(client, channel_id: int) -> ValidationResult:
    """Check the bot's membership + permissions in `channel_id`."""
    # Resolve chat first.
    try:
        chat = await client.get_chat(channel_id)
    except Exception as e:
        return ValidationResult(
            status=ValidationStatus.INVALID,
            channel_id=channel_id,
            error_detail=f"Can't access chat: {e}",
        )

    ch_type = getattr(getattr(chat, "type", None), "value", str(getattr(chat, "type", ""))).lower()
    ch_title = getattr(chat, "title", None) or "Channel"

    if ch_type not in ("channel", "supergroup"):
        return ValidationResult(
            status=ValidationStatus.INVALID,
            channel_id=chat.id,
            channel_name=ch_title,
            channel_type=ch_type,
            error_detail=(
                "This chat is not a channel or supergroup — dumb channels must "
                "be a channel the bot can post into."
            ),
        )

    try:
        me = await client.get_me()
        member = await client.get_chat_member(chat.id, me.id)
    except Exception as e:
        # Pyrogram raises UserNotParticipant, but the class moved around across
        # versions — treat any failure here as NOT_MEMBER with the message kept.
        reason = f"{type(e).__name__}: {e}"
        return ValidationResult(
            status=ValidationStatus.NOT_MEMBER,
            channel_id=chat.id,
            channel_name=ch_title,
            channel_type=ch_type,
            error_detail=reason,
        )

    status = _status_str(member)

    if "owner" in status or "creator" in status:
        return ValidationResult(
            status=ValidationStatus.OK_ADMIN_POST,
            channel_id=chat.id,
            channel_name=ch_title,
            channel_type=ch_type,
        )

    if "administrator" in status or "admin" in status:
        priv = getattr(member, "privileges", None)
        can_post = False
        if priv is not None:
            # Channels: can_post_messages. Supergroups: having any admin privs
            # typically allows posting via the bot API.
            can_post = (
                bool(getattr(priv, "can_post_messages", False))
                or bool(getattr(priv, "can_manage_chat", False))
                or bool(getattr(priv, "can_delete_messages", False))
            )
        # Supergroups don't use can_post_messages — treat admin-in-supergroup
        # as OK by default.
        if ch_type == "supergroup":
            can_post = True
        if can_post:
            return ValidationResult(
                status=ValidationStatus.OK_ADMIN_POST,
                channel_id=chat.id,
                channel_name=ch_title,
                channel_type=ch_type,
            )
        return ValidationResult(
            status=ValidationStatus.OK_ADMIN_NO_POST,
            channel_id=chat.id,
            channel_name=ch_title,
            channel_type=ch_type,
        )

    if "member" in status:
        return ValidationResult(
            status=ValidationStatus.MEMBER_NO_ADMIN,
            channel_id=chat.id,
            channel_name=ch_title,
            channel_type=ch_type,
        )

    return ValidationResult(
        status=ValidationStatus.NOT_MEMBER,
        channel_id=chat.id,
        channel_name=ch_title,
        channel_type=ch_type,
        error_detail=f"Unexpected member status: {status!r}",
    )


def already_configured(channels_dict: dict, channel_id: int) -> bool:
    """Check whether the given channel is already in the user's/global list.
    `channels_dict` is what `db.get_dumb_channels()` returns — keys may be
    strings or ints depending on how they were inserted."""
    if not channels_dict:
        return False
    sid = str(channel_id)
    if sid in channels_dict:
        return True
    try:
        return int(channel_id) in channels_dict
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
