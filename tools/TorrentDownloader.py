# --- Imports ---
import os
import re
import time
import asyncio
import hashlib
from urllib.parse import quote, unquote, urlparse, parse_qs
from pyrogram import Client, filters, StopPropagation, ContinuePropagation
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified
from utils.state import set_state, get_state, get_data, update_data, clear_session
from utils.log import get_logger
from database import db
from plugins.user_setup import track_tool_usage
from config import Config
from utils.XTVengine import XTVEngine

logger = get_logger("tools.TorrentDownloader")

# === Constants ===
RESULTS_PER_PAGE = 5
MAX_RESULTS_PER_PROVIDER = 20
SEARCH_TIMEOUT = 15  # seconds per provider
SIZE_LIMITS = {
    "free": 2 * 1024 * 1024 * 1024,       # 2 GB (fallback defaults)
    "standard": 5 * 1024 * 1024 * 1024,    # 5 GB
    "deluxe": 0,                             # 0 = unlimited
}


async def _get_size_limit(user_id: int) -> tuple:
    """Returns (size_limit_bytes, plan_name). In non-public mode, returns 0 (unlimited)."""
    if not Config.PUBLIC_MODE:
        return 0, "admin"

    plan_name, _ = await _get_user_plan_info(user_id)
    config = await db.get_public_config()

    if plan_name == "free":
        limit_mb = config.get("torrent_size_limit_mb_free", 2048)  # default 2 GB
    else:
        plan_settings = config.get(f"premium_{plan_name}", {})
        limit_mb = plan_settings.get("torrent_size_limit_mb", 0)  # default unlimited for premium

    if limit_mb <= 0:
        return 0, plan_name

    return limit_mb * 1024 * 1024, plan_name

CATEGORY_MAP = {
    "all": {"1337x": "", "tgx": "", "lime": ""},
    "movies": {"1337x": "Movies/", "tgx": "c2=1&", "lime": "movies"},
    "tv": {"1337x": "TV/", "tgx": "c8=1&", "lime": "tv"},
    "music": {"1337x": "Music/", "tgx": "c22=1&", "lime": "music"},
    "games": {"1337x": "Games/", "tgx": "c10=1&", "lime": "games"},
    "software": {"1337x": "Apps/", "tgx": "c18=1&", "lime": "applications"},
    "anime": {"1337x": "Anime/", "tgx": "c28=1&", "lime": "anime"},
}

TYPE_ICONS = {
    "video": "\U0001F3AC",     # 🎬
    "audio": "\U0001F3B5",     # 🎵
    "archive": "\U0001F4E6",   # 📦
    "subtitle": "\U0001F4C4",  # 📄
    "image": "\U0001F5BC",     # 🖼
    "other": "\U0001F4CE",     # 📎
}

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".flac", ".aac", ".ogg", ".wav", ".wma", ".m4a", ".opus"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}
SUBTITLE_EXTS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}


# ============================================================
# Helper Functions
# ============================================================

async def _get_user_plan_info(user_id: int) -> tuple:
    """Returns (plan_name, plan_features) using the standard plan check pattern."""
    user_doc = await db.get_user(user_id)
    plan_name = "free"
    now = time.time()
    if user_doc and user_doc.get("is_premium"):
        exp = user_doc.get("premium_expiry")
        if exp is None or exp > now:
            plan_name = user_doc.get("premium_plan", "standard")

    config = await db.get_public_config()
    premium_system_enabled = config.get("premium_system_enabled", False)
    if not premium_system_enabled:
        plan_name = "free"

    plan_key = f"premium_{plan_name}" if plan_name != "free" else None
    plan_features = {}
    if plan_key:
        plan_features = config.get(plan_key, {}).get("features", {})

    return plan_name, plan_features


def _extract_info_hash(magnet: str) -> str:
    """Extract the info hash from a magnet link."""
    match = re.search(r"btih:([a-fA-F0-9]{40})", magnet)
    if match:
        return match.group(1).lower()
    match = re.search(r"btih:([a-zA-Z2-7]{32})", magnet)
    if match:
        import base64
        try:
            decoded = base64.b32decode(match.group(1).upper())
            return decoded.hex().lower()
        except Exception:
            pass
    return hashlib.md5(magnet.encode()).hexdigest()


def _parse_size_bytes(size_str: str) -> int:
    """Parse human-readable size string to bytes."""
    if not size_str:
        return 0
    size_str = size_str.strip().upper().replace(",", "")
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|TB|B)", size_str)
    if not match:
        return 0
    val = float(match.group(1))
    unit = match.group(2)
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(val * multipliers.get(unit, 1))


def _format_file_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    if size_bytes <= 0:
        return "Unknown"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes / 1024**2:.1f} MB"
    elif size_bytes < 1024**4:
        return f"{size_bytes / 1024**3:.2f} GB"
    else:
        return f"{size_bytes / 1024**4:.2f} TB"


def _progress_bar(percent: float, length: int = 10) -> str:
    """Generate a progress bar using ■□ style."""
    filled = int(length * percent / 100)
    bar = "■" * filled + "□" * (length - filled)
    return f"[{bar}]"


def _format_eta(seconds: float) -> str:
    """Format ETA in human-readable form."""
    if seconds <= 0 or seconds > 86400:
        return "N/A"
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m, {s}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h, {m}m"


