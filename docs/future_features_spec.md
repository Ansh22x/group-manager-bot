# Technical Specifications: Advanced Future Features

This document outlines the database schemas, API integrations, and code architectures required to implement the proposed advanced features for **Giyu-Bot**.

---

## 🛡️ 1. Advanced Moderation & Security

### A. New Member Captcha System
*   **Goal**: Mute new users upon joining, present an interactive inline button captcha, and auto-kick them if they fail or timeout.
*   **Telegram Event**: `filters.StatusUpdate.NEW_CHAT_MEMBERS` triggers the validation.
*   **Supabase Schema (`captcha_logs`)**:
    ```sql
    CREATE TABLE IF NOT EXISTS captcha_logs (
        chat_id BIGINT,
        user_id BIGINT,
        correct_answer VARCHAR(50),
        message_id INT, -- Captcha message ID (to delete/edit later)
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (chat_id, user_id)
    );
    ```
*   **Execution Flow**:
    1. A user joins -> Bot calls `context.bot.restrict_chat_member` setting all send permissions to `False`.
    2. Bot generates a simple equation (e.g. `5 + 3 = ?`) and stores the correct answer in `captcha_logs`.
    3. Bot sends a message in the group: *"Welcome [User]. Please solve this within 2 minutes: 5 + 3 = ?"* with multiple-choice inline buttons.
    4. **CallbackQueryHandler**: Captures button presses. If correct, restore chat permissions and delete DB log/message. If incorrect, kick the user.
    5. **JobQueue Scheduler**: Run a background task scheduled for 120 seconds. If the log still exists in the DB, delete the message and kick the user.

### B. Time-Restricted Muting (Temp-Mute)
*   **Goal**: Enable `/tempmute @username 10m` or `/tempmute @username 2h`.
*   **Execution Flow**:
    1. Parse the command arguments using regex matching `(\d+)(m|h|d)` (minutes, hours, days).
    2. Restrict the target user's messaging permissions immediately.
    3. Use python-telegram-bot's `context.job_queue.run_once` to schedule an unmute task:
       ```python
       context.job_queue.run_once(unmute_callback, duration_seconds, data={
           "chat_id": chat_id, 
           "user_id": user_id
       })
       ```
    4. At execution, `unmute_callback` restores the permissions.
*   **Persistence**: If the bot restarts, active temp-mutes in memory will be lost. To prevent this, schedule checks in the database:
    ```sql
    CREATE TABLE IF NOT EXISTS temp_mutes (
        chat_id BIGINT,
        user_id BIGINT,
        unmute_at TIMESTAMP,
        PRIMARY KEY (chat_id, user_id)
    );
    ```
    Upon bot startup in `main.py`, scan `temp_mutes` and re-schedule jobs for any unexpired restrictions.

---

## 🧠 2. AI & RAG Advancements

### A. Demon Slayer Multi-Persona Selector
*   **Goal**: Let admins switch Giyu's personality to other characters (e.g., Tanjiro, Inosuke, Muzan).
*   **Supabase Schema (`chat_characters`)**:
    ```sql
    CREATE TABLE IF NOT EXISTS chat_characters (
        chat_id BIGINT PRIMARY KEY,
        character_name VARCHAR(100) DEFAULT 'giyu'
    );
    ```
*   **Character Definitions (`services/character_lore.py`)**:
    Store prompts and seed chunks for different characters:
    ```python
    CHARACTERS = {
        "giyu": {
            "prompt": "You are Giyu Tomioka...",
            "chunks": ["Giyu is the Water Hashira...", "Giyu is stoic..."]
        },
        "tanjiro": {
            "prompt": "You are Tanjiro Kamado, a kind, empathetic, and earnest Demon Slayer. You speak warmly, use Sun Breathing references, and show deep concern for others...",
            "chunks": ["Tanjiro is kind-hearted...", "Tanjiro uses Sun/Water Breathing..."]
        }
    }
    ```
*   **Transition Execution**:
    1. Admin calls `/setchar tanjiro`.
    2. Bot updates `chat_characters` setting character to `tanjiro`.
    3. Bot clears RAG lore tables for this specific chat, or dynamically queries embeddings filtered by a `character` column:
       ```sql
       -- Refactored bot_lore schema to support multi-character RAG
       ALTER TABLE bot_lore ADD COLUMN IF NOT EXISTS character_name VARCHAR(100) DEFAULT 'giyu';
       ```
    4. When querying similarities, filter by the active character:
       `SELECT content FROM bot_lore WHERE character_name = %s ORDER BY embedding <=> %s::vector LIMIT 2;`

---

## 🎮 3. Group Economy System

*   **Goal**: Incentivize users to chat by rewarding them with coins that can be spent in an interactive shop.
*   **Supabase Schema**:
    ```sql
    -- Wallet balances
    CREATE TABLE IF NOT EXISTS economy_wallets (
        chat_id BIGINT,
        user_id BIGINT,
        balance INT DEFAULT 0,
        PRIMARY KEY (chat_id, user_id)
    );

    -- Shop Items
    CREATE TABLE IF NOT EXISTS shop_items (
        item_id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        cost INT NOT NULL,
        description TEXT
    );
    ```
*   **Code Implementation**:
    1. **Earning**: In `handlers/leveling_handler.py`, award 1-5 coins per message (with a cooldown matching the XP timer).
    2. **Shop Command (`/shop`)**: Displays available items (e.g. *Mute Shield*, *Custom Tag Title*, *Double XP Token*) via Inline Keyboard.
    3. **Buying Command (`/buy <item_id>`)**: Validates the wallet balance, subtracts the cost, and applies the item (e.g., updates `users.tag` if they bought a Custom Title).

---

## 💻 4. Next.js Admin Panel Dashboard

*   **Goal**: Manage settings, view logs, and edit filters from a web browser.
*   **Authentication**: Use **Telegram Login Widget**. When a user logs in, Telegram sends queries (`id`, `first_name`, `username`, `photo_url`, `auth_date`, `hash`).
*   **Security (Hash Validation)**: Next.js API validates the widget parameter signature using the bot's secret key (`SHA-256` of `BOT_TOKEN`):
    ```javascript
    // Next.js Route validation logic
    import crypto from 'crypto';
    
    function checkTelegramAuth(data, botToken) {
      const secret = crypto.createHash('sha256').update(botToken).digest();
      const checkString = Object.keys(data)
        .filter(key => key !== 'hash')
        .sort()
        .map(key => `${key}=${data[key]}`)
        .join('\n');
      const hash = crypto.createHmac('sha256', secret).update(checkString).digest('hex');
      return hash === data.hash;
    }
    ```
*   **Web Portal Features**:
    - **Dashboard UI**: Next.js (shadcn/ui + TailwindCSS).
    - **Settings Editor**: Forms to edit `welcome_msg` and `rules` that call API endpoints, writing changes to `chats` table.
    - **RAG Log Viewer**: View database-backed chat histories for security auditing.
