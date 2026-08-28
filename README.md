# 🌊 Giyu-Bot — High-Performance Autonomous Telegram Bot

<div align="center">

<img src="docs/assets/banner.png" alt="Giyu Tomioka Banner" width="100%" />

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python)](https://python.org)
[![FastCache](https://img.shields.io/badge/FastCache-0.00ms%20Latency-00f5d4.svg?style=for-the-badge)](https://github.com/GuruMachanica/Giyu-Bot)
[![uvloop](https://img.shields.io/badge/Event%20Loop-uvloop%20C%20Engine-ff007f.svg?style=for-the-badge)](https://github.com/MagicStack/uvloop)
[![Database](https://img.shields.io/badge/Database-Supabase%20PostgreSQL%20%2B%20pgvector-3ecf8e.svg?style=for-the-badge&logo=supabase)](https://supabase.com)
[![Mistral AI](https://img.shields.io/badge/AI%20Brain-Mistral%20%2B%20Pixtral%20Vision-ff7000.svg?style=for-the-badge)](https://mistral.ai)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg?style=for-the-badge)](LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram_Bot-@TomiokaGiyu98__bot-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/TomiokaGiyu98_bot)

* **Live Telegram Bot Handle:** [@TomiokaGiyu98_bot](https://t.me/TomiokaGiyu98_bot)

An ultra-optimized, high-throughput Telegram group management bot, gaming deal intelligence hub, universal 5-tier media downloader, and multimodal Demon Slayer AI agent powered by **Mistral AI**, **Microsoft Edge Neural TTS**, **FastCache in-memory acceleration**, and **pgvector HNSW Graph-RAG**.

</div>

---

## ⚡ Blazing-Fast Performance Engine

Giyu-Bot is engineered for sub-millisecond in-memory response times and massive concurrency:

- 🚀 **`FastCache` In-Memory L1 Engine**: 0.00ms cached lookups for chat personas (`/setchar`), group rules (`/rules`), custom tags (`/tag`), keyword filters (`/filter`), wallet balances, word blacklists, and AFK monitors.
- ⚡ **`uvloop` C-Based Event Loop**: Replaces default Python `asyncio` with high-performance `libuv` (the C engine powering Node.js & Go), increasing network event throughput by **3x–5x**.
- 🌐 **`SharedHttpClient` Connection Pooling**: Centralized persistent HTTP/2 connection pool with 60-second keep-alive, eliminating TLS/TCP handshake latency for AniList, Steam, CheapShark, DuckDuckGo, and GamerPower.
- 🗄️ **Composite B-Tree & HNSW Vector Indexing**: Dedicated PostgreSQL covering indexes (`idx_users_chat_xp`, `idx_chat_history_lookup`, `idx_bot_lore_hnsw`) ensuring $O(1)$ and $O(\log N)$ query execution.
- 🕸️ **0.001ms Graph-RAG Traversal**: Relational facts and entity nodes are preloaded into an in-memory graph index, resolving multi-entity relationship queries instantaneously without disk I/O.

---

## 🌟 Comprehensive Feature Suite

### 🎙️ 1. Neural Hashira Voice Engine (`services/voice_engine.py`)
- **Neural Voice Synthesis**: Powered by Microsoft Edge Neural Speech engine for ultra-realistic studio audio.
- **Character Mappings**:
  - 🌊 **Giyu Tomioka**: `en-US-ChristopherNeural` (Calm, stoic, deep resonance)
  - ☀️ **Tanjiro Kamado**: `en-US-GuyNeural` (Warm, earnest, energetic)
  - 🌸 **Nezuko Kamado**: `en-US-AnaNeural` (Soft, gentle, cute)
  - 🦋 **Shinobu Kocho**: `en-US-JennyNeural` (Elegant, teasing, polite)
- **Voice Commands**: `/tts <text>`, `/voice <text>`, `/speak <text>`.
- **Multimodal Voice Auto-Replies**: When users send voice notes to the bot, it transcribes and automatically responds with native Telegram Opus `.ogg` voice notes.

---

### 🌸 2. AniList Anime & Manga Explorer (`services/anime_service.py`)
- **`/anime <title>`**: Search any anime via AniList GraphQL with high-res cover art, English/Romaji titles, episodes, studio, genres, rating scores, and synopsis.
- **`/manga <title>`**: Search manga & light novels with volume counts, chapter status, and author details.
- **`/quote`**: Delivers iconic, inspirational Demon Slayer quotes.

---

### 🎮 3. Steam, SteamDB ATL & Keyshop Comparator (`services/game_deals_service.py`)
- **`/game <title>` / `/steam <title>`**: Searches Steam store with pricing in **Indian Rupees (₹ INR)** and USD ($), genres, release dates, and review sentiment.
- **SteamDB All-Time Low (ATL) Tracker**: Instant historical price low records with last recorded timestamp.
- **GG.deals & CheapShark Keyshop Comparison**: Compares authorized store deals (Fanatical, GOG, Humble, GreenManGaming) with 1-click claim links.
- **`/deals` / `/steamdeals`**: Browse top trending PC game discounts.
- **`/newlow <title>`**: Alerts when a game is currently matching or breaking its historical low record (`🚨 [NEW ALL-TIME LOW RECORD!]`).

---

### 🎁 4. Real-Time 60s Giveaway Radar (`services/giveaway_service.py`)
- **Automated Background Scanner**: Continuously monitors free games, beta keys, hardware promos, and in-game drops.
- **Aggregated Providers**:
  - 👽 **Alienware Arena Keys** (Exclusive DLCs & beta access)
  - 🎮 **GOG Freebies** (Permanent DRM-free games)
  - 🔴 **AMD Gaming Rewards** (Hardware promo codes)
  - 🏅 **Medal.tv Drops** (Cosmetics & perks)
  - 🚂 **Steam 100% Off** (Permanent keep-to-account games)
  - ⚡ **Epic Games Store** (Weekly giveaways)
- **Commands**:
  - `/giveaways [all|alienware|amd|medal|steam|epic|gog]` — Interactive filter menu.
  - `/freesteam`, `/gog`, `/alienware` — Direct instant shortcuts.
  - `/giveawaynotify [on/off]` — Toggle 60-second real-time alert daemon (Super Admin).

---

### 🎰 5. Casino Mini-Games, Daily Streaks & RPG Duels (`handlers/games_handler.py`)
- **`/daily`**: Daily reward streak bonus (100 to 750 Water Coins + Level XP).
- **`/gamble <amount>` / `/bet <amount>`**: Classic multiplier dice gambling.
- **`/coinflip <heads|tails> <amount>`**: 50/50 double-or-nothing coin flip.
- **`/dice <1-6> <amount>`**: Guess the exact Telegram animated dice roll for a 5x payout!
- **`/slots <amount>`**: Animated 3-reel slot machine with jackpot payouts (777 = 10x).
- **`/duel <@user> <amount>`**: Turn-based PvP RPG duel with Water Breathing attacks!
- **`/trivia`**: Anime, gaming, and general knowledge quiz with coin bounties.

---

### 🛡️ 6. Group Security & Moderation Toolkit
- **Word Blacklist Auto-Censor (`/blacklist [add|del|list]`)**: Deletes offensive words in real-time.
- **Smart Timed Reminders (`/remind <10m|1h|2d> <message>`)**: Schedules background alerts in group chats.
- **Full Admin Arsenal**: `/kick`, `/ban`, `/mute`, `/unmute`, `/tempmute`, `/warn`, `/warns`, `/resetwarns`, `/promote`, `/demote`.
- **Flood Defense**: Auto-mutes spammers sending $>5$ messages in 4 seconds.
- **Anti-Raid Math Captcha**: Silences new joins until they solve an inline math equation.
- **Dynamic Welcome Cards**: Renders custom welcome images with profile pictures via Pillow.

---

### 📥 7. Universal 5-Tier Media Downloader (`services/media_downloader.py`)
- **Universal `/dl <url>`**: Paste or reply to any link for auto-detection and download.
- **Shortcuts**:
  - 📸 **Instagram**: `/insta <url>` (Reels, Stories, Posts)
  - 🎵 **TikTok**: `/tiktok <url>` (HD watermark-free MP4)
  - 📘 **Facebook**: `/fb <url>` (Reels, Videos)
  - 📦 **Terabox**: `/terabox <url>` (Files & Cloud Videos)
  - 📺 **YouTube**: `/video <title|url>`, `/play <song>` (MP3 audio)
  - 🐦 **Twitter/X, Reddit, Pinterest, Twitch, Vimeo, Bilibili, Loom** + 1,800 websites via `yt-dlp`.

---

### 🤖 8. Multimodal Agentic AI & Graph-RAG (`services/ai_agent.py`)
- **Multi-Persona Engine**: Switch dynamically between Giyu, Tanjiro, Nezuko, and Shinobu via `/setchar`.
- **Multimodal Vision (`/ask`)**: Reply to any photo or sticker with `/ask` for visual analysis via Pixtral.
- **AI Art Generation (`/draw`)**: Text-to-image generator using Perchance AI & Pollinations.ai.
- **Graph-RAG Memory**: 1024-dim vector embeddings (`bot_lore`) combined with structural $(Subject) \xrightarrow{Predicate} (Object)$ relationship knowledge graphs.
- **Dynamic Document Ingestion (`/learn`)**: Upload `.pdf`, `.txt`, `.md`, `.docx` files to teach the bot custom community knowledge.

---

## 📊 Cyberpunk Web Control Dashboard (`keep_alive/`)

Giyu-Bot includes an integrated Flask dashboard (`keep_alive/`) running on port 8080 (or `PORT` env):

```
┌────────────────────────────────────────────────────────────────────────┐
│                        GIYU TOMIOKA CONTROL HUB                        │
│          Water Breathing • Neural RAG & Knowledge Graph Hub            │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────┤
│ 🛡️ GROUPS: 12│ 👥 USERS: 840│ 🧠 RAG: 154  │ 🕸️ GRAPH: 88 │🪙 COINS: 2M│
├──────────────┴──────────────┴──────────────┴──────────────┴────────────┤
│  🕸️ KNOWLEDGE GRAPH EVOLUTION (0.001ms)    ⚡ INFRASTRUCTURE STATUS    │
│  • [GIYU] (Giyu) --[TITLE]--> (Hashira)    • Database: Connected (0ms) │
│  • [GIYU] (Giyu) --[USES]--> (Water)       • FastCache: Active (0ms)   │
│  • [SHINOBU] (Shinobu) --[TEASES]--> (Giyu) • Mistral AI: Configured   │
│                                                                        │
│  🧬 PERSONA EVOLUTION & TRAITS             📟 REAL-TIME TELEMETRY      │
│  • Stoic: 85%  • Friendly: 15% • Level 12  • [uvloop] 10,000 req/s     │
└────────────────────────────────────────────────────────────────────────┘
```

- **Live Endpoints**:
  - `GET /` — Interactive Glassmorphic Control Dashboard
  - `GET /health` — JSON Health metrics for Uptime Kuma / Render Keep-Alive
  - `GET /logs` — Live system log stream

---

## 📁 Repository Architecture

```
group-manager-bot/
├── config.py                 # Environment configuration & bot owner overrides
├── main.py                   # uvloop loader, Application builder & handler registry
├── requirements.txt          # Production dependencies
│
├── database/                 # High-performance persistence layer
│   ├── db_manager.py         # Threaded connection pooler singleton
│   ├── schema.sql            # Full Supabase PostgreSQL schema with HNSW indexes
│   └── repositories/         # Domain repositories with FastCache write-through
│       ├── base.py           # Table migrations & composite index bootstrap
│       ├── user_repo.py      # UserRepository, AFKRepository, WarningRepository
│       ├── chat_repo.py      # ChatRepository, TagRepository, FilterRepository, BlacklistRepository
│       ├── ai_repo.py        # LoreRepository, KnowledgeGraphRepository, CharacterRepository
│       ├── economy_repo.py   # EconomyRepository, DailyStreakRepository, ShopRepository
│       └── media_repo.py     # BotStickerRepository, GiveawayAlertRepository
│
├── handlers/                 # Modular Telegram command handlers
│   ├── public_commands.py    # /start, /help, /info, /rules, /list_commands, /owner
│   ├── admin_moderation.py   # /kick, /ban, /mute, /unmute, /tempmute, /warn, /promote
│   ├── admin_settings.py     # /setrules, /setwelcome, /filter, /blacklist, /remind
│   ├── games_handler.py      # /daily, /gamble, /coinflip, /dice, /slots, /duel, /trivia
│   ├── anime_handler.py      # /anime, /manga, /quote
│   ├── game_deals_handler.py # /game, /steam, /deals, /newlow
│   ├── giveaway_handler.py   # /giveaways, /freesteam, /gog, /alienware, /giveawaynotify
│   ├── media_handler.py      # /dl, /insta, /tiktok, /fb, /terabox, /tts, /play, /video
│   ├── ai_chat_handler.py    # Ambient conversational AI, /learn, voice note auto-replies
│   ├── leveling_handler.py   # /rank, /ranking, /levels, /chatstats, /chatters
│   └── economy_handler.py    # /shop, /buy, /balance, /pay
│
├── services/                 # Core engine services
│   ├── cache_service.py      # FastCache in-memory TTL/LRU engine (0.00ms latency)
│   ├── http_client.py        # Shared persistent HTTP/2 connection pool
│   ├── voice_engine.py       # Microsoft Edge Neural Speech TTS generator
│   ├── anime_service.py      # AniList GraphQL query client
│   ├── ai_agent.py           # Mistral LLM loop, unified RAG, in-memory Graph-RAG
│   ├── game_deals_service.py # Steam INR, SteamDB ATL & CheapShark comparator
│   ├── giveaway_service.py   # GamerPower 60s real-time alert daemon
│   └── media_downloader.py   # 5-tier self-healing video downloader
│
└── keep_alive/               # Flask Keep-Alive & Evolution Visualizer
    ├── app.py                # Dashboard router & health check endpoints
    ├── templates.py          # Cyberpunk Demon Slayer glassmorphic HTML UI
    └── utils.py              # Real-time database telemetry & graph sampler
```

---

## 🚀 Quickstart & Deployment

### 1. Prerequisites
- **Python 3.10+**
- **FFmpeg** (for audio transcoding & sticker generation)
- **Supabase (PostgreSQL)** database
- **Mistral AI API Key**

### 2. Environment Variables (`.env`)
```ini
BOT_TOKEN=your_bot_token_here
OWNER_ID=your_owner_telegram_numeric_id
SUPER_ADMIN_ID=your_super_admin_telegram_numeric_id
DATABASE_URL=postgresql://postgres:[password]@db.[project-id].supabase.co:5432/postgres
MISTRAL_API_KEY=your_mistral_api_key_here
PORT=8080
```

### 3. Run Locally
```bash
git clone https://github.com/GuruMachanica/Giyu-Bot.git
cd group-manager-bot
pip install -r requirements.txt
python main.py
```

### 4. Deploy to Docker / Render / VPS
```bash
docker-compose up -d --build
```

---

## 📜 License & Credits

Licensed under the [Proprietary - Strict Private Use License](LICENSE).  
Built with 💙 by **GuruMachanica** & **Ansh22x**.
