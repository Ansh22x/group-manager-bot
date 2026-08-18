# Hinata Hyuga — Advanced Telegram Group Manager Bot

An advanced, modular Telegram Group Manager Bot written in Python using the `python-telegram-bot` framework. It provides complete moderation tools, warning/strike tracking, a message-based XP leveling system, custom note hashtag tags, and keyword filters. 

Additionally, she features an integrated **Mistral AI conversational agent** customized with the **Hinata Hyuga (Naruto)** personality. It is secured by a vector-based **RAG (Retrieval-Augmented Generation)** identity guard, database-backed thread memory, and an advanced **FFmpeg/Pillow media converter** for creating static and video stickers.

---

## 🌟 Key Features

*   🛡️ **Complete Moderation**: Promote/demote admins, mute/unmute, pin/unpin messages, and kick users.
*   ⚠️ **Warning / Strike System**: Issue warnings; users reaching 3 warnings are automatically banned.
*   📈 **XP & Leveling System**: Active members gain 15 XP per message (with a 60-second cooldown). Admins can assign custom titles/tags (e.g. VIP Member), and members can view their stats and a top 10 group leaderboard.
*   💤 **AFK Tracking**: Users can set an AFK status. The bot notifies users who reply to them and automatically welcomes them back when they message.
*   🏷️ **Hashtags & Filters**: Save custom notes (triggered by `#notename`) and configure auto-replies for specific keywords.
*   🎬 **FFmpeg Media Sticker Converter (`/kang`)**: Reply to any photo, document, animated sticker, GIF, or video and convert it into a static or animated/video sticker. Videos/GIFs are converted to compliant VP9 WebM files under 3 seconds and 256 KB.
*   💮 **Hinata Hyuga AI Agent (Mistral AI)**:
    *   **Conversational Agent**: Triggers when mentioned, replied to, or in private chats.
    *   **Vector RAG Identity Guard**: Uses Mistral Embeddings and Supabase `pgvector` to dynamically fetch and inject Hinata's personality traits into the system prompt context.
    *   **Conversational Thread Memory**: Retains the last 8 messages in the database for coherent conversations.
    *   **People Tag Memory**: Recognizes developer status and user levels to speak with proper honorifics (`-kun`, `-san`).
    *   **Agentic Database Tools**: Mistral Function calling allows her to check rules, levels, and leaderboards using local database tools.

---

## 📁 Codebase Directory Structure

```text
group-manager-bot/
├── config.py                 # Configuration loader (.env, API keys)
├── keep_alive.py             # Render keep-alive server (prevents container sleep)
├── main.py                   # Main entry point (initializes DB, registers handlers, starts polling)
├── requirements.txt          # Dependencies (python-telegram-bot, mistralai, psycopg2-binary, Pillow, Flask)
├── LICENSE                   # MIT License
│
├── database/
│   ├── __init__.py           # Database connection manager (psycopg2 ThreadedConnectionPool)
│   └── models.py             # Database tables creation, vector search, and query CRUD functions
│
├── handlers/
│   ├── __init__.py           # Registers handlers with the Application builder
│   ├── admin.py              # Moderation commands (/kick, /mute, /warn, /setwelcome, etc.)
│   ├── public.py             # Public commands (/start, /rules, /afk, /kang, etc.)
│   ├── leveling.py           # XP increments listener and ranking commands
│   └── ai_chat.py            # AI Chat triggers (replies, mentions, and /ask command)
│
├── services/
│   ├── __init__.py
│   ├── ai_agent.py           # Mistral client, Hinata prompt context, RAG search, and agentic tools
│   └── image_processor.py    # Pillow and FFmpeg video transcoding helper
│
└── docs/
    └── roadmap.md            # Completed features log & future Todos list
```

---

## 🚀 Setup & Installation

### Prerequisite Dependencies
1. **Python 3.8+**
2. **FFmpeg**: Required for `/kang` video sticker conversion (ensure `ffmpeg` is added to your OS system Path).
3. **Supabase (PostgreSQL)**: Ensure you have a running PostgreSQL database (transaction pooler connection string is recommended).
4. **Mistral API Key**: Sign up at [Mistral Console](https://console.mistral.ai/) and generate an API key.

### Local Installation
1. Clone the repository and navigate to the project directory.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root folder with the following variables:
   ```ini
   BOT_TOKEN=your_telegram_bot_token
   OWNER_ID=your_telegram_user_id
   DATABASE_URL=postgresql://postgres:[password]@[host]:6543/postgres
   MISTRAL_API_KEY=your_mistral_api_key
   ```
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
5. Render will automatically bind to the port defined in `keep_alive.py` (which default to `10000` or the `PORT` env variable) to keep the bot active.

---

## 👮‍♂️ Commands Reference

### 👥 Public Commands
*   `/start` - Shows the start greeting panel and profile links.
*   `/help` - Shows commands overview.
*   `/rules` - Displays the group rules.
*   `/afk [reason]` - Sets your status to sleeping/busy.
*   `/kang` - (Reply-to media) Converts the replied image, GIF, or video into a static or WebM video sticker.
*   `/rank` - Displays your current Custom Title, Level, and XP.
*   `/ranking` (or `/levels`) - Displays the top 10 group leaderboard by XP.
*   `/owner` - Lists the group's creator (owner) and the developer of the bot.

### 🛡️ Admin Commands
*   `/kick` - (Reply-to user) Bans the user and immediately unbans them (removing them from the chat).
*   `/unban` - (Reply-to user) Unbans the user.
*   `/mute` - (Reply-to user) Restricts the user's ability to send messages.
*   `/unmute` - (Reply-to user) Restores message permissions.
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

### 💻 Bot Owner Commands (Owner ID required)
*   `/botstats` - Shows active groups and total AFK users.
*   `/broadcast [message]` - Sends a global announcement to all managed groups.

---

## 📜 License & Project Status

*   **License**: Licensed under the [Inspiration-Only License](LICENSE).
*   **Enhancements and Future Scope**: Check out the completed updates and pending todos in the [Roadmap Guide](docs/roadmap.md).
