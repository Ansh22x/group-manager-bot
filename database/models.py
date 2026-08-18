import time
import json
from database import get_db_connection, release_db_connection

def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Enable pgvector extension for Supabase
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                conn.commit()
                print("pgvector extension ensured in database.")
            except Exception as ve:
                conn.rollback()
                print(f"WARNING: Could not create pgvector extension: {ve}. Vector search might fail.")

            # Create chats table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id BIGINT PRIMARY KEY,
                    rules TEXT DEFAULT 'No rules have been set for this group yet.',
                    welcome_msg TEXT DEFAULT 'Welcome to the group, {name}!',
                    welcome_on BOOLEAN DEFAULT TRUE,
                    afk_on BOOLEAN DEFAULT TRUE
                );
            """)
            # Create warnings table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    chat_id BIGINT,
                    user_id BIGINT,
                    warn_count INT DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create custom_tags table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS custom_tags (
                    chat_id BIGINT,
                    tag VARCHAR(100),
                    reply TEXT,
                    PRIMARY KEY (chat_id, tag)
                );
            """)
            # Create custom_filters table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS custom_filters (
                    chat_id BIGINT,
                    keyword VARCHAR(255),
                    reply TEXT,
                    PRIMARY KEY (chat_id, keyword)
                );
            """)
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id BIGINT,
                    user_id BIGINT,
                    xp INT DEFAULT 0,
                    level INT DEFAULT 1,
                    last_xp_time DOUBLE PRECISION DEFAULT 0,
                    tag VARCHAR(100) DEFAULT 'Member',
                    name VARCHAR(255),
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create afk_users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS afk_users (
                    user_id BIGINT PRIMARY KEY,
                    reason TEXT
                );
            """)
            # Create bot_lore table for character traits RAG system
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_lore (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector(1024)
                );
            """)
            # Create chat_history table for bot conversational memory
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            print("Database tables initialized successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error initializing tables: {e}")
        raise e
    finally:
        release_db_connection(conn)

# --- CHATS SETTINGS HELPERS ---
def get_chat_settings(chat_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rules, welcome_msg, welcome_on, afk_on FROM chats WHERE chat_id = %s;", (chat_id,))
            res = cur.fetchone()
            if not res:
                # Insert default settings
                cur.execute(
                    "INSERT INTO chats (chat_id) VALUES (%s) RETURNING rules, welcome_msg, welcome_on, afk_on;",
                    (chat_id,)
                )
                res = cur.fetchone()
                conn.commit()
            return {
                'rules': res[0],
                'welcome_msg': res[1],
                'welcome_on': res[2],
                'afk_on': res[3]
            }
    except Exception as e:
        print(f"Error in get_chat_settings: {e}")
        return {
            'rules': "No rules have been set for this group yet.",
            'welcome_msg': "Welcome to the group, {name}!",
            'welcome_on': True,
            'afk_on': True
        }
    finally:
        release_db_connection(conn)

def update_chat_settings(chat_id: int, **kwargs):
    conn = get_db_connection()
    try:
        # Check if chat exists
        get_chat_settings(chat_id)
        with conn.cursor() as cur:
            for field, val in kwargs.items():
                if field in ['rules', 'welcome_msg', 'welcome_on', 'afk_on']:
                    cur.execute(f"UPDATE chats SET {field} = %s WHERE chat_id = %s;", (val, chat_id))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in update_chat_settings: {e}")
    finally:
        release_db_connection(conn)

# --- WARNINGS HELPERS ---
def get_warnings(chat_id: int, user_id: int) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT warn_count FROM warnings WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
            res = cur.fetchone()
            return res[0] if res else 0
    except Exception as e:
        print(f"Error in get_warnings: {e}")
        return 0
    finally:
        release_db_connection(conn)

def add_warning(chat_id: int, user_id: int) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO warnings (chat_id, user_id, warn_count) 
                VALUES (%s, %s, 1) 
                ON CONFLICT (chat_id, user_id) 
                DO UPDATE SET warn_count = warnings.warn_count + 1 
                RETURNING warn_count;
            """, (chat_id, user_id))
            res = cur.fetchone()
            conn.commit()
            return res[0] if res else 1
    except Exception as e:
        conn.rollback()
        print(f"Error in add_warning: {e}")
        return 1
    finally:
        release_db_connection(conn)

def remove_warning(chat_id: int, user_id: int) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO warnings (chat_id, user_id, warn_count) 
                VALUES (%s, %s, 0) 
                ON CONFLICT (chat_id, user_id) 
                DO UPDATE SET warn_count = GREATEST(0, warnings.warn_count - 1) 
                RETURNING warn_count;
            """, (chat_id, user_id))
            res = cur.fetchone()
            conn.commit()
            return res[0] if res else 0
    except Exception as e:
        conn.rollback()
        print(f"Error in remove_warning: {e}")
        return 0
    finally:
        release_db_connection(conn)

def reset_warnings(chat_id: int, user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM warnings WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in reset_warnings: {e}")
    finally:
        release_db_connection(conn)

# --- CUSTOM TAGS HELPERS ---
def get_tags(chat_id: int) -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tag, reply FROM custom_tags WHERE chat_id = %s;", (chat_id,))
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        print(f"Error in get_tags: {e}")
        return {}
    finally:
        release_db_connection(conn)

def add_tag(chat_id: int, tag: str, reply: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO custom_tags (chat_id, tag, reply) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (chat_id, tag) 
                DO UPDATE SET reply = EXCLUDED.reply;
            """, (chat_id, tag.lower(), reply))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in add_tag: {e}")
    finally:
        release_db_connection(conn)

