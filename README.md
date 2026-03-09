# 𝕏TV Rename Bot 🚀

> **Business-Class Media Management Solution**
> *Developed by [𝕏0L0™](https://t.me/davdxpx) for the [𝕏TV Network](https://t.me/XTVglobal)*

![XTV Banner](https://telegra.ph/file/857e23117462419409849.jpg)

The **XTV Rename Bot** is a high-performance, enterprise-grade Telegram bot engineered for automated media processing. It combines robust FFmpeg metadata injection with intelligent file renaming algorithms, designed specifically for maintaining large-scale media libraries.

## 🌟 Key Features

### 🔹 Advanced Processing Engines
*   **XTV Core™**: Lightning-fast processing for standard files (up to 2GB) using the primary bot API.
*   **XTV Pro™**: Seamless integration with a Userbot session to handle **Large Files (up to 4GB)**, bypassing standard bot limitations (Premium required).

### 🔹 Intelligent Recognition
*   **Auto-Detection Matrix**: Automatically scans filenames to detect Movie/Series titles, Years, Qualities, and Episode numbers with high accuracy.
*   **Smart Metadata Fetching**: Integration with **TMDb** to pull official titles, release years, and artwork.

### 🔹 Media Management
*   **Multiple Dumb Channels (Storage/Forwarding)**: Configure multiple destination channels (globally or per-user). The bot automatically queues files and strictly forwards them in sequential order (e.g., sorting series by Season/Episode and movies by resolution precedence: 2160p > 1080p > 720p > 480p).
*   **Smart Timeout Queue**: Never get stuck waiting for crashed files. The sequential forwarding queue obeys a customizable timeout limit (configurable by the CEO).
*   **Personal Media & Unlisted Content**: Direct menu options to bypass metadata databases (e.g., TMDb) for personal files, camera footage, photos, and unlisted regional content. Smartly preserves original file extensions (like `.jpeg`) and lets you choose your preferred output format.
*   **Series & Movies**: Specialized handling for different media types.
    *   *Series*: Season/Episode numbering (S01E01) format.
    *   *Movies*: Clean Title.Year.Quality format.
*   **Subtitle Workflow**: Dedicated flow for subtitle files (`.srt`, `.ass`), supporting language codes and custom naming.
*   **Dynamic Filename Templates**: Fully customizable filename structures via the Admin Panel for Movies, Series, and Subtitles using variables like `{Title}`, `{Year}`, `{Quality}`, `{Season}`, `{Episode}`, `{Season_Episode}`, `{Language}`, and `{Channel}`.

### 🔹 Professional Metadata Injection
*   **FFmpeg Power**: Injects custom metadata (Title, Author, Artist, Copyright) directly into MKV/MP4 containers. The ultimate Telegram FFmpeg media processing bot.
*   **Branding**: Sets "Encoded by @XTVglobal" and custom audio/subtitle track titles.
*   **Thumbnail Embedding**: Embeds custom or poster-based thumbnails into video files.

### 🔹 Security & Privacy
*   **Anti-Hash Algorithm**: Generates unique, random captions for every file to prevent hash-based tracking or duplicate detection.
*   **Concurrency Control**: Global semaphore system prevents server overload by managing simultaneous downloads/uploads.

### 🔹 Other Features
*   **Admin Panel**: Full control over bot settings, metadata templates, filename templates, and thumbnails via an inline menu.
*   **Custom Thumbnails**: Set a global default thumbnail for all processed files.
*   **Caption Templates**: Customizable templates with variables like `{filename}`, `{size}`, and `{duration}`.
*   **Channel Branding**: Set a global `{Channel}` variable in the Admin Panel (e.g., `@XTVglobal`) to inject into filenames and metadata.
*   **Force Subtitles**: Intelligent logic to set default subtitle tracks.
*   **Album Support**: Handles multiple file uploads (albums) concurrently without issues.
*   **Session State**: Robust user state management allows for cancelling and restarting flows easily.
*   **Broadcast & Logs**: (Planned) Features for mass notifications and logging processed files.

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
| `ADMIN_IDS` | Allowed User IDs (comma separated) (Formerly FRANCHISEE_IDS) | ❌ |
| `PUBLIC_MODE` | Set to `True` to allow anyone to use the bot. | ❌ |
| `TMDB_API_KEY` | TMDb API Key for metadata | ✅ |
| `USER_SESSION` | Pyrogram String Session for Userbot (XTV Pro™) | ❌ |

> **Note:** To generate a `USER_SESSION` string, run `python3 generate_session.py` locally.

## 🌍 Public Mode vs Private Mode

The XTV Rename Bot can operate in two distinct modes via the `PUBLIC_MODE` environment variable. **It is highly recommended to choose a mode initially and stick with it**, as the database structure and bot functionality changes drastically between the two.

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
  * **Rate Limits**: Set a delay (in seconds) between file uploads to prevent spam.
  * **Bot Branding**: Customize the bot name and community name displayed to users.
  * **Support Contact**: Define a contact link for the `/info` command.
* **Commands for BotFather**:
  ```text
  start - Start the bot
  help - How to use the bot
  settings - Customize your personal templates and thumbnail
  info - View bot info and support contact
  admin - Access Global Configurations (CEO Only)
  end - Cancel the current task
  ```

## 🎮 Usage

*   **/start**: Check bot status and ping.
*   **/admin**: Access the **Admin Panel** to configure global settings.
*   **/settings**: Access **Personal Settings** to configure your own templates and thumbnails (Public Mode only).
*   **/info**: View bot details and support info (Public Mode only).
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
    <i>© 2026 XTV Network Global. All Rights Reserved.</i>
  </p>
</div>
