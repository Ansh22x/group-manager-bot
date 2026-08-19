# Giyu-Bot Deployment Guide

This guide provides step-by-step instructions to deploy Giyu-Bot using **Supabase** (database) and **Render** (backend host) via **Docker**. 

By deploying with the included **`Dockerfile`**, the deployment is fully automated: Render automatically installs FFmpeg (required for sticker video conversions), builds the environment, and runs the application without requiring any manual build or start commands!

---

## 📋 Prerequisites
Before starting, ensure you have:
1. **Telegram Bot Token**: Created via [@BotFather](https://t.me/BotFather) on Telegram.
2. **Owner User ID**: Your personal Telegram numeric ID (get it from [@userinfobot](https://t.me/userinfobot)).
3. **Mistral AI API Key**: Created from the [Mistral AI Console](https://console.mistral.ai/).

---

## 🗄️ Step 1: Database Setup (Supabase)

1. **Create Project**:
   - Log in to [Supabase](https://supabase.com/).
   - Click **New Project**, choose your organization, set a project name, and create a strong Database Password.
   - Choose a hosting region close to your target audience.

2. **Bootstrap Database Schema**:
   - Once your project is provisioned, go to the left sidebar and click **SQL Editor**.
   - Click **New Query**.
   - Open [`database/schema.sql`](file:///c:/Desktop/Stand-Up/Projects/TG-Group-Manage-bot/group-manager-bot/database/schema.sql) from the repository, copy its entire contents, and paste them into the SQL editor.
   - Click **Run** at the bottom right.
   - This single script will automatically:
     - Enable the `vector` (pgvector RAG) and `pgcrypto` (data-at-rest encryption) extensions.
     - Create all 13 required database tables, indices, and RLS policies.
     - Seed default group shop items.

3. **Retrieve Database Connection URI**:
   - Go to **Project Settings** (gear icon) -> **Database**.
   - Scroll down to the **Connection String** section and select the **URI** tab.
   - Copy the connection string.
   - **Crucial Changes**:
     - Change the port from `5432` to **`6543`** (this routes queries through Supabase's transaction pooler, which prevents connection exhaustion).
     - Append **`?sslmode=require`** to the end of the string.
     - Replace `[YOUR-PASSWORD]` with the actual database password you created.
   - Your final connection URL should look like this:
     ```text
     postgresql://postgres.[your-project-ref]:[your-password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require
     ```
   - **Where to apply this modified URL**:
     1. **Production Hosting**: On the **Render Dashboard** under the **Environment** tab (as the value for the `DATABASE_URL` environment variable).
     2. **Local Development**: In the `.env` file at the root directory of Giyu-Bot (`DATABASE_URL=postgresql://...`).

---

## 🚀 Step 2: Backend Deployment (Render via Docker)

Because the project includes a `Dockerfile` at the root, Render will build the environment automatically.

1. Log in to [Render](https://render.com/).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository fork (`Giyu-Bot`).
4. Configure the service settings:
   - **Name**: `giyu-bot`
   - **Environment**: **`Docker`** (Render detects the `Dockerfile` automatically; leave all build/start commands blank!)
   - **Branch**: `main`
   - **Instance Type**: `Free` (or paid)
5. Scroll down to **Environment Variables** (see Step 3 below).
6. Click **Deploy Web Service**.

---

## ⚙️ Step 3: Configure Environment Variables

In your Render Web Service dashboard under the **Environment** tab, add the following 4 environment keys:

| Key | Example Value | Description |
|-----|---------------|-------------|
| `BOT_TOKEN` | `123456789:ABCdef...` | Obtained from @BotFather. |
| `OWNER_ID` | `987654321` | Your personal Telegram user ID. |
| `DATABASE_URL` | `postgresql://...:6543/...?sslmode=require` | The modified Supabase Connection URI. |
| `MISTRAL_API_KEY` | `your_mistral_api_key` | Obtained from Mistral AI console. |

Click **Save Changes** to trigger a rebuild and deploy the live bot.

---

## ⚡ Step 3.5: Configure Automatic GitHub Commit Redeployments (Optional)

By default, Render might not trigger automatic deploys when commits are pushed by background GitHub Action bots. To enforce automatic redeployment whenever code is updated:

1. **Retrieve Render Deploy Hook**:
   - Go to your **Render Web Service Dashboard**.
   - Navigate to the **Settings** tab.
   - Scroll down to the **Deploy Hook** section and copy the unique URL.
2. **Add GitHub Repository Secret**:
   - Open your fork repository page on GitHub.
   - Click **Settings** -> **Secrets and variables** (on the left sidebar) -> **Actions**.
   - Click **New repository secret**.
   - Name: **`RENDER_DEPLOY_HOOK_URL`**
   - Value: Paste the Deploy Hook URL you copied from Render.
   - Click **Add secret**.
3. **Execution**: The `.github/workflows/deploy-render.yml` action will now automatically ping Render to trigger a rebuilding redeployment on every commit pushed to `main`.

---

## 🌊 Step 4: Web Status Panel & Keeping the Bot Alive

Render's Free Tier web services automatically spin down (go to sleep) if they do not receive HTTP requests for **15 minutes**. 

Giyu-Bot comes pre-configured with a **Flask Keep-Alive web dashboard** running on port `10000` (handled automatically by Render binding). When visited, it displays Giyu's Water Breathing health monitor.

To prevent the bot from sleeping:
1. Copy the public **Web Service URL** generated by Render (e.g. `https://giyu-bot.onrender.com`).
2. Create a free account on an uptime monitoring service like [UptimeRobot](https://uptimerobot.com/) or [Better Stack Uptime](https://betterstack.com/uptime).
3. Create a new **HTTPS Monitor**:
   - **URL**: `https://[your-service-name].onrender.com/health` (The JSON health check endpoint)
   - **Monitoring Interval**: Every **5 minutes** (or 10 minutes)
4. Save the monitor. This will ping Giyu-Bot regularly, keeping the backend active 24/7!
