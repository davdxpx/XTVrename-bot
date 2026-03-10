# 🛠 Deployment Guide

This document contains step-by-step instructions for deploying the **𝕏TV Rename Bot** to various cloud platforms.

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
6.  You will be prompted to fill in the **Environment Variables**. Most are standard (`BOT_TOKEN`, `API_ID`, etc. - *see Configuration in README*), but pay special attention to **`PUBLIC_MODE`**:
    *   Type **`True`** if you want the bot open to everyone (Public Mode).
    *   Type **`False`** if you want the bot locked so only you (the CEO) can use it (Private Mode).
7.  Click **Save** and Render will automatically build and start your bot as a Background Worker!

> **Note on Free Tier & RAM:** The blueprint defaults to Render's Free Tier, which requires **no credit card**. However, since this bot uses **FFmpeg** to process large media files, it can consume significant RAM. If your bot crashes or restarts during heavy video processing (like embedding thumbnails into large MKV files), you may need to upgrade your Render plan to give the bot more memory.

### 2. Deploy on Railway

This repository is also optimized for **Railway** with a custom `Dockerfile`, though be aware of potential bandwidth (egress) costs.

1.  **Fork this Repository** to your GitHub account.
2.  **Create a New Project** on [Railway.app](https://railway.app).
3.  **Deploy from GitHub Repo** and select your forked repository.
4.  **Add Variables**: Go to the "Variables" tab and add the configuration (see README).
5.  **Build & Deploy**: Railway will automatically detect the Dockerfile and start the bot.

### 3. Oracle Cloud (The Ultimate Solution for 10TB Free Egress)

If you have been struggling with massive bandwidth (egress) bills on platforms like Railway because of heavy media processing, **Oracle Cloud's Always Free ARM A1 Instance is the ultimate solution.** You get 4 CPU Cores, 24GB of RAM, and **10TB of Free Egress Bandwidth** every month!

*(Note: You do **not** need to install Docker on your personal computer for this. We will be installing everything directly on your new Oracle server.)*

**Step-by-Step Oracle Setup (Beginner Friendly):**

#### Step A: Create Your Free Account and Instance
1. **Sign Up:** Go to [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) and create an account. You will need to provide a credit card for verification, but you won't be charged as long as you stay within the "Always Free" limits.
2. **Create Instance:** Once logged into your dashboard, click **"Create a VM instance"**.
3. **Name & Image:** Give your instance a name (e.g., `XTV-Bot`). Under "Image and shape", click "Edit". Change the Image to **Canonical Ubuntu** (pick the latest LTS version, like 22.04 or 24.04).
4. **Shape (Crucial Step):** Under "Shape", click "Change shape". Select **"Virtual machine"**, then select the **"Ampere"** series. Choose the **VM.Standard.A1.Flex** shape. Max out the sliders to get your full free allowance: **4 OCPUs** and **24GB RAM**. Click "Select shape".
5. **Networking (Primary VNIC):** Under "Networking", click "Edit". Look for **Primary VNIC information** and select **"Create a new virtual cloud network"**. You will then be given options for the subnet; select **"Create a new public subnet"**. Ensure **"Assign a public IPv4 address"** is checked so you can connect to your server.
6. **Storage:** Leave the default boot volume size as it is (it should default to the free 46.6 GB limit).
7. **SSH Keys (Crucial Step):** Under "Add SSH keys", ensure **"Generate a key pair for me"** is selected. Click **"Save private key"** and download the `.key` file to your computer. *Keep this safe! You will need it to connect to your server.*
8. **Create:** Scroll down and click **"Create"**. Wait a few minutes for the instance to provision. Once it's green and says "RUNNING", copy the **"Public IP Address"** shown on the page.

#### Step B: Connect to Your Server (SSH)
**What is SSH?** SSH (Secure Shell) is simply a way to remotely log into your new Oracle server from your own computer's terminal. It gives you a text-based window into your cloud server.

1. **Open your Terminal:**
   - **Mac/Linux:** Open the built-in "Terminal" app.
   - **Windows:** Open "Command Prompt" or "PowerShell".
2. **Find your key:** Locate the private key you downloaded in Step A (it usually has a `.key` extension). For this example, let's pretend it's in your Downloads folder: `C:\Users\YourName\Downloads\ssh-key-2023-10-26.key`.
3. **Connect:** Type the following command in your terminal, replacing the path with the actual path to your key, and the IP with your server's Public IP:
   ```bash
   ssh -i "path/to/your/private_key.key" ubuntu@YOUR_PUBLIC_IP
   ```
   *Example: `ssh -i "C:\Users\YourName\Downloads\ssh-key-2023-10-26.key" ubuntu@123.45.67.89`*
4. **Confirm:** If it asks "Are you sure you want to continue connecting (yes/no)?", type **`yes`** and press Enter. You should now see `ubuntu@instance-name:~$`. You are in!

#### Step C: Install Docker and Run the Bot
Now that you are connected to your Oracle server, you can copy and paste these commands exactly as written.

1. **Update the server and install Docker:**
   Copy the entire block below and paste it into your terminal, then press Enter. It might take a minute to finish.
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install docker.io docker-compose git -y
   sudo systemctl enable --now docker
   sudo usermod -aG docker ubuntu
   ```
2. **Refresh permissions:** Type `exit` to log out of the server, then press Enter. Now, press the "Up" arrow key on your keyboard to bring up your previous `ssh ...` command and press Enter to log back in. (This applies the Docker permissions).
3. **Download the Bot Code:**
   ```bash
   git clone https://github.com/davdxpx/XTVrename-bot.git
   cd XTVrename-bot
   ```
4. **Configure your Settings:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   This opens a simple text editor called `nano`. Use your arrow keys to move around. Fill in your `API_ID`, `API_HASH`, `BOT_TOKEN`, `MAIN_URI` (MongoDB connection string), and `CEO_ID`.
   - To save: Press **Ctrl+O** (the letter O), then press **Enter**.
   - To exit: Press **Ctrl+X**.
5. **Start the Bot!**
   Copy and paste this final command to build and run your bot in the background:
   ```bash
   docker-compose up -d --build
   ```
   *(Note: Our Dockerfile automatically detects the ARM architecture of your free Oracle server and optimizes the build!)*

Your bot is now running 24/7 for free!

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
