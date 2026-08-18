# Giyu-Bot — Giyu Tomioka Group Manager Bot

An advanced, OOP-heavy, modular Telegram Group Manager Bot written in Python using the `python-telegram-bot` framework. It provides complete moderation tools, warning/strike tracking, a message-based XP leveling system, custom note hashtag tags, and keyword filters. 

Additionally, he features an integrated **Mistral AI conversational agent** supporting multiple Demon Slayer personas (Giyu, Tanjiro, Nezuko, Shinobu) via `/setchar`. It is secured by a vector-based **RAG (Retrieval-Augmented Generation)** identity guard, a SQL-backed **Knowledge Graph (Graph-RAG)** triplets store, database-backed thread memory, and external information lookup capabilities (**Wikipedia Article Lookup** and **Web Search**).

---

## 🌟 Key Features

*   🛡️ **Complete Moderation**: Promote/demote admins, mute/unmute, pin/unpin messages, and kick users.
*   ⚠️ **Warning / Strike System**: Issue warnings; users reaching 3 warnings are automatically banned.
*   📈 **XP & Leveling System**: Active members gain 15 XP per message (with a 60-second cooldown). Admins can assign custom titles/tags (e.g. VIP Member), and members can view their stats and a top 10 group leaderboard.
*   💰 **Interactive Group Economy**: Chatters gain coins alongside XP. A group shop `/shop` allows users to purchase tag custom rank changes, warning cleanses, or breathing licenses via `/buy`.
*   🛡️ **Captcha & Spam Security**: Silences new users upon entry and serves an addition captcha equation. Auto-kicks on timeout or failure. Automatically deletes chat floods (>5 messages in 4 seconds) or invite link spam from normal members.
*   💤 **AFK Tracking**: Users can set an AFK status. The bot notifies users who reply to them and automatically welcomes them back when they message.
*   🏷️ **Hashtags & Filters**: Save custom notes (triggered by `#notename`) and configure auto-replies for specific keywords.
*   🎬 **FFmpeg Media Sticker Converter (`/kang`)**: Reply to any photo, document, animated sticker, GIF, or video and convert it into a static or animated/video sticker. Videos/GIFs are converted to compliant VP9 WebM files under 3 seconds and 256 KB.
*   🌊 **Multi-Persona AI Agent (Mistral AI)**:
    *   **Conversational Agent**: Triggers when mentioned, replied to, or in private chats. Switch between characters dynamically via `/setchar` (`giyu`, `tanjiro`, `nezuko`, `shinobu`).
    *   **Vector RAG Identity Guard**: Uses Mistral Embeddings and Supabase `pgvector` to dynamically fetch and inject character-specific personality traits into the system prompt context.
    *   **Knowledge Graph (Graph-RAG)**: Extracts entities from the user prompt and matches them against database relations `(subject, predicate, object)`. Appends structured triples to the system prompt to maintain character context.
    *   **Agentic Tool Calls**: Exposes database tools for checking rules, leaderboards, and relationship graphs (`query_knowledge_graph`).
    *   **Conversational Thread Memory**: Retains the last 8 messages in the database for coherent conversations.
    *   **Search Tools**: Can query **Wikipedia summaries** (`wikipedia_search`) and **perform DuckDuckGo web search** (`web_search`) to retrieve real-time news or general facts directly inside chat conversations.

---

## 📁 Codebase Directory Structure

