# Giyu-Bot — Giyu Tomioka Group Manager Bot

An advanced, modular Telegram Group Manager Bot written in Python using `python-telegram-bot`. It provides complete moderation tools, XP leveling, global economy, media downloads, Steam & GG.deals deal tracking, guarded real-time giveaway monitors, and a fully **autonomous agentic AI** powered by Mistral AI.

---

## 🌟 Key Features

### 🛡️ Moderation & Security
- **Full admin toolkit**: Promote/demote, kick, ban, mute, unmute, temp-mute (with auto-unmute scheduler)
- **Warning / Strike system**: Issue warnings; 3 strikes = auto-ban
- **Flood protection**: Auto-mutes users sending >5 messages in 4 seconds
- **Invite link spam detection**: Auto-deletes invite links posted by non-admins
- **Captcha on join**: Math equation captcha for new members; auto-kicks on timeout or wrong answer
- **Identity & Data Inspector (`/info`, `/id`)**: Complete card showing Telegram numeric ID, group permissions, wallet, leveling, and permanent links.

### 🎮 Steam, SteamDB & GG.deals Game Engine
- **`/game <title>` / `/steam <title>`**: Search Steam games with cover art, genres, developer, release date, Metacritic, and Steam review ratings.
- **SteamDB All-Time Low (ATL) Tracker**: Fetches historical low records with exact date and relative time (e.g. `$17.99 (Last hit: Jun 17, 2024 • 2 months ago)`).
- **GG.deals Keyshop Comparator**: Compares authorized keyshops (GreenManGaming, Fanatical, GOG, Humble) with 1-click claim links.
- **`/deals` / `/steamdeals`**: Browse top trending PC game discounts.
- **`/newlow <title>`**: Checks if a game is currently matching or breaking its historical low record (`🚨 [NEW ALL-TIME LOW RECORD!]`).

### 🎁 Guarded Real-Time Giveaway & Key Monitor (Super Admin Only)
- **Aggregated Providers**:
  - 👽 **Alienware Arena Keys** (Exclusive game keys, DLCs, beta access)
  - 🎮 **GOG Freebies** (DRM-free PC games)
  - 🔴 **AMD Gaming Rewards** (Hardware promo codes, game packs)
  - 🏅 **Medal.tv Drops** (In-game cosmetics and game drops)
  - 🚂 **Steam 100% Off** (Permanent keep-to-account free games)
  - ⚡ **Epic Games Store** (Weekly free games)
- **Commands**:
  - `/giveaways [all|alienware|amd|medal|steam|epic|gog]` — Browse active giveaways with interactive filter buttons.
  - `/gog`, `/alienware` — Instant direct shortcuts.
  - `/giveawaynotify [on/off]` — Toggle 60-second real-time background monitor.
- **Real-Time 60s Private DM Pings**: Instant alerts dispatched directly to Super Admin & Owner with official banner art, value ($), instructions, and 1-click claim button.
- **Persistent Database (`giveaway_alerts`)**: Deduplication engine ensures you are never spammed twice across server restarts.

### 📈 XP, Leveling & Economy
- Members earn **15 XP per message** (60-second cooldown)
- Admins assign **custom title tags** (e.g. `VIP Member`, `Demon Slayer`)
- `/shop` and `/buy` for purchasing tags, warning cleanses, and breathing licenses with coins
- `/rank`, `/ranking`, `/chatstats`, `/chatters` leaderboards
- **Global Economy**: 100M coin central treasury with `/balance`, `/pay`, `/add`, `/remove`, and `/botbalance`.

### 🎵 Media Downloads (Command-Only)
- `/play [song name or YouTube URL]` — Downloads and sends audio as MP3
- `/video [video name or YouTube URL]` — Downloads and sends video (≤50MB)
- **3-tier download strategy** (fastest to fallback):
  1. **Direct** — `android_music` → `tv_embedded` → `mweb` player clients (full server bandwidth, no proxy needed)
  2. **Proxy** — Rotating public HTTP proxy (if datacenter IP is blocked by YouTube)
  3. **SoundCloud** — `/play` only; automatic fallback for non-URL search queries
- **Concurrent**: Up to **5 simultaneous downloads** via `asyncio.Semaphore(5)`
- Media **only** triggers via explicit `/play` or `/video` commands — never from passive ambient chat text

### 🤖 Autonomous Agentic AI & Multimodal Capabilities
- **Multi-persona**: Switch between Giyu, Tanjiro, Nezuko, Shinobu via `/setchar`
- **Ambient @mention agent**: Responds when @mentioned, replied to, or bot name (giyu/tomioka) is typed in chat — **questions and conversation only**
- **Multimodal Voice-to-Voice**: Transcribes incoming voice notes (via Voxtral Transcribe model `voxtral-mini-latest`) and responds with synthetic voice replies generated dynamically (via Voxtral TTS model `voxtral-mini-tts-latest`).
- **Multimodal Vision in `/ask`**: Reply to any photo, image, or static WebP sticker with `/ask [question]`, and it downloads the image bytes and calls the Pixtral multimodal vision pipeline (`pixtral-large-latest` → `pixtral-12b-2409`).
- **AI Image Generation (`/draw`)**: Generates custom artwork using Perchance AI, with automatic fallback to Pollinations.ai.
- **Autonomous Tool Registry (`services/ai_tools/`)**: 19 agentic tools with self-healing error observation:

| Category | Tool | Description |
|---|---|---|
| Observe | `get_group_rules` | Fetch current group rules |
| Observe | `get_user_level_stats` | XP / level of the asking user |
| Observe | `get_leaderboard` | Top 10 XP leaderboard |
| Observe | `get_chat_stats` | Group activity stats |
| Observe | `get_user_balance` | User coin wallet balance |
| Observe | `get_shop_items` | List shop items |
| Observe | `wikipedia_search` | Search Wikipedia |
| Observe | `web_search` | DuckDuckGo web search |
| Observe | `query_knowledge_graph` | Character relationship triples |
| Observe | `get_bot_level_stats` | View bot's own level, traits, and skills |
| Observe | `search_game_deals` | Search Steam, SteamDB ATL, and GG.deals keys |
| Observe | `get_steam_deals` | Fetch top trending PC game discounts |
| Observe | `get_sticker_stock` | View saved sticker collection |
| Act | `send_message` | Proactively send a chat message |
| Act | `play_audio` | Queue audio download |
| Act | `play_video` | Queue video download |
| Act | `warn_user` | Issue a warning (admin-gated) |
| Act | `mute_user` | Temporarily mute a user (admin-gated) |
| Act | `add_lore` | Add a fact to bot memory (admin-gated) |
| Act | `save_user_memory` | Save user preference to long-term memory |
| Act | `save_sticker_to_stock`| Save sticker file ID to personal collection |

---

## 📁 Directory Structure

```
group-manager-bot/
├── config.py                 # Env vars (BOT_TOKEN, OWNER_ID, SUPER_ADMIN_ID)
├── main.py                   # Entry point — Application builder + handler registration
├── requirements.txt          # Dependencies
│
├── database/                 # Modular domain database package
│   ├── db_manager.py         # Singleton psycopg2 ThreadedConnectionPool
│   ├── schema.sql            # Full Supabase migration (tables, pgvector, RLS)
│   └── repositories/         # Domain repositories
│       ├── base.py           # BaseRepository & setup_db_schema bootstrap
│       ├── user_repo.py      # UserRepository, AFKRepository, WarningRepository, TempMuteRepository
│       ├── chat_repo.py      # ChatRepository, TagRepository, FilterRepository, CaptchaRepository
│       ├── ai_repo.py        # LoreRepository, HistoryRepository, CharacterRepository, KnowledgeGraphRepository, BotStatsRepository
│       ├── economy_repo.py   # EconomyRepository, ShopRepository
│       └── media_repo.py     # BotStickerRepository, GiveawayAlertRepository
│
├── handlers/                 # Modular Telegram command & callback handlers
│   ├── base_handler.py       # Abstract BaseHandler ABC
│   ├── utils.py              # Shared target user resolver & admin permission validator
│   ├── public_commands.py    # /start, /help, /info, /rules, /kang, /owner, /list_commands
│   ├── admin_moderation.py   # /kick, /ban, /mute, /unmute, /tempmute, /warn, /promote…
│   ├── admin_settings.py     # /setrules, /setwelcome, /filter, /addtag, /setchar…
│   ├── owner_commands.py     # /botstats, /broadcast, /add, /remove, /botbalance, /leave
│   ├── leveling_handler.py   # /rank, /ranking, /levels, /chatstats, /chatters
│   ├── economy_handler.py    # /shop, /buy, /balance, /pay
│   ├── game_deals_handler.py # /game, /steam, /deals, /newlow
│   ├── giveaway_handler.py   # /giveaways, /gog, /alienware, /giveawaynotify (Super Admin)
│   ├── captcha_handler.py    # Math captcha on join, welcome card sender
│   ├── media_handler.py      # /play, /video — 3-tier concurrent YouTube/SoundCloud downloader
│   └── ai_chat_handler.py    # AI agent, multimodal vision in /ask, flood-mute
│
└── services/                 # Business logic & autonomous engines
    ├── ai_agent.py           # Mistral persona loop, RAG, Graph-RAG, vision pipeline
    ├── ai_tools/             # Autonomous agentic tool definitions & executor registry
    │   └── tool_registry.py  # TOOLS schema declarations and AIToolExecutor
    ├── game_deals_service.py # Multi-source Steam, SteamDB ATL, and CheapShark/GG.deals aggregator
    ├── giveaway_service.py   # GamerPower Alienware/AMD/Medal/GOG/Steam giveaway aggregator
    ├── media_downloader.py   # Isolated search and download scraper pipeline
    ├── intent_detector.py    # Zero-cost keyword intent classifier for @mention routing
    ├── welcome_card.py       # Pillow dynamic welcome card generator
    └── sticker_engine.py     # FFmpeg/Pillow sticker transcoder
```

---

## 🚀 Setup & Installation

### Prerequisites
1. **Python 3.10+**
2. **FFmpeg** — Required for `/kang` and audio post-processing. Add to system PATH.
3. **Supabase (PostgreSQL)** — Run `database/schema.sql` in your Supabase SQL editor.
4. **Mistral API Key** — Sign up at https://console.mistral.ai/

### Environment Variables

Create a `.env` file at project root:

```ini
# Telegram Bot Token — from @BotFather
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Telegram Numeric IDs for Super Admin & Owner — from /info
OWNER_ID=8750329317
SUPER_ADMIN_ID=8750329317

# Supabase Transaction Pooler URL
DATABASE_URL=postgresql://postgres:[password]@db.[project-id].supabase.co:5432/postgres

# Mistral AI API key
MISTRAL_API_KEY=your_mistral_api_key_here
```

### Local Development

```bash
git clone https://github.com/GuruMachanica/Giyu-Bot.git
cd group-manager-bot
pip install -r requirements.txt
python main.py
```

---

## 📜 License

Licensed under the [Proprietary - Strict Private Use & Inspection License](LICENSE).  
Built and maintained by **GuruMachanica** & **Ansh22x**.
