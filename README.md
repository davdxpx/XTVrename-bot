# 𝕏TV Rename Bot 🚀

> **Business-Class Media Management Solution**
> *Developed by [𝕏0L0™](https://t.me/davdxpx) for the [𝕏TV Network](https://t.me/XTVglobal)*

![XTV Banner](https://telegra.ph/file/857e23117462419409849.jpg)

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-Latest-blue.svg?logo=telegram&logoColor=white)](https://docs.pyrogram.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Included-green.svg?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-XTV_Public_v2.0-red.svg)](https://github.com/davdxpx/XTVrename-bot/blob/main/LICENSE)

The **XTV Rename Bot** is a high-performance, enterprise-grade **Telegram Bot** engineered for automated media processing, file renaming, and video metadata editing. It combines robust **FFmpeg** metadata injection with intelligent file renaming algorithms, designed specifically for maintaining large-scale media libraries on Telegram. Whether you need an **auto renamer bot**, a **TMDb movie scraper**, or a **video metadata editor**, XTV Rename Bot is the ultimate **media management solution**.

## 🌟 Key Features

### 🔹 Advanced Processing Engines
*   **XTV Core™**: Lightning-fast processing for standard files (up to 2GB) using the primary bot API.
*   **XTV Pro™**: Seamless integration with a Userbot session to handle **Large Files (up to 4GB)**, bypassing standard bot limitations (Premium required). The perfect **4GB Telegram bot** solution.

### 🔹 Intelligent Recognition
*   **Auto-Detection Matrix**: Automatically scans filenames to detect Movie/Series titles, Years, Qualities, and Episode numbers with high accuracy.
*   **Smart Metadata Fetching**: Integration with **TMDb** to pull official titles, release years, and artwork.

### 🔹 Media Management
*   **Multiple Dumb Channels (Storage/Forwarding)**: Configure multiple destination channels (globally or per-user). The bot automatically queues files and strictly forwards them in sequential order (e.g., sorting series by Season/Episode and movies by resolution precedence: 2160p > 1080p > 720p > 480p).
*   **Smart Debounce Queue Manager**: Automatically sorts batched media uploads logically. Instead of simple alphabetical sorting, series are ordered by SxxExx and movies by quality precedence, preventing out-of-order uploads to your channels.
*   **Smart Timeout Queue**: Never get stuck waiting for crashed files. The sequential forwarding queue obeys a customizable timeout limit (configurable by the CEO).
*   **Spam-Proof Forwarding**: Utilizing Pyrogram's `copy()` method, the bot cleanly removes 'Forwarded from' tags when sending to Dumb Channels, preventing Telegram's spam detection from flagging bulk media (which can result in 0KB files and stripped thumbnails).
*   **Personal Media & Unlisted Content**: Direct menu options to bypass metadata databases (e.g., TMDb) for personal files, camera footage, photos, and unlisted regional content. Smartly preserves original file extensions (like `.jpeg`) and lets you choose your preferred output format.
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
*   **Broadcast & Logs**: (Planned) Features for mass notifications and logging processed files.

## 🛠 Deployment Guide

### 1. Deploy on Render.com (Highly Recommended - Zero Egress Costs)

**Why Render?** Telegram bots that process media use significant bandwidth downloading and uploading files. Platforms like Railway charge high fees for bandwidth (egress). Render provides **generous unmetered bandwidth**, saving you from unexpected bills!

This repository includes a `render.yaml` blueprint for a seamless, 1-click deployment.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

**Beginner-Friendly Setup Guide:**
1.  **Fork this Repository** to your GitHub account.
2.  Sign up or log in to [Render.com](https://render.com).
3.  Click **New +** and select **Blueprint**.
4.  Connect your GitHub account and select your forked `XTVrename-bot` repository.
5.  Render will automatically detect the `render.yaml` file. Click **Apply**.
6.  You will be prompted to fill in the **Environment Variables**. Most are standard (`BOT_TOKEN`, `API_ID`, etc. - *see Configuration below*), but pay special attention to **`PUBLIC_MODE`**:
    *   Type **`True`** if you want the bot open to everyone (Public Mode).
    *   Type **`False`** if you want the bot locked so only you (the CEO) can use it (Private Mode).
7.  Click **Save** and Render will automatically build and start your bot as a Background Worker!

> **Note on Free Tier & RAM:** The blueprint defaults to Render's Free Tier, which requires **no credit card**. However, since this bot uses **FFmpeg** to process large media files, it can consume significant RAM. If your bot crashes or restarts during heavy video processing (like embedding thumbnails into large MKV files), you may need to upgrade your Render plan to give the bot more memory.

### 2. Deploy on Railway

This repository is also optimized for **Railway** with a custom `Dockerfile`, though be aware of potential bandwidth (egress) costs.

1.  **Fork this Repository** to your GitHub account.
2.  **Create a New Project** on [Railway.app](https://railway.app).
3.  **Deploy from GitHub Repo** and select your forked repository.
4.  **Add Variables**: Go to the "Variables" tab and add the configuration (see below).
5.  **Build & Deploy**: Railway will automatically detect the Dockerfile and start the bot.

### 3. Oracle Cloud (The Ultimate Solution for 10TB Free Egress)

If you have been struggling with massive bandwidth (egress) bills on platforms like Railway because of heavy media processing, **Oracle Cloud's Always Free ARM A1 Instance is the ultimate solution.** You get 4 CPU Cores, 24GB of RAM, and **10TB of Free Egress Bandwidth** every month!

**Step-by-Step Oracle Setup:**
1. **Create Instance:** Go to the Oracle Cloud console, create a new compute instance, and select **Canonical Ubuntu**. Change the shape to **Ampere VM.Standard.A1.Flex** (ARM), and max out the sliders (4 OCPUs, 24GB RAM). Assign a Public IPv4 address.
2. **Connect via SSH:** `ssh -i /path/to/key ubuntu@YOUR_SERVER_IP`
3. **Install Docker & Docker Compose:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install docker.io docker-compose -y
   sudo systemctl enable --now docker
   sudo usermod -aG docker ubuntu
   # (Log out and back in for the group to apply)
   ```
4. **Deploy the Bot:**
   ```bash
   # Clone the repo
   git clone https://github.com/davdxpx/XTVrename-bot.git
   cd XTVrename-bot

   # Configure Environment
   cp .env.example .env
   nano .env # Fill in your API_ID, BOT_TOKEN, etc.

   # Build & Run in the background
   docker-compose up -d --build
   ```
   *(Note: Our Dockerfile automatically detects the ARM architecture and optimizes the build!)*

### 4. Local / VPS (Standard Docker)

If you prefer using standard Docker commands instead of Docker Compose:

```bash
# 1. Clone the repo
git clone https://github.com/davdxpx/XTVrename-bot.git
cd XTVrename-bot

# 2. Configure Environment
cp .env.example .env
nano .env # Add your tokens here

# 3. Build the image
docker build -t xtv-bot .

# 4. Run the container
docker run -d --env-file .env --name xtv-bot xtv-bot
```

## ⚙️ Configuration (.env)

Create a `.env` file in the root directory. You will need a **MongoDB** instance and **Pyrogram** session (optional for 4GB files).

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

## 🚀 𝕏TV Pro™ Setup (4GB File Support)

To bypass Telegram's standard 2GB bot upload limit, the **𝕏TV Rename Bot** features a built-in **𝕏TV Pro™** mode. This mode uses a Premium Telegram account (Userbot) to act as a seamless tunnel for processing and delivering files up to 4GB.

**How to Setup:**
1. Send `/admin` to your bot.
2. Click the **"🚀 Manage 𝕏TV Pro™"** button.
3. Follow the interactive setup guide. You will be asked to provide your **API ID**, **API Hash**, and **Phone Number**.
4. The bot will request a login code from Telegram. *(Enter the code with spaces, e.g., `1 2 3 4 5`, to avoid Telegram's security triggers).*
5. If 2FA is enabled, enter your password.
6. The bot will verify that the account has **Telegram Premium**. If successful, it securely saves the session credentials to the MongoDB database and hot-starts the Userbot instantly—**no restart required**.

> **Privacy & Ephemeral Tunneling:** When processing a file > 2GB, the Premium Userbot creates a temporary, private "Ephemeral Tunnel" channel specific to that file. It uploads the transcoded file to this tunnel, and the Main Bot seamlessly copies the file from the tunnel directly to the user. After the transfer, the Userbot instantly deletes the temporary channel. This entirely bypasses standard bot API limitations, completely hides the Userbot's identity, prevents `PEER_ID_INVALID` caching errors, and removes any "Forwarded from" tags for a flawless delivery!

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
