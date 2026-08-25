import logging
import datetime
from database.db_manager import DatabaseManager
from config import is_bot_owner

logger = logging.getLogger(__name__)


def setup_db_schema():
    """Bootstraps the database tables and pgvector extension if not exists"""
    db = DatabaseManager()
    conn = db.get_connection()
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

            # Enable pgcrypto extension for data encryption at rest
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                conn.commit()
                print("pgcrypto extension ensured in database.")
            except Exception as pe:
                conn.rollback()
                print(f"WARNING: Could not create pgcrypto extension: {pe}. Data encryption might fail.")

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
            
            # Recreate chat_history with BYTEA format if it is currently text
            cur.execute("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = 'chat_history' AND column_name = 'content';
            """)
            col_type = cur.fetchone()
            if col_type and col_type[0] != 'bytea':
                print("setup_db_schema: Migrating chat_history content column to BYTEA...")
                cur.execute("DROP TABLE IF EXISTS chat_history;")
                conn.commit()

            # Create chat_history table for bot conversational memory (encrypting content as BYTEA)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    content BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Create captcha_logs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS captcha_logs (
                    chat_id BIGINT,
                    user_id BIGINT,
                    correct_answer VARCHAR(50),
                    message_id INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create temp_mutes table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS temp_mutes (
                    chat_id BIGINT,
                    user_id BIGINT,
                    unmute_at TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create chat_characters table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_characters (
                    chat_id BIGINT PRIMARY KEY,
                    character_name VARCHAR(100) DEFAULT 'giyu'
                );
            """)
            # Create economy_wallets table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS economy_wallets (
                    chat_id BIGINT,
                    user_id BIGINT,
                    balance INT DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create shop_items table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    item_id INT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    cost INT NOT NULL,
                    description TEXT
                );
            """)
            # Seed default shop items if empty
            cur.execute("SELECT COUNT(*) FROM shop_items;")
            if cur.fetchone()[0] == 0:
                cur.execute("""
                    INSERT INTO shop_items (item_id, name, cost, description) VALUES
                    (1, 'Custom Title Tag', 200, 'Changes your leveling rank title/tag to anything you choose!'),
                    (2, 'Warning Cleanse', 150, 'Removes 1 warning strike from your profile.'),
                    (3, 'Water Breathing License', 100, 'Unlocks special Giyu Water Breathing stickers!');
                """)
            
            # Alter bot_lore to add character_name column
            cur.execute("ALTER TABLE bot_lore ADD COLUMN IF NOT EXISTS character_name VARCHAR(100) DEFAULT 'giyu';")

            # Alter users to add message_count column for analytics
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS message_count INT DEFAULT 0;")
            
            # Create giveaway_alerts table for persistent real-time freebie alerts
            cur.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_alerts (
                    giveaway_id INT PRIMARY KEY,
                    title TEXT,
                    alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # --- ENABLE ROW LEVEL SECURITY (RLS) ---
            cur.execute("ALTER TABLE chats ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE warnings ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;")

            # Create default RLS access policies for authenticated dashboard web-panel users
            cur.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'authenticated_chats_policy') THEN
                        CREATE POLICY authenticated_chats_policy ON chats
                        FOR ALL TO authenticated
                        USING (chat_id IN (SELECT chat_id FROM users WHERE user_id = auth.uid()::text::bigint));
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'authenticated_users_policy') THEN
                        CREATE POLICY authenticated_users_policy ON users
                        FOR ALL TO authenticated
                        USING (chat_id IN (SELECT chat_id FROM users WHERE user_id = auth.uid()::text::bigint));
                    END IF;
                END $$;
            """)

            # Create knowledge_graph table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    id SERIAL PRIMARY KEY,
                    subject VARCHAR(255) NOT NULL,
                    predicate VARCHAR(100) NOT NULL,
                    object VARCHAR(255) NOT NULL,
                    character_name VARCHAR(100) DEFAULT 'giyu'
                );
            """)
            # Create bot_memories table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_memories (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT,
                    memory_key VARCHAR(255) NOT NULL,
                    memory_value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_chat_user_mem UNIQUE (chat_id, user_id, memory_key)
                );
            """)

            # Create bot_stats table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_stats (
                    chat_id BIGINT PRIMARY KEY,
                    xp INT DEFAULT 0,
                    level INT DEFAULT 1,
                    unlocked_skills TEXT DEFAULT 'water_breathing_1',
                    traits TEXT DEFAULT '{"stoic": 80, "friendly": 20, "energy": 50}'
                );
            """)

            # Create bot_sticker_stock table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_sticker_stock (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    file_id VARCHAR(255) NOT NULL,
                    emoji VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_chat_sticker UNIQUE (chat_id, file_id)
                );
            """)

            conn.commit()
            print("Database schema and security constraints verified and loaded.")
    except Exception as e:
        conn.rollback()
        print(f"Error seeding database schema: {e}")
        raise e
    finally:
        db.release_connection(conn)