```text
group-manager-bot/
├── config.py                 # Configuration loader (.env, API keys)
├── main.py                   # Main entry point (instantiates DatabaseManager and registers polymorphic handlers)
├── requirements.txt          # Dependencies (python-telegram-bot, mistralai, psycopg2-binary, Pillow, beautifulsoup4, Flask)
├── LICENSE                   # Inspiration-Only License
│
├── keep_alive/               # Modular Flask background keep-alive dashboard package
│   ├── __init__.py           # Exports keep_alive background server thread
│   ├── app.py                # Configures Flask routes (/, /health endpoints)
│   ├── server.py             # Spawns server Thread and configures logging
│   ├── templates.py          # Holds styled HSL breathing wave dashboard template
│   └── utils.py              # Status checking (Supabase database health and uptime)
│
├── database/
│   ├── __init__.py           # Database package exports
│   ├── db_manager.py         # DatabaseManager (Singleton class wrapping psycopg2 ThreadedConnectionPool)
│   ├── repositories.py       # Entity Repositories (ChatRepository, UserRepository, WarningRepository, KnowledgeGraphRepository, etc.)
│   └── schema.sql            # Supabase database bootstrap migration schema (tables, pgvector, pgcrypto, RLS policies)
│
├── handlers/
│   ├── __init__.py           # Handler registry (instantiates and registers BaseHandler subclasses)
│   ├── base_handler.py       # BaseHandler (Abstract Base Class for all command/message modules)
│   ├── public_commands.py    # PublicCommands class (/start, /help, /rules, /owner, /list_commands, /kang)
│   ├── admin_moderation.py   # AdminModeration class (/kick, /unban, /mute, /unmute, /warn, /dwarn, /promote, /demote, /pin/unpin, /admin_list)
│   ├── admin_settings.py     # AdminSettings class (/setrules, /welcome, /setwelcome, /filter, /afkstat, /addtag, /edit_tag, /settag)
│   ├── owner_commands.py     # OwnerCommands class (/botstats, /broadcast)
│   ├── leveling_handler.py   # LevelingHandler class (/rank, /ranking, /levels)
│   ├── captcha_handler.py    # CaptchaHandler class (Status welcomes, Captchas)
│   ├── economy_handler.py    # EconomyHandler class (/shop, /buy)
│   └── ai_chat_handler.py    # AIChatHandler class (AFK, Tags, Filters, spam muting, and Giyu AI triggers)
│
└── services/
    ├── __init__.py
    ├── ai_agent.py           # AIAgent class (Mistral client, pgvector RAG, Graph-RAG, search tools, agent tools)
    ├── welcome_card.py       # WelcomeCard class (dynamic Pillow welcome card drawer)
    └── sticker_engine.py     # StickerEngine class (static images Pillow and video/GIF FFmpeg sticker transcoder)
```

---

## 🚀 Setup & Installation

