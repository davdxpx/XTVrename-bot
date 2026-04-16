# 𝕏TV MediaStudio™ 🚀

> **Business-Class Media Management Solution**
> *Developed by [𝕏0L0™](https://t.me/davdxpx) for the [𝕏TV Network](https://t.me/XTVglobal)*

<p align="center">
  <img src="./assets/banner.png" alt="𝕏TV MediaStudio™ Banner" width="100%">
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.9+-blue.svg?logo=python&logoColor=white" alt="Python"></a>
  <a href="https://docs.pyrogram.org/"><img src="https://img.shields.io/badge/Pyrogram-v2.0+-blue.svg?logo=telegram&logoColor=white" alt="Pyrogram"></a>
  <a href="https://ffmpeg.org/"><img src="https://img.shields.io/badge/FFmpeg-Included-green.svg?logo=ffmpeg&logoColor=white" alt="FFmpeg"></a>
  <a href="https://www.mongodb.com/"><img src="https://img.shields.io/badge/MongoDB-Ready-47A248.svg?logo=mongodb&logoColor=white" alt="MongoDB"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://github.com/davdxpx/XTV-MediaStudio/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-XTV_Public_v3.0-red.svg" alt="License"></a>
</p>

The **𝕏TV MediaStudio™** is a high-performance, enterprise-grade **Telegram Bot** engineered for automated media processing, file renaming, and video metadata editing. It combines robust **FFmpeg** metadata injection with intelligent file renaming algorithms, designed specifically for maintaining large-scale media libraries on Telegram. Whether you need an **automated media manager**, a **TMDb movie scraper**, or a **video metadata editor**, 𝕏TV MediaStudio™ is the ultimate **media management solution**.

---

### 📋 What's New in v1.5.2
*   **🎬 YouTube Tool (`/yt`)**: Full-featured downloader — Video (up to 4K / 4GB with 𝕏TV Pro), Audio (MP3 128/192/320 kbps with embedded cover art), Thumbnail (HQ JPG), Subtitles/Captions (12 languages, SRT output, auto-caption fallback), and complete Video Info metadata.
*   **🛡 YouTube Anti-Bot Hardening**: Three-layer defense against YouTube's "sign in to confirm you're not a bot" guard — cookie file support (`/ytcookies` admin command to upload a Netscape `cookies.txt`), automatic player-client rotation (iOS / Android / TV / web-embedded) on bot-check failures, and a dedicated in-chat help screen with Retry + Upload-cookies buttons.
*   **🎛 File Converter Mega Edition (`/c`)**: Completely redesigned with category-based submenus. **Video**: Container swap (MP4, MKV, MOV, AVI, WEBM, FLV, 3GP, TS), Codec (x264, x265, VP9, AV1), Extract Audio (MP3, M4A, OGG, OPUS, FLAC, WAV), Extract Frame (PNG/JPG/WEBP), Animated GIF presets, Audio FX (Normalize / Boost / Mono), Transform (Resolution 480p/720p/1080p/4K, Mute, Speed 0.5×/1.5×/2×, Reverse). **Audio**: Format (MP3/M4A/OGG/OPUS/FLAC/WAV/WMA), Bitrate 128/192/256/320 kbps, FX (Normalize, Boost, Bass Boost, Speed, Reverse, Mono). **Image**: Format (PNG/JPG/WEBP/BMP/TIFF/GIF/ICO/AVIF/PDF), Resize (presets + 50% / 25%), Rotate/Flip, Filters (Grayscale/Invert/Sepia), Compress presets.
*   **📡 Unified Dumb Channel Wizard (v2)**: The old broken "Add Dumb Channel" flow is replaced by a proper 3-step wizard. Accepts forwarded messages (both legacy and new Pyrogram forward APIs), `-100…` IDs, `@usernames`, bare usernames, `t.me/user` and `t.me/c/id` links. Pre-save bot-admin validation with 5 distinct result states (ok+post, ok-no-post, member-no-admin, not-member, invalid). Native Telegram "Add me as admin" deep-link button. Dedup check, retry flow, and quick-default shortcuts (set as Standard / Movie / Series default after save).
*   **🧰 New Media Tools**: MediaInfo (`/mi`) for detailed stream analysis, Subtitle Extractor (`/s`) for ripping subs from MKV/MP4, Video Trimmer (`/t`) for cutting clips without re-encoding, Voice Note Converter (`/v`) and Video Note Converter (`/vn`) for Telegram's round-note formats.
*   **🎨 YouTube Tool UX Polish**: Thumbnail flow now offers `← Back to Menu` and `🔗 New Link` buttons (session persists across retries). Fixed markdown italic rendering across 8 label locations so text no longer shows literal underscores.

<details>
<summary><b>📋 What's New in v1.5.1</b></summary>

*   **Migration to Pyrofork**: The underlying Telegram framework was migrated from Pyrogram to Pyrofork, enabling the usage of modern Telegram API Layer features.
*   **Expandable Quotes**: Added native support for `<blockquote expandable>` for long text fields (e.g. inside `/help`).
*   **System Info Refactor**: Added detailed system info natively in the `/info` menu.
*   **Robust Peer Caching**: Fixed pesky `PeerIdInvalid` errors. The bot now explicitly forces a re-cache by fetching the chat when channels are not found dynamically!
</details>

<details>
<summary><b>📋 What's New in v1.5.0</b></summary>
• The biggest update in 𝕏TV history — 77 pull requests, a full rebrand, and an entirely new product.

- **🏷️ Rebrand:** XTV Rename Bot is now **𝕏TV MediaStudio™** — new name, new identity, new era
- **📁 MyFiles V2.0 — Endgame Evolution:** Personal cloud storage with auto-folders, custom folders, batch multi-select actions, season grouping, Netflix-style TMDb poster dashboard, inline query search (`@bot query`), system filename templates, dynamic sorting, and privacy settings
- **💎 Premium System Overhaul:** Multi-tier plans (Standard ⭐ / Deluxe 💎), Telegram Stars payments, PayPal, Crypto (USDT/BTC/ETH), UPI, automated trial system, priority queue, and per-plan feature overrides
- **📡 Dumb Channel Auto-Routing:** Automatic Movie / Series / Default channel routing based on TMDb detection
- **🎯 Unified Destination Menu:** Folder + channel selection combined in a single paginated UI
- **🖼️ Thumbnail Mode Preferences:** None / Auto / Custom modes configurable per user and globally
- **🔧 Global Feature Toggles:** Admin can enable/disable resource-heavy tools globally, with premium cascade overrides
- **📺 Season & Episode Detection:** Multi-episode file support and improved parsing accuracy
- **✏️ Edit Instead of Send UX:** Admin configuration prompts now edit messages in-place for a cleaner chat
- **🗂️ Major Codebase Refactor:** Core processing extracted to `tools/` directory, pre-processing separated into standalone modules
- **📖 Start Menu & Help Guide Overhaul:** Redesigned interactive starter setup, expandable troubleshooting sub-menus, and categorized help sections
- **⚡ Performance:** Persistent HTTP sessions, database settings cache (60s TTL), programmatic MongoDB indexes, async file cleanup
- **🔒 Security:** SSL bypass removed, config validation on startup, FFmpeg metadata sanitization
- **🧹 Reliability:** State TTL auto-cleanup, queue memory leak fix, graceful shutdown, robust subprocess cleanup with disk checks
- **🎨 UI Polish:** 150+ back-button labels standardized with contextual `← Back to [Page]` format
- **🏗️ Infrastructure:** Ruff linter, GitHub Actions CI, pinned dependencies, Dockerfile optimization
</details>  

---

## 📑 Table of Contents

- [🌟 Core Features](#-core-features)
- [💎 Premium & Payment System](#-premium--payment-system)
- [⚙️ Configuration (.env)](#️-configuration-env)
- [🚀 𝕏TV Pro™ Setup (4GB File Support)](#-xtv-pro-setup-4gb-file-support)
- [🌍 Public Mode vs Private Mode](#-public-mode-vs-private-mode)
- [🛠 Deployment Guide](#-deployment-guide)
- [🎮 Usage Commands](#-usage-commands)
- [🧩 Credits & License](#-credits--license)

---

## 🌟 Core Features

### 🔹 Advanced Processing Engines
*   **𝕏TV Core™**: Lightning-fast processing for standard files (up to 2GB) using the primary bot API.
*   **𝕏TV Pro™: Ephemeral Tunnels**: Seamless integration with a Premium Userbot session to handle **Large Files (>2GB up to 4GB)**. The system generates secure, temporary private tunnels for every single large file transfer, bypassing API limits, cache crashing, and `PEER_ID_INVALID` errors.
*   **Concurrency Control**: Global semaphore system prevents server overload by managing simultaneous downloads/uploads.

### 🔹 Intelligent Recognition
*   **MyFiles V2.1 Endgame Evolution**:
    *   **Inline Query Search:** Use `@YourBotName [search query]` anywhere to instantly pull up your files and share them via Deep Links!
    *   **Netflix-Style Visual Dashboard:** When viewing your files in `/myfiles`, the bot dynamically updates the interface to display the beautiful TMDb media poster inline.
    *   **Smart System Filenames:** Use `{title} ({year})` and other customizable templates to completely automate how your internal media files are saved and displayed.
    *   **Batch Actions (Multi-Select):** Easily move, send, or delete multiple files at once in your MyFiles dashboard via the new interactive checkmark system.
    *   **Dynamic Sorting:** Sort files by Newest, Oldest, or A-Z natively inside the MyFiles interface.
*   **Workflow Modes (Starter Setup)**: The bot greets users with an interactive, beautifully-formatted **Starter Setup Menu** when they join your Force-Sub channel or press `/start`. Users can pick their primary mode of operation:
    *   **🧠 Smart Media Mode**: Best for TV Shows & Movies. Automatically triggers the Auto-Detection Matrix and fetches TMDb metadata/posters natively.
    *   **⚡ Quick Rename Mode**: Best for Personal Videos, Anime, or generic files. Instantly bypasses all auto-detection logic and brings the user straight to the renaming prompt for rapid processing.
*   **Seamless Chat Cleanup**: The bot aggressively keeps the chat history pristine during the renaming process. It auto-deletes its own prompts and the user's replies, keeping the interface uncluttered.
*   **Auto-Detection Matrix**: Automatically scans filenames to detect Movie/Series titles, Years, Qualities, and Episode numbers with high accuracy.
*   **Smart Metadata Fetching**: Integration with **TMDb** to pull official titles, release years, and artwork. Now supports **Multilingual Metadata** (e.g. `de-DE`, `es-ES`), customizable per user in `/settings`!
*   **Automatic Archive Unpacking**: Automatically detects and downloads `.zip`, `.rar`, and `.7z` archives. It smartly identifies password-protected archives, prompts the user for the password, extracts the contents, and automatically feeds all valid media files directly into the batch processing queue!

### 🔹 Media Management & Workflows
*   **MyFiles System (`/myfiles`)**: A completely interactive, in-bot cloud storage management system! Every file processed by the bot is safely routed to hidden **Database Channels** and stored persistently.
    *   **Auto-Folders**: Automatically organizes your media into "Movies", "Series", or "Subtitles" folders using the advanced TMDb Auto-Detection Matrix.
    *   **Custom Folders**: Users can create their own custom folders, move files between them, and rename files natively.
    *   **Temporary vs Permanent Storage**: Admins can set precise plan limits for how many "Permanent" slots users receive. Files exceeding the limits are stored as "Temporary" and automatically cleared by the bot's background cleanup engine based on expiration rules.
    *   **Team Drive Mode**: In Non-Public Mode, the `/myfiles` system transforms into a single, shared "Global Workspace" where the entire team can securely access and manage all files across a unified global database channel.
*   **Multiple Dumb Channels & Sequential Batch Forwarding**: Configure multiple independent destination channels (globally or per-user). The bot automatically queues seasons or movie collections in bulk and strictly forwards them in sequential order (e.g., sorting series by Season/Episode and movies by resolution precedence: 2160p > 1080p > 720p > 480p).
*   **Unified Dumb Channel Wizard (v2)**: Adding a channel is now a clean 3-step flow — prompt → resolve → validate → save. Accepts forwarded messages (both legacy `forward_from_chat` and the newer `forward_origin.chat` APIs), `-100…` IDs, `@username`, bare usernames, `t.me/user` and `t.me/c/id` links. Rejects invite links with a helpful hint. Pre-save bot-permission validation with 5 distinct outcomes (admin+post / admin-no-post / member-no-admin / not-member / invalid) and a native Telegram "Add me as admin" deep-link button. Dedup check prevents duplicate adds. Quick-default shortcuts right after save let you flag the new channel as your Standard / Movie / Series default in one click.
*   **Smart Debounce Queue Manager**: Automatically sorts batched media uploads logically. Instead of simple alphabetical sorting, series are ordered by SxxExx and movies by quality precedence, preventing out-of-order uploads to your channels.
*   **Smart Timeout Queue**: Never get stuck waiting for crashed files. The sequential forwarding queue obeys a customizable timeout limit.
*   **Spam-Proof Forwarding**: Utilizing Pyrogram's `copy()` method, the bot cleanly removes 'Forwarded from' tags when sending to Dumb Channels, preventing Telegram's spam detection from flagging bulk media.
*   **Personal Media & Unlisted Content**: Direct menu options to bypass metadata databases for personal files, preserving original file extensions (like `.jpeg`) and letting you choose your preferred output format.
*   **Multipurpose File Utilities**: A complete in-bot suite of direct editing tools accessible via the **✨ Other Features** menu or their shortcut commands:
    *   **`/g` General Rename** — rename any file, bypass TMDb lookup.
    *   **`/a` Audio Metadata Editor** — edit MP3/FLAC title, artist, album, cover art.
    *   **`/c` File Converter Mega Edition** — category-based menus for Video (container swap, codec, audio/frame extract, GIF, audio FX, resolution/speed/reverse), Audio (format, bitrate, FX, bass boost), and Image (format, resize, rotate/flip, filters, compression). See the v1.5.2 changelog for the full op list.
    *   **`/w` Image Watermarker** — text or overlay-image watermarks.
    *   **`/s` Subtitle Extractor** — rip embedded subtitle tracks from MKV/MP4 containers.
    *   **`/t` Video Trimmer** — fast clip-cut without re-encoding, configurable start/end.
    *   **`/v` Voice Note Converter** — convert audio to Telegram's native voice-note format.
    *   **`/vn` Video Note Converter** — convert video to Telegram's round "video note" bubble format.
    *   **`/mi` MediaInfo** — detailed stream / codec / bitrate / duration / track breakdown for any media file.
    *   **`/yt` YouTube Tool** — see "YouTube Tool" section below.
*   **Dynamic Filename Templates**: Fully customizable filename structures via the Admin Panel for Movies, Series, and Subtitles using variables like `{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, `{Season_Episode}`, `{Language}`, and `{Channel}`.

### 🔹 YouTube Tool (`/yt`)
*   **Five Download Modes**:
    *   **🎬 Video** — 360p / 480p / 720p / 1080p / Best-Available. Merges into MP4 with embedded thumbnail and FFmpeg metadata. Respects your plan's filesize cap (2 GB Standard, 4 GB with 𝕏TV Pro).
    *   **🎵 Audio (MP3)** — 128 / 192 / 320 kbps with embedded cover art.
    *   **🖼 Thumbnail** — highest-available JPG. Success screen offers `← Back to Menu` and `🔗 New Link` so you can chain multiple downloads without re-sending the URL.
    *   **📝 Subtitles / Captions** — 12 languages (EN/ES/FR/DE/HI/PT/IT/JA/KO/ZH/RU/AR), SRT output, automatic fallback to auto-captions if manual subs aren't available.
    *   **ℹ️ Video Info** — full yt-dlp metadata dump (title, uploader, duration, view count, formats, upload date, etc.).
*   **Live Progress**: status message edits every ~3 seconds with a visual progress bar, size, speed, ETA.
*   **Auto-URL Detection**: paste any `youtube.com` / `youtu.be` / `music.youtube.com` / `youtube-nocookie.com` link in chat without an active state and the bot offers to open the tool.
*   **🛡 Anti-Bot Hardening** — three defensive layers against YouTube's "sign in to confirm you're not a bot" guard:
    1. **Cookies**: admin command `/ytcookies` lets you upload a Netscape-format `cookies.txt`. The file is stored at `config/yt_cookies.txt` and used automatically for every subsequent request. Export with a browser extension like "Get cookies.txt LOCALLY" while logged into youtube.com.
    2. **Player-Client Fallback**: on bot-check failure the extractor automatically rotates through `default → ios → android → tv_embedded → web_embedded → mweb` before giving up.
    3. **Dedicated UI**: when YouTube still blocks the request the bot shows a clear in-chat help screen with a Retry button, an `🍪 Upload cookies` button (admins only), and cookie-status indicator — never a silent "Could not fetch info".

### 🔹 Professional Metadata Injection
*   **FFmpeg Power**: Injects custom metadata (Title, Author, Artist, Copyright) directly into MKV/MP4 containers. The ultimate Telegram FFmpeg media processing bot.
*   **Branding**: Sets e.g. "Encoded by @YourChannel" and custom audio/subtitle track titles.
*   **Thumbnail Embedding**: Embeds custom or poster-based thumbnails into video files. Natively toggleable through the interactive settings menu (Auto-detect, Custom, or Deactivated).
*   **Album Support**: Handles multiple file uploads (albums) concurrently without issues.

### 🔹 Security & Privacy
*   **Anti-Hash Algorithm**: Generates unique, random captions for every file to prevent hash-based tracking or duplicate detection.
*   **Smart Force-Sub Setup**: Automatically detects when the bot is promoted to an Administrator in a channel, verifies permissions, and dynamically generates and saves an invite link for seamless Force-Sub configuration.
*   **Admin Feature Toggles**: Protect your server by toggling heavy CPU/RAM features (like Video Conversion and Watermarking) on or off globally.

---

## ☁️ Mirror-Leech

`MYFILES_VERSION 2.2` adds a **Mirror-Leech** subsystem that takes any
supported source and fans it out to one or more cloud destinations.
Deeply fused with MyFiles — every file in your cloud can be pushed to
Drive, MEGA, Pixeldrain, or another destination in one click.

### Sources (downloaders)

| Source | Notes |
|---|---|
| Direct HTTP(S) URL | streaming aiohttp, resume on Content-Length |
| YouTube + social (via yt-dlp) | any URL a yt-dlp extractor accepts |
| Telegram file (`tg:<chat>:<msg>`) | auto-used for MyFiles buttons |
| RSS feed | `.rss` / `.xml` / `/feed/` URLs; first enclosure via HTTP |

Peer-to-peer swarm links are out of scope on this branch and fall
through to a generic "unsupported source" message.

### Destinations (uploaders)

| Destination | Credentials |
|---|---|
| Google Drive | OAuth refresh_token + client_id + client_secret |
| Rclone (70+ backends) | `rclone.conf` body + default `remote:path` |
| MEGA.nz | email + password (requires `pip install mega.py`) |
| GoFile | anonymous OK, optional account token |
| Pixeldrain | anonymous OK, optional API key |
| Telegram | DM by default; set a channel id to override |
| Direct Download Link | needs `DDL_BASE_URL` env — one-time URLs |

### Usage

1. **Enable** under `/admin → ☁️ Mirror-Leech Config`. The feature stays
   off until an admin flips it on, and the toggle itself refuses to
   turn on until `SECRETS_KEY` is configured.
2. **Link providers** under `/settings → ☁️ Mirror-Leech` (public mode)
   or the same admin screen (non-public mode). Paste-to-link messages
   are deleted automatically after storage.
3. **Run a transfer**: `/ml <url>` picks a downloader automatically,
   prompts for destinations, and edits a single progress message in
   place until the task finishes.
4. **From MyFiles**: every single-file view has an "☁️ Mirror-Leech
   Options" button, and multi-select adds a "☁️ Mirror-Leech Selected
   (N)" batch action — each file queues its own task.
5. **Queue & cancel**: `/mlqueue` lists your last 20 tasks with inline
   cancel buttons.

### Secrets

Provider credentials are Fernet-encrypted at rest with `SECRETS_KEY`
(required — the bot refuses to store plaintext). Back the key up before
handing out logins — losing it means every user has to re-link their
providers.

Generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 💎 Premium & Payment System

The 𝕏TV MediaStudio™ features a highly robust, business-class **Premium Subscription System** designed to monetize your bot and provide exclusive features to power users.

<details>
<summary><b>🌟 Premium System Highlights</b></summary>
<br>

*   **Multi-Tier Subscription Model**: Supports customizable **Standard** (⭐) and **Deluxe** (💎) premium plans. Admins can configure completely different daily egress limits, file processing limits, `/myfiles` folder limits, permanent storage capacities, and pricing for each tier.
*   **Donator Plan**: When a user's premium subscription expires, they are elegantly downgraded to the exclusive **Donator Plan**. This honors their support while applying free-tier restrictions and custom expiration logic for their overflow files.
*   **Feature Overrides**: Premium plans can be configured to bypass global "Admin Feature Toggles". For example, you can disable the heavy **Video Converter** for free users to save server CPU, but explicitly enable it for Premium Deluxe users!
*   **Priority Queue Processing**: Premium users bypass standard wait times via a specialized queue mechanism with reduced debounce delays and higher asynchronous concurrency limits.
*   **Automated Trials**: Admins can enable a customizable "Trial System", allowing free users to claim a 1-to-7 day premium trial directly from the bot.
*   **User Dashboard**: Premium users receive an aesthetically pleasing dashboard with heavy padding and decorative elements (`>`), displaying their current plan, expiry date, and active limits.

</details>

<details>
<summary>📈 <b>Unified Limit Management</b></summary>
Admins can easily set Free, Standard, and Deluxe plan limits (daily files, egress limits, custom folders, etc.) from a single unified menu under "Access & Limits".
</details>

<details>
<summary><b>💳 High-End Payment Gateways</b></summary>
<br>

*   **Telegram Stars Integration**: Seamlessly accepts native Telegram Stars using Pyrogram's `LabeledPrice` and raw MTProto API integration. Fast, secure, and native to the app!
*   **Professional Crypto Checkout**: Supports manual cryptocurrency payments. Admins can configure multiple specific wallet addresses (e.g., USDT, BTC, ETH) which are dynamically presented to the user during checkout.
*   **PayPal & UPI**: Direct manual payment integration for major fiat gateways.
*   **Automated Admin Approval Flow**: When a user makes a manual payment (Crypto/PayPal), the bot generates a unique Payment ID and logs it. Admins receive an instant notification with the receipt and can approve or deny the transaction with a single click, automatically applying the premium duration to the user.
*   **Dynamic Fiat Pricing**: Prices are displayed dynamically in both the user's local currency and USD equivalent (e.g., `2000 ₹ / $22.40`), with smart formatting for strong vs. weak currencies. Multi-month discounts (e.g., 3-month or 12-month) are calculated automatically.

</details>

---

## ⚙️ Configuration (.env)

Create a `.env` file in the root directory. You will need a **MongoDB** instance and **Pyrogram** session (optional for 4GB files).

### 🏁 Minimal setup (5 env vars → running bot)

Five vars and you're live. Everything else is optional.

```env
BOT_TOKEN=<from @BotFather>
API_ID=<from my.telegram.org>
API_HASH=<from my.telegram.org>
MAIN_URI=<MongoDB connection string — free Atlas tier works>
CEO_ID=<your Telegram user ID>
```

Features that need an API key (TMDb poster lookup, Mirror-Leech cloud
uploads) ship a friendly 🔒 notice when the key is missing and unlock
themselves the moment you add it — no redeploy needed for most keys.

### Full variable reference

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `BOT_TOKEN` | ✅ | — | Bot token from @BotFather |
| `API_ID` | ✅ | — | Telegram API ID (my.telegram.org) |
| `API_HASH` | ✅ | — | Telegram API Hash (my.telegram.org) |
| `MAIN_URI` | ✅ | — | MongoDB connection string (free Atlas tier supported) |
| `CEO_ID` | ✅ | — | Your Telegram user ID — only this user can open `/admin` |
| `ADMIN_IDS` | ❌ | empty | Comma-separated extra admin user IDs |
| `PUBLIC_MODE` | ❌ | `false` | `true` to open the bot to everyone |
| `DEBUG_MODE` | ❌ | `false` | Verbose logs |
| `TMDB_API_KEY` | ❌ | empty | Unlocks title matching, posters, auto channel routing. Free key at https://www.themoviedb.org/settings/api |
| `SECRETS_KEY` | ❌ | empty | Fernet key encrypting Mirror-Leech provider credentials. Required only when Mirror-Leech is enabled. |
| `YT_COOKIES_FILE` | ❌ | `config/yt_cookies.txt` | Absolute path to a Netscape YouTube cookies file. Admins can also upload at runtime via `/ytcookies`. |

---

## 🚀 𝕏TV Pro™ Setup (4GB File Support)

To bypass Telegram's standard 2GB bot upload limit, the **𝕏TV MediaStudio™** features a built-in **𝕏TV Pro™** mode. This mode uses a Premium Telegram account (Userbot) to act as a seamless tunnel for processing and delivering files up to 4GB.

<details>
<summary><b>🛠 How to Setup</b></summary>
<br>

1. Send `/admin` to your bot.
2. Click the **"🚀 Setup 𝕏TV Pro™"** button.
3. Follow the completely interactive, fast, and fail-safe setup guide. You will be asked to provide your **API ID**, **API Hash**, and **Phone Number**.
4. The bot will request a login code from Telegram. *(Enter the code with spaces, e.g., `1 2 3 4 5`, to avoid Telegram's security triggers).*
5. If 2FA is enabled, enter your password.
6. The bot will verify that the account has **Telegram Premium**. If successful, it securely saves the session credentials to the MongoDB database and hot-starts the Userbot instantly—**no restart required**.

> **Privacy & Ephemeral Tunneling (Market First!):** When processing a file > 2GB, the Premium Userbot creates a temporary, private "Ephemeral Tunnel" channel specific to that file. It uploads the transcoded file to this tunnel, and the Main Bot seamlessly copies the file from the tunnel directly to the user. After the transfer, the Userbot instantly deletes the temporary channel. This entirely bypasses standard bot API limitations, completely hides the Userbot's identity, prevents `PEER_ID_INVALID` caching errors, and removes any "Forwarded from" tags for a flawless delivery!

</details>

---

## 🌍 Public Mode vs Private Mode

The bot can operate in two distinct modes via the `PUBLIC_MODE` environment variable. **Choose a mode initially and stick with it**, as the database structure changes drastically between the two.

<details>
<summary><b>🔒 Private Mode (PUBLIC_MODE=False - Default)</b></summary>
<br>

* **Access**: Only the `CEO_ID` and `ADMIN_IDS` can use the bot.
* **Settings**: Global. The `/admin` command configures one global thumbnail, one set of filename templates, and one caption template for all files processed.
</details>

<details>
<summary><b>🔓 Public Mode (PUBLIC_MODE=True)</b></summary>
<br>

* **Access**: Anyone can use the bot!
* **User-Specific Settings**: Every user gets their own profile to customize thumbnails and templates without affecting others.
* **CEO Controls**: The `/admin` command transforms into a global configuration panel:
  * **User Management Dashboard**: Inspect detailed user profiles, active/banned status, usage stats, and manually grant/revoke Premium access.
  * **Daily Quotas & Limits**: Configure maximum daily egress (MB) and daily file limits per user to prevent abuse.
  * **Usage Dashboard**: Monitor global egress usage (last 7 days), track live bot activity, and block abusers.
  * **Premium Setup**: Configure the complete Premium & Payment gateway system.
</details>

---

## 🛠 Deployment Guide

Welcome to the **𝕏TV MediaStudio™** deployment documentation! Because this bot processes media with **FFmpeg**, it consumes significant **RAM** and **Bandwidth (Egress)**. Keep this in mind when choosing a provider!

> **TL;DR** — set the 5 required env vars and click any deploy button below. `TMDB_API_KEY` is **optional**; the bot runs fine without it and shows a 🔒 notice on TMDb-dependent features until you add one. Same story for `SECRETS_KEY` (Mirror-Leech only).

<details>
<summary><b>⚡ 1-Click Cloud Deployments (PaaS)</b></summary>
<br>

Platform-as-a-Service (PaaS) providers build and run the code directly from your GitHub repository.

### 1. Render (Highly Recommended - Zero Egress Costs)
Render provides **generous unmetered bandwidth**, saving you from unexpected egress bills when processing large video files.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. **Fork** this repository to your GitHub account.
2. Click the **Deploy to Render** button above.
3. Connect your GitHub account and select your forked repository.
4. Render will detect the `render.yaml` file automatically.
5. Fill in the required **Environment Variables** (like `BOT_TOKEN`, `API_ID`, etc.). Pay special attention to `PUBLIC_MODE`.
6. Click **Apply/Save**. Your bot will build and start as a Background Worker!
*Note: If out-of-memory crashes occur, consider upgrading from the Free Tier.*

### 2. Railway
Railway offers lightning-fast deployments and great performance, though be mindful of monthly egress bandwidth usage.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

1. **Fork** this repository.
2. Click the **Deploy on Railway** button above.
3. Select your GitHub repository.
4. Go to the **Variables** tab in your new Railway project and add your required configuration.
5. Railway will automatically build the `Dockerfile` and start your bot!

### 3. Koyeb
Koyeb provides high-performance global infrastructure with a generous free tier for compute, though bandwidth is limited.

[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy)

1. **Fork** this repository.
2. Click **Create Service** on Koyeb. Choose **GitHub** and select your repository.
3. Set the **Builder** to Docker. Add your `.env` values under **Environment variables**.
4. Click **Deploy**.

### 4. Zeabur
Zeabur makes deploying bots effortless.

[![Deploy on Zeabur](https://zeabur.com/button.svg)](https://dash.zeabur.com/templates/github)

1. **Fork** this repository.
2. Log in to Zeabur, create a **Project**, click **Add Service** -> **Git** and select your repository.
3. Add your environment variables in the **Variables** tab.

</details>

<details>
<summary><b>🖥️ VPS & Dedicated Server Deployments</b></summary>
<br>

If you need maximum control, massive storage, and the cheapest bandwidth, deploying on a Virtual Private Server (VPS) via SSH is the best route.

### 1. Oracle Cloud (Always Free ARM)
The "Always Free" Ampere A1 instance gives you 4 CPU Cores, 24GB of RAM, and **10TB of Free Egress Bandwidth** every month!

1. Create a Canonical Ubuntu instance (Virtual machine -> Ampere -> VM.Standard.A1.Flex).
2. Connect via SSH: `ssh -i "path/to/key.key" ubuntu@YOUR_PUBLIC_IP`
3. Follow the Standard Docker Deployment steps below. Our Dockerfile automatically detects and optimizes for ARM!

### 2. Hetzner Cloud (The Ultimate Budget VPS - 20TB Traffic)
For around €4 a month, you get a dedicated IPv4 and a massive **20TB of Traffic (Bandwidth)** per month included.

1. Create an Ubuntu 24.04 server. The cheapest Arm64 (CAX series) or x86 (CX series) is perfect.
2. Connect via SSH: `ssh root@YOUR_SERVER_IP`
3. Follow the Standard Docker Deployment steps below.

### 3. Standard VPS (DigitalOcean, AWS EC2, etc.)
1. **Connect** to your server via SSH.
2. **Install Docker**:
   ```
   sudo apt update && sudo apt upgrade -y
   sudo apt install docker.io docker-compose git -y
   sudo systemctl enable --now docker
   ```
3. **Download the Bot:**
   ```
   git clone https://github.com/davdxpx/XTV-MediaStudio.git
   cd XTV-MediaStudio
   ```
4. **Configure Settings:** (Create a `.env` file and put your variables there)
   ```
   cp .env.example .env
   # Edit .env using a text editor
   ```
5. **Run the Bot:**
   ```
   docker-compose up -d --build
   ```
*(View logs anytime using `docker-compose logs -f`)*

</details>

---


## 🤖 BotFather Commands

Use these ready-to-copy command lists to easily set up your bot menu in @BotFather via `Edit Bot > Edit Commands`. Choose the block that matches your `PUBLIC_MODE` configuration.

<details>
<summary><b>🔓 Public Mode Commands (PUBLIC_MODE=True)</b></summary>
<br>

```text
start - ▶️ Start the bot
settings - ⚙️ Customize your templates & thumbnails
myfiles - 🗃️ Your personal Cloud Media Library
premium - 💎 View and upgrade your premium plan
usage - 📊 Track your limits & active storage
yt - 🎬 YouTube downloader (video, audio, thumb, subs)
c - 🎛 File Converter (video/audio/image)
a - 🎵 Audio metadata editor
w - 🖼 Image watermarker
s - 📝 Subtitle extractor
t - ✂️ Video trimmer
v - 🎙 Voice note converter
vn - ⭕ Video note converter
mi - 🔍 MediaInfo (stream analyzer)
g - ✏️ General rename (skip TMDb)
p - 📁 Personal files mode
r - 🏷 Classic manual rename
help - 🆘 Read the Help Guide & troubleshooting
info - ℹ️ View bot version and support info
end - 🚫 Cancel the current task or state
admin - ⛔ Access Global Configurations (CEO Only)
```
</details>

<details>
<summary><b>🔒 Private Mode Commands (PUBLIC_MODE=False)</b></summary>
<br>

```text
start - ▶️ Start the bot
myfiles - 🗃️ Open your Cloud Media Library
yt - 🎬 YouTube downloader (video, audio, thumb, subs)
c - 🎛 File Converter (video/audio/image)
a - 🎵 Audio metadata editor
w - 🖼 Image watermarker
s - 📝 Subtitle extractor
t - ✂️ Video trimmer
v - 🎙 Voice note converter
vn - ⭕ Video note converter
mi - 🔍 MediaInfo (stream analyzer)
g - ✏️ General rename (skip TMDb)
p - 📁 Personal files mode
r - 🏷 Classic manual rename
ytcookies - 🍪 Upload YouTube cookies (admins)
help - 🆘 Read the Help Guide & troubleshooting
info - ℹ️ View bot version and support info
end - 🚫 Cancel the current task or state
admin - ⛔ Access Global Configurations (Admins Only)
```
</details>

---
## 🎮 Usage Commands

### Core Commands
*   **/start**: Check bot status and show the interactive starter menu.
*   **/admin**: Access the **Admin Panel** to configure global settings (or CEO controls in Public Mode).
*   **/settings**: Access **Personal Settings** to configure your own templates and thumbnails (Public Mode only).
*   **/myfiles**: Open your interactive cloud storage menu to view, manage, and batch-send your processed files.
*   **/premium**: Open the **Premium Dashboard** to view or upgrade your plan.
*   **/info**: View bot details and support info.
*   **/usage**: View your daily limits and personal usage (Public Mode only).
*   **/end**: Clear current session state (useful to reset auto-detection).
*   **/help**: Open the Help Guide & troubleshooting pages.

### Rename & Metadata
*   **/r** or **/rename**: Open the classic manual rename menu directly.
*   **/p** or **/personal**: Open Personal Files mode directly.
*   **/g** or **/general**: Open General Mode (rename any file, bypass TMDb lookup).
*   **/a** or **/audio**: Open the Audio Metadata Editor (MP3/FLAC title, artist, album, cover art).

### Media Tools
*   **/yt** or **/youtube**: Open the **YouTube Tool** (video / audio / thumbnail / subtitles / info).
*   **/c** or **/convert**: Open the **File Converter Mega Edition** (category-based video / audio / image operations).
*   **/w** or **/watermark**: Open the **Image Watermarker** (text or overlay image).
*   **/s** or **/subtitle**: Open the **Subtitle Extractor** (rip subs from MKV/MP4).
*   **/t** or **/trim**: Open the **Video Trimmer** (fast cut without re-encoding).
*   **/v** or **/voice**: Open the **Voice Note Converter** (to Telegram voice-note format).
*   **/vn** or **/videonote**: Open the **Video Note Converter** (to Telegram round-note format).
*   **/mi** or **/mediainfo**: Open **MediaInfo** (detailed stream/codec analyzer).

### Admin-Only
*   **/ytcookies**: Upload a Netscape-format `cookies.txt` to bypass YouTube's anti-bot guard. Admins only — see the [YouTube Tool section](#-youtube-tool-yt) for the full flow.

---

## 🧩 Credits & License

This project is released under the **XTV Public License v3.0** — a "Source Available" license designed to keep the code open while protecting the identity and branding of XTV Network Global.

Key points:
*   **Hosting**: You may run this bot publicly or commercially, as long as the full XTV credits remain visible.
*   **Forks**: Public forks are permitted — rebranding or removing credits is strictly prohibited.
*   **Commercial Code Use**: Embedding this code in your own sold/licensed product requires a separate commercial license — open a [GitHub Issue](https://github.com/davdxpx/xtv-mediastudio/issues) or contact @davdxpx on Telegram.
*   **Patch-Back Obligation**: All modifications (bugfixes, features, improvements) must be submitted as a Pull Request back to this repository.
*   **Attribution**: **You must retain all original author credits in full.** Unauthorized removal of the "Developed by 𝕏0L0™" notice or any XTV branding is strictly prohibited.

---
<div align="center">
  <h3>Developed by 𝕏0L0™</h3>
  <p>
    <b>Don't Remove Credit</b><br>
    Telegram Channel: <a href="https://t.me/XTVbots">@XTVbots</a><br>
    Developed for the <a href="https://t.me/XTVglobal">𝕏TV Network</a><br>
    Backup Channel: <a href="https://t.me/XTVhome">@XTVhome</a><br>
    Contact on Telegram: <a href="https://t.me/davdxpx">@davdxpx</a>
  </p>
  <p>
    <i>© 2026 XTV Network Global. All Rights Reserved.</i>
  </p>
</div>