class BaseRepository:
    def __init__(self):
        self.db = DatabaseManager()
        # Derive master key from BOT_TOKEN to encrypt column data securely at rest
        from config import BOT_TOKEN
        self.master_key = BOT_TOKEN if BOT_TOKEN else "GiyuWaterBreathingMasterKey123"


class ChatRepository(BaseRepository):
    def get_chat_settings(self, chat_id: int) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT rules, welcome_msg, welcome_on, afk_on FROM chats WHERE chat_id = %s;", (chat_id,))
                res = cur.fetchone()
                if not res:
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
            print(f"Error in ChatRepository.get_chat_settings: {e}")
            return {
                'rules': "No rules have been set for this group yet.",
                'welcome_msg': "Welcome to the group, {name}!",
                'welcome_on': True,
                'afk_on': True
            }
        finally:
            self.db.release_connection(conn)

    def update_chat_settings(self, chat_id: int, **kwargs):
        conn = self.db.get_connection()
        try:
            self.get_chat_settings(chat_id)  # Ensure exists
            with conn.cursor() as cur:
                for field, val in kwargs.items():
                    if field in ['rules', 'welcome_msg', 'welcome_on', 'afk_on']:
                        cur.execute(f"UPDATE chats SET {field} = %s WHERE chat_id = %s;", (val, chat_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in ChatRepository.update_chat_settings: {e}")
        finally:
            self.db.release_connection(conn)


class WarningRepository(BaseRepository):
    def get_warnings(self, chat_id: int, user_id: int) -> int:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT warn_count FROM warnings WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                res = cur.fetchone()
                return res[0] if res else 0
        except Exception as e:
            print(f"Error in WarningRepository.get_warnings: {e}")
            return 0
        finally:
            self.db.release_connection(conn)

    def add_warning(self, chat_id: int, user_id: int) -> int:
        conn = self.db.get_connection()
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
            print(f"Error in WarningRepository.add_warning: {e}")
            return 1
        finally:
            self.db.release_connection(conn)

    def remove_warning(self, chat_id: int, user_id: int) -> int:
        conn = self.db.get_connection()
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
            print(f"Error in WarningRepository.remove_warning: {e}")
            return 0
        finally:
            self.db.release_connection(conn)

    def reset_warnings(self, chat_id: int, user_id: int):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM warnings WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in WarningRepository.reset_warnings: {e}")
        finally:
            self.db.release_connection(conn)


class TagRepository(BaseRepository):
    def get_tags(self, chat_id: int) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT tag, reply FROM custom_tags WHERE chat_id = %s;", (chat_id,))
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception as e:
            print(f"Error in TagRepository.get_tags: {e}")
            return {}
        finally:
            self.db.release_connection(conn)

    def add_tag(self, chat_id: int, tag: str, reply: str):
        conn = self.db.get_connection()
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
            print(f"Error in TagRepository.add_tag: {e}")
        finally:
            self.db.release_connection(conn)


class FilterRepository(BaseRepository):
    def get_filters(self, chat_id: int) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT keyword, reply FROM custom_filters WHERE chat_id = %s;", (chat_id,))
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception as e:
            print(f"Error in FilterRepository.get_filters: {e}")
            return {}
        finally:
            self.db.release_connection(conn)

    def add_filter(self, chat_id: int, keyword: str, reply: str):
        conn = self.db.get_connection()
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
            print(f"Error in FilterRepository.add_filter: {e}")
        finally:
            self.db.release_connection(conn)


class UserRepository(BaseRepository):
    def get_user_stats(self, chat_id: int, user_id: int, name: str = "Member") -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT xp, level, last_xp_time, tag, name, message_count FROM users WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                res = cur.fetchone()
                if not res:
                    cur.execute("""
                        INSERT INTO users (chat_id, user_id, xp, level, last_xp_time, tag, name, message_count) 
                        VALUES (%s, %s, 0, 1, 0, 'Member', %s, 0) 
                        RETURNING xp, level, last_xp_time, tag, name, message_count;
                    """, (chat_id, user_id, name))
                    res = cur.fetchone()
                    conn.commit()

                # 👑 GLOBAL OWNER OVERRIDE: Automatically assigns max level and Owner tag
                is_owner = is_bot_owner(user_id)
                
                return {
                    'xp': res[0],
                    'level': 999 if is_owner else res[1],
                    'last_xp_time': res[2],
                    'tag': '👑 Bot Creator / Owner' if is_owner else res[3],
                    'name': res[4],
                    'message_count': res[5]
                }
        except Exception as e:
            logger.error(f"Error in UserRepository.get_user_stats: {e}")
            is_owner = is_bot_owner(user_id)
            return {'xp': 0, 'level': 999 if is_owner else 1, 'last_xp_time': 0, 'tag': '👑 Bot Creator / Owner' if is_owner else 'Member', 'name': name, 'message_count': 0}
        finally:
            self.db.release_connection(conn)

    def update_user_stats(self, chat_id: int, user_id: int, **kwargs):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                for field, val in kwargs.items():
                    if field in ['xp', 'level', 'last_xp_time', 'tag', 'name', 'message_count']:
                        cur.execute(f"UPDATE users SET {field} = %s WHERE chat_id = %s AND user_id = %s;", (val, chat_id, user_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in UserRepository.update_user_stats: {e}")
        finally:
            self.db.release_connection(conn)

    def increment_message_count(self, chat_id: int, user_id: int):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET message_count = message_count + 1 WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
        finally:
            self.db.release_connection(conn)

    def get_chat_summary_stats(self, chat_id: int) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*), MAX(level), SUM(xp), SUM(message_count) FROM users WHERE chat_id = %s;", (chat_id,))
                row = cur.fetchone()
                return {
                    "total_members": row[0] if row else 0,
                    "max_level": row[1] if row and row[1] else 1,
                    "total_xp": row[2] if row and row[2] else 0,
                    "total_messages": row[3] if row and row[3] else 0
                }
        except Exception:
            return {"total_members": 0, "max_level": 1, "total_xp": 0, "total_messages": 0}
        finally:
            self.db.release_connection(conn)

    def get_top_users(self, chat_id: int, limit: int = 10) -> list:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name, level, tag, xp, message_count FROM users WHERE chat_id = %s ORDER BY xp DESC LIMIT %s;", (chat_id, limit))
                return [{'name': row[0], 'level': row[1], 'tag': row[2], 'xp': row[3], 'message_count': row[4]} for row in cur.fetchall()]
        except Exception:
            return []
        finally:
            self.db.release_connection(conn)


class AFKRepository(BaseRepository):
    def get_afk_users(self) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, reason FROM afk_users;")
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception as e:
            print(f"Error in AFKRepository.get_afk_users: {e}")
            return {}
        finally:
            self.db.release_connection(conn)

    def set_user_afk(self, user_id: int, reason: str):
        conn = self.db.get_connection()
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
            print(f"Error in AFKRepository.set_user_afk: {e}")
        finally:
            self.db.release_connection(conn)

    def remove_user_afk(self, user_id: int):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM afk_users WHERE user_id = %s;", (user_id,))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in AFKRepository.remove_user_afk: {e}")
        finally:
            self.db.release_connection(conn)


class LoreRepository(BaseRepository):
    def is_lore_empty(self) -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bot_lore;")
                count = cur.fetchone()[0]
                return count == 0
        except Exception as e:
            print(f"Error in LoreRepository.is_lore_empty: {e}")
            return True
        finally:
            self.db.release_connection(conn)

    def clear_lore(self, character_name: str = "giyu"):
        """Clears seeded bot lore for a specific character"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bot_lore WHERE character_name = %s;", (character_name.lower(),))
                conn.commit()
                print(f"LoreRepository: Cleared bot_lore table for character '{character_name}'.")
        except Exception as e:
            conn.rollback()
            print(f"Error in LoreRepository.clear_lore: {e}")
        finally:
            self.db.release_connection(conn)

    def get_first_lore_chunk(self, character_name: str = "giyu") -> str:
        """Retrieves the first chunk content for a specific character"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT content FROM bot_lore WHERE character_name = %s LIMIT 1;", (character_name.lower(),))
                res = cur.fetchone()
                return res[0] if res else ""
        except Exception as e:
            print(f"Error in LoreRepository.get_first_lore_chunk: {e}")
            return ""
        finally:
            self.db.release_connection(conn)

    def insert_lore(self, content: str, embedding: list, character_name: str = "giyu"):
        conn = self.db.get_connection()
        try:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO bot_lore (content, embedding, character_name) VALUES (%s, %s::vector, %s);",
                    (content, embedding_str, character_name.lower())
                )
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in LoreRepository.insert_lore: {e}")
        finally:
            self.db.release_connection(conn)

    def get_similar_lore(self, embedding: list, character_name: str = "giyu", limit: int = 3) -> list:
        conn = self.db.get_connection()
        try:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content FROM bot_lore WHERE character_name = %s ORDER BY embedding <=> %s::vector LIMIT %s;",
                    (character_name.lower(), embedding_str, limit)
                )
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            print(f"Error in LoreRepository.get_similar_lore: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    def get_similar_lore_with_scores(self, embedding: list, character_name: str = "giyu", limit: int = 5) -> list:
        """Returns list of (content, cosine_similarity_score) tuples, ordered by relevance.
        Cosine similarity is computed as 1 - cosine_distance (pgvector uses <=> operator for distance).
        """
        conn = self.db.get_connection()
        try:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content, 1 - (embedding <=> %s::vector) AS score FROM bot_lore WHERE character_name = %s ORDER BY score DESC LIMIT %s;",
                    (embedding_str, character_name.lower(), limit)
                )
                return [(row[0], float(row[1])) for row in cur.fetchall()]
        except Exception as e:
            print(f"Error in LoreRepository.get_similar_lore_with_scores: {e}")
            return []
        finally:
            self.db.release_connection(conn)


