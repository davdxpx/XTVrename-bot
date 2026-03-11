# 🛠 Deployment Guide

Welcome to the **𝕏TV Rename Bot** deployment documentation! This guide provides standardized, beginner-friendly instructions for hosting your bot on various platforms.

Because this bot downloads media, processes it with **FFmpeg**, and uploads it back to Telegram, it consumes significant **RAM** and **Bandwidth (Egress)**. Keep this in mind when choosing a provider!

---

## ⚡ 1-Click Cloud Deployments (PaaS)

Platform-as-a-Service (PaaS) providers are the easiest way to deploy. They build and run the code directly from your GitHub repository.

### 1. Render (Highly Recommended - Zero Egress Costs)
Render is our top recommendation because it provides **generous unmetered bandwidth**, saving you from unexpected egress bills when processing large video files.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. **Fork** this repository to your GitHub account.
2. Click the **Deploy to Render** button above.
3. Connect your GitHub account and select your forked repository.
4. Render will detect the `render.yaml` file automatically.
5. Fill in the required **Environment Variables** (like `BOT_TOKEN`, `API_ID`, etc.). Pay special attention to `PUBLIC_MODE` (`True` for public access, `False` for private).
6. Click **Apply/Save**. Your bot will build and start as a Background Worker!
*Note: If processing massive files causes out-of-memory crashes, consider upgrading from the Free Tier to give the bot more RAM.*

### 2. Railway
Railway offers lightning-fast deployments and great performance, though be mindful of your monthly egress bandwidth usage.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

1. **Fork** this repository.
2. Click the **Deploy on Railway** button above.
3. Select your GitHub repository.
4. Go to the **Variables** tab in your new Railway project.
5. Add your required configuration (e.g., `BOT_TOKEN`, `API_ID`, `MAIN_URI`, `CEO_ID`).
6. Railway will automatically detect the `Dockerfile`, build the image, and start your bot!

### 3. Koyeb
Koyeb provides high-performance global infrastructure with a generous free tier for compute, though bandwidth is limited.

[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy)

1. **Fork** this repository.
2. Create a [Koyeb account](https://app.koyeb.com/) and click **Create Service**.
3. Choose **GitHub** as the deployment method and select your repository.
4. Set the **Builder** to Docker.
5. Scroll down to **Environment variables** and add your `.env` values (`BOT_TOKEN`, `API_ID`, etc.).
6. Click **Deploy**. Koyeb will provision your bot in seconds.

### 4. Zeabur
Zeabur is an incredibly simple PaaS that makes deploying bots effortless.

[![Deploy on Zeabur](https://zeabur.com/button.svg)](https://dash.zeabur.com/templates/github)

1. **Fork** this repository.
2. Log in to the [Zeabur Dashboard](https://dash.zeabur.com) and create a new **Project**.
3. Click **Add Service** -> **Git** and select your repository.
4. Zeabur will automatically recognize the Dockerfile.
5. Go to the **Variables** tab for the service and add your environment variables.
6. The bot will deploy automatically!

---

## 🖥️ VPS & Dedicated Server Deployments

If you need maximum control, massive storage, and the cheapest bandwidth, deploying on a Virtual Private Server (VPS) via SSH is the best route.

### 1. Oracle Cloud (Always Free ARM)
Oracle Cloud is the ultimate choice for heavy users. The "Always Free" Ampere A1 instance gives you 4 CPU Cores, 24GB of RAM, and **10TB of Free Egress Bandwidth** every month!

1. Go to [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) and create an instance.
2. Choose the **Canonical Ubuntu** image.
3. For the Shape, select **Virtual machine -> Ampere -> VM.Standard.A1.Flex** (max out at 4 OCPUs and 24GB RAM).
4. Save the generated SSH Key and connect to your server via your terminal:
   ```bash
   ssh -i "path/to/key.key" ubuntu@YOUR_PUBLIC_IP
   ```
5. Follow the **Standard Docker Deployment** steps below to run the bot. Our Dockerfile automatically detects and optimizes for the ARM architecture!

### 2. Hetzner Cloud (The Ultimate Budget VPS - 20TB Traffic)
If you need high performance but don't want to rely on the Oracle Free Tier, **Hetzner Cloud** is widely considered the best budget option in the industry. For around €4 a month, you get a dedicated IPv4 and a massive **20TB of Traffic (Bandwidth)** per month included!

1. Create an account on [Hetzner Cloud](https://www.hetzner.com/cloud/).
2. Create a new Project, then click **Add Server**.
3. Choose your Location. Under **Image**, select **Ubuntu 24.04** (or latest LTS).
4. Under **Type**, choose either **Shared vCPU -> x86 (CX series)** or **Shared vCPU -> Arm64 (CAX series)**. The cheapest CAX11 or CX22 is more than powerful enough.
5. Add an SSH Key (or use a root password), name your server, and click **Create & Buy now**.
6. Once running, connect via SSH:
   ```bash
   ssh root@YOUR_SERVER_IP
   ```
7. Follow the **Standard Docker Deployment** steps below. (If you chose an Arm64 CAX server, our Dockerfile will automatically optimize for it!).

### 3. Standard VPS (DigitalOcean, AWS EC2, etc.)
Whether you are using a $5 DigitalOcean Droplet, an AWS EC2 instance, or any other Linux VPS provider, the standard Docker deployment method is identical.

1. **Connect** to your server via SSH: `ssh root@YOUR_SERVER_IP`
2. **Install Docker** (if not already installed):
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install docker.io docker-compose git -y
   sudo systemctl enable --now docker
   ```
3. **Download the Bot:**
   ```bash
   git clone https://github.com/davdxpx/XTVrename-bot.git
   cd XTVrename-bot
   ```
4. **Configure Settings:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Fill in your variables (press `Ctrl+O` to save, `Enter`, then `Ctrl+X` to exit).*
5. **Run the Bot in the Background:**
   ```bash
   docker-compose up -d --build
   ```

*(Your bot is now running 24/7! You can view logs at any time using `docker-compose logs -f`)*