### Prerequisite Dependencies
1. **Python 3.8+**
2. **FFmpeg**: Required for `/kang` video sticker conversion (ensure `ffmpeg` is added to your OS system Path).
3. **Supabase (PostgreSQL)**: Ensure you have a running PostgreSQL database (transaction pooler connection string is recommended). You can copy and run the migration script in [database/schema.sql](file:///c:/Desktop/Stand-Up/Projects/TG-Group-Manage-bot/group-manager-bot/database/schema.sql) directly in your Supabase SQL Editor to initialize all tables, extensions, and RLS policies.
4. **Mistral API Key**: Sign up at [Mistral Console](https://console.mistral.ai/) and generate an API key.

### Environment Variables Configuration

Create a `.env` file in the root folder of your project (or define these inside your VPS / Render service environment variables settings):

```ini
# 1. Telegram Bot API Token (Obtained by direct messaging @BotFather on Telegram)
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# 2. Your Telegram User ID (Get by messaging @userinfobot or running /id to MissRose on Telegram)
OWNER_ID=987654321

# 3. Supabase Database connection Pooler URL
# Go to settings -> Database -> Connection String -> Select 'URI' (Select Port 6543 for Transaction pooler mode)
DATABASE_URL=postgresql://postgres.[your-project-id]:[your-password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require

# 4. Mistral AI API Key (Sign up and generate a key at https://console.mistral.ai/)
MISTRAL_API_KEY=your_actual_mistral_api_key_here
```

### Local Installation
1. Clone the repository and navigate to the project directory.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create your `.env` file using the configuration schema detailed above.
4. Start the bot:
   ```bash
   python main.py
   ```

### Render Deployment
This bot is pre-configured to run on [Render](https://render.com) (or similar Docker/container platforms):
1. Create a new **Web Service** on Render connected to your repository.
2. Select **Python** as the environment.
3. Set the **Start Command** to:
   ```bash
   python main.py
   ```
4. Under Environment Variables, add `BOT_TOKEN`, `OWNER_ID`, `DATABASE_URL`, and `MISTRAL_API_KEY`.
5. Render will automatically bind to the port defined in the `keep_alive` package (which defaults to `10000` or the `PORT` env variable) to keep the bot active.

---

## 👮‍♂️ Commands Reference

### 👥 Public Commands
*   `/start` - Shows the start greeting panel and profile links.
*   `/help` - Shows commands overview.
*   `/rules` - Displays the group rules.
*   `/afk [reason]` - Sets your status to sleeping/busy.
*   `/kang` - (Reply-to media) Converts the replied image, GIF, or video into a static or WebM video sticker.
*   `/rank` - Displays your current Custom Title, Level, XP, and Message count.
*   `/ranking` (or `/levels`) - Displays the top 10 group leaderboard by XP.
*   `/chatstats` - Shows total group participants, levels, and total message statistics.
*   `/chatters` - Lists the top 5 most active chat members in the group.
*   `/shop` - Lists items available for purchase in the group economy.
*   `/buy [item_id] [args]` - Purchases shop goods (custom titles, warning cleanses).
*   `/owner` - Lists the group's creator (owner) and the developer of the bot.
*   `/ask [question]` - Query the AI agent directly. If she does not know the answer, she will use Wikipedia or web search.

### 🛡️ Admin Commands
*   `/kick` - (Reply-to user) Bans the user and immediately unbans them (removing them from the chat).
*   `/unban` - (Reply-to user) Unbans the user.
*   `/mute` - (Reply-to user) Restricts the user's ability to send messages.
*   `/unmute` - (Reply-to user) Restores default group message permissions.
*   `/tempmute [duration]` - (Reply-to user) Mutes a user for a duration (e.g. `/tempmute 10m`).
*   `/warn` - (Reply-to user) Issues a warning. Banned at 3 warnings.
*   `/dwarn` - (Reply-to user) Removes 1 warning strike from the user.
*   `/promote` - (Reply-to user) Promotes a member to an administrator.
*   `/demote` - (Reply-to user) Revokes admin privileges.
*   `/pin` / `/unpin` - (Reply-to message) Pins or unpins a message.
*   `/admin_list` - Lists administrators in the group.
*   `/setrules [rules_text]` - Sets the text shown when users call `/rules`.
*   `/welcome` - Toggles the welcome greeting for new users on or off.
*   `/setwelcome [message]` - Updates the welcome greeting. Supports `{name}` as a placeholder.
*   `/filter [keyword] [reply_text]` - Configures the bot to reply with `[reply_text]` when `[keyword]` is matched.
*   `/afkstat` - Toggles AFK monitoring on/off in the group.
*   `/addtag [tag_name] [reply_text]` - Saves a tag. Anyone can call `#[tag_name]` to print the `[reply_text]`.
*   `/edit_tag [tag_name] [reply_text]` - Edits an existing `#hashtag` reply.
*   `/settag` - (Reply-to user) Sets a custom text title for the user in the leveling system.
*   `/setchar [char_name]` - Changes Giyu-Bot's AI active persona (`giyu`, `tanjiro`, `nezuko`, `shinobu`).

### 💻 Bot Owner Commands (Owner ID required)
*   `/botstats` - Shows active groups and total AFK users.
*   `/broadcast [message]` - Sends a global announcement to all managed groups.

---

## 📜 License & Project Status

*   **License**: Licensed under the [Inspiration-Only License](LICENSE).
*   **Enhancements and Future Scope**: Check out the completed updates and pending todos in the [Roadmap Guide](docs/roadmap.md).
