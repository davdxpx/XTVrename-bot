# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Dynamic help-guide builder.

Every `/help` page is rendered as a pure function here and dispatched by
`plugins/help.py`. Builders read their state from a single `HelpContext`
that is loaded once per callback via `build_help_context(user_id)` — no
builder touches the database on its own.

The gate logic mirrors `plugins/start.py:290-361` exactly so the help
guide tracks whatever the admin has enabled in `/admin` right now:

* Tool buttons disappear when a toggle is off (premium-plan override keeps
  the button visible if the user owns a plan that re-enables the tool).
* The 💎 Premium main-menu button obeys `premium_system_enabled`.
* The 📁 File Management main-menu button obeys `myfiles_enabled`.
* Premium / Quotas text is rendered from live admin values — prices,
  egress, file count, MyFiles limits, trial days — no stale copy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db

# ---------------------------------------------------------------------------
# Formatting helpers (shared with plugins/premium.py)
# ---------------------------------------------------------------------------

def format_egress(mb: int | float) -> str:
    """Format an egress quota in MB to the largest sensible unit."""
    if mb is None or mb <= 0:
        return "Unlimited"
    if mb >= 1048576:
        return f"{mb / 1048576:.2f} TB"
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{int(mb)} MB"


def format_limit(n: int | None) -> str:
    """Format a count where -1 (or None) means unlimited."""
    if n is None or n == -1:
        return "Unlimited"
    return str(n)


def format_file_count(n: int | None) -> str:
    """Format a daily-file-count field. 0 or None is treated as unlimited."""
    if n is None or n <= 0:
        return "Unlimited"
    return str(n)


def format_expiry_days(n: int | None) -> str:
    """Format a MyFiles expiry in days. -1 means never expire."""
    if n is None or n == -1:
        return "Never"
    return f"{n} days"


# ---------------------------------------------------------------------------
# Tool registry — single source of truth for button grids and gates.
# The `toggle_key` matches the key in `feature_toggles` and in each plan's
# `features` dict (premium_standard.features / premium_deluxe.features).
# `always=True` marks tools that are never gated (mirrors start.py logic).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolEntry:
    toggle_key: str
    label: str
    callback: str
    always: bool = False


TOOLS: tuple[ToolEntry, ...] = (
    ToolEntry("rename",                "📁 Rename & Tag Media",  "help_tool_rename",    always=True),
    ToolEntry("audio_editor",          "🎵 Audio Editor",        "help_tool_audio"),
    ToolEntry("file_converter",        "🔀 File Converter",      "help_tool_convert"),
    ToolEntry("watermarker",           "© Image Watermarker",    "help_tool_watermark"),
    ToolEntry("subtitle_extractor",    "📝 Subtitle Extractor",  "help_tool_subtitle"),
    ToolEntry("video_trimmer",         "✂️ Video Trimmer",       "help_tool_trimmer"),
    ToolEntry("media_info",            "ℹ️ Media Info",          "help_tool_mediainfo"),
    ToolEntry("voice_converter",       "🎙️ Voice Converter",     "help_tool_voice"),
    ToolEntry("video_note_converter",  "⭕ Video Note",          "help_tool_videonote"),
    ToolEntry("youtube_tool",          "▶️ YouTube Tool",        "help_tool_youtube"),
    ToolEntry("mirror_leech",          "☁️ Mirror-Leech",        "help_tool_ml",        always=True),
)

TOOL_BY_CALLBACK: dict[str, ToolEntry] = {t.callback: t for t in TOOLS}


# ---------------------------------------------------------------------------
# HelpContext — loaded once per render
# ---------------------------------------------------------------------------

@dataclass
class HelpContext:
    user_id: int
    toggles: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    myfiles_enabled: bool = False
    is_premium: bool = False
    plan: str = "free"                          # "free" | "standard" | "deluxe"
    plan_features: dict[str, Any] = field(default_factory=dict)
    premium_expiry: float | None = None
    trial_claimed: bool = False

    # Convenience flags derived from config (computed in the factory)
    premium_system_enabled: bool = False
    premium_deluxe_enabled: bool = False
    premium_trial_enabled: bool = False
    premium_trial_days: int = 0


async def build_help_context(user_id: int) -> HelpContext:
    """Load every admin-state input the help guide needs, exactly once."""
    try:
        toggles = await db.get_feature_toggles() or {}
    except Exception:
        toggles = {}

    try:
        config = await db.get_public_config() or {}
    except Exception:
        config = {}

    try:
        myfiles_enabled = bool(await db.get_setting("myfiles_enabled", default=False))
    except Exception:
        myfiles_enabled = False

    ctx = HelpContext(
        user_id=user_id,
        toggles=toggles,
        config=config,
        myfiles_enabled=myfiles_enabled,
        premium_system_enabled=bool(config.get("premium_system_enabled", False)),
        premium_deluxe_enabled=bool(config.get("premium_deluxe_enabled", False)),
        premium_trial_enabled=bool(config.get("premium_trial_enabled", False)),
        premium_trial_days=int(config.get("premium_trial_days", 0) or 0),
    )

    # Premium user resolution mirrors plugins/premium.py:28-34
    if Config.PUBLIC_MODE:
        try:
            user_doc = await db.get_user(user_id)
        except Exception:
            user_doc = None
        if user_doc:
            exp = user_doc.get("premium_expiry")
            if user_doc.get("is_premium") and (exp is None or exp > time.time()):
                ctx.is_premium = True
                ctx.plan = user_doc.get("premium_plan", "standard") or "standard"
                ctx.premium_expiry = exp
            ctx.trial_claimed = bool(user_doc.get("trial_claimed", False))

        if ctx.is_premium and ctx.premium_system_enabled:
            plan_settings = config.get(f"premium_{ctx.plan}", {}) or {}
            ctx.plan_features = plan_settings.get("features", {}) or {}

    return ctx


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def is_tool_available(tool_key: str, ctx: HelpContext) -> bool:
    """Mirror of plugins/start.py:342-346 — same truth table everywhere."""
    entry = next((t for t in TOOLS if t.toggle_key == tool_key), None)
    if entry and entry.always:
        return True
    if ctx.toggles.get(tool_key, True):
        return True
    return bool(ctx.is_premium and ctx.plan_features.get(tool_key, False))


