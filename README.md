# Giyu-Bot — Giyu Tomioka Group Manager Bot

An advanced, modular Telegram Group Manager Bot written in Python using `python-telegram-bot`. It provides complete moderation tools, XP leveling, economy, media downloads, and a fully **autonomous agentic AI** powered by Mistral AI.

---

## 🌟 Key Features

### 🛡️ Moderation
- **Full admin toolkit**: Promote/demote, kick, ban, mute, unmute, temp-mute (with auto-unmute scheduler)
- **Warning / Strike system**: Issue warnings; 3 strikes = auto-ban
- **Flood protection**: Auto-mutes users sending >5 messages in 4 seconds
- **Invite link spam detection**: Auto-deletes invite links posted by non-admins
- **Captcha on join**: Math equation captcha for new members; auto-kicks on timeout or wrong answer

### 📈 XP, Leveling & Economy
- Members earn **15 XP per message** (60-second cooldown)
- Admins assign **custom title tags** (e.g. `VIP Member`, `Demon Slayer`)
- `/shop` and `/buy` for purchasing tags, warning cleanses, and breathing licenses with coins
- `/rank`, `/ranking`, `/chatstats`, `/chatters` leaderboards

### 🎵 Media Downloads (Command-Only)
- `/play [song name or YouTube URL]` — Downloads and sends audio as MP3
- `/video [video name or YouTube URL]` — Downloads and sends video (≤50MB)
- **3-tier download strategy** (fastest to fallback):
  1. **Direct** — `android_music` → `tv_embedded` → `mweb` player clients (full server bandwidth, no proxy needed)
  2. **Proxy** — Rotating public HTTP proxy (if datacenter IP is blocked by YouTube)
  3. **SoundCloud** — `/play` only; automatic fallback for non-URL search queries
- **Concurrent**: Up to **5 simultaneous downloads** via `asyncio.Semaphore(5)`
- Media **only** triggers via explicit `/play` or `/video` commands — never from passive ambient chat text

### 🤖 Autonomous Agentic AI (Mistral AI)
- **Multi-persona**: Switch between Giyu, Tanjiro, Nezuko, Shinobu via `/setchar`
- **Ambient @mention agent**: Responds when @mentioned, replied to, or bot name (giyu/tomioka) is typed in chat — **questions and conversation only**
- **15 tools** the AI can autonomously call during a multi-step reasoning loop:

| Category | Tool | Description |
|----------|------|-------------|
| Observe | `get_group_rules` | Fetch current group rules |
| Observe | `get_user_level_stats` | XP / level of the asking user |
| Observe | `get_leaderboard` | Top 10 XP leaderboard |
| Observe | `get_chat_stats` | Group activity stats |
| Observe | `get_user_balance` | User coin wallet balance |
| Observe | `get_shop_items` | List shop items |
| Observe | `wikipedia_search` | Search Wikipedia |
| Observe | `web_search` | DuckDuckGo web search |
| Observe | `query_knowledge_graph` | Character relationship triples |
| Act | `send_message` | Proactively send a chat message |
| Act | `play_audio` | Queue audio download (via agentic /ask only) |
| Act | `play_video` | Queue video download (via agentic /ask only) |
| Act | `warn_user` | Issue a warning (admin-gated) |
| Act | `mute_user` | Temporarily mute a user (admin-gated) |
| Act | `add_lore` | Add a fact to bot memory (admin-gated) |

- **Vector RAG identity guard**: pgvector embeddings inject character personality into system prompt
- **Knowledge Graph (Graph-RAG)**: Structured `(subject, predicate, object)` triples per character
- **Conversational memory**: Last 8 messages stored per chat thread in database
- **Agentic loop**: Multi-step tool call reasoning, up to 5 iterations

### 💤 AFK Tracking
- `/afk [reason]` — Set AFK; bot notifies anyone who mentions or replies to you

