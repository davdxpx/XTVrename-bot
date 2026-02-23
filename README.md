# 𝕏TV Rename Bot 🚀

> **Business-Class Media Management Solution**
> *Developed by [𝕏0L0™](https://t.me/davdxpx) for the [𝕏TV Network](https://t.me/XTVglobal)*

![XTV Banner](https://telegra.ph/file/857e23117462419409849.jpg)

The **XTV Rename Bot** is a high-performance, enterprise-grade Telegram bot engineered for automated media processing. It combines robust FFmpeg metadata injection with intelligent file renaming algorithms, designed specifically for maintaining large-scale media libraries.

## 🌟 Key Features

### 🔹 Advanced Processing Engines
*   **XTV Core™**: Lightning-fast processing for standard files (up to 2GB) using the primary bot API.
*   **XTV Pro™**: Seamless integration with a Userbot session to handle **Large Files (>2GB)**, bypassing standard bot limitations (Premium required).

### 🔹 Intelligent Recognition
*   **Auto-Detection Matrix**: Automatically scans filenames to detect Movie/Series titles, Years, Qualities, and Episode numbers with high accuracy.
*   **Smart Metadata Fetching**: Integration with **TMDb** to pull official titles, release years, and artwork.

### 🔹 Media Management
*   **Series & Movies**: Specialized handling for different media types.
    *   *Series*: Season/Episode numbering (S01E01) format.
    *   *Movies*: Clean Title.Year.Quality format.
*   **Subtitle Workflow**: Dedicated flow for subtitle files (`.srt`, `.ass`), supporting language codes and custom naming.

### 🔹 Professional Metadata Injection
*   **FFmpeg Power**: Injects custom metadata (Title, Author, Artist, Copyright) directly into MKV/MP4 containers.
*   **Branding**: Sets "Encoded by @XTVglobal" and custom audio/subtitle track titles.
*   **Thumbnail Embedding**: Embeds custom or poster-based thumbnails into video files.

### 🔹 Security & Privacy
*   **Anti-Hash Algorithm**: Generates unique, random captions for every file to prevent hash-based tracking or duplicate detection.
*   **Concurrency Control**: Global semaphore system prevents server overload by managing simultaneous downloads/uploads.

## 🛠 Deployment Guide

### 1. Deploy on Railway (Recommended)

This repository is optimized for **Railway** with a custom `Dockerfile`.

1.  **Fork this Repository** to your GitHub account.
2.  **Create a New Project** on [Railway.app](https://railway.app).
3.  **Deploy from GitHub Repo** and select your forked repository.
4.  **Add Variables**: Go to the "Variables" tab and add the configuration (see below).
5.  **Build & Deploy**: Railway will automatically detect the Dockerfile and start the bot.

### 2. Local / VPS (Docker)

```bash
# 1. Clone the repo
git clone https://github.com/davdxpx/XTVrename-bot.git
cd XTVrename-bot

# 2. Build the image
docker build -t xtv-bot .

# 3. Run the container
docker run -d --env-file .env --name xtv-bot xtv-bot
```

## ⚙️ Configuration (.env)

Create a `.env` file in the root directory:

| Variable | Description | Required |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID (my.telegram.org) | ✅ |
| `API_HASH` | Telegram API Hash (my.telegram.org) | ✅ |
| `BOT_TOKEN` | Bot Token from @BotFather | ✅ |
| `MAIN_URI` | MongoDB Connection String | ✅ |
| `CEO_ID` | Your Telegram User ID (Admin) | ✅ |
| `FRANCHISEE_IDS` | Allowed User IDs (comma separated) | ❌ |
| `TMDB_API_KEY` | TMDb API Key for metadata | ✅ |
| `USER_SESSION` | Pyrogram String Session for Userbot (XTV Pro™) | ❌ |

> **Note:** To generate a `USER_SESSION` string, run `python3 generate_session.py` locally.

## 🎮 Usage

*   **/start**: Check bot status and ping.
*   **/admin**: Access the **Admin Panel** to configure thumbnails, templates, and settings.
*   **/end**: Clear current session state (useful to reset auto-detection).

**Workflow:**
1.  **Forward a File**: The bot will Auto-Detect the content.
2.  **Confirm/Edit**: Use the inline menu to correct the Title, Season, Episode, or Quality.
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
    <i>© 2024 XTV Network Global. All Rights Reserved.</i>
  </p>
</div>