class HistoryRepository(BaseRepository):
    def add_chat_history(self, chat_id: int, role: str, name: str, content: str):
        """Encrypts content before inserting it into Supabase via symmetric pgp keys"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat_history (chat_id, role, name, content) VALUES (%s, %s, %s, pgp_sym_encrypt(%s, %s));",
                    (chat_id, role, name, content, self.master_key)
                )
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in HistoryRepository.add_chat_history: {e}")
        finally:
            self.db.release_connection(conn)

    def get_chat_history(self, chat_id: int, limit: int = 10) -> list:
        """Decrypts content dynamically when loading past logs into AI memory"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT role, name, pgp_sym_decrypt(content, %s) FROM chat_history WHERE chat_id = %s ORDER BY created_at DESC LIMIT %s;",
                    (self.master_key, chat_id, limit)
                )
                rows = cur.fetchall()
                return [(r[0], r[1], r[2]) for r in reversed(rows)]
        except Exception as e:
            print(f"Error in HistoryRepository.get_chat_history: {e}")
            return []
        finally:
            self.db.release_connection(conn)


# --- REPOSITORIES FOR ADVANCED FEATURES ---

class CaptchaRepository(BaseRepository):
    def add_captcha_log(self, chat_id: int, user_id: int, correct_answer: str, message_id: int):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO captcha_logs (chat_id, user_id, correct_answer, message_id) 
                    VALUES (%s, %s, %s, %s) 
                    ON CONFLICT (chat_id, user_id) 
                    DO UPDATE SET correct_answer = EXCLUDED.correct_answer, message_id = EXCLUDED.message_id;
                """, (chat_id, user_id, correct_answer, message_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in CaptchaRepository.add_captcha_log: {e}")
        finally:
            self.db.release_connection(conn)

    def get_captcha_log(self, chat_id: int, user_id: int) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT correct_answer, message_id FROM captcha_logs WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                res = cur.fetchone()
                return {"correct_answer": res[0], "message_id": res[1]} if res else {}
        except Exception as e:
            print(f"Error in CaptchaRepository.get_captcha_log: {e}")
            return {}
        finally:
            self.db.release_connection(conn)

    def remove_captcha_log(self, chat_id: int, user_id: int):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM captcha_logs WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in CaptchaRepository.remove_captcha_log: {e}")
        finally:
            self.db.release_connection(conn)


class TempMuteRepository(BaseRepository):
    def add_temp_mute(self, chat_id: int, user_id: int, unmute_at: float):
        conn = self.db.get_connection()
        unmute_dt = datetime.datetime.fromtimestamp(unmute_at)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO temp_mutes (chat_id, user_id, unmute_at) 
                    VALUES (%s, %s, %s) 
                    ON CONFLICT (chat_id, user_id) 
                    DO UPDATE SET unmute_at = EXCLUDED.unmute_at;
                """, (chat_id, user_id, unmute_dt))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in TempMuteRepository.add_temp_mute: {e}")
        finally:
            self.db.release_connection(conn)

    def remove_temp_mute(self, chat_id: int, user_id: int):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM temp_mutes WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in TempMuteRepository.remove_temp_mute: {e}")
        finally:
            self.db.release_connection(conn)

    def get_expired_mutes(self) -> list:
        conn = self.db.get_connection()
        now = datetime.datetime.now()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id, user_id FROM temp_mutes WHERE unmute_at <= %s;", (now,))
                return [{"chat_id": row[0], "user_id": row[1]} for row in cur.fetchall()]
        except Exception as e:
            print(f"Error in TempMuteRepository.get_expired_mutes: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    def get_all_pending_mutes(self) -> list:
        conn = self.db.get_connection()
        now = datetime.datetime.now()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id, user_id, unmute_at FROM temp_mutes WHERE unmute_at > %s;", (now,))
                return [{"chat_id": row[0], "user_id": row[1], "unmute_at": row[2].timestamp()} for row in cur.fetchall()]
        except Exception as e:
            print(f"Error in TempMuteRepository.get_all_pending_mutes: {e}")
            return []
        finally:
            self.db.release_connection(conn)


class CharacterRepository(BaseRepository):
    def get_chat_character(self, chat_id: int) -> str:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT character_name FROM chat_characters WHERE chat_id = %s;", (chat_id,))
                res = cur.fetchone()
                if not res:
                    cur.execute("INSERT INTO chat_characters (chat_id, character_name) VALUES (%s, 'giyu') RETURNING character_name;", (chat_id,))
                    res = cur.fetchone()
                    conn.commit()
                return res[0] if res else 'giyu'
        except Exception as e:
            print(f"Error in CharacterRepository.get_chat_character: {e}")
            return 'giyu'
        finally:
            self.db.release_connection(conn)

    def set_chat_character(self, chat_id: int, character_name: str):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_characters (chat_id, character_name) 
                    VALUES (%s, %s) 
                    ON CONFLICT (chat_id) 
                    DO UPDATE SET character_name = EXCLUDED.character_name;
                """, (chat_id, character_name.lower()))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in CharacterRepository.set_chat_character: {e}")
        finally:
            self.db.release_connection(conn)

class EconomyRepository(BaseRepository):
    def get_bot_wallet_balance(self, bot_id: int = 0) -> int:
        """Retrieves or initializes the 100M coin Bot Treasury (Uses chat_id 0)"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM economy_wallets WHERE chat_id = 0 AND user_id = %s;", (bot_id,))
                res = cur.fetchone()
                if res: return res[0]
                
                initial_treasury = 100_000_000
                cur.execute("INSERT INTO economy_wallets (chat_id, user_id, balance) VALUES (0, %s, %s) RETURNING balance;", (bot_id, initial_treasury))
                conn.commit()
                return initial_treasury
        except Exception as e:
            logger.error(f"Error getting bot wallet: {e}")
            return 100_000_000
        finally:
            self.db.release_connection(conn)

    def modify_bot_wallet(self, amount: int, bot_id: int = 0) -> int:
        """Deducts or adds coins to the central Bot Treasury"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE economy_wallets SET balance = balance + %s WHERE chat_id = 0 AND user_id = %s RETURNING balance;", (amount, bot_id))
                res = cur.fetchone()
                conn.commit()
                return res[0] if res else 0
        except Exception as e:
            conn.rollback()
            return 0
        finally:
            self.db.release_connection(conn)

    def get_balance(self, chat_id: int, user_id: int) -> int:
        """Gets user balance. chat_id is ignored to force a GLOBAL wallet."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                # We hardcode chat_id = 0 so the user's wallet is global
                cur.execute("SELECT balance FROM economy_wallets WHERE chat_id = 0 AND user_id = %s;", (user_id,))
                res = cur.fetchone()
                if not res:
                    cur.execute("INSERT INTO economy_wallets (chat_id, user_id, balance) VALUES (0, %s, 0) RETURNING balance;", (user_id,))
                    res = cur.fetchone()
                    conn.commit()
                return res[0] if res else 0
        except Exception:
            return 0
        finally:
            self.db.release_connection(conn)

    def add_coins(self, chat_id: int, user_id: int, amount: int) -> int:
        """Adds coins to the user's GLOBAL wallet."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO economy_wallets (chat_id, user_id, balance) 
                    VALUES (0, %s, %s) 
                    ON CONFLICT (chat_id, user_id) 
                    DO UPDATE SET balance = economy_wallets.balance + EXCLUDED.balance 
                    RETURNING balance;
                """, (user_id, amount))
                res = cur.fetchone()
                conn.commit()
                return res[0] if res else amount
        except Exception:
            conn.rollback()
            return 0
        finally:
            self.db.release_connection(conn)

    def deduct_coins(self, chat_id: int, user_id: int, amount: int) -> bool:
        """Deducts coins from the user's GLOBAL wallet."""
        if self.get_balance(chat_id, user_id) < amount: return False
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE economy_wallets SET balance = balance - %s WHERE chat_id = 0 AND user_id = %s;", (amount, user_id))
                conn.commit()
                return True
        except Exception:
            conn.rollback()
            return False
        finally:
            self.db.release_connection(conn)

    def get_shop_items(self) -> list:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT item_id, name, cost, description FROM shop_items ORDER BY item_id ASC;")
                return [{"item_id": r[0], "name": r[1], "cost": r[2], "description": r[3]} for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            self.db.release_connection(conn)

    def get_shop_item(self, item_id: int) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT item_id, name, cost, description FROM shop_items WHERE item_id = %s;", (item_id,))
                r = cur.fetchone()
                return {"item_id": r[0], "name": r[1], "cost": r[2], "description": r[3]} if r else {}
        except Exception:
            return {}
        finally:
            self.db.release_connection(conn)

class KnowledgeGraphRepository(BaseRepository):
    def add_triple(self, subject: str, predicate: str, obj: str, character_name: str = "giyu"):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO knowledge_graph (subject, predicate, object, character_name)
                    VALUES (%s, %s, %s, %s);
                """, (subject, predicate, obj, character_name.lower()))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in KnowledgeGraphRepository.add_triple: {e}")
        finally:
            self.db.release_connection(conn)

    def get_triples_for_entity(self, entity: str, character_name: str = "giyu") -> list:
        conn = self.db.get_connection()
        try:
            entity_lower = f"%{entity.lower()}%"
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT subject, predicate, object FROM knowledge_graph
                    WHERE character_name = %s AND (LOWER(subject) LIKE %s OR LOWER(object) LIKE %s)
                    LIMIT 15;
                """, (character_name.lower(), entity_lower, entity_lower))
                return [{"subject": r[0], "predicate": r[1], "object": r[2]} for r in cur.fetchall()]
        except Exception as e:
            print(f"Error in KnowledgeGraphRepository.get_triples_for_entity: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    def is_empty(self, character_name: str = "giyu") -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM knowledge_graph WHERE character_name = %s;", (character_name.lower(),))
                return cur.fetchone()[0] == 0
        except Exception as e:
            print(f"Error in KnowledgeGraphRepository.is_empty: {e}")
            return True
        finally:
            self.db.release_connection(conn)

    def seed_knowledge_graph(self):
        """Seeds the database with personality relationships triplets for all supported characters"""
        if not self.is_empty("giyu"):
            return
            
        logger = logging.getLogger(__name__)
        logger.info("KnowledgeGraphRepository: Seeding default anime character relationships...")
        
        # Giyu relationships
        giyu_triplets = [
            ("Giyu Tomioka", "TITLE", "Water Hashira"),
            ("Giyu Tomioka", "MEMBER_OF", "Demon Slayer Corps"),
            ("Giyu Tomioka", "USES", "Water Breathing"),
            ("Giyu Tomioka", "STUDENT_OF", "Sakonji Urokodaki"),
            ("Giyu Tomioka", "COMPANION_OF", "Sabito"),
            ("Giyu Tomioka", "SISTER_OF", "Tsutako Tomioka"),
            ("Giyu Tomioka", "TARGET_OF_TEASING", "Shinobu Kocho"),
            ("Sakonji Urokodaki", "TRAINED", "Giyu Tomioka"),
            ("Sabito", "FRIEND_OF", "Giyu Tomioka"),
            ("Tsutako Tomioka", "SISTER_OF", "Giyu Tomioka")
        ]
        for s, p, o in giyu_triplets:
            self.add_triple(s, p, o, "giyu")

        # Tanjiro relationships
        tanjiro_triplets = [
            ("Tanjiro Kamado", "MEMBER_OF", "Demon Slayer Corps"),
            ("Tanjiro Kamado", "BROTHER_OF", "Nezuko Kamado"),
            ("Tanjiro Kamado", "USES", "Water Breathing"),
            ("Tanjiro Kamado", "USES", "Hinokami Kagura"),
            ("Tanjiro Kamado", "STUDENT_OF", "Sakonji Urokodaki"),
            ("Tanjiro Kamado", "FRIEND_OF", "Zenitsu Agatsuma"),
            ("Tanjiro Kamado", "FRIEND_OF", "Inosuke Hashibira"),
            ("Nezuko Kamado", "SISTER_OF", "Tanjiro Kamado")
        ]
        for s, p, o in tanjiro_triplets:
            self.add_triple(s, p, o, "tanjiro")

        # Shinobu relationships
        shinobu_triplets = [
            ("Shinobu Kocho", "TITLE", "Insect Hashira"),
            ("Shinobu Kocho", "MEMBER_OF", "Demon Slayer Corps"),
            ("Shinobu Kocho", "USES", "Insect Breathing"),
            ("Shinobu Kocho", "CREATOR_OF", "Wisteria Poison"),
            ("Shinobu Kocho", "SISTER_OF", "Kanae Kocho"),
            ("Shinobu Kocho", "ADOPTIVE_SISTER_OF", "Kanao Tsuyuri"),
            ("Shinobu Kocho", "TEASES", "Giyu Tomioka")
        ]
        for s, p, o in shinobu_triplets:
            self.add_triple(s, p, o, "shinobu")

        # Nezuko relationships
        nezuko_triplets = [
            ("Nezuko Kamado", "SISTER_OF", "Tanjiro Kamado"),
            ("Nezuko Kamado", "IS", "Demon"),
            ("Nezuko Kamado", "USES_ART", "Exploding Blood"),
            ("Nezuko Kamado", "PROTECTS", "Humans")
        ]
        for s, p, o in nezuko_triplets:
            self.add_triple(s, p, o, "nezuko")
            
        logger.info("KnowledgeGraphRepository: Seeding completed successfully.")


