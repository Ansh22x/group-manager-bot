# Technical Specifications: Advanced Bot Features

This document outlines the database schemas, API integrations, and code architectures implemented for **Giyu-Bot**'s advanced capabilities, including core moderation modules and the Graph-RAG engine.

---

## 🛡️ 1. Core Moderation & Security [IMPLEMENTED]

### A. New Member Captcha System
*   **Goal**: Mute new users upon joining, present an interactive addition captcha prompt with inline buttons, and auto-kick them on timeout or incorrect responses.
*   **Telegram Event**: `filters.StatusUpdate.NEW_CHAT_MEMBERS` captured in [`CaptchaHandler`](file:///c:/Desktop/Stand-Up/Projects/TG-Group-Manage-bot/group-manager-bot/handlers/captcha_handler.py).
*   **Supabase Schema (`captcha_logs`)**:
    ```sql
    CREATE TABLE IF NOT EXISTS captcha_logs (
        chat_id BIGINT,
        user_id BIGINT,
        correct_answer VARCHAR(50),
        message_id INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (chat_id, user_id)
    );
    ```
*   **Execution Flow**:
    1. A user joins -> Bot calls `context.bot.restrict_chat_member` setting all messaging permissions to `False`.
    2. Generates a randomized simple addition problem (e.g. `4 + 5 = ?`) and stores the correct answer in `captcha_logs`.
    3. Sends an interactive inline button prompt listing correct and incorrect options.
    4. **CallbackQueryHandler**: If correct answer is clicked, restores default group permissions and deletes the verification message. If wrong, bans and unbans the user to kick them.
    5. **JobQueue Scheduler**: Spawns a 120-second timeout task. If the log entry is still present, deletes the prompt and kicks the user.

### B. Time-Restricted Muting (Temp-Mute)
*   **Goal**: Enable `/tempmute @username [duration]` (e.g. `10m`, `2h`, `1d`) to silence users temporarily.
*   **Supabase Schema (`temp_mutes`)**:
    ```sql
    CREATE TABLE IF NOT EXISTS temp_mutes (
        chat_id BIGINT,
        user_id BIGINT,
        unmute_at TIMESTAMP,
        PRIMARY KEY (chat_id, user_id)
    );
    ```
*   **Execution Flow**:
    1. Parse the command duration using regex `^(\d+)([smhd])$`.
    2. Set `can_send_messages=False` via `restrict_chat_member()`.
    3. Persist the unmute timestamp (`unmute_at`) in `temp_mutes`.
    4. Register a release callback in the `JobQueue`. Upon trigger, restore group permissions and clean up the database log.
    5. **Startup Recovery**: On startup inside `main.py`, the scheduler queries the database for active unmute times, calculates the remaining durations, and schedules background release jobs for any pending temp-mutes.

---

## 🧠 2. AI Character & Persona Selector [IMPLEMENTED]

*   **Goal**: Allow group administrators to swap Giyu-Bot's AI persona dynamically via `/setchar`.
*   **Supabase Schema (`chat_characters`)**:
    ```sql
    CREATE TABLE IF NOT EXISTS chat_characters (
        chat_id BIGINT PRIMARY KEY,
        character_name VARCHAR(100) DEFAULT 'giyu'
    );
    ```
*   **Supported Personas**:
    - `giyu`: Stoic, blunt, quiet Water Hashira.
    - `tanjiro`: Kind, earnest, Hinokami Kagura/Water Breathing user.
    - `nezuko`: Speaks in sounds (`Mmph!`) with translations in parentheses.
    - `shinobu`: Melodic, smiling, teasing Insect Hashira.
*   **RAG Partitioning**:
    - The vector database `bot_lore` matches trait similarity filtered by a `character_name` column:
      ```sql
      ALTER TABLE bot_lore ADD COLUMN character_name VARCHAR(100) DEFAULT 'giyu';
      ```

---

## 🕸️ 3. Knowledge Graph & Graph-RAG System [IMPLEMENTED]

*   **Goal**: Model relationships and connections between entities (e.g. characters, organizations, items) in a structured relational format. Use this to complement semantic vector search with strict logical relationship retrieval.
*   **Supabase Schema (`knowledge_graph`)**:
    ```sql
    CREATE TABLE IF NOT EXISTS knowledge_graph (
        id SERIAL PRIMARY KEY,
        subject VARCHAR(255) NOT NULL,
        predicate VARCHAR(100) NOT NULL,
        object VARCHAR(255) NOT NULL,
        character_name VARCHAR(100) DEFAULT 'giyu'
    );

    CREATE INDEX IF NOT EXISTS idx_kg_subject ON knowledge_graph (LOWER(subject));
    CREATE INDEX IF NOT EXISTS idx_kg_object ON knowledge_graph (LOWER(object));
    ```
*   **Retrieval Mechanics (Graph-RAG)**:
    1. **Pre-emptive Scan**: The `AIAgent` scans the user prompt for known names/entities (e.g. *Sabito*, *Shinobu*).
    2. **Triplet Search**: Fetches matching triples where the entity is the subject or object.
    3. **Context Injection**: Formats matching relationships cleanly as `(Subject) --[Predicate]--> (Object)` and appends them to the system prompt context.
    4. **Agentic Tool call (`query_knowledge_graph`)**: Exposes a database search tool to the Mistral AI model. The agent can invoke this tool programmatically to query connections dynamically during conversations.

---

## 🎮 4. Group Economy System [IMPLEMENTED]

*   **Goal**: Incentivize user chat participation by rewarding activity with virtual coins.
*   **Supabase Schema**:
    ```sql
    CREATE TABLE IF NOT EXISTS economy_wallets (
        chat_id BIGINT,
        user_id BIGINT,
        balance INT DEFAULT 0,
        PRIMARY KEY (chat_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS shop_items (
        item_id INT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        cost INT NOT NULL,
        description TEXT
    );
    ```
*   **Shop Offerings**:
    - **Item 1**: Custom Title Tag (200 coins). Updates a user's display title tag in database.
    - **Item 2**: Warning Cleanse (150 coins). Removes a warn strike.
    - **Item 3**: Water Breathing License (100 coins).
*   **Execution Flow**:
    - Active users receive `5-10` coins per message, synchronized with the leveling system's 1-minute cooldown.
    - Users can view goods via `/shop` and make purchases via `/buy [item_id] [arguments]`.