# --- CUSTOM FILTERS HELPERS ---
def get_filters(chat_id: int) -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT keyword, reply FROM custom_filters WHERE chat_id = %s;", (chat_id,))
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        print(f"Error in get_filters: {e}")
        return {}
    finally:
        release_db_connection(conn)

def add_filter(chat_id: int, keyword: str, reply: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO custom_filters (chat_id, keyword, reply) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (chat_id, keyword) 
                DO UPDATE SET reply = EXCLUDED.reply;
            """, (chat_id, keyword.lower(), reply))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in add_filter: {e}")
    finally:
        release_db_connection(conn)

# --- USER LEVELS HELPERS ---
def get_user_stats(chat_id: int, user_id: int, name: str = "Member") -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT xp, level, last_xp_time, tag, name FROM users WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
            res = cur.fetchone()
            if not res:
                # Create user
                cur.execute("""
                    INSERT INTO users (chat_id, user_id, xp, level, last_xp_time, tag, name) 
                    VALUES (%s, %s, 0, 1, 0, 'Member', %s) 
                    RETURNING xp, level, last_xp_time, tag, name;
                """, (chat_id, user_id, name))
                res = cur.fetchone()
                conn.commit()
            return {
                'xp': res[0],
                'level': res[1],
                'last_xp_time': res[2],
                'tag': res[3],
                'name': res[4]
            }
    except Exception as e:
        print(f"Error in get_user_stats: {e}")
        return {'xp': 0, 'level': 1, 'last_xp_time': 0, 'tag': 'Member', 'name': name}
    finally:
        release_db_connection(conn)

def update_user_stats(chat_id: int, user_id: int, **kwargs):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for field, val in kwargs.items():
                if field in ['xp', 'level', 'last_xp_time', 'tag', 'name']:
                    cur.execute(f"UPDATE users SET {field} = %s WHERE chat_id = %s AND user_id = %s;", (val, chat_id, user_id))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in update_user_stats: {e}")
    finally:
        release_db_connection(conn)

def get_top_users(chat_id: int, limit: int = 10):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name, level, tag, xp FROM users WHERE chat_id = %s ORDER BY xp DESC LIMIT %s;", (chat_id, limit))
            return [{'name': row[0], 'level': row[1], 'tag': row[2], 'xp': row[3]} for row in cur.fetchall()]
    except Exception as e:
        print(f"Error in get_top_users: {e}")
        return []
    finally:
        release_db_connection(conn)

# --- AFK HELPERS ---
def get_afk_users() -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, reason FROM afk_users;")
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        print(f"Error in get_afk_users: {e}")
        return {}
    finally:
        release_db_connection(conn)

def set_user_afk(user_id: int, reason: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO afk_users (user_id, reason) 
                VALUES (%s, %s) 
                ON CONFLICT (user_id) 
                DO UPDATE SET reason = EXCLUDED.reason;
            """, (user_id, reason))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in set_user_afk: {e}")
    finally:
        release_db_connection(conn)

def remove_user_afk(user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM afk_users WHERE user_id = %s;", (user_id,))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in remove_user_afk: {e}")
    finally:
        release_db_connection(conn)

# --- RAG / BOT LORE HELPERS ---
def is_lore_empty() -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bot_lore;")
            count = cur.fetchone()[0]
            return count == 0
    except Exception as e:
        print(f"Error checking if lore empty: {e}")
        return True
    finally:
        release_db_connection(conn)

def insert_lore(content: str, embedding: list):
    conn = get_db_connection()
    try:
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bot_lore (content, embedding) VALUES (%s, %s::vector);",
                (content, embedding_str)
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error inserting lore: {e}")
    finally:
        release_db_connection(conn)

def get_similar_lore(embedding: list, limit: int = 3) -> list:
    conn = get_db_connection()
    try:
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM bot_lore ORDER BY embedding <=> %s::vector LIMIT %s;",
                (embedding_str, limit)
            )
            return [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error querying similar lore: {e}")
        return []
    finally:
        release_db_connection(conn)

# --- CHAT MEMORY HELPERS ---
def add_chat_history(chat_id: int, role: str, name: str, content: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (chat_id, role, name, content) VALUES (%s, %s, %s, %s);",
                (chat_id, role, name, content)
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error adding chat history: {e}")
    finally:
        release_db_connection(conn)

def get_chat_history(chat_id: int, limit: int = 10) -> list:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, name, content FROM chat_history WHERE chat_id = %s ORDER BY created_at DESC LIMIT %s;",
                (chat_id, limit)
            )
            rows = cur.fetchall()
            # Since we fetched DESC (newest first), we reverse it to get ASC order (oldest to newest)
            return [(r[0], r[1], r[2]) for r in reversed(rows)]
    except Exception as e:
        print(f"Error fetching chat history: {e}")
        return []
    finally:
        release_db_connection(conn)
