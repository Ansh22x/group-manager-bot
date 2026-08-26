import logging
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

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
            logger.error(f"Error in HistoryRepository.add_chat_history: {e}")
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
            logger.error(f"Error in HistoryRepository.get_chat_history: {e}")
            return []
        finally:
            self.db.release_connection(conn)
