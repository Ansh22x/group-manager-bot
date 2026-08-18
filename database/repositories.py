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

    def insert_lore(self, content: str, embedding: list):
        conn = self.db.get_connection()
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
            print(f"Error in LoreRepository.insert_lore: {e}")
        finally:
            self.db.release_connection(conn)

    def get_similar_lore(self, embedding: list, limit: int = 3) -> list:
        conn = self.db.get_connection()
        try:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content FROM bot_lore ORDER BY embedding <=> %s::vector LIMIT %s;",
                    (embedding_str, limit)
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
