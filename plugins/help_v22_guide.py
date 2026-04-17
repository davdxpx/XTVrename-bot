# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""`/help → ✨ New in v2.2` guide pages.

One short page per feature; every page fits in a single Telegram
message and carries its own ← Back button. The hub menu is reached via
help_new_v22; individual pages are help_v22_<topic>.

Kept standalone from plugins/start.py's main help router so the guide
is easy to extend with more v2.2 topics later.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


# --- Hub ---------------------------------------------------------------------

def _hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔒 TMDb is now optional", callback_data="help_v22_tmdb")],
            [InlineKeyboardButton("☁️ Mirror-Leech overview", callback_data="help_v22_ml_intro")],
            [
                InlineKeyboardButton("📥 Sources", callback_data="help_v22_ml_sources"),
                InlineKeyboardButton("☁️ Destinations", callback_data="help_v22_ml_dests"),
            ],
            [InlineKeyboardButton("🔗 Linking a provider", callback_data="help_v22_ml_link")],
            [InlineKeyboardButton("🧩 MyFiles integration", callback_data="help_v22_ml_myfiles")],
            [InlineKeyboardButton("🎲 SECRETS_KEY one-click", callback_data="help_v22_secrets")],
            [InlineKeyboardButton("🩺 System Health panel", callback_data="help_v22_health")],
            [InlineKeyboardButton("🗃 DB layout migration", callback_data="help_v22_dblayout")],
            [InlineKeyboardButton("← Back to Guide", callback_data="help_guide")],
        ]
    )


def _hub_text() -> str:
    return (
        "**✨ What's new in v2.2**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bite-sized pages covering everything MyFiles 2.2 added on top of "
        "the original bot. Tap a topic; each page is one screen of copy "
        "with a back button.\n\n"
        "> __Tip:__ If you're just starting out, read **☁️ Mirror-Leech "
        "overview** first — it ties most of the other pages together."
    )


@Client.on_callback_query(filters.regex(r"^help_new_v22$"))
async def help_v22_hub(client: Client, callback_query: CallbackQuery) -> None:
    try:
        await callback_query.message.edit_text(_hub_text(), reply_markup=_hub_keyboard())
    except MessageNotModified:
        pass
    try:
        await callback_query.answer()
    except Exception:
        pass


# --- Individual pages --------------------------------------------------------

