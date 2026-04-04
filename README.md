# 𝕏TV MediaStudio™ 🚀

> **Business-Class Media Management Solution**
> *Developed by [𝕏0L0™](https://t.me/davdxpx) for the [𝕏TV Network](https://t.me/XTVglobal)*

<p align="center">
  <img src="./assets/banner.png" alt="𝕏TV MediaStudio™ Banner" width="100%">
</p>

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-Latest-blue.svg?logo=telegram&logoColor=white)](https://docs.pyrogram.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Included-green.svg?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-XTV_Public_v2.0-red.svg)](https://github.com/davdxpx/XTV-MediaStudio/blob/main/LICENSE)

The **𝕏TV MediaStudio™** is a high-performance, enterprise-grade **Telegram Bot** engineered for automated media processing, file renaming, and video metadata editing. It combines robust **FFmpeg** metadata injection with intelligent file renaming algorithms, designed specifically for maintaining large-scale media libraries on Telegram. Whether you need an **automated media manager**, a **TMDb movie scraper**, or a **video metadata editor**, 𝕏TV MediaStudio™ is the ultimate **media management solution**.

## 🌟 Key Features

### 🔹 Advanced Processing Engines
*   **𝕏TV Core™**: Lightning-fast processing for standard files (up to 2GB) using the primary bot API.
*   **𝕏TV Pro™: Ephemeral Tunnels**: Seamless integration with a Premium Userbot session to handle **Large Files (>2GB up to 4GB)**. The system generates secure, temporary private tunnels for every single large file transfer, bypassing API limits, cache crashing, and `PEER_ID_INVALID` errors.

### 🔹 Intelligent Recognition
*   **Workflow Modes (Starter Setup)**: The bot greets users with an interactive, beautifully-formatted **Starter Setup Menu** when they join your Force-Sub channel or press `/start`. Users can pick their primary mode of operation, which can be changed anytime via settings:
    *   **🧠 Smart Media Mode**: Best for TV Shows & Movies. Automatically triggers the Auto-Detection Matrix and fetches TMDb metadata/posters natively.
    *   **⚡ Quick Rename Mode**: Best for Personal Videos, Anime, or generic files. Instantly bypasses all auto-detection logic and brings the user straight to the General Mode renaming prompt for rapid processing.
*   **Seamless Chat Cleanup**: The bot aggressively keeps the chat history pristine during the renaming process. It natively utilizes Telegram's `ForceReply` functionality to ask for new filenames, ensuring absolute accuracy even with multiple files in the queue. As soon as a user provides the new filename, the bot **auto-deletes** both its own prompt and the user's reply, keeping the interface uncluttered.
*   **Auto-Detection Matrix**: Automatically scans filenames to detect Movie/Series titles, Years, Qualities, and Episode numbers with high accuracy.
*   **Smart Metadata Fetching**: Integration with **TMDb** to pull official titles, release years, and artwork. Now supports **Multilingual Metadata** (e.g. `de-DE`, `es-ES`), customizable per user in `/settings`!
*   **Automatic Archive Unpacking**: Automatically detects and downloads `.zip`, `.rar`, and `.7z` archives. It smartly identifies password-protected archives, prompts the user for the password, extracts the contents, and automatically feeds all valid media files directly into the batch processing queue!

### 🔹 Media Management & Workflows
*   **Multiple Dumb Channels & Sequential Batch Forwarding**: Configure multiple independent destination channels (globally or per-user). The bot automatically queues seasons or movie collections in bulk and strictly forwards them in sequential order (e.g., sorting series by Season/Episode and movies by resolution precedence: 2160p > 1080p > 720p > 480p).
*   **Smart Debounce Queue Manager**: Automatically sorts batched media uploads logically. Instead of simple alphabetical sorting, series are ordered by SxxExx and movies by quality precedence, preventing out-of-order uploads to your channels.
*   **Smart Timeout Queue**: Never get stuck waiting for crashed files. The sequential forwarding queue obeys a customizable timeout limit (configurable by the CEO).
*   **Spam-Proof Forwarding**: Utilizing Pyrogram's `copy()` method, the bot cleanly removes 'Forwarded from' tags when sending to Dumb Channels, preventing Telegram's spam detection from flagging bulk media (which can result in 0KB files and stripped thumbnails).
*   **Personal Media & Unlisted Content**: Direct menu options to bypass metadata databases (e.g., TMDb) for personal files, camera footage, photos, and unlisted regional content. Smartly preserves original file extensions (like `.jpeg`) and lets you choose your preferred output format.
*   **Multipurpose File Utilities**: Built-in direct editing tools accessible via the **✨ Other Features** menu or shortcuts for general renaming (`/g`), audio metadata & cover art editing (`/a`), advanced media format conversion (including **x264/x265** and **Audio Normalization**) (`/c`), automated image watermarking (`/w`), and a standalone **Subtitle Extractor**!
*   **Auto-Delete (Clean Chat)**: Automatically deletes the original unoptimized uploaded file after successful processing and delivery, keeping your Telegram chat clean and organized.
*   **Series & Movies**: Specialized handling for different media types.
    *   *Series*: Season/Episode numbering (S01E01) format.
    *   *Movies*: Clean Title.Year.Quality format.
*   **Subtitle Workflow**: Dedicated flow for subtitle files (`.srt`, `.ass`), supporting language codes and custom naming.
*   **Dynamic Filename Templates**: Fully customizable filename structures via the Admin Panel for Movies, Series, and Subtitles using variables like `{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, `{Season_Episode}`, `{Language}`, and `{Channel}`. The template is the absolute source of truth for spacing and formatting.

### 🔹 Professional Metadata Injection
*   **FFmpeg Power**: Injects custom metadata (Title, Author, Artist, Copyright) directly into MKV/MP4 containers. The ultimate Telegram FFmpeg media processing bot.
*   **Branding**: Sets "Encoded by @XTVglobal" and custom audio/subtitle track titles.
*   **Thumbnail Embedding**: Embeds custom or poster-based thumbnails into video files.

### 🔹 Security & Privacy
*   **Anti-Hash Algorithm**: Generates unique, random captions for every file to prevent hash-based tracking or duplicate detection.
*   **Concurrency Control**: Global semaphore system prevents server overload by managing simultaneous downloads/uploads.
*   **Smart Force-Sub Setup**: Automatically detects when the bot is promoted to an Administrator in a channel, verifies permissions, and dynamically generates and saves an invite link for seamless Force-Sub configuration.

### 🔹 Other Features
*   **Admin Panel**: Full control over bot settings, metadata templates, filename templates, and thumbnails via an inline menu.
*   **Custom Thumbnails**: Set a global default thumbnail for all processed files.
*   **Caption Templates**: Customizable templates with variables like `{filename}`, `{size}`, and `{duration}`.
*   **Channel Branding**: Set a global `{Channel}` variable in the Admin Panel (e.g., `@XTVglobal`) to inject into filenames and metadata.
*   **Force Subtitles**: Intelligent logic to set default subtitle tracks.
*   **Album Support**: Handles multiple file uploads (albums) concurrently without issues.
*   **Session State**: Robust user state management allows for cancelling and restarting flows easily.
*   **Broadcast & Logs**: Features for mass notifications and logging processed files.
*   **Admin Feature Toggles (Resource Management)**: As the bot processes extremely heavy tasks like **Video Conversion**, **Subtitle Extraction**, and **Image Watermarking**, it can easily overwhelm standard VPS servers (high CPU & RAM usage). To protect your server and Telegram Premium tunnel account from spam or rate limits.

## 🛠 Deployment Guide

We have created comprehensive, beginner-friendly, step-by-step guides for deploying the 𝕏TV MediaStudio™ across multiple platforms.

### 👉 [Click Here for the Full Deployment Guide](DEPLOYMENT.md) 👈

---

## ⚙️ Configuration (.env)

Create a `.env` file in the root directory. You will need a **MongoDB** instance and **Pyrogram** session (optional for 4GB files).

| Variable | Description | Required |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID (my.telegram.org) | ✅ |
| `API_HASH` | Telegram API Hash (my.telegram.org) | ✅ |
| `BOT_TOKEN` | Bot Token from @BotFather | ✅ |
| `MAIN_URI` | MongoDB Connection String | ✅ |
| `CEO_ID` | Your Telegram User ID (Admin) | ✅ |
| `ADMIN_IDS` | Allowed User IDs (comma separated) | ❌ |
| `PUBLIC_MODE` | Set to `True` to allow anyone to use the bot. | ❌ |
| `DEBUG_MODE` | Enable verbose debug logging. Default: False. | ❌ |
| `TMDB_API_KEY` | TMDb API Key for metadata | ✅ |

## 🚀 𝕏TV Pro™ Setup (4GB File Support)

To bypass Telegram's standard 2GB bot upload limit, the **𝕏TV MediaStudio™** features a built-in **𝕏TV Pro™** mode. This mode uses a Premium Telegram account (Userbot) to act as a seamless tunnel for processing and delivering files up to 4GB.

**How to Setup:**
1. Send `/admin` to your bot.
2. Click the **"🚀 Setup 𝕏TV Pro™"** button.
3. Follow the completely interactive, fast, and fail-safe setup guide. You will be asked to provide your **API ID**, **API Hash**, and **Phone Number**.
4. The bot will request a login code from Telegram. *(Enter the code with spaces, e.g., `1 2 3 4 5`, to avoid Telegram's security triggers).*
5. If 2FA is enabled, enter your password.
6. The bot will verify that the account has **Telegram Premium**. If successful, it securely saves the session credentials to the MongoDB database and hot-starts the Userbot instantly—**no restart required**.

> **Privacy & Ephemeral Tunneling (Market First!):** When processing a file > 2GB, the Premium Userbot creates a temporary, private "Ephemeral Tunnel" channel specific to that file. It uploads the transcoded file to this tunnel, and the Main Bot seamlessly copies the file from the tunnel directly to the user. After the transfer, the Userbot instantly deletes the temporary channel. This entirely bypasses standard bot API limitations, completely hides the Userbot's identity, prevents `PEER_ID_INVALID` caching errors, and removes any "Forwarded from" tags for a flawless delivery!

## 🌍 Public Mode vs Private Mode

The 𝕏TV MediaStudio™ can operate in two distinct modes via the `PUBLIC_MODE` environment variable. **It is highly recommended to choose a mode initially and stick with it**, as the database structure and bot functionality changes drastically between the two.

### 🔒 Private Mode (`PUBLIC_MODE=False` - Default)
* **Access**: Only the `CEO_ID` and `ADMIN_IDS` can use the bot.
* **Settings**: Global. The `/admin` command configures one global thumbnail, one set of filename templates, and one caption template for all files processed.
* **Commands for BotFather**:
  ```text
  start - Start the bot
  help - How to use the bot
  admin - Access the Admin Panel (Global Settings)
  end - Cancel the current task
  ```

### 🔓 Public Mode (`PUBLIC_MODE=True`)
* **Access**: Anyone can use the bot!
* **User-Specific Settings**: Every user gets their own profile. Users can use the `/settings` command to set their own custom thumbnails, filename templates, and metadata templates without affecting others.
* **CEO Controls**: The `/admin` command transforms into a global configuration panel for the CEO. The CEO can set:
  * **Force-Sub Channel**: Require users to join a specific channel before using the bot.
  * **Daily Quotas**: Configure maximum daily egress (MB) and daily file limits per user to prevent abuse.
  * **Premium System & Trials**: Set up a Premium tier with independent limits or complete unlimited access. Allow users to claim a custom configurable Trial period via the `/premium` command.
  * **User Management Dashboard**: A dedicated panel for the CEO to view all users, search by ID or username, inspect detailed profiles (showing active/banned status, usage stats, and join dates), and manually grant or revoke Premium access.
  * **Usage Dashboard**: Track live bot activity, monitor top users, block/unblock accounts, and view the last 7 days of global egress usage.
  * **Bot Branding**: Customize the bot name and community name displayed to users.
  * **Support Contact**: Define a contact link for the `/info` command.
* **Commands for BotFather**:
  ```text
  start - Start the bot
  help - How to use the bot
  settings - Customize your personal templates and thumbnail
  info - View bot info and support contact
  usage - Track your daily limits
  admin - Access Global Configurations (CEO Only)
  end - Cancel the current task
  ```

## 🎮 Usage

*   **/start**: Check bot status and ping.
*   **/admin**: Access the **Admin Panel** to configure global settings.
*   **/settings**: Access **Personal Settings** to configure your own templates and thumbnails (Public Mode only).
*   **/info**: View bot details and support info (Public Mode only).
*   **/usage**: View your daily limits and personal usage (Public Mode only).
*   **/end**: Clear current session state (useful to reset auto-detection).

**Shortcut Commands:**
*   **/r** or **/rename**: Open the classic manual rename menu directly.
*   **/p** or **/personal**: Open Personal Files mode directly.
*   **/g** or **/general**: Open General Mode (Rename any file, bypass TMDb lookup).
*   **/a** or **/audio**: Open Audio Metadata Editor (Edit MP3/FLAC title, artist, cover art).
*   **/c** or **/convert**: Open File Converter (Extract audio, image to webp, video to gif, etc).
*   **/w** or **/watermark**: Open Image Watermarker (Add text or overlay image).

**Workflow:**
1.  **Forward a File**: The bot will Auto-Detect the content.
2.  **Confirm/Edit**: Use the inline menu to correct the Title, Season, Episode, or Quality. The bot now natively auto-detects Season and Episode numbers from filenames even during manual renaming!
3.  **Process**: The bot downloads, injects metadata, renames, and re-uploads the file.

## 🧩 Credits & License

This project is open-source under the **XTV Public License**.
*   **Modifications**: You may fork and modify for personal use.
*   **Attribution**: **You must retain the original author credits.** Unauthorized removal of the "Developed by 𝕏0L0™" notice is strictly prohibited.

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
