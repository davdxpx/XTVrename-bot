import asyncio
import base64
import os
import uuid
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified
from plugins.user_setup import track_tool_usage
from utils.state import set_state, get_state, get_data, update_data, clear_session
from utils.log import get_logger
import aiohttp
from bs4 import BeautifulSoup
from plugins.process import process_file
from database import db
import shutil
import urllib.parse

logger = get_logger("tools.TorrentDownloader")

ARIA2_RPC_URL = "http://localhost:6800/jsonrpc"

async def call_aria2(method, params=None):
    if params is None:
        params = []
    payload = {
        "jsonrpc": "2.0",
        "id": "qwe",
        "method": method,
        "params": params
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ARIA2_RPC_URL, json=payload) as response:
                return await response.json()
    except Exception as e:
        logger.error(f"Aria2 RPC Error: {e}")
        return None

async def scrape_1337x(query):
    encoded_query = urllib.parse.quote(query)
    url = f"https://1337x.to/search/{encoded_query}/1/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    results = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    rows = soup.select("table.table-list tbody tr")
                    for row in rows[:5]:
                        tds = row.find_all("td")
                        if len(tds) > 0:
                            a_tag = tds[0].find_all("a")[1]
                            name = a_tag.text
                            link = "https://1337x.to" + a_tag["href"]
                            size = tds[4].text
                            seeders = tds[1].text
                            leechers = tds[2].text

                            async with session.get(link, headers=headers) as sub_res:
                                if sub_res.status == 200:
                                    sub_html = await sub_res.text()
                                    sub_soup = BeautifulSoup(sub_html, "html.parser")
                                    magnet_a = sub_soup.select_one('a[href^="magnet:"]')
                                    if magnet_a:
                                        magnet = magnet_a["href"]
                                        results.append({
                                            "name": name,
                                            "size": size,
                                            "seeders": seeders,
                                            "leechers": leechers,
                                            "magnet": magnet
                                        })
    except Exception as e:
        logger.error(f"Scraper error: {e}")
    return results

@Client.on_callback_query(filters.regex(r"^torrent_downloader_menu$"))
async def handle_torrent_downloader_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'torrent_downloader')
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_torrent_input")
    update_data(user_id, {"bot_msg_id": callback_query.message.id})

    try:
        await callback_query.message.edit_text(
            "🧲 **Torrent Downloader**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me a **Magnet Link**, a **.torrent file**, \n"
            "> or just click search to find torrents.\n\n"
            "What would you like to do?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔍 Search Torrent", callback_data="torrent_search_prompt")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
                ]
            )
        )
    except MessageNotModified:
        pass

@Client.on_callback_query(filters.regex(r"^torrent_search_prompt$"))
async def torrent_search_prompt(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    set_state(user_id, "awaiting_torrent_search")
    try:
        await callback_query.message.edit_text(
            "🧲 **Torrent Search**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me the movie, series, or game you want to search.\n\n"
            "*(e.g., Ubuntu 22.04)*",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]]
            )
        )
    except MessageNotModified:
        pass

@Client.on_message(filters.private & ~filters.command(["start", "help", "myfiles", "end", "t", "torrent"]), group=3)
async def torrent_message_handler(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == "awaiting_torrent_search":
        await message.delete()
        query = message.text

        session_data = get_data(user_id)

        plan = await db.get_user_plan(user_id)
        last_search = session_data.get("last_search_time", 0)
        is_free = plan.get('plan', 'free') == 'free'

        if is_free and time.time() - last_search < 30:
            rem = int(30 - (time.time() - last_search))
            await client.send_message(user_id, f"⏳ Free users can search once every 30s. Please wait {rem}s.")
            return

        update_data(user_id, {"last_search_time": time.time()})

        bot_msg_id = session_data.get("bot_msg_id")
        if bot_msg_id:
            try:
                await client.edit_message_text(user_id, bot_msg_id, "🔍 Searching for torrents, please wait...")
            except:
                pass

        results = await scrape_1337x(query)
        if not results:
            if bot_msg_id:
                try:
                    await client.edit_message_text(
                        user_id, bot_msg_id,
                        "❌ No results found. Please try another query.",
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]]
                        )
                    )
                except:
                    pass
            return

        text = f"🧲 **Search Results for:** `{query}`\n━━━━━━━━━━━━━━━━━━━━\n\n"
        buttons = []
        for i, res in enumerate(results):
            text += f"**{i+1}.** {res['name']}\n"
            text += f"📦 `{res['size']}` | 🟢 `{res['seeders']}` 🔴 `{res['leechers']}`\n\n"

            update_data(user_id, {f"magnet_{i}": res['magnet']})
            buttons.append([InlineKeyboardButton(f"⬇️ Download #{i+1}", callback_data=f"torrent_dl_mag_{i}")])

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")])

        if bot_msg_id:
            try:
                await client.edit_message_text(user_id, bot_msg_id, text, reply_markup=InlineKeyboardMarkup(buttons))
            except:
                pass

    elif state == "awaiting_torrent_input":
        session_data = get_data(user_id)
        bot_msg_id = session_data.get("bot_msg_id")

        if message.text and message.text.startswith("magnet:?"):
            await message.delete()
            if bot_msg_id:
                try:
                    await client.edit_message_text(user_id, bot_msg_id, "⏳ Initializing Torrent Download...")
                except:
                    pass
            await start_torrent_download(client, user_id, message.chat.id, message.text, bot_msg_id)

        elif message.document and message.document.file_name.endswith(".torrent"):
            await message.delete()
            if bot_msg_id:
                try:
                    await client.edit_message_text(user_id, bot_msg_id, "⏳ Initializing Torrent Download from file...")
                except:
                    pass

            file_path = await message.download()
            with open(file_path, "rb") as f:
                torrent_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(file_path)

            await start_torrent_download_b64(client, user_id, message.chat.id, torrent_data, bot_msg_id)