def is_callback_tool_available(callback: str, ctx: HelpContext) -> bool:
    entry = TOOL_BY_CALLBACK.get(callback)
    if entry is None:
        return True
    return is_tool_available(entry.toggle_key, ctx)


# ---------------------------------------------------------------------------
# Common UI pieces
# ---------------------------------------------------------------------------

_BACK_TO_GUIDE = [[InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]]
_BACK_TO_TOOLS = [[InlineKeyboardButton("← Back to Tools", callback_data="help_tools")]]
_BACK_TO_PREMIUM = [[InlineKeyboardButton("← Back to Premium", callback_data="help_premium")]]


def back_to(callback: str, label: str = "← Back") -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(label, callback_data=callback)]]


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

_MAIN_MENU_TEXT = (
    "**📖 MediaStudio Guide**\n\n"
    "> Welcome to your complete reference manual.\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Whether you are organizing a massive media library of popular series and movies, "
    "or just want to process and manage your **personal media** and files, I can help!\n\n"
    "Please select a topic below to explore the guide:"
)


def build_main_menu(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    """Render the top-level help menu with admin-gated buttons."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("🚀 Quick Start", callback_data="help_quickstart")],
        [InlineKeyboardButton("🛠 All Tools & Features", callback_data="help_tools")],
    ]

    # Row: File Management + Auto-Detect (File Mgmt gated on myfiles_enabled)
    row = []
    if ctx.myfiles_enabled:
        row.append(InlineKeyboardButton("📁 File Management", callback_data="help_file_management"))
    row.append(InlineKeyboardButton("🤖 Auto-Detect", callback_data="help_auto_detect"))
    rows.append(row)

    rows.append([
        InlineKeyboardButton("📄 Personal & General", callback_data="help_general"),
        InlineKeyboardButton("🏷️ Templates", callback_data="help_templates"),
    ])
    rows.append([
        InlineKeyboardButton("📺 Dumb Channels", callback_data="help_dumb_channels"),
        InlineKeyboardButton("🔗 Bot Commands", callback_data="help_commands"),
    ])
    rows.append([InlineKeyboardButton("⚙️ Settings & Info", callback_data="help_settings")])
    rows.append([
        InlineKeyboardButton("🎞️ Formats & Codecs", callback_data="help_formats"),
        InlineKeyboardButton("📈 Quotas & Limits", callback_data="help_quotas"),
    ])

    # Premium is gated on premium_system_enabled
    if ctx.premium_system_enabled:
        rows.append([InlineKeyboardButton("💎 Premium Plans", callback_data="help_premium")])

    rows.append([InlineKeyboardButton("🔧 Troubleshooting", callback_data="help_troubleshooting")])
    rows.append([InlineKeyboardButton("❌ Close", callback_data="help_close")])

    return _MAIN_MENU_TEXT, InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Tools menu
# ---------------------------------------------------------------------------

_TOOLS_MENU_HEADER = (
    "**🛠 All Tools & Features**\n\n"
    "> A complete suite of media processing tools.\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Pick any tool below to learn how to use it, what it does, and its shortcuts."
)

_TOOLS_MENU_EMPTY = (
    "**🛠 All Tools & Features**\n\n"
    "> Tools are currently being configured.\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "No tools are available right now. Please check back later."
)


def build_tools_menu(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    """Render the tools sub-menu with only the tools the user can access."""
    available = [t for t in TOOLS if is_tool_available(t.toggle_key, ctx)]

    if not available:
        rows = [[InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")]]
        return _TOOLS_MENU_EMPTY, InlineKeyboardMarkup(rows)

    rows: list[list[InlineKeyboardButton]] = []
    # Rename always gets its own full-width row if available (matches current UI).
    rename_entry = next((t for t in available if t.toggle_key == "rename"), None)
    mirror_entry = next((t for t in available if t.toggle_key == "mirror_leech"), None)
    youtube_entry = next((t for t in available if t.toggle_key == "youtube_tool"), None)

    if rename_entry:
        rows.append([InlineKeyboardButton(rename_entry.label, callback_data=rename_entry.callback)])

    # Middle tools go into 2-wide rows; exclude the full-width ones.
    middle = [
        t for t in available
        if t.toggle_key not in ("rename", "youtube_tool", "mirror_leech")
    ]
    for i in range(0, len(middle), 2):
        pair = middle[i : i + 2]
        rows.append([InlineKeyboardButton(t.label, callback_data=t.callback) for t in pair])

    if youtube_entry:
        rows.append([InlineKeyboardButton(youtube_entry.label, callback_data=youtube_entry.callback)])
    if mirror_entry:
        rows.append([InlineKeyboardButton(mirror_entry.label, callback_data=mirror_entry.callback)])

    rows.append([InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")])
    return _TOOLS_MENU_HEADER, InlineKeyboardMarkup(rows)


DISABLED_TOOL_ALERT = "This tool is currently disabled."


# ---------------------------------------------------------------------------
# Quotas
# ---------------------------------------------------------------------------

def _tier_line(emoji: str, label: str, egress_mb, file_count, expiry_days=None) -> str:
    parts = [
        f"{emoji} **{label}:**",
        f"Egress `{format_egress(egress_mb)}`",
        f"· Files `{format_file_count(file_count)}`",
    ]
    if expiry_days is not None:
        parts.append(f"· Expiry `{format_expiry_days(expiry_days)}`")
    return " ".join(parts)


def build_quotas(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    """Render Quotas & Limits from the admin's actual configured values."""
    cfg = ctx.config
    mf_limits = cfg.get("myfiles_limits", {}) or {}

    free_expiry = mf_limits.get("free", {}).get("expiry_days") if ctx.myfiles_enabled else None
    lines: list[str] = [
        "**📈 Quotas & Limits**",
        "",
        "> Fair-use limits, updated live from admin settings.",
        "━━━━━━━━━━━━━━━━━━━━",
        _tier_line("🆓", "Free", cfg.get("daily_egress_mb", 0), cfg.get("daily_file_count", 0), free_expiry),
    ]

    if ctx.premium_system_enabled:
        std = cfg.get("premium_standard", {}) or {}
        std_expiry = mf_limits.get("standard", {}).get("expiry_days") if ctx.myfiles_enabled else None
        lines.append(_tier_line(
            "⭐", "Standard",
            std.get("daily_egress_mb", 0), std.get("daily_file_count", 0), std_expiry,
        ))

    if ctx.premium_deluxe_enabled:
        dlx = cfg.get("premium_deluxe", {}) or {}
        dlx_expiry = mf_limits.get("deluxe", {}).get("expiry_days") if ctx.myfiles_enabled else None
        lines.append(_tier_line(
            "💎", "Deluxe",
            dlx.get("daily_egress_mb", 0), dlx.get("daily_file_count", 0), dlx_expiry,
        ))

    lines.append("")
    if ctx.myfiles_enabled:
        lines.append("Check `/profile` or `/myfiles` for your current usage.")
    else:
        lines.append("Check `/profile` for your current usage.")

    return "\n".join(lines), InlineKeyboardMarkup(_BACK_TO_GUIDE)


# ---------------------------------------------------------------------------
# Premium — landing hub + sub-pages
# ---------------------------------------------------------------------------

# Cascade: advertise a plan tool perk only when the plan enables it AND it is
# currently disabled globally (mirrors plugins/premium.py:126-137).
_PLAN_CASCADE_TOOLS: tuple[tuple[str, str], ...] = (
    ("subtitle_extractor", "💬 Subtitle Extractor"),
    ("watermarker",        "🎨 Image Watermarker"),
    ("file_converter",     "🔄 File Converter"),
    ("audio_editor",       "🎵 Audio Editor"),
    ("youtube_tool",       "▶️ YouTube Tool"),
    ("video_trimmer",      "✂️ Video Trimmer"),
    ("media_info",         "ℹ️ Media Info"),
    ("voice_converter",    "🎙️ Voice Converter"),
    ("video_note_converter", "⭕ Video Note"),
    ("4k_enhancement",     "🖼 4K Enhancement"),
    ("batch_processing_pro", "📦 Batch Pro"),
)


def _plan_perks(features: dict[str, Any], toggles: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if features.get("priority_queue"):
        lines.append("🚀 Priority Queue")
    if features.get("batch_sharing"):
        lines.append("🔗 Batch Sharing")
    if features.get("xtv_pro_4gb"):
        lines.append("⚡ XTV Pro 4GB Bypass")
    for key, label in _PLAN_CASCADE_TOOLS:
        if features.get(key) and not toggles.get(key, True):
            lines.append(label)
    return lines


def _premium_hub_text(ctx: HelpContext) -> str:
    lines = [
        "**💎 Premium Plans**",
        "",
        "> Live status from admin settings.",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if ctx.is_premium:
        plan_label = "💎 Deluxe" if ctx.plan == "deluxe" else "⭐ Standard"
        lines.append(f"**Your plan:** `{plan_label}` — active ✅")
    else:
        lines.append("**Your plan:** `Free`")

    tiers = []
    if ctx.premium_system_enabled:
        tiers.append("⭐ Standard")
    if ctx.premium_deluxe_enabled:
        tiers.append("💎 Deluxe")
    if ctx.premium_trial_enabled and ctx.premium_trial_days > 0:
        tiers.append(f"🎁 Trial ({ctx.premium_trial_days}d)")
    if tiers:
        lines.append("**Available:** " + " · ".join(tiers))

    lines.append("")
    lines.append("Pick a topic below:")
    return "\n".join(lines)


def build_premium_landing(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    rows: list[list[InlineKeyboardButton]] = []

    if ctx.is_premium:
        rows.append([InlineKeyboardButton("🪪 My Plan", callback_data="help_premium_myplan")])

    if ctx.premium_trial_enabled and ctx.premium_trial_days > 0:
        rows.append([InlineKeyboardButton("🎁 Free Trial", callback_data="help_premium_trial")])

    tier_row: list[InlineKeyboardButton] = []
    if ctx.premium_system_enabled:
        tier_row.append(InlineKeyboardButton("⭐ Standard", callback_data="help_premium_standard"))
    if ctx.premium_deluxe_enabled:
        tier_row.append(InlineKeyboardButton("💎 Deluxe", callback_data="help_premium_deluxe"))
    if tier_row:
        rows.append(tier_row)

    rows.append([InlineKeyboardButton("✨ Perks Cascade", callback_data="help_premium_perks")])
    if ctx.myfiles_enabled:
        rows.append([InlineKeyboardButton("📦 MyFiles Limits", callback_data="help_premium_limits")])

    rows.append([InlineKeyboardButton("← Back to Help Menu", callback_data="help_guide")])
    return _premium_hub_text(ctx), InlineKeyboardMarkup(rows)


def build_premium_myplan(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    if not ctx.is_premium:
        text = (
            "**🪪 My Plan**\n\n"
            "> No active premium plan.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "You are currently on the Free tier. Tap Standard or Deluxe on the Premium hub "
            "to see what each plan unlocks."
        )
        return text, InlineKeyboardMarkup(_BACK_TO_PREMIUM)

    if ctx.premium_expiry:
        exp_str = datetime.fromtimestamp(ctx.premium_expiry).strftime("%Y-%m-%d %H:%M")
    else:
        exp_str = "Lifetime"

    plan_label = "💎 Deluxe" if ctx.plan == "deluxe" else "⭐ Standard"
    perks = _plan_perks(ctx.plan_features, ctx.toggles)
    perks_line = "\n".join(f"• {p}" for p in perks) if perks else "• (see Perks Cascade)"

    plan_settings = ctx.config.get(f"premium_{ctx.plan}", {}) or {}
    egress = format_egress(plan_settings.get("daily_egress_mb", 0))
    files = format_file_count(plan_settings.get("daily_file_count", 0))

    text = (
        f"**🪪 My Plan**\n\n"
        f"> Your active benefits.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"**Plan:** `{plan_label}`\n"
        f"**Expiry:** `{exp_str}`\n"
        f"**Daily Egress:** `{egress}` · **Files:** `{files}`\n\n"
        f"**Active perks:**\n{perks_line}"
    )
    return text, InlineKeyboardMarkup(_BACK_TO_PREMIUM)


def build_premium_trial(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    if not (ctx.premium_trial_enabled and ctx.premium_trial_days > 0):
        text = (
            "**🎁 Free Trial**\n\n"
            "> No trial is currently offered.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "The admin has disabled the trial. Check back later."
        )
        return text, InlineKeyboardMarkup(_BACK_TO_PREMIUM)

    claimed = "already claimed ✅" if ctx.trial_claimed else "still available 🎁"
    text = (
        f"**🎁 Free Trial**\n\n"
        f"> Try Premium risk-free.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Length:** `{ctx.premium_trial_days} days`\n"
        f"• **Your status:** {claimed}\n\n"
        f"Open `/start` → `💎 Premium Dashboard` to claim it."
    )
    return text, InlineKeyboardMarkup(_BACK_TO_PREMIUM)


def _plan_page(label: str, emoji: str, plan_key: str, ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    plan = ctx.config.get(f"premium_{plan_key}", {}) or {}
    mf = (ctx.config.get("myfiles_limits", {}) or {}).get(plan_key, {}) or {}

    price = plan.get("price_string", "—")
    stars = plan.get("stars_price", 0)
    stars_line = f" · ⭐ `{stars}`" if stars else ""

    egress = format_egress(plan.get("daily_egress_mb", 0))
    files = format_file_count(plan.get("daily_file_count", 0))

    lines = [
        f"**{emoji} Premium {label}**",
        "",
        "> Current admin configuration.",
        "━━━━━━━━━━━━━━━━━━━━",
        f"**Price:** `{price}`{stars_line}",
        f"**Daily Egress:** `{egress}`",
        f"**Daily Files:** `{files}`",
    ]
    if ctx.myfiles_enabled:
        lines.append(
            f"**MyFiles:** perm `{format_limit(mf.get('permanent_limit'))}` · "
            f"folders `{format_limit(mf.get('folder_limit'))}` · "
            f"expiry `{format_expiry_days(mf.get('expiry_days'))}`"
        )
    perks = _plan_perks(plan.get("features", {}) or {}, ctx.toggles)
    if perks:
        lines.append("")
        lines.append("**Perks:** " + " · ".join(perks))

    return "\n".join(lines), InlineKeyboardMarkup(_BACK_TO_PREMIUM)


def build_premium_standard(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    if not ctx.premium_system_enabled:
        text = (
            "**⭐ Premium Standard**\n\n"
            "> Premium is currently disabled.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "The admin has turned Premium off."
        )
        return text, InlineKeyboardMarkup(_BACK_TO_PREMIUM)
    return _plan_page("Standard", "⭐", "standard", ctx)


def build_premium_deluxe(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    if not ctx.premium_deluxe_enabled:
        text = (
            "**💎 Premium Deluxe**\n\n"
            "> Deluxe is currently disabled.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "The admin has not enabled the Deluxe tier."
        )
        return text, InlineKeyboardMarkup(_BACK_TO_PREMIUM)
    return _plan_page("Deluxe", "💎", "deluxe", ctx)


def build_premium_perks(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        "**✨ Perks Cascade**",
        "",
        "> What each plan adds on top of Free.",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if ctx.premium_system_enabled:
        std = (ctx.config.get("premium_standard", {}) or {}).get("features", {}) or {}
        std_perks = _plan_perks(std, ctx.toggles)
        lines.append("**⭐ Standard:**")
        lines.append("\n".join(f"• {p}" for p in std_perks) if std_perks else "• (no extras configured)")
    if ctx.premium_deluxe_enabled:
        dlx = (ctx.config.get("premium_deluxe", {}) or {}).get("features", {}) or {}
        dlx_perks = _plan_perks(dlx, ctx.toggles)
        lines.append("")
        lines.append("**💎 Deluxe:**")
        lines.append("\n".join(f"• {p}" for p in dlx_perks) if dlx_perks else "• (no extras configured)")
    if not ctx.premium_system_enabled and not ctx.premium_deluxe_enabled:
        lines.append("No premium perks are currently configured.")
    return "\n".join(lines), InlineKeyboardMarkup(_BACK_TO_PREMIUM)


def build_premium_limits(ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup]:
    if not ctx.myfiles_enabled:
        text = (
            "**📦 MyFiles Limits**\n\n"
            "> MyFiles is currently disabled.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "The admin has turned MyFiles off."
        )
        return text, InlineKeyboardMarkup(_BACK_TO_PREMIUM)

    mf = ctx.config.get("myfiles_limits", {}) or {}

    def row(emoji: str, label: str, key: str) -> str:
        tier = mf.get(key, {}) or {}
        return (
            f"{emoji} **{label}:** perm `{format_limit(tier.get('permanent_limit'))}` · "
            f"folders `{format_limit(tier.get('folder_limit'))}` · "
            f"expiry `{format_expiry_days(tier.get('expiry_days'))}`"
        )

    lines = [
        "**📦 MyFiles Limits**",
        "",
        "> Per-tier storage configuration.",
        "━━━━━━━━━━━━━━━━━━━━",
        row("🆓", "Free", "free"),
    ]
    if ctx.premium_system_enabled:
        lines.append(row("⭐", "Standard", "standard"))
    if ctx.premium_deluxe_enabled:
        lines.append(row("💎", "Deluxe", "deluxe"))

    return "\n".join(lines), InlineKeyboardMarkup(_BACK_TO_PREMIUM)


PREMIUM_SUB_BUILDERS: dict[str, Any] = {
    "help_premium_myplan":   build_premium_myplan,
    "help_premium_trial":    build_premium_trial,
    "help_premium_standard": build_premium_standard,
    "help_premium_deluxe":   build_premium_deluxe,
    "help_premium_perks":    build_premium_perks,
    "help_premium_limits":   build_premium_limits,
}


# ---------------------------------------------------------------------------
# Expanded tool sub-guides
#
# Each entry defines:
#   * hub_text  — overview shown on `help_tool_<name>`
#   * buttons   — rows of (label, child_callback) tuples
#   * children  — mapping child_callback → body text
#   * hub_cb    — this tool's parent callback (so children know where "back" goes)
#
# Text length target: every child page matches today's one-paragraph tool page.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolGuide:
    hub_cb: str
    hub_text: str
    buttons: tuple[tuple[tuple[str, str], ...], ...]
    children: dict[str, str]


def _hub_markup(guide: ToolGuide) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=cb) for (label, cb) in row]
        for row in guide.buttons
    ]
    rows.append([InlineKeyboardButton("← Back to Tools", callback_data="help_tools")])
    return InlineKeyboardMarkup(rows)


def _child_markup(hub_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("← Back", callback_data=hub_cb)],
        [InlineKeyboardButton("← Tools", callback_data="help_tools")],
    ])


TOOL_GUIDES: dict[str, ToolGuide] = {
    # ------------------------------------------------------------------
    # Rename & Tag Media
    # ------------------------------------------------------------------
    "help_tool_rename": ToolGuide(
        hub_cb="help_tool_rename",
        hub_text=(
            "**📁 Rename & Tag Media**\n\n"
            "> The core feature of the bot.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Send any file and it is auto-scanned, named, and tagged.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/r` or `/rename`"
        ),
        buttons=(
            (("🚀 How to Use", "help_rn_howto"), ("⚡ Shortcuts", "help_rn_shortcuts")),
            (("🎞 TMDb Lookup", "help_rn_tmdb"), ("✏️ Manual Mode", "help_rn_manual")),
        ),
        children={
            "help_rn_howto": (
                "**🚀 How to Use Rename**\n\n"
                "> Three steps, no setup.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "1. Send a file to the bot.\n"
                "2. Confirm the detected metadata or edit it.\n"
                "3. Receive the renamed & tagged file.\n\n"
                "Filename templates from `/settings` are applied automatically."
            ),
            "help_rn_shortcuts": (
                "**⚡ Shortcuts**\n\n"
                "> Fast paths for repeat work.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• `/r` or `/rename` — start from a replied-to file.\n"
                "• Reply to a batch with `/r` to process multiple.\n"
                "• `/g` — General Mode (skip TMDb lookup).\n"
                "• `/end` — cancel the current session."
            ),
            "help_rn_tmdb": (
                "**🎞 TMDb Lookup**\n\n"
                "> Automatic poster + metadata.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Known movies and series are matched against TMDb for the official "
                "title, year, poster, and episode info. You always get a confirm "
                "screen — tap **Skip / Manual** to bypass it for personal files."
            ),
            "help_rn_manual": (
                "**✏️ Manual Mode**\n\n"
                "> Full control over names.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Pick **Skip / Manual** on the TMDb screen to enter your own title. "
                "Extensions are added automatically. Use `/g` for pure filename "
                "processing without any metadata lookup."
            ),
        },
    ),

    # ------------------------------------------------------------------
    # Audio Editor
    # ------------------------------------------------------------------
    "help_tool_audio": ToolGuide(
        hub_cb="help_tool_audio",
        hub_text=(
            "**🎵 Audio Metadata Editor**\n\n"
            "> Perfect for your music collection.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Edit ID3 tags, album art, and track info on MP3, FLAC, M4A and more.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/a` or `/audio`"
        ),
        buttons=(
            (("🚀 How to Use", "help_ae_howto"), ("🏷 Tags", "help_ae_tags")),
            (("🖼 Cover Art", "help_ae_cover"), ("💡 Tips", "help_ae_tips")),
        ),
        children={
            "help_ae_howto": (
                "**🚀 How to Use Audio Editor**\n\n"
                "> Tag in three taps.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "1. Send an audio file (or reply to one with `/a`).\n"
                "2. Pick the field to edit — Title, Artist, Album, Cover.\n"
                "3. Send the new value. Repeat for any other field.\n"
                "4. Hit **Save** and the tagged file is returned."
            ),
            "help_ae_tags": (
                "**🏷 Supported Tags**\n\n"
                "> Core ID3 fields.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **Title** — track title\n"
                "• **Artist** — performing artist\n"
                "• **Album** — album name\n"
                "• **Year**, **Genre**, **Track #** (where present)\n\n"
                "Works with MP3, FLAC, M4A, OGG, WAV."
            ),
            "help_ae_cover": (
                "**🖼 Cover Art**\n\n"
                "> Embed album artwork.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Pick **Cover** in the editor, then send an image. The art is "
                "embedded into the file. Square images (≥ 500×500) give the best "
                "result across players."
            ),
            "help_ae_tips": (
                "**💡 Tips**\n\n"
                "> Get more out of it.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Tag multiple files in a row — the editor keeps the session open.\n"
                "• Use consistent Artist + Album values so music apps group correctly.\n"
                "• Combine with `/c` (Converter) if you need to change format first."
            ),
        },
    ),

    # ------------------------------------------------------------------
    # Image Watermarker
    # ------------------------------------------------------------------
    "help_tool_watermark": ToolGuide(
        hub_cb="help_tool_watermark",
        hub_text=(
            "**© Image Watermarker**\n\n"
            "> Brand your media.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Burn a PNG logo into any video or image, position it wherever you want.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/w` or `/watermark`"
        ),
        buttons=(
            (("🚀 How to Use", "help_wm_howto"), ("📐 Position", "help_wm_position")),
            (("🎬 Video", "help_wm_video"), ("🖼 Image", "help_wm_image")),
            (("💡 Tips", "help_wm_tips"),),
        ),
        children={
            "help_wm_howto": (
                "**🚀 How to Use Watermarker**\n\n"
                "> Burn a logo in one pass.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "1. Send your logo (PNG with transparency works best).\n"
                "2. Send the target video or image.\n"
                "3. Pick a position + size preset.\n"
                "4. Receive the watermarked file."
            ),
            "help_wm_position": (
                "**📐 Position & Size**\n\n"
                "> Nine placement zones.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Pick from a 3×3 grid: top/middle/bottom × left/center/right.\n"
                "Size presets: `Small`, `Medium`, `Large` (relative to the shorter edge).\n"
                "Your last choice is remembered for the session."
            ),
            "help_wm_video": (
                "**🎬 Video Watermarks**\n\n"
                "> Re-encoded with the logo burned in.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Supports MP4, MKV, MOV, WEBM.\n"
                "• Audio streams are copied untouched.\n"
                "• Very long or high-bitrate videos take longer — be patient."
            ),
            "help_wm_image": (
                "**🖼 Image Watermarks**\n\n"
                "> Instant overlay.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Supports JPG, PNG, WEBP.\n"
                "• Output keeps the original resolution.\n"
                "• Transparent PNG logos blend naturally."
            ),
            "help_wm_tips": (
                "**💡 Tips**\n\n"
                "> Make your brand stick.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Use a square logo around 512×512 for consistent scaling.\n"
                "• White-on-transparent PNGs read well on any background.\n"
                "• For dark footage, prefer bottom-right; for bright, prefer top-left."
            ),
        },
    ),

    # ------------------------------------------------------------------
    # Subtitle Extractor
    # ------------------------------------------------------------------
    "help_tool_subtitle": ToolGuide(
        hub_cb="help_tool_subtitle",
        hub_text=(
            "**📝 Subtitle Extractor**\n\n"
            "> Pull subs out of your videos.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Extract embedded subtitle tracks to `.srt` or `.ass`.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/s` or `/subtitle`"
        ),
        buttons=(
            (("🚀 How to Use", "help_se_howto"), ("📄 Formats", "help_se_formats")),
            (("📈 Limits", "help_se_limits"), ("💡 Tips", "help_se_tips")),
        ),
        children={
            "help_se_howto": (
                "**🚀 How to Extract Subtitles**\n\n"
                "> One file, all tracks.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "1. Send a video (or reply to one with `/s`).\n"
                "2. Pick which subtitle track to export.\n"
                "3. Receive a `.srt` or `.ass` file."
            ),
            "help_se_formats": (
                "**📄 Output Formats**\n\n"
                "> Two standards covered.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **SRT** — plain text timing, universal player support.\n"
                "• **ASS** — preserves styling (fonts, colors, karaoke).\n"
                "Input containers: MKV, MP4, MOV, WEBM."
            ),
            "help_se_limits": (
                "**📈 Limits**\n\n"
                "> What this tool cannot do.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Burned-in (hardcoded) subs cannot be extracted — they are pixels.\n"
                "• Image-based subs (PGS/VobSub) are exported as-is, not OCR-converted.\n"
                "• One track per export; repeat for additional languages."
            ),
            "help_se_tips": (
                "**💡 Tips**\n\n"
                "> Workflow helpers.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Use `/mi` first to list all tracks + languages.\n"
                "• Rename your output with `/r` for library consistency.\n"
                "• ASS subs preserve typesetting — great for fan-subs."
            ),
        },
    ),

    # ------------------------------------------------------------------
    # Video Trimmer
    # ------------------------------------------------------------------
    "help_tool_trimmer": ToolGuide(
        hub_cb="help_tool_trimmer",
        hub_text=(
            "**✂️ Video Trimmer**\n\n"
            "> Cut by timestamp, no re-encode.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Trim a video between two timestamps using stream copy.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/t` or `/trim`"
        ),
        buttons=(
            (("🚀 How to Use", "help_vt_howto"), ("⏱ Time Format", "help_vt_format")),
            (("⚡ Stream Copy", "help_vt_streamcopy"), ("💡 Tips", "help_vt_tips")),
        ),
        children={
            "help_vt_howto": (
                "**🚀 How to Trim**\n\n"
                "> Two timestamps, one file.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "1. Send a video (or reply to one with `/t`).\n"
                "2. Send the start time.\n"
                "3. Send the end time.\n"
                "4. Receive the trimmed clip."
            ),
            "help_vt_format": (
                "**⏱ Time Format**\n\n"
                "> Accepted inputs.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• `HH:MM:SS` — `01:23:45`\n"
                "• `MM:SS` — `05:30`\n"
                "• Plain seconds — `120`\n\n"
                "End time must be greater than start time."
            ),
            "help_vt_streamcopy": (
                "**⚡ Stream Copy**\n\n"
                "> Fast, lossless cuts.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Trimming uses `-c copy` — no re-encoding, so output quality is "
                "identical to input. Cuts snap to the nearest keyframe, which may "
                "shift your timestamp by up to ~2 seconds on some files."
            ),
            "help_vt_tips": (
                "**💡 Tips**\n\n"
                "> Get frame-accurate cuts.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• For keyframe-snap accuracy, use `/c` (Converter) with re-encode.\n"
                "• Run multiple trims in a row — the session stays open.\n"
                "• Combine with Watermarker to brand short clips."
            ),
        },
    ),

    # ------------------------------------------------------------------
    # Media Info
    # ------------------------------------------------------------------
    "help_tool_mediainfo": ToolGuide(
        hub_cb="help_tool_mediainfo",
        hub_text=(
            "**ℹ️ Media Info**\n\n"
            "> Inspect any media file.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Detailed codec, stream, and container report for any video or audio.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/mi` or `/mediainfo`"
        ),
        buttons=(
            (("🚀 How to Use", "help_mi_howto"), ("📋 Fields", "help_mi_fields")),
            (("🧪 Examples", "help_mi_examples"), ("💡 Tips", "help_mi_tips")),
        ),
        children={
            "help_mi_howto": (
                "**🚀 How to Use Media Info**\n\n"
                "> Zero-config inspection.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Send any media file or reply to one with `/mi`. A report is "
                "generated and sent back — container, video + audio + subtitle "
                "streams, resolution, bitrate, duration."
            ),
            "help_mi_fields": (
                "**📋 Reported Fields**\n\n"
                "> What the report covers.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **Container** — format + overall bitrate + size\n"
                "• **Video** — codec, resolution, fps, bitrate, profile\n"
                "• **Audio** — codec, channels, sample rate, language\n"
                "• **Subtitles** — format, language tag\n"
                "• **Chapters** — timestamps + titles (if present)"
            ),
            "help_mi_examples": (
                "**🧪 Examples**\n\n"
                "> Typical use cases.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Verify a 4K source before re-encoding.\n"
                "• Find the exact audio language track before `/s` extraction.\n"
                "• Confirm bitrate / codec before adding a watermark."
            ),
            "help_mi_tips": (
                "**💡 Tips**\n\n"
                "> Small helpers.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Works on files already in your `/myfiles` locker.\n"
                "• Copy values directly from the report into filename templates.\n"
                "• Run before every conversion — it saves a lot of wrong guesses."
            ),
        },
    ),

    # ------------------------------------------------------------------
    # Voice Note Converter
    # ------------------------------------------------------------------
    "help_tool_voice": ToolGuide(
        hub_cb="help_tool_voice",
        hub_text=(
            "**🎙️ Voice Note Converter**\n\n"
            "> Turn audio into Telegram voice notes.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Convert any audio to OGG Opus voice-note format.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/v` or `/voice`"
        ),
        buttons=(
            (("🚀 How to Use", "help_vc_howto"), ("🎚 Opus Settings", "help_vc_opus")),
            (("💡 Tips", "help_vc_tips"),),
        ),
        children={
            "help_vc_howto": (
                "**🚀 How to Use Voice Converter**\n\n"
                "> One step.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Send an audio file or reply to one with `/v`. The bot converts "
                "it to OGG Opus and posts it back as a Telegram voice note — "
                "complete with waveform and one-tap playback."
            ),
            "help_vc_opus": (
                "**🎚 Opus Settings**\n\n"
                "> What the converter does.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Container: OGG (Telegram voice-note spec)\n"
                "• Codec: Opus @ 48 kHz mono\n"
                "• Typical bitrate: 32–64 kbps\n\n"
                "Telegram re-samples anything non-compliant — we do it cleanly upfront."
            ),
            "help_vc_tips": (
                "**💡 Tips**\n\n"
                "> Get the best voice notes.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Trim first with `/t` to stay under Telegram's voice-note length.\n"
                "• Mono sources convert 1:1 — stereo is downmixed.\n"
                "• For music snippets, try `/vn` (round video) for a visual vibe."
            ),
        },
    ),

    # ------------------------------------------------------------------
    # Video Note Converter
    # ------------------------------------------------------------------
    "help_tool_videonote": ToolGuide(
        hub_cb="help_tool_videonote",
        hub_text=(
            "**⭕ Video Note Converter**\n\n"
            "> Round Telegram video messages.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Converts any video into a circular 384×384 video note, ≤ 60s.\n"
            "Pick a topic below:\n\n"
            "**Shortcut:** `/vn` or `/videonote`"
        ),
        buttons=(
            (("🚀 How to Use", "help_vn_howto"), ("📏 Limits", "help_vn_limits")),
            (("💡 Tips", "help_vn_tips"),),
        ),
        children={
            "help_vn_howto": (
                "**🚀 How to Use Video Note**\n\n"
                "> Round in one shot.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Send a video or reply to one with `/vn`. The bot center-crops "
                "to square, scales to 384 px, and returns a round video note "
                "that plays inline in any chat."
            ),
            "help_vn_limits": (
                "**📏 Hard Limits**\n\n"
                "> Telegram's own constraints.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• **Max duration:** 60 seconds\n"
                "• **Resolution:** always cropped to 384×384\n"
                "• **Audio:** kept if possible, else muted\n"
                "• **Format:** MP4 / H.264 / AAC"
            ),
            "help_vn_tips": (
                "**💡 Tips**\n\n"
                "> Make it pop.\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Pre-trim with `/t` to stay under 60 s.\n"
                "• Frame your subject center-screen — the crop is centered.\n"
                "• Great for reactions, shorts, and voice replies with a face."
            ),
        },
    ),
}


# Reverse index: child callback → parent hub callback.
# Used by the dispatcher to route "← Back" from any child page.
CHILD_TO_HUB: dict[str, str] = {
    child: guide.hub_cb
    for guide in TOOL_GUIDES.values()
    for child in guide.children
}

# Each new-sub-page prefix is mapped to the tool it belongs to so the
# plugins/help.py router can gate on the right toggle in one line.
SUBPAGE_PREFIX_TO_TOOL: dict[str, str] = {
    "help_rn_": "rename",
    "help_ae_": "audio_editor",
    "help_wm_": "watermarker",
    "help_se_": "subtitle_extractor",
    "help_vt_": "video_trimmer",
    "help_mi_": "media_info",
    "help_vc_": "voice_converter",
    "help_vn_": "video_note_converter",
}


def build_tool_hub(callback: str, ctx: HelpContext) -> tuple[str, InlineKeyboardMarkup] | None:
    """Return (text, markup) for a tool overview page, or None if unknown.

    The caller is responsible for checking `is_callback_tool_available`
    first and answering with `DISABLED_TOOL_ALERT` when False.
    """
    guide = TOOL_GUIDES.get(callback)
    if guide is None:
        return None
    return guide.hub_text, _hub_markup(guide)


def build_tool_child(callback: str) -> tuple[str, InlineKeyboardMarkup] | None:
    """Return (text, markup) for a tool child page, or None if unknown."""
    hub_cb = CHILD_TO_HUB.get(callback)
    if hub_cb is None:
        return None
    guide = TOOL_GUIDES[hub_cb]
    text = guide.children.get(callback)
    if text is None:
        return None
    return text, _child_markup(hub_cb)


def tool_key_for_subpage(callback: str) -> str | None:
    """Map a `help_xy_*` child callback to its toggle key."""
    for prefix, tool_key in SUBPAGE_PREFIX_TO_TOOL.items():
        if callback.startswith(prefix):
            return tool_key
    return None