def _format_elapsed(seconds: float) -> str:
    """Format elapsed time as MM:SS or HH:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_speed(bytes_per_sec: float) -> str:
    """Format download speed."""
    if bytes_per_sec <= 0:
        return "0 B/s"
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024**2:
        return f"{bytes_per_sec / 1024:.2f} KB/s"
    else:
        return f"{bytes_per_sec / 1024**2:.2f} MB/s"


def _get_type_icon(filename: str) -> str:
    """Get emoji icon for a file type."""
    ext = os.path.splitext(filename.lower())[1]
    if ext in VIDEO_EXTS:
        return TYPE_ICONS["video"]
    elif ext in AUDIO_EXTS:
        return TYPE_ICONS["audio"]
    elif ext in ARCHIVE_EXTS:
        return TYPE_ICONS["archive"]
    elif ext in SUBTITLE_EXTS:
        return TYPE_ICONS["subtitle"]
    elif ext in IMAGE_EXTS:
        return TYPE_ICONS["image"]
    return TYPE_ICONS["other"]


async def check_aria2_health() -> bool:
    """Check if aria2 RPC is reachable."""
    try:
        import xmlrpc.client
        server = xmlrpc.client.ServerProxy("http://localhost:6800/rpc")
        loop = asyncio.get_event_loop()
        version = await loop.run_in_executor(None, server.aria2.getVersion)
        return bool(version)
    except Exception as e:
        logger.error(f"aria2 health check failed: {e}")
        return False


# ============================================================
# Scraper Functions
# ============================================================

async def scrape_1337x(query: str, category: str = "all", page: int = 1) -> list:
    """Scrape 1337x.to for torrents."""
    import aiohttp
    from bs4 import BeautifulSoup

    results = []
    cat_path = CATEGORY_MAP.get(category, {}).get("1337x", "")
    url = f"https://1337x.to/category-search/{quote(query)}/{cat_path}{page}/"
    if category == "all":
        url = f"https://1337x.to/search/{quote(query)}/{page}/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=SEARCH_TIMEOUT)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.table-list tbody tr")

        for row in rows[:MAX_RESULTS_PER_PROVIDER]:
            try:
                name_tag = row.select_one("td.name a:nth-of-type(2)")
                if not name_tag:
                    continue
                name = name_tag.text.strip()
                detail_path = name_tag.get("href", "")
                detail_url = f"https://1337x.to{detail_path}"

                cols = row.find_all("td")
                seeders = int(cols[1].text.strip()) if len(cols) > 1 else 0
                leechers = int(cols[2].text.strip()) if len(cols) > 2 else 0
                date = cols[3].text.strip() if len(cols) > 3 else ""
                size = cols[4].text.strip() if len(cols) > 4 else ""
                # Clean size (remove duplicate from span)
                size_clean = size.split("\n")[0].strip() if "\n" in size else size

                results.append({
                    "name": name,
                    "size": size_clean,
                    "size_bytes": _parse_size_bytes(size_clean),
                    "seeders": seeders,
                    "leechers": leechers,
                    "date": date,
                    "provider": "1337x",
                    "detail_url": detail_url,
                    "magnet": None,  # Needs detail page fetch
                })
            except Exception as e:
                logger.error(f"1337x row parse error: {e}")
                continue
    except asyncio.TimeoutError:
        logger.warning("1337x search timed out")
    except Exception as e:
        logger.error(f"1337x scrape error: {e}")

    return results


async def _fetch_1337x_magnet(detail_url: str) -> str:
    """Fetch magnet link from a 1337x detail page."""
    import aiohttp
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(detail_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return ""
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        magnet_tag = soup.select_one("a[href^='magnet:']")
        if magnet_tag:
            return magnet_tag["href"]
    except Exception as e:
        logger.error(f"1337x magnet fetch error: {e}")
    return ""


async def scrape_torrentgalaxy(query: str, category: str = "all", page: int = 1) -> list:
    """Scrape TorrentGalaxy for torrents (magnet on search page)."""
    import aiohttp
    from bs4 import BeautifulSoup

    results = []
    cat_param = CATEGORY_MAP.get(category, {}).get("tgx", "")
    pg = page - 1  # TGX is 0-indexed
    url = f"https://torrentgalaxy.to/torrents.php?search={quote(query)}&{cat_param}sort=seeders&order=desc&page={pg}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=SEARCH_TIMEOUT)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("div.tgxtablerow")

        for row in rows[:MAX_RESULTS_PER_PROVIDER]:
            try:
                name_tag = row.select_one("a.txlight")
                if not name_tag:
                    # Try alternate selector
                    name_tag = row.select_one("div.tgxtablecell a[href*='/torrent/']")
                if not name_tag:
                    continue

                name = name_tag.text.strip()
                detail_url = name_tag.get("href", "")
                if detail_url and not detail_url.startswith("http"):
                    detail_url = f"https://torrentgalaxy.to{detail_url}"

                # Find magnet link directly on page
                magnet_tag = row.select_one("a[href^='magnet:']")
                magnet = magnet_tag["href"] if magnet_tag else ""

                # Parse size, seeders, leechers from cells
                cells = row.select("div.tgxtablecell")
                size = ""
                seeders = 0
                leechers = 0
                date = ""

                if len(cells) >= 8:
                    size = cells[7].text.strip() if cells[7] else ""
                    date = cells[11].text.strip() if len(cells) > 11 and cells[11] else ""

                # Seeders/leechers in span with specific styling
                seed_tag = row.select_one("span[title='Seeders/Leechers'] font[color='green']")
                leech_tag = row.select_one("span[title='Seeders/Leechers'] font[color='#ff0000']")
                if seed_tag:
                    try:
                        seeders = int(seed_tag.text.strip())
                    except ValueError:
                        pass
                if leech_tag:
                    try:
                        leechers = int(leech_tag.text.strip())
                    except ValueError:
                        pass

                if magnet:
                    results.append({
                        "name": name,
                        "size": size,
                        "size_bytes": _parse_size_bytes(size),
                        "seeders": seeders,
                        "leechers": leechers,
                        "date": date,
                        "provider": "TGx",
                        "detail_url": detail_url,
                        "magnet": magnet,
                    })
            except Exception as e:
                logger.error(f"TGx row parse error: {e}")
                continue
    except asyncio.TimeoutError:
        logger.warning("TorrentGalaxy search timed out")
    except Exception as e:
        logger.error(f"TorrentGalaxy scrape error: {e}")

    return results


async def scrape_limetorrents(query: str, category: str = "all", page: int = 1) -> list:
    """Scrape LimeTorrents for torrents."""
    import aiohttp
    from bs4 import BeautifulSoup

    results = []
    cat_path = CATEGORY_MAP.get(category, {}).get("lime", "")
    if category == "all":
        url = f"https://www.limetorrents.lol/search/all/{quote(query)}/seeds/{page}/"
    else:
        url = f"https://www.limetorrents.lol/search/{cat_path}/{quote(query)}/seeds/{page}/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=SEARCH_TIMEOUT)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.table2")
        if not table:
            return []

        rows = table.select("tr")[1:]  # skip header

        for row in rows[:MAX_RESULTS_PER_PROVIDER]:
            try:
                name_tag = row.select_one("td.tdleft div.tt-name a:nth-of-type(2)")
                if not name_tag:
                    name_tag = row.select_one("td.tdleft a")
                if not name_tag:
                    continue

                name = name_tag.text.strip()
                detail_path = name_tag.get("href", "")
                detail_url = detail_path
                if detail_url and not detail_url.startswith("http"):
                    detail_url = f"https://www.limetorrents.lol{detail_path}"

                # Try to find a hash link for magnet construction
                hash_link = row.select_one("td.tdleft div.tt-name a:first-of-type")
                magnet = ""
                if hash_link:
                    href = hash_link.get("href", "")
                    # LimeTorrents sometimes has torrent cache links with hash
                    hash_match = re.search(r"/([a-fA-F0-9]{40})\.torrent", href)
                    if hash_match:
                        info_hash = hash_match.group(1)
                        magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote(name)}"

                cols = row.find_all("td")
                size = cols[2].text.strip() if len(cols) > 2 else ""
                seeders = 0
                leechers = 0
                date = cols[1].text.strip() if len(cols) > 1 else ""

                seed_td = row.select_one("td.tdseed")
                leech_td = row.select_one("td.tdleech")
                if seed_td:
                    try:
                        seeders = int(seed_td.text.strip().replace(",", ""))
                    except ValueError:
                        pass
                if leech_td:
                    try:
                        leechers = int(leech_td.text.strip().replace(",", ""))
                    except ValueError:
                        pass

                if magnet or detail_url:
                    results.append({
                        "name": name,
                        "size": size,
                        "size_bytes": _parse_size_bytes(size),
                        "seeders": seeders,
                        "leechers": leechers,
                        "date": date,
                        "provider": "Lime",
                        "detail_url": detail_url,
                        "magnet": magnet if magnet else None,
                    })
            except Exception as e:
                logger.error(f"LimeTorrents row parse error: {e}")
                continue
    except asyncio.TimeoutError:
        logger.warning("LimeTorrents search timed out")
    except Exception as e:
        logger.error(f"LimeTorrents scrape error: {e}")

    return results


async def search_torrents(query: str, category: str = "all") -> list:
    """Run all scrapers concurrently, deduplicate, sort by seeders."""
    tasks = [
        scrape_1337x(query, category),
        scrape_torrentgalaxy(query, category),
        scrape_limetorrents(query, category),
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    for result in raw_results:
        if isinstance(result, Exception):
            logger.error(f"Provider error: {result}")
            continue
        if isinstance(result, list):
            all_results.extend(result)

    # Deduplicate by info_hash where possible
    seen_hashes = set()
    unique = []
    for r in all_results:
        if r.get("magnet"):
            h = _extract_info_hash(r["magnet"])
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
        unique.append(r)

    # Sort by seeders descending
    unique.sort(key=lambda x: x.get("seeders", 0), reverse=True)
    return unique


# ============================================================
# UI Rendering
# ============================================================

async def render_search_results(client, user_id: int, chat_id: int, bot_msg_id: int, page: int = 0):
    """Render a page of search results with navigation."""
    data = get_data(user_id)
    results = data.get("search_results", [])
    category = data.get("search_category", "all")
    query = data.get("search_query", "")
    total = len(results)

    if total == 0:
        try:
            await client.edit_message_text(
                chat_id, bot_msg_id,
                f"🔍 **No Results Found**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Try a different search term or category.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data="torrent_downloader_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    start = page * RESULTS_PER_PAGE
    end = min(start + RESULTS_PER_PAGE, total)
    page_results = results[start:end]
    total_pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    text = (
        f"🔍 **Search:** `{query}`\n"
        f"🏷 **Category:** {category.title()}\n"
        f"📊 **Results:** {total} found (page {page + 1}/{total_pages})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    buttons = []
    for i, r in enumerate(page_results):
        idx = start + i  # absolute index
        seeders = r.get("seeders", 0)
        seed_emoji = "🟢" if seeders > 10 else ("🟡" if seeders > 0 else "🔴")
        size = r.get("size", "?")
        provider = r.get("provider", "?")

        name = r["name"]
        if len(name) > 55:
            name = name[:52] + "..."

        text += (
            f"**{idx + 1}.** {name}\n"
            f"   {seed_emoji} S:`{seeders}` | L:`{r.get('leechers', 0)}` | "
            f"💾 `{size}` | 🌐 `{provider}`\n\n"
        )
        buttons.append([
            InlineKeyboardButton(f"📋 #{idx + 1} Info", callback_data=f"tdl_info_{idx}"),
            InlineKeyboardButton(f"⬇ Download", callback_data=f"torrent_dl_mag_{idx}"),
        ])

    # Navigation buttons
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("\u25C0 Prev", callback_data="tdl_page_prev"))
    if end < total:
        nav_row.append(InlineKeyboardButton("Next \u25B6", callback_data="tdl_page_next"))
    if nav_row:
        buttons.append(nav_row)

    # Bottom row
    buttons.append([
        InlineKeyboardButton("📜 History", callback_data="tdl_history"),
        InlineKeyboardButton("⭐ Favorites", callback_data="tdl_favorites"),
    ])
    buttons.append([
        InlineKeyboardButton("🔙 Back to Menu", callback_data="torrent_downloader_menu")
    ])

    update_data(user_id, "search_page", page)

    try:
        await client.edit_message_text(
            chat_id, bot_msg_id, text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


def _render_file_selection_text(files: list, selected: set, sort_by: str = "default") -> str:
    """Build text for file selection view."""
    sorted_files = list(enumerate(files))
    if sort_by == "size":
        sorted_files.sort(key=lambda x: x[1].get("size_bytes", 0), reverse=True)
    elif sort_by == "name":
        sorted_files.sort(key=lambda x: x[1].get("name", "").lower())

    total_selected_size = 0
    text = "📂 **Select Files to Process**\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    for orig_idx, f in sorted_files:
        name = f.get("name", "unknown")
        size = f.get("size_bytes", 0)
        icon = _get_type_icon(name)
        check = "\u2705" if orig_idx in selected else "\u2B1C"
        if orig_idx in selected:
            total_selected_size += size

        short_name = name
        if len(short_name) > 40:
            short_name = short_name[:37] + "..."

        text += f"{check} {icon} `{short_name}`\n"
        text += f"     💾 `{_format_file_size(size)}`\n"

    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"> **Selected:** `{len(selected)}/{len(files)} files`\n"
    text += f"> **Total Size:** `{_format_file_size(total_selected_size)}`"

    return text


# ============================================================
# Main Menu Handler
# ============================================================

@Client.on_callback_query(filters.regex(r"^torrent_downloader_menu$"))
async def handle_torrent_menu(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    await track_tool_usage(user_id, "torrent_downloader")
    clear_session(user_id)

    # Check aria2 health
    healthy = await check_aria2_health()
    if not healthy:
        try:
            await callback_query.message.edit_text(
                f"🧲 **Torrent Downloader**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ aria2 service is not available.\n"
                f"Please contact the admin to restart the aria2 daemon.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="help_close")]
                ])
            )
        except MessageNotModified:
            pass
        return

    # Check plan for torrent feature
    size_limit, plan_name = await _get_size_limit(user_id)
    limit_display = f"`{_format_file_size(size_limit)}`" if size_limit > 0 else "`Unlimited`"

    text = (
        f"🧲 **Torrent Downloader**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> **Plan:** `{plan_name.title()}`\n"
        f"> **Size Limit:** {limit_display}\n\n"
        f"Search and download torrents directly.\n"
        f"Files are processed through the bot pipeline."
    )

    buttons = [
        [InlineKeyboardButton("🔍 Search Torrent", callback_data="torrent_search_prompt")],
        [
            InlineKeyboardButton("📜 Recent Searches", callback_data="tdl_history"),
            InlineKeyboardButton("⭐ Favorites", callback_data="tdl_favorites"),
        ],
        [InlineKeyboardButton("📊 Download History", callback_data="tdl_dl_history")],
        [InlineKeyboardButton("🔙 Back", callback_data="help_close")],
    ]

    try:
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


# ============================================================
# Category Selection
# ============================================================

@Client.on_callback_query(filters.regex(r"^torrent_search_prompt$"))
async def handle_torrent_search_prompt(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    set_state(user_id, "awaiting_torrent_category")
    update_data(user_id, "bot_msg_id", callback_query.message.id)
    update_data(user_id, "bot_chat_id", callback_query.message.chat.id)

    buttons = [
        [
            InlineKeyboardButton("🌍 All", callback_data="tdl_cat_all"),
            InlineKeyboardButton("🎬 Movies", callback_data="tdl_cat_movies"),
        ],
        [
            InlineKeyboardButton("📺 TV Shows", callback_data="tdl_cat_tv"),
            InlineKeyboardButton("🎵 Music", callback_data="tdl_cat_music"),
        ],
        [
            InlineKeyboardButton("🎮 Games", callback_data="tdl_cat_games"),
            InlineKeyboardButton("💻 Software", callback_data="tdl_cat_software"),
        ],
        [InlineKeyboardButton("🌸 Anime", callback_data="tdl_cat_anime")],
        [InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")],
    ]

    try:
        await callback_query.message.edit_text(
            f"🏷 **Select Category**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Choose a category to narrow your search.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^tdl_cat_(.+)$"))
async def handle_category_select(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    category = callback_query.data.split("_")[2]

    update_data(user_id, "search_category", category)
    set_state(user_id, "awaiting_torrent_search")
    update_data(user_id, "bot_msg_id", callback_query.message.id)
    update_data(user_id, "bot_chat_id", callback_query.message.chat.id)

    try:
        await callback_query.message.edit_text(
            f"🔍 **Search Torrents** — {category.title()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Send me the torrent name or keywords to search.\n\n"
            f"__(Send /cancel to abort)__",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="torrent_downloader_menu")]
            ]),
        )
    except MessageNotModified:
        pass


# ============================================================
# Text Message Handler (search query input)
# ============================================================

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "new", "cancel"]), group=3)
async def torrent_message_handler(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == "awaiting_torrent_search":
        query = message.text.strip()
        if not query or len(query) < 2:
            await message.reply_text("⚠️ Please enter at least 2 characters.")
            raise StopPropagation

        data = get_data(user_id)
        category = data.get("search_category", "all")
        bot_msg_id = data.get("bot_msg_id")
        bot_chat_id = data.get("bot_chat_id", message.chat.id)

        # Save search to history
        await db.add_torrent_search(user_id, query)

        update_data(user_id, "search_query", query)
        set_state(user_id, "torrent_searching")

        # Show searching message
        status_msg = await message.reply_text(
            f"🔎 **Searching** `{query}` in **{category.title()}**...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"__Checking multiple providers...__\n"
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature()}"
        )

        results = await search_torrents(query, category)

        # For 1337x results without magnets, we'll fetch them on-demand (at download time)
        update_data(user_id, "search_results", results)
        update_data(user_id, "search_page", 0)
        set_state(user_id, "torrent_results")

        await render_search_results(client, user_id, message.chat.id, status_msg.id, page=0)
        raise StopPropagation

    elif state == "awaiting_torrent_input":
        # Direct magnet link input
        text = message.text.strip()
        if text.startswith("magnet:?"):
            data = get_data(user_id)
            update_data(user_id, "direct_magnet", text)
            set_state(user_id, "torrent_downloading")
            status_msg = await message.reply_text(
                f"🧲 **Starting download...**\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            await start_torrent_download(client, user_id, message.chat.id, status_msg.id, text)
            raise StopPropagation
        else:
            await message.reply_text("⚠️ Please send a valid magnet link starting with `magnet:?`")
            raise StopPropagation

    # Not our state - let it fall through
    return


# ============================================================
# Pagination
# ============================================================

@Client.on_callback_query(filters.regex(r"^tdl_page_next$"))
async def handle_page_next(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = get_data(user_id)
    page = data.get("search_page", 0) + 1
    await render_search_results(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id, page
    )


@Client.on_callback_query(filters.regex(r"^tdl_page_prev$"))
async def handle_page_prev(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = get_data(user_id)
    page = max(0, data.get("search_page", 0) - 1)
    await render_search_results(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id, page
    )


# ============================================================
# Detail View
# ============================================================

@Client.on_callback_query(filters.regex(r"^tdl_info_(\d+)$"))
async def handle_info_view(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[2])

    data = get_data(user_id)
    results = data.get("search_results", [])
    if idx >= len(results):
        await callback_query.answer("Result not found.", show_alert=True)
        return

    r = results[idx]
    seeders = r.get('seeders', 0)
    seed_emoji = "🟢" if seeders > 10 else ("🟡" if seeders > 0 else "🔴")

    text = (
        f"📋 **Torrent Details**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Name:** {r['name']}\n\n"
        f"> **Size:** `{r.get('size', 'Unknown')}`\n"
        f"> {seed_emoji} **Seeders:** `{seeders}`\n"
        f"> 🔴 **Leechers:** `{r.get('leechers', 0)}`\n"
        f"> **Date:** `{r.get('date', 'Unknown')}`\n"
        f"> **Provider:** `{r.get('provider', 'Unknown')}`"
    )

    buttons = [
        [
            InlineKeyboardButton("⬇ Download", callback_data=f"torrent_dl_mag_{idx}"),
            InlineKeyboardButton("⭐ Favorite", callback_data=f"tdl_fav_{idx}"),
        ],
        [InlineKeyboardButton("🔙 Back to Results", callback_data="tdl_back_results")],
    ]

    try:
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^tdl_back_results$"))
async def handle_back_results(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = get_data(user_id)
    page = data.get("search_page", 0)
    await render_search_results(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id, page
    )


# ============================================================
# Download Torrent
# ============================================================

@Client.on_callback_query(filters.regex(r"^torrent_dl_mag_(\d+)$"))
async def handle_download_magnet(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[3])

    data = get_data(user_id)
    results = data.get("search_results", [])
    if idx >= len(results):
        await callback_query.answer("Result not found.", show_alert=True)
        return

    r = results[idx]
    magnet = r.get("magnet")

    # If no magnet (1337x), fetch from detail page
    if not magnet and r.get("detail_url"):
        try:
            await callback_query.message.edit_text(
                f"🔗 **Fetching magnet link...**\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
        except MessageNotModified:
            pass
        magnet = await _fetch_1337x_magnet(r["detail_url"])
        if magnet:
            results[idx]["magnet"] = magnet
            update_data(user_id, "search_results", results)

    if not magnet:
        try:
            await callback_query.message.edit_text(
                f"❌ **Could Not Retrieve Magnet**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"This torrent may no longer be available.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="tdl_back_results")]
                ])
            )
        except MessageNotModified:
            pass
        return

    # Check size limit
    size_limit, plan_name = await _get_size_limit(user_id)
    size_bytes = r.get("size_bytes", 0)

    if size_limit > 0 and size_bytes > 0 and size_bytes > size_limit:
        try:
            await callback_query.message.edit_text(
                f"❌ **File Too Large**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"This torrent exceeds your plan's size limit.\n\n"
                f"> **Size:** `{_format_file_size(size_bytes)}`\n"
                f"> **Plan ({plan_name.title()}):** `{_format_file_size(size_limit)}`\n\n"
                f"Upgrade your plan for larger downloads.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="tdl_back_results")]
                ])
            )
        except MessageNotModified:
            pass
        return

    # Record download in DB
    download_id = await db.save_torrent_download(user_id, {
        "name": r.get("name", "Unknown"),
        "magnet": magnet,
        "size": r.get("size", "Unknown"),
        "size_bytes": size_bytes,
        "provider": r.get("provider", "Unknown"),
        "status": "starting",
    })
    update_data(user_id, "current_download_id", str(download_id) if download_id else None)

    set_state(user_id, "torrent_downloading")
    await start_torrent_download(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id, magnet, torrent_name=r.get("name", "")
    )


async def start_torrent_download(client, user_id: int, chat_id: int, msg_id: int, magnet: str, torrent_name: str = ""):
    """Start aria2 download and monitor progress."""
    import xmlrpc.client

    download_dir = f"/tmp/torrent_{user_id}_{int(time.time())}"
    os.makedirs(download_dir, exist_ok=True)
    update_data(user_id, "download_dir", download_dir)

    try:
        server = xmlrpc.client.ServerProxy("http://localhost:6800/rpc")
        loop = asyncio.get_event_loop()

        options = {
            "dir": download_dir,
            "max-connection-per-server": "16",
            "split": "16",
            "seed-time": "0",
            "bt-stop-timeout": "300",
        }

        gid = await loop.run_in_executor(
            None, lambda: server.aria2.addUri([magnet], options)
        )
        update_data(user_id, "active_gid", gid)

        try:
            name_display = torrent_name[:60] if torrent_name else "Torrent"
            await client.edit_message_text(
                chat_id, msg_id,
                f"📥 **Downloading Torrent...**\n"
                f"📝 `{name_display}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"**Progress:**  `0.0%`\n"
                f"{_progress_bar(0)}\n\n"
                f"> ⏳ Waiting for metadata...\n"
                f"\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature()}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel Download", callback_data="tdl_dl_cancel")]
                ])
            )
        except MessageNotModified:
            pass

        await monitor_download(client, user_id, chat_id, msg_id, server, gid, torrent_name, download_dir)

    except Exception as e:
        logger.error(f"Download start error: {e}")
        data = get_data(user_id)
        dl_id = data.get("current_download_id")
        if dl_id:
            await db.update_torrent_download(dl_id, {"status": "failed", "error": str(e)})

        try:
            await client.edit_message_text(
                chat_id, msg_id,
                f"❌ **Download Failed**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"`{e}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]
                ])
            )
        except MessageNotModified:
            pass


async def monitor_download(client, user_id, chat_id, msg_id, server, gid, torrent_name, download_dir):
    """Monitor aria2 download progress."""
    loop = asyncio.get_event_loop()
    last_update = 0
    start_time = time.time()
    update_interval = 3  # seconds

    while True:
        try:
            status = await loop.run_in_executor(
                None, lambda: server.aria2.tellStatus(gid)
            )
        except Exception as e:
            logger.error(f"aria2 status error: {e}")
            break

        state = status.get("status", "")
        total_length = int(status.get("totalLength", 0))
        completed = int(status.get("completedLength", 0))
        speed = int(status.get("downloadSpeed", 0))

        # Check if cancelled
        data = get_data(user_id)
        if data.get("download_cancelled"):
            try:
                await loop.run_in_executor(None, lambda: server.aria2.remove(gid))
            except Exception:
                pass
            dl_id = data.get("current_download_id")
            if dl_id:
                await db.update_torrent_download(dl_id, {"status": "cancelled"})
            return

        # Check plan size limit after metadata
        if total_length > 0:
            size_limit, plan_name = await _get_size_limit(user_id)
            if size_limit > 0 and total_length > size_limit:
                try:
                    await loop.run_in_executor(None, lambda: server.aria2.remove(gid))
                except Exception:
                    pass
                dl_id = data.get("current_download_id")
                if dl_id:
                    await db.update_torrent_download(dl_id, {"status": "failed", "error": "Size limit exceeded"})
                try:
                    await client.edit_message_text(
                        chat_id, msg_id,
                        f"❌ **Download Cancelled**\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"Torrent exceeds your plan's size limit.\n\n"
                        f"> **Torrent Size:** `{_format_file_size(total_length)}`\n"
                        f"> **Your Limit ({plan_name.title()}):** `{_format_file_size(size_limit)}`",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]
                        ])
                    )
                except MessageNotModified:
                    pass
                return

        if state == "complete":
            dl_id = data.get("current_download_id")
            if dl_id:
                await db.update_torrent_download(dl_id, {
                    "status": "completed",
                    "total_size": total_length,
                    "completed_at": time.time(),
                })

            # Gather downloaded files
            files_info = await loop.run_in_executor(
                None, lambda: server.aria2.getFiles(gid)
            )
            downloaded_files = []
            for f in files_info:
                path = f.get("path", "")
                if path and os.path.exists(path):
                    size = os.path.getsize(path)
                    downloaded_files.append({
                        "path": path,
                        "name": os.path.basename(path),
                        "size_bytes": size,
                    })

            if not downloaded_files:
                # Check download_dir for files
                for root, dirs, fnames in os.walk(download_dir):
                    for fname in fnames:
                        fpath = os.path.join(root, fname)
                        size = os.path.getsize(fpath)
                        downloaded_files.append({
                            "path": fpath,
                            "name": fname,
                            "size_bytes": size,
                        })

            update_data(user_id, "downloaded_files", downloaded_files)
            update_data(user_id, "selected_files", set())
            update_data(user_id, "file_sort", "default")
            set_state(user_id, "torrent_file_select")

            await render_file_selection(client, user_id, chat_id, msg_id)
            return

        elif state in ("error", "removed"):
            error_msg = status.get("errorMessage", "Unknown error")
            dl_id = data.get("current_download_id")
            if dl_id:
                await db.update_torrent_download(dl_id, {"status": "failed", "error": error_msg})

            try:
                await client.edit_message_text(
                    chat_id, msg_id,
                    f"❌ **Download Failed**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"`{error_msg}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]
                    ])
                )
            except MessageNotModified:
                pass
            return

        # Update progress (throttled)
        now = time.time()
        if now - last_update >= update_interval:
            last_update = now
            if total_length > 0:
                percent = (completed / total_length) * 100
                eta_seconds = (total_length - completed) / speed if speed > 0 else 0
            else:
                percent = 0
                eta_seconds = 0

            name_display = torrent_name[:50] if torrent_name else "Torrent"
            elapsed = time.time() - start_time
            progress_text = (
                f"📥 **Downloading Torrent...**\n"
                f"📝 `{name_display}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"**Progress:**  `{percent:.1f}%`\n"
                f"{_progress_bar(percent)}\n\n"
                f"> **Size:** `{_format_file_size(completed)}` / `{_format_file_size(total_length)}`\n"
                f"> **Speed:** `{_format_speed(speed)}`\n"
                f"> **Elapsed:** `{_format_elapsed(elapsed)}` · **ETA:** `{_format_eta(eta_seconds)}`\n"
                f"\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature()}"
            )

            try:
                await client.edit_message_text(
                    chat_id, msg_id, progress_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Cancel Download", callback_data="tdl_dl_cancel")]
                    ])
                )
            except MessageNotModified:
                pass
            except Exception as e:
                logger.error(f"Progress update error: {e}")

        await asyncio.sleep(2)


# ============================================================
# Download Cancel
# ============================================================

@Client.on_callback_query(filters.regex(r"^tdl_dl_cancel$"))
async def handle_download_cancel(client, callback_query: CallbackQuery):
    await callback_query.answer("Cancelling download...", show_alert=False)
    user_id = callback_query.from_user.id
    update_data(user_id, "download_cancelled", True)

    try:
        await callback_query.message.edit_text(
            f"⏳ **Cancelling download...**\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    except MessageNotModified:
        pass


# ============================================================
# File Selection
# ============================================================

async def render_file_selection(client, user_id: int, chat_id: int, msg_id: int):
    """Render file selection UI after download."""
    data = get_data(user_id)
    files = data.get("downloaded_files", [])
    selected = data.get("selected_files", set())
    sort_by = data.get("file_sort", "default")

    if not files:
        try:
            await client.edit_message_text(
                chat_id, msg_id,
                f"⚠️ **No Files Found**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"No downloadable files were found in this torrent.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    text = _render_file_selection_text(files, selected, sort_by)

    buttons = []
    for i, f in enumerate(files):
        name = f.get("name", "file")
        short = name[:25] + "..." if len(name) > 25 else name
        check = "\u2705" if i in selected else "\u2B1C"
        buttons.append([InlineKeyboardButton(f"{check} {short}", callback_data=f"tdl_sel_{i}")])

    buttons.append([
        InlineKeyboardButton("✅ Select All", callback_data="tdl_sel_all"),
        InlineKeyboardButton("📊 Sort: Size", callback_data="tdl_sort_size"),
    ])
    buttons.append([
        InlineKeyboardButton("🔡 Sort: Name", callback_data="tdl_sort_name"),
    ])

    if selected:
        buttons.append([InlineKeyboardButton("✅ Process Selected", callback_data="tdl_process")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="tdl_cancel")])

    try:
        await client.edit_message_text(
            chat_id, msg_id, text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^tdl_sel_(\d+)$"))
async def tdl_sel_cb(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[2])

    data = get_data(user_id)
    selected = data.get("selected_files", set())

    if idx in selected:
        selected.discard(idx)
    else:
        selected.add(idx)

    update_data(user_id, "selected_files", selected)
    await render_file_selection(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id
    )


@Client.on_callback_query(filters.regex(r"^tdl_sel_all$"))
async def tdl_sel_all_cb(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    data = get_data(user_id)
    files = data.get("downloaded_files", [])
    selected = data.get("selected_files", set())

    if len(selected) == len(files):
        selected = set()
    else:
        selected = set(range(len(files)))

    update_data(user_id, "selected_files", selected)
    await render_file_selection(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id
    )


@Client.on_callback_query(filters.regex(r"^tdl_sort_(size|name)$"))
async def tdl_sort_cb(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    sort_by = callback_query.data.split("_")[2]
    update_data(user_id, "file_sort", sort_by)
    await render_file_selection(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id
    )


@Client.on_callback_query(filters.regex(r"^tdl_cancel$"))
async def tdl_cancel_cb(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)

    try:
        await callback_query.message.edit_text(
            f"❌ **Torrent Operation Cancelled**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"The operation has been cancelled.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="torrent_downloader_menu")]
            ])
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^tdl_process$"))
async def tdl_process_cb(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    data = get_data(user_id)
    files = data.get("downloaded_files", [])
    selected = data.get("selected_files", set())

    if not selected:
        await callback_query.answer("No files selected!", show_alert=True)
        return

    selected_files = [files[i] for i in sorted(selected) if i < len(files)]

    try:
        await callback_query.message.edit_text(
            f"⚙️ **Processing {len(selected_files)} file(s)...**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Files will be sent through the bot pipeline.\n"
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature()}"
        )
    except MessageNotModified:
        pass

    for sf in selected_files:
        file_path = sf.get("path")
        if not file_path or not os.path.exists(file_path):
            continue

        try:
            file_msg = await client.send_document(
                callback_query.message.chat.id,
                file_path,
                caption=f"📤 Processing: {sf.get('name', 'file')}",
            )

            process_data = {
                "type": "torrent_download",
                "original_name": sf.get("name", ""),
                "file_message_id": file_msg.id,
                "file_chat_id": file_msg.chat.id,
                "is_auto": True,
            }

            from plugins.process import process_file
            asyncio.create_task(process_file(client, file_msg, process_data))

        except Exception as e:
            logger.error(f"File processing error for {sf.get('name')}: {e}")
            await client.send_message(
                callback_query.message.chat.id,
                f"❌ Failed to process `{sf.get('name', 'file')}`: {e}"
            )

    # Update download record
    dl_id = data.get("current_download_id")
    if dl_id:
        await db.update_torrent_download(dl_id, {
            "files_processed": len(selected_files),
        })

    clear_session(user_id)


# ============================================================
# Favorites
# ============================================================

@Client.on_callback_query(filters.regex(r"^tdl_fav_(\d+)$"))
async def handle_save_favorite(client, callback_query: CallbackQuery):
    await callback_query.answer("Saved to favorites!", show_alert=False)
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[2])

    data = get_data(user_id)
    results = data.get("search_results", [])
    if idx >= len(results):
        return

    r = results[idx]
    await db.save_torrent_favorite(user_id, {
        "name": r.get("name", ""),
        "size": r.get("size", ""),
        "seeders": r.get("seeders", 0),
        "magnet": r.get("magnet", ""),
        "provider": r.get("provider", ""),
        "detail_url": r.get("detail_url", ""),
    })


@Client.on_callback_query(filters.regex(r"^tdl_favorites$"))
async def handle_favorites_list(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    favorites = await db.get_torrent_favorites(user_id, limit=10)

    if not favorites:
        try:
            await callback_query.message.edit_text(
                f"⭐ **Favorites**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"No saved favorites yet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    text = f"⭐ **Your Favorites**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []

    for i, fav in enumerate(favorites):
        name = fav.get("name", "Unknown")
        if len(name) > 45:
            name = name[:42] + "..."
        text += f"**{i + 1}.** {name}\n   💾 `{fav.get('size', '?')}` | 🌐 `{fav.get('provider', '?')}`\n\n"

        fav_id = str(fav.get("_id", ""))
        buttons.append([
            InlineKeyboardButton(f"⬇ #{i + 1}", callback_data=f"tdl_fav_dl_{fav_id[:20]}"),
            InlineKeyboardButton(f"🗑 Remove", callback_data=f"tdl_fav_rm_{fav_id[:20]}"),
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")])

    # Store favorites in session for ID lookup
    update_data(user_id, "fav_list", favorites)

    try:
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^tdl_fav_dl_(.+)$"))
async def handle_fav_download(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    fav_id_prefix = callback_query.data.split("_")[3]
    data = get_data(user_id)
    fav_list = data.get("fav_list", [])

    fav = None
    for f in fav_list:
        if str(f.get("_id", "")).startswith(fav_id_prefix):
            fav = f
            break

    if not fav or not fav.get("magnet"):
        await callback_query.answer("Favorite not found or no magnet.", show_alert=True)
        return

    # Record download
    download_id = await db.save_torrent_download(user_id, {
        "name": fav.get("name", "Unknown"),
        "magnet": fav["magnet"],
        "size": fav.get("size", "Unknown"),
        "provider": fav.get("provider", "Unknown"),
        "status": "starting",
        "source": "favorite",
    })
    update_data(user_id, "current_download_id", str(download_id) if download_id else None)
    set_state(user_id, "torrent_downloading")

    await start_torrent_download(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id, fav["magnet"],
        torrent_name=fav.get("name", "")
    )


@Client.on_callback_query(filters.regex(r"^tdl_fav_rm_(.+)$"))
async def handle_fav_remove(client, callback_query: CallbackQuery):
    await callback_query.answer("Removed from favorites.")
    user_id = callback_query.from_user.id

    fav_id_prefix = callback_query.data.split("_")[3]
    data = get_data(user_id)
    fav_list = data.get("fav_list", [])

    for f in fav_list:
        fav_id = str(f.get("_id", ""))
        if fav_id.startswith(fav_id_prefix):
            await db.remove_torrent_favorite(user_id, fav_id)
            break

    # Re-render favorites
    await handle_favorites_list(client, callback_query)


# ============================================================
# Search History
# ============================================================

@Client.on_callback_query(filters.regex(r"^tdl_history$"))
async def handle_search_history(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    history = await db.get_torrent_search_history(user_id)

    if not history:
        try:
            await callback_query.message.edit_text(
                f"📜 **Recent Searches**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"No search history yet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]
                ])
            )
        except MessageNotModified:
            pass
        return

    text = f"📜 **Recent Searches**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []

    for i, q in enumerate(history):
        text += f"**{i + 1}.** `{q}`\n"
        buttons.append([InlineKeyboardButton(f"🔍 {q[:30]}", callback_data=f"tdl_history_{i}")])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")])

    update_data(user_id, "search_history_list", history)

    try:
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^tdl_history_(\d+)$"))
async def handle_history_rerun(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[2])

    data = get_data(user_id)
    history = data.get("search_history_list", [])

    if idx >= len(history):
        return

    query = history[idx]
    category = data.get("search_category", "all")

    update_data(user_id, "search_query", query)
    set_state(user_id, "torrent_searching")

    try:
        await callback_query.message.edit_text(
            f"🔎 **Searching** `{query}`...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"__Checking multiple providers...__\n"
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature()}"
        )
    except MessageNotModified:
        pass

    results = await search_torrents(query, category)
    update_data(user_id, "search_results", results)
    update_data(user_id, "search_page", 0)
    set_state(user_id, "torrent_results")

    await render_search_results(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id, page=0
    )


# ============================================================
# Download History
# ============================================================

@Client.on_callback_query(filters.regex(r"^tdl_dl_history$"))
async def handle_download_history(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    page = 0
    data = get_data(user_id)
    if "dl_hist_page" in data:
        page = data["dl_hist_page"]

    await render_download_history(client, user_id, callback_query.message.chat.id, callback_query.message.id, page)


async def render_download_history(client, user_id, chat_id, msg_id, page=0):
    """Render download history with pagination."""
    per_page = 5
    skip = page * per_page
    history = await db.get_torrent_history(user_id, limit=per_page, skip=skip)
    stats = await db.get_torrent_stats(user_id)

    text = (
        f"📊 **Download History**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"> Total: `{stats['total']}` | ✅ `{stats['completed']}` | ❌ `{stats['failed']}`\n\n"
    )

    if not history:
        text += "__No downloads yet.__\n"

    for i, dl in enumerate(history):
        status_icon = {
            "completed": "✅",
            "failed": "❌",
            "cancelled": "⏹",
            "starting": "⏳",
        }.get(dl.get("status", ""), "❓")

        name = dl.get("name", "Unknown")
        if len(name) > 40:
            name = name[:37] + "..."

        text += (
            f"{status_icon} **{name}**\n"
            f"   💾 `{dl.get('size', '?')}` | `{dl.get('provider', '?')}`\n\n"
        )

    update_data(user_id, "dl_hist_page", page)

    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"tdl_dl_hist_p_{page - 1}"))
    if len(history) == per_page:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"tdl_dl_hist_p_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")])

    try:
        await client.edit_message_text(
            chat_id, msg_id, text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^tdl_dl_hist_p_(\d+)$"))
async def handle_dl_history_page(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    page = int(callback_query.data.split("_")[4])

    update_data(user_id, "dl_hist_page", page)
    await render_download_history(
        client, user_id, callback_query.message.chat.id,
        callback_query.message.id, page
    )


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