async def start_torrent_download(client, user_id, chat_id, magnet_link, bot_msg_id=None):
    dl_dir = f"./downloads/torrent_{user_id}_{uuid.uuid4()}"
    res = await call_aria2("aria2.addUri", [[magnet_link], {"dir": dl_dir}])
    if not res or 'error' in res:
        if bot_msg_id:
            try:
                await client.edit_message_text(chat_id, bot_msg_id, "❌ Failed to add torrent to aria2c.")
            except:
                pass
        return
    await monitor_download(client, user_id, chat_id, res['result'], dl_dir, bot_msg_id)

async def start_torrent_download_b64(client, user_id, chat_id, b64_data, bot_msg_id=None):
    dl_dir = f"./downloads/torrent_{user_id}_{uuid.uuid4()}"
    res = await call_aria2("aria2.addTorrent", [b64_data, [], {"dir": dl_dir}])
    if not res or 'error' in res:
        if bot_msg_id:
            try:
                await client.edit_message_text(chat_id, bot_msg_id, "❌ Failed to add torrent to aria2c.")
            except:
                pass
        return
    await monitor_download(client, user_id, chat_id, res['result'], dl_dir, bot_msg_id)

async def monitor_download(client, user_id, chat_id, gid, dl_dir, bot_msg_id=None):
    while True:
        status_res = await call_aria2("aria2.tellStatus", [gid])
        if not status_res or 'result' not in status_res:
            break

        info = status_res['result']
        status = info['status']

        if status == 'complete':
            if bot_msg_id:
                try:
                    await client.edit_message_text(chat_id, bot_msg_id, "✅ Download complete! Preparing files...")
                except:
                    pass
            await handle_downloaded_files(client, user_id, chat_id, dl_dir, bot_msg_id)
            break
        elif status == 'error':
            if bot_msg_id:
                try:
                    await client.edit_message_text(chat_id, bot_msg_id, "❌ Download failed.")
                except:
                    pass
            clear_session(user_id)
            break
        else:
            total = int(info.get('totalLength', 0))
            completed = int(info.get('completedLength', 0))
            speed = int(info.get('downloadSpeed', 0))
            if total > 0:
                percent = (completed / total) * 100
                if bot_msg_id:
                    try:
                        await client.edit_message_text(
                            chat_id, bot_msg_id,
                            f"⬇️ **Downloading:** {percent:.1f}%\n"
                            f"📦 Speed: {speed / 1024 / 1024:.2f} MB/s"
                        )
                    except MessageNotModified:
                        pass

        await asyncio.sleep(3)


async def handle_downloaded_files(client, user_id, chat_id, dl_dir, bot_msg_id=None):
    files = []
    for root, _, filenames in os.walk(dl_dir):
        for f in filenames:
            if f.endswith(('.mkv', '.mp4', '.avi', '.mp3', '.mov', '.zip', '.rar', '.7z')):
                files.append(os.path.join(root, f))

    if not files:
        if bot_msg_id:
            try:
                await client.edit_message_text(chat_id, bot_msg_id, "❌ No supported media files found in torrent.")
            except:
                pass
        shutil.rmtree(dl_dir, ignore_errors=True)
        clear_session(user_id)
        return

    update_data(user_id, {"torrent_files": files, "torrent_dl_dir": dl_dir, "selected_files": []})
    await render_file_selection(client, user_id, chat_id, bot_msg_id)