### 🏷️ Hashtags & Filters
- `/addtag` / `#tagname` — Custom hashtag notes for quick info sharing
- `/filter [keyword] [reply]` — Keyword auto-reply triggers

### 🎬 Sticker Converter (`/kang`)
- Reply to any photo, GIF, video, or document to convert it into a Telegram sticker (static PNG or animated WebM)

### 🌐 Keep-Alive (Anti-Sleep)
- Self-pinging Flask server hits `/health` every **10 minutes**
- Prevents Render free tier from sleeping (Render's idle threshold: 15 min)
- Uses `RENDER_EXTERNAL_URL` env var automatically — no manual URL config needed
- Dashboard at `/`, health JSON at `/health`, live logs at `/logs`

---

## 📁 Directory Structure

`
group-manager-bot/
├── config.py                 # Env vars and config loader
├── main.py                   # Entry point — Application builder + handler registration
├── requirements.txt          # Dependencies
│
├── keep_alive/               # Anti-sleep Flask dashboard package
│   ├── app.py                # Routes: /, /health, /logs
│   ├── server.py             # Flask thread + self-pinger thread (10-min interval)
│   ├── templates.py          # Glassmorphism breathing-wave dashboard HTML
│   └── utils.py              # DB health check, uptime helpers
│
├── database/
│   ├── db_manager.py         # Singleton psycopg2 ThreadedConnectionPool
│   ├── repositories.py       # All entity repos (Chat, User, Warning, Lore, KG, History…)
│   └── schema.sql            # Full Supabase migration (tables, pgvector, RLS)
│
├── handlers/
│   ├── base_handler.py       # Abstract BaseHandler ABC
│   ├── public_commands.py    # /start, /help, /rules, /kang, /owner, /list_commands
│   ├── admin_moderation.py   # /kick, /ban, /mute, /unmute, /tempmute, /warn, /promote…
│   ├── admin_settings.py     # /setrules, /setwelcome, /filter, /addtag, /setchar…
│   ├── owner_commands.py     # /botstats, /broadcast
│   ├── leveling_handler.py   # /rank, /ranking, /levels, /chatstats, /chatters
│   ├── economy_handler.py    # /shop, /buy
│   ├── captcha_handler.py    # Math captcha on join, welcome card sender
│   ├── media_handler.py      # /play, /video — 3-tier concurrent YouTube/SoundCloud downloader
│   └── ai_chat_handler.py    # AI agent, AFK, Tags, Filters, flood-mute, /ask
│
└── services/
    ├── ai_agent.py           # Mistral agentic loop — 15 tools, RAG, Graph-RAG, memory
    ├── intent_detector.py    # Zero-cost keyword intent classifier for @mention routing
    ├── welcome_card.py       # Pillow dynamic welcome card generator
    └── sticker_engine.py     # FFmpeg/Pillow sticker transcoder
`

---

## 🚀 Setup & Installation

### Prerequisites
1. **Python 3.10+**
2. **FFmpeg** — Required for `/kang` and audio post-processing. Add to system PATH.
3. **Supabase (PostgreSQL)** — Run `database/schema.sql` in your Supabase SQL editor to initialize all tables and extensions.
4. **Mistral API Key** — Sign up at https://console.mistral.ai/

### Environment Variables

Create a `.env` file at project root (or set in your Render service dashboard):

`ini
# Telegram Bot Token — from @BotFather
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Your Telegram User ID — from @userinfobot
OWNER_ID=987654321

# Supabase Transaction Pooler URL (port 6543)
DATABASE_URL=postgresql://postgres.[project-id]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require

# Mistral AI API key
MISTRAL_API_KEY=your_mistral_api_key_here
`

### Local Development

`ash
git clone https://github.com/GuruMachanica/Giyu-Bot.git
cd Giyu-Bot
pip install -r requirements.txt
# Create .env with your keys
python main.py
`

### Render Deployment

1. Create a **Web Service** on Render connected to this GitHub repo
2. **Runtime**: Python 3
3. **Start command**: `python main.py`
4. Add environment variables: `BOT_TOKEN`, `OWNER_ID`, `DATABASE_URL`, `MISTRAL_API_KEY`
5. Render auto-sets `RENDER_EXTERNAL_URL` — the self-pinger uses it automatically

> **Optional**: Mount a `cookies.txt` (Netscape format) under **Render → Environment → Secret Files** at path `cookies.txt` to bypass YouTube's stricter datacenter IP bot-detection for more reliable media downloads.

---

## 👮 Commands Reference

### 👥 Public Commands

| Command | Description |
|---------|-------------|
| `/start` | Start panel with project links |
| `/help` | Commands overview |
| `/list_commands` | Full detailed command reference |
| `/rules` | Display group rules |
| `/afk [reason]` | Set AFK status |
| `/rank` | Your XP, level, and custom title |
| `/ranking` / `/levels` | Top 10 XP leaderboard |
| `/chatstats` | Group activity stats |
| `/chatters` | Top 5 most active members |
| `/shop` | View purchasable items |
| `/buy [item_id]` | Purchase a shop item with coins |
| `/owner` | Group owner and bot developer info |
| `/play [song or URL]` | Download and send audio (YouTube → SoundCloud fallback) |
| `/video [title or URL]` | Download and send video (YouTube, max 50MB) |
| `/ask [question]` | Ask the AI agent directly with full tool access |
| `/kang` | Reply to media to convert it into a Telegram sticker |
| `/report [reason]` | Reply to any message to report it to group admins |

### 🛡️ Admin Commands

| Command | Description |
|---------|-------------|
| `/kick` | Reply → remove user from group |
| `/unban` | Reply → unban user |
| `/mute` | Reply → silence user indefinitely |
| `/unmute` | Reply → restore user's send permissions |
| `/tempmute [duration]` | Reply → mute for duration (e.g. `10m`, `2h`, `1d`) — auto-unmutes |
| `/warn` | Reply → issue a warning (3 warnings = auto-ban) |
| `/dwarn` | Reply → remove one warning strike |
| `/promote` | Reply → grant admin rights |
| `/demote` | Reply → revoke admin rights |
| `/pin` / `/unpin` | Reply → pin or unpin a message |
| `/admin_list` | List all current group administrators |
| `/setrules [text]` | Set the group rules text |
| `/welcome` | Toggle welcome message on/off |
| `/setwelcome [msg]` | Set welcome message (`{name}` placeholder supported) |
| `/filter [keyword] [reply]` | Add keyword auto-reply trigger |
| `/afkstat` | Toggle AFK monitoring on/off for the group |
| `/addtag [name] [text]` | Save a `#hashtag` note |
| `/edit_tag [name] [text]` | Edit an existing hashtag note |
| `/settag` | Reply → assign a custom title tag to a user |
| `/setchar [name]` | Switch AI persona: `giyu`, `tanjiro`, `nezuko`, `shinobu` |
| `/learn` | Reply to a document or text to teach the AI agent new facts |

### 💻 Bot Owner Commands

| Command | Description |
|---------|-------------|
| `/botstats` | Active groups, AFK count, system statistics |
| `/broadcast [message]` | Send announcement to all managed groups |

---

## 🤖 AI Agent Trigger Reference

| Trigger | Behaviour |
|---------|-----------|
| `@mention` in group | AI responds in-thread |
| Reply to bot's message | AI continues conversation |
| Private message | AI always responds |
| `giyu [question]` in group | Ambient name trigger — AI responds |
| `tomioka [question]` in group | Ambient name trigger — AI responds |
| `/ask [question]` | Direct agentic query with full 15-tool access |
| `/play [song]` | Media download — **command-only** |
| `/video [title]` | Media download — **command-only** |

---

## 📜 License

Licensed under the [Inspiration-Only License](LICENSE).  
Built and maintained by **GuruMachanica**.