class BotMemoryRepository:
    def __init__(self):
        self.db = DatabaseManager()

    def save_memory(self, chat_id: int, user_id: int, memory_key: str, memory_value: str):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_memories (chat_id, user_id, memory_key, memory_value, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (chat_id, user_id, memory_key)
                    DO UPDATE SET memory_value = EXCLUDED.memory_value, updated_at = CURRENT_TIMESTAMP;
                """, (chat_id, user_id, memory_key, memory_value))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"BotMemoryRepository.save_memory error: {e}")
        finally:
            self.db.release_connection(conn)

    def get_user_memories(self, chat_id: int, user_id: int) -> dict:
        conn = self.db.get_connection()
        memories = {}
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT memory_key, memory_value FROM bot_memories
                    WHERE chat_id = %s AND user_id = %s;
                """, (chat_id, user_id))
                rows = cur.fetchall()
                for key, val in rows:
                    memories[key] = val
        except Exception as e:
            logger.error(f"BotMemoryRepository.get_user_memories error: {e}")
        finally:
            self.db.release_connection(conn)
        return memories


class BotStatsRepository:
    def __init__(self):
        self.db = DatabaseManager()

    def get_bot_stats(self, chat_id: int) -> dict:
        conn = self.db.get_connection()
        stats = {"chat_id": chat_id, "xp": 0, "level": 1, "unlocked_skills": "water_breathing_1", "traits": '{"stoic": 80, "friendly": 20, "energy": 50}'}
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT xp, level, unlocked_skills, traits FROM bot_stats WHERE chat_id = %s;", (chat_id,))
                row = cur.fetchone()
                if row:
                    stats["xp"] = row[0]
                    stats["level"] = row[1]
                    stats["unlocked_skills"] = row[2]
                    stats["traits"] = row[3]
                else:
                    cur.execute("""
                        INSERT INTO bot_stats (chat_id, xp, level, unlocked_skills, traits)
                        VALUES (%s, 0, 1, 'water_breathing_1', '{"stoic": 80, "friendly": 20, "energy": 50}')
                        ON CONFLICT (chat_id) DO NOTHING;
                    """, (chat_id,))
                    conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"BotStatsRepository.get_bot_stats error: {e}")
        finally:
            self.db.release_connection(conn)
        return stats

    def add_xp(self, chat_id: int, amount: int) -> tuple[int, bool]:
        """Adds XP to the bot. Returns (new_level, leveled_up)"""
        stats = self.get_bot_stats(chat_id)
        xp = stats["xp"] + amount
        level = stats["level"]
        leveled_up = False

        # Level up threshold: level * 100
        while xp >= level * 100:
            xp -= level * 100
            level += 1
            leveled_up = True

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                import json
                try:
                    traits = json.loads(stats["traits"])
                except Exception:
                    traits = {"stoic": 80, "friendly": 20, "energy": 50}
                
                if leveled_up:
                    traits["friendly"] = min(100, traits.get("friendly", 20) + 2)
                    traits["energy"] = min(100, traits.get("energy", 50) + 3)
                    traits["stoic"] = max(10, traits.get("stoic", 80) - 1)
                
                traits_str = json.dumps(traits)
                
                skills = [s.strip() for s in stats["unlocked_skills"].split(",")]
                if level >= 5 and "sarcasm_master" not in skills:
                    skills.append("sarcasm_master")
                if level >= 10 and "universal_sage" not in skills:
                    skills.append("universal_sage")
                skills_str = ",".join(skills)

                cur.execute("""
                    INSERT INTO bot_stats (chat_id, xp, level, unlocked_skills, traits)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (chat_id)
                    DO UPDATE SET xp = EXCLUDED.xp, level = EXCLUDED.level, unlocked_skills = EXCLUDED.unlocked_skills, traits = EXCLUDED.traits;
                """, (chat_id, xp, level, skills_str, traits_str))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"BotStatsRepository.add_xp error: {e}")
        finally:
            self.db.release_connection(conn)
        return level, leveled_up


