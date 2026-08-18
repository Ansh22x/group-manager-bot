import datetime
from database.db_manager import DatabaseManager

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
            # --- NEW SCHEMAS FOR ADVANCED FEATURES ---
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
            
            conn.commit()
            print("Database schema verified and loaded.")
    except Exception as e:
        conn.rollback()
        print(f"Error seeding database schema: {e}")
        raise e
    finally:
        db.release_connection(conn)


class BaseRepository:
    def __init__(self):
        self.db = DatabaseManager()


class ChatRepository(BaseRepository):
    def get_chat_settings(self, chat_id: int) -> dict:
        conn = self.db.get_connection()
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
                cur.execute("SELECT xp, level, last_xp_time, tag, name FROM users WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                res = cur.fetchone()
                if not res:
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
            print(f"Error in UserRepository.get_user_stats: {e}")
            return {'xp': 0, 'level': 1, 'last_xp_time': 0, 'tag': 'Member', 'name': name}
        finally:
            self.db.release_connection(conn)

    def update_user_stats(self, chat_id: int, user_id: int, **kwargs):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                for field, val in kwargs.items():
                    if field in ['xp', 'level', 'last_xp_time', 'tag', 'name']:
                        cur.execute(f"UPDATE users SET {field} = %s WHERE chat_id = %s AND user_id = %s;", (val, chat_id, user_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in UserRepository.update_user_stats: {e}")
        finally:
            self.db.release_connection(conn)

    def get_top_users(self, chat_id: int, limit: int = 10) -> list:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name, level, tag, xp FROM users WHERE chat_id = %s ORDER BY xp DESC LIMIT %s;", (chat_id, limit))
                return [{'name': row[0], 'level': row[1], 'tag': row[2], 'xp': row[3]} for row in cur.fetchall()]
        except Exception as e:
            print(f"Error in UserRepository.get_top_users: {e}")
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


class HistoryRepository(BaseRepository):
    def add_chat_history(self, chat_id: int, role: str, name: str, content: str):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat_history (chat_id, role, name, content) VALUES (%s, %s, %s, %s);",
                    (chat_id, role, name, content)
                )
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error in HistoryRepository.add_chat_history: {e}")
        finally:
            self.db.release_connection(conn)

    def get_chat_history(self, chat_id: int, limit: int = 10) -> list:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT role, name, content FROM chat_history WHERE chat_id = %s ORDER BY created_at DESC LIMIT %s;",
                    (chat_id, limit)
                )
                rows = cur.fetchall()
                return [(r[0], r[1], r[2]) for r in reversed(rows)]
        except Exception as e:
            print(f"Error in HistoryRepository.get_chat_history: {e}")
            return []
        finally:
            self.db.release_connection(conn)


# --- NEW REPOSITORIES FOR ADVANCED FEATURES ---

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
    def get_balance(self, chat_id: int, user_id: int) -> int:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM economy_wallets WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
                res = cur.fetchone()
                if not res:
                    cur.execute("INSERT INTO economy_wallets (chat_id, user_id, balance) VALUES (%s, %s, 0) RETURNING balance;", (chat_id, user_id))
                    res = cur.fetchone()
                    conn.commit()
                return res[0] if res else 0
        except Exception as e:
            print(f"Error in EconomyRepository.get_balance: {e}")
            return 0
        finally:
            self.db.release_connection(conn)

    def add_coins(self, chat_id: int, user_id: int, amount: int) -> int:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO economy_wallets (chat_id, user_id, balance) 
                    VALUES (%s, %s, %s) 
                    ON CONFLICT (chat_id, user_id) 
                    DO UPDATE SET balance = economy_wallets.balance + EXCLUDED.balance 
                    RETURNING balance;
                """, (chat_id, user_id, amount))
                res = cur.fetchone()
                conn.commit()
                return res[0] if res else amount
        except Exception as e:
            conn.rollback()
            print(f"Error in EconomyRepository.add_coins: {e}")
            return 0
        finally:
            self.db.release_connection(conn)

    def deduct_coins(self, chat_id: int, user_id: int, amount: int) -> bool:
        balance = self.get_balance(chat_id, user_id)
        if balance < amount:
            return False
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE economy_wallets 
                    SET balance = balance - %s 
                    WHERE chat_id = %s AND user_id = %s;
                """, (amount, chat_id, user_id))
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            print(f"Error in EconomyRepository.deduct_coins: {e}")
            return False
        finally:
            self.db.release_connection(conn)

    def get_shop_items(self) -> list:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT item_id, name, cost, description FROM shop_items ORDER BY item_id ASC;")
                return [{"item_id": r[0], "name": r[1], "cost": r[2], "description": r[3]} for r in cur.fetchall()]
        except Exception as e:
            print(f"Error in EconomyRepository.get_shop_items: {e}")
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
        except Exception as e:
            print(f"Error in EconomyRepository.get_shop_item: {e}")
            return {}
        finally:
            self.db.release_connection(conn)