_PAGES: dict[str, tuple[str, str]] = {
    "tmdb": (
        "🔒 TMDb is now optional",
        "**🔒 TMDb is now optional**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "The bot runs fine without a TMDb API key — only the features "
        "that actually need TMDb show a 🔒 badge until you add one.\n\n"
        "**Keeps working without TMDb**\n"
        "> • General Mode renaming\n"
        "> • File Converter, YouTube Tool, MyFiles, all other Tools\n\n"
        "**Unlocks with a key**\n"
        "> • Auto-match of uploads to Movie / Series\n"
        "> • Posters on MyFiles + rename previews\n"
        "> • Auto-route between Movie / Series dumb channels\n\n"
        "Check `/admin → 🩺 System Health → 🎬 TMDb Status` to see the "
        "current state and grab a free key if you want to light it up.",
    ),
    "ml_intro": (
        "☁️ Mirror-Leech overview",
        "**☁️ Mirror-Leech overview**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Mirror-Leech takes any supported source and fans it out to every "
        "cloud destination you've linked.\n\n"
        "> 🔗 One URL in → many destinations out\n"
        "> 🧩 Deep fusion with MyFiles (single + batch)\n"
        "> 📊 `/mlqueue` tracks jobs with inline cancel\n"
        "> 🔐 Credentials encrypted at rest (Fernet)\n\n"
        "**Entry points**\n"
        "> • `/ml <url>` — pick destinations, hit Start\n"
        "> • `/settings → ☁️ Mirror-Leech` — link providers\n"
        "> • MyFiles `☁️ Mirror-Leech Options` on any file\n\n"
        "Admins flip the feature toggle at `/admin → 🩺 System Health "
        "→ ☁️ Mirror-Leech Config`.",
    ),
    "ml_sources": (
        "📥 Mirror-Leech sources",
        "**📥 Mirror-Leech sources**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "What `/ml` accepts:\n\n"
        "> • **Direct HTTP(S) URL** — aiohttp streaming with resume\n"
        "> • **yt-dlp page** — any URL a yt-dlp extractor recognises "
        "(YouTube, social video, etc.)\n"
        "> • **Telegram file** — automatically used when you tap "
        "☁️ Mirror-Leech on a MyFiles entry\n"
        "> • **RSS feed** — first enclosure is handed to HTTP\n\n"
        "The Controller picks the right downloader on its own — you "
        "just paste the URL.\n\n"
        "__Heads-up:__ peer-to-peer links aren't supported on the main "
        "branch; use the torrent-edition build for that.",
    ),
    "ml_dests": (
        "☁️ Mirror-Leech destinations",
        "**☁️ Mirror-Leech destinations**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Every registered uploader can be fanned to in parallel:\n\n"
        "> • **Google Drive** — OAuth refresh-token flow\n"
        "> • **Rclone** — covers 70+ backends via your rclone.conf\n"
        "> • **MEGA.nz** — email + password\n"
        "> • **GoFile** — anonymous by default, optional token\n"
        "> • **Pixeldrain** — anonymous by default, optional key\n"
        "> • **Telegram** — DM fallback, userbot for >2 GB\n"
        "> • **DDL** — one-time signed URLs served from the host\n\n"
        "Availability depends on what's installed — unavailable "
        "providers are hidden automatically in the picker.",
    ),
    "ml_link": (
        "🔗 Linking a provider",
        "**🔗 Linking a provider**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "1. Open `/settings → ☁️ Mirror-Leech`.\n"
        "2. Tap the provider you want to link.\n"
        "3. Hit **📝 Paste / update credentials**, then send the token "
        "(or email+password, or rclone.conf) as your next message.\n"
        "4. The bot encrypts it with Fernet, deletes your paste "
        "message, and confirms.\n"
        "5. Tap **🔌 Test connection** to verify.\n\n"
        "**Clearing a provider**\n"
        "> Same screen → **🗑 Clear credential**. Removes every field "
        "for that provider so you can re-link cleanly.",
    ),
    "ml_myfiles": (
        "🧩 MyFiles integration",
        "**🧩 MyFiles integration**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Every MyFiles entry now has a **☁️ Mirror-Leech Options** "
        "button alongside Send / Rename / Move.\n\n"
        "**Single file**\n"
        "> Tap the button → pick destinations → **🚀 Start**.\n\n"
        "**Multi-select**\n"
        "> Tick the files you want, then the bottom bar shows "
        "`☁️ Mirror-Leech Selected (N)`. The picker queues one "
        "MLTask per file × destination so everything runs in parallel.\n\n"
        "Each task gets its own progress message with a cancel button, "
        "and `/mlqueue` lists them all at once.",
    ),
    "secrets": (
        "🎲 SECRETS_KEY one-click",
        "**🎲 SECRETS_KEY one-click generator**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Mirror-Leech encrypts every provider credential with Fernet. "
        "The key lives in the `SECRETS_KEY` env var and can be generated "
        "in-bot:\n\n"
        "1. `/admin → 🩺 System Health → ☁️ Mirror-Leech Config`\n"
        "2. Tap **🎲 Generate SECRETS_KEY**\n"
        "3. Copy the posted key + follow the per-host install block\n"
        "4. Restart the bot → tap **✅ Enable Mirror-Leech**\n\n"
        "__⚠️ Back the key up.__ Losing it means every user has to "
        "re-link their providers.",
    ),
    "health": (
        "🩺 System Health panel",
        "**🩺 System Health & Statuses**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "One admin entry gathering every operator-facing diagnostics "
        "page. Open via `/admin → 🩺 System Health & Statuses`.\n\n"
        "> 🩺 **DB Schema Health** — collection counts, migration state, "
        "recent unknown-key writes\n"
        "> 🎬 **TMDb Status** — is the key configured, what unlocks\n"
        "> ☁️ **Mirror-Leech Config** — master toggle, provider "
        "availability, SECRETS_KEY state\n\n"
        "All three pages switch between compact (when configured) and "
        "full-onboarding copy (when something is missing).",
    ),
    "dblayout": (
        "🗃 DB layout migration",
        "**🗃 DB layout migration**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "v2.2 renames every MongoDB collection to the **`MediaStudio-*`** "
        "scheme and splits the monolithic settings doc into per-concern "
        "docs (branding, payments, premium_plans, ...).\n\n"
        "> ✅ Runs once automatically at startup\n"
        "> 🛡 Idempotent, advisory-locked, safe to restart mid-run\n"
        "> 💾 Every legacy collection is copied to `<name>_backup_legacy` "
        "before the split\n\n"
        "**Operator actions** at `/admin → 🩺 System Health → 🩺 DB "
        "Schema Health`:\n"
        "> • **🔁 Re-run migration (dry-run)** — plan-only, no writes\n"
        "> • **🗑 Drop legacy backups** — reclaim disk once you're sure",
    ),
}


def _page_keyboard(topic_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("← Back to New in v2.2", callback_data="help_new_v22")],
            [InlineKeyboardButton("❌ Close", callback_data="help_close")],
        ]
    )


@Client.on_callback_query(filters.regex(r"^help_v22_(tmdb|ml_intro|ml_sources|ml_dests|ml_link|ml_myfiles|secrets|health|dblayout)$"))
async def help_v22_page(client: Client, callback_query: CallbackQuery) -> None:
    topic_id = callback_query.data.removeprefix("help_v22_")
    page = _PAGES.get(topic_id)
    if not page:
        await callback_query.answer("Unknown page.", show_alert=True)
        return
    _, body = page
    try:
        await callback_query.message.edit_text(body, reply_markup=_page_keyboard(topic_id))
    except MessageNotModified:
        pass
    try:
        await callback_query.answer()
    except Exception:
        pass