class BotStickerRepository:
    def __init__(self):
        self.db = DatabaseManager()

    def save_sticker(self, chat_id: int, file_id: str, emoji: str):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_sticker_stock (chat_id, file_id, emoji)
                    VALUES (%s, %s, %s)
                    ON CONFLICT ON CONSTRAINT unique_chat_sticker DO NOTHING;
                """, (chat_id, file_id, emoji))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"BotStickerRepository.save_sticker error: {e}")
        finally:
            self.db.release_connection(conn)

    def get_sticker_stock(self, chat_id: int) -> list[dict]:
        conn = self.db.get_connection()
        stock = []
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT file_id, emoji FROM bot_sticker_stock
                    WHERE chat_id = %s;
                """, (chat_id,))
                rows = cur.fetchall()
                for fid, emo in rows:
                    stock.append({"file_id": fid, "emoji": emo})
        except Exception as e:
            logger.error(f"BotStickerRepository.get_sticker_stock error: {e}")
        finally:
            self.db.release_connection(conn)
        return stock

class GiveawayAlertRepository(BaseRepository):
    def is_alerted(self, giveaway_id: int) -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM giveaway_alerts WHERE giveaway_id = %s;", (giveaway_id,))
                return cur.fetchone() is not None
        except Exception:
            return False
        finally:
            self.db.release_connection(conn)

    def mark_alerted(self, giveaway_id: int, title: str = ""):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO giveaway_alerts (giveaway_id, title) VALUES (%s, %s) ON CONFLICT (giveaway_id) DO NOTHING;", (giveaway_id, title))
                conn.commit()
        except Exception:
            conn.rollback()
        finally:
            self.db.release_connection(conn)

    def get_all_alerted_ids(self) -> set[int]:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT giveaway_id FROM giveaway_alerts;")
                return {row[0] for row in cur.fetchall()}
        except Exception:
            return set()
        finally:
            self.db.release_connection(conn)