async def render_file_selection(client, user_id, chat_id, bot_msg_id):
    session_data = get_data(user_id)
    files = session_data.get("torrent_files", [])
    selected = session_data.get("selected_files", [])

    text = "🧲 **Select Files to Process**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []

    for i, f in enumerate(files):
        name = os.path.basename(f)
        prefix = "✅ " if i in selected else "⬜️ "
        buttons.append([InlineKeyboardButton(f"{prefix}{name}", callback_data=f"tdl_sel_{i}")])

    plan = await db.get_user_plan(user_id)
    plan_settings = await db.get_plan_settings(plan.get('plan', 'free'))
    has_multi = plan_settings.get("features", {}).get("torrent_multi_select", False)

    action_row = []
    if has_multi:
        action_row.append(InlineKeyboardButton("✅ Select All", callback_data="tdl_sel_all"))
    action_row.append(InlineKeyboardButton("▶️ Process", callback_data="tdl_process"))

    buttons.append(action_row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="tdl_cancel")])

    if bot_msg_id:
        try:
            await client.edit_message_text(chat_id, bot_msg_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass

@Client.on_callback_query(filters.regex(r"^tdl_sel_(\d+)$"))
async def tdl_sel_cb(client, callback_query):
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[-1])

    session_data = get_data(user_id)
    selected = session_data.get("selected_files", [])

    plan = await db.get_user_plan(user_id)
    plan_settings = await db.get_plan_settings(plan.get('plan', 'free'))
    has_multi = plan_settings.get("features", {}).get("torrent_multi_select", False)

    if not has_multi:
        selected = [idx]
    else:
        if idx in selected:
            selected.remove(idx)
        else:
            selected.append(idx)

    update_data(user_id, {"selected_files": selected})
    await render_file_selection(client, user_id, callback_query.message.chat.id, callback_query.message.id)

@Client.on_callback_query(filters.regex(r"^tdl_sel_all$"))
async def tdl_sel_all_cb(client, callback_query):
    user_id = callback_query.from_user.id
    session_data = get_data(user_id)
    files = session_data.get("torrent_files", [])
    update_data(user_id, {"selected_files": list(range(len(files)))})
    await render_file_selection(client, user_id, callback_query.message.chat.id, callback_query.message.id)

@Client.on_callback_query(filters.regex(r"^tdl_cancel$"))
async def tdl_cancel_cb(client, callback_query):
    user_id = callback_query.from_user.id
    session_data = get_data(user_id)
    dl_dir = session_data.get("torrent_dl_dir")
    if dl_dir:
        shutil.rmtree(dl_dir, ignore_errors=True)
    clear_session(user_id)
    await callback_query.message.edit_text("❌ Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="torrent_downloader_menu")]]))

@Client.on_callback_query(filters.regex(r"^tdl_process$"))
async def tdl_process_cb(client, callback_query):
    user_id = callback_query.from_user.id
    session_data = get_data(user_id)
    files = session_data.get("torrent_files", [])
    selected = session_data.get("selected_files", [])

    if not selected:
        await callback_query.answer("⚠️ No files selected!", show_alert=True)
        return

    await callback_query.message.edit_text("⏳ Pushing files to processing queue...")

    class MockMessage:
        def __init__(self, original_msg, text):
            self.id = original_msg.id
            self.chat = original_msg.chat
            self.from_user = original_msg.from_user
            self.text = text
            self.document = None
            self.video = None
            self.audio = None

        async def reply_text(self, *args, **kwargs):
            return await client.send_message(self.chat.id, *args, **kwargs)

    msg = MockMessage(callback_query.message, "Torrent Downloaded")

    for idx in selected:
        fpath = files[idx]

        data = {
            "type": "general",
            "local_file_path": fpath,
            "original_name": os.path.basename(fpath),
            "is_auto": False,
            "cleanup_dir": session_data.get("torrent_dl_dir") if idx == selected[-1] else None
        }

        asyncio.create_task(process_file(client, msg, data))

    clear_session(user_id)

@Client.on_callback_query(filters.regex(r"^torrent_dl_mag_(\d+)$"))
async def torrent_dl_mag_cb(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    idx = callback_query.data.split("_")[-1]

    session_data = get_data(user_id)
    magnet = session_data.get(f"magnet_{idx}")
    bot_msg_id = session_data.get("bot_msg_id")

    if not magnet:
        await callback_query.message.edit_text("❌ Session expired.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="torrent_downloader_menu")]]))
        return

    await callback_query.message.edit_text("⏳ Starting download...", reply_markup=None)
    await start_torrent_download(client, user_id, callback_query.message.chat.id, magnet, bot_msg_id)
