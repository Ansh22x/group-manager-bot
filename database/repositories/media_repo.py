import logging
from database.repositories.base import BaseRepository
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

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

    def is_user_alerted(self, user_id: int, giveaway_id: int) -> bool:
        """Checks if a specific user has already received an alert for this giveaway/game."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM user_giveaway_alerts WHERE user_id = %s AND giveaway_id = %s;", (user_id, giveaway_id))
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

    def mark_user_alerted(self, user_id: int, giveaway_id: int, title: str = ""):
        """Permanently records that this user was notified so they NEVER receive it again."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_giveaway_alerts (
                        user_id BIGINT,
                        giveaway_id BIGINT,
                        title TEXT,
                        alerted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, giveaway_id)
                    );
                """)
                cur.execute("""
                    INSERT INTO user_giveaway_alerts (user_id, giveaway_id, title)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, giveaway_id) DO NOTHING;
                """, (user_id, giveaway_id, title))
                cur.execute("""
                    INSERT INTO giveaway_alerts (giveaway_id, title)
                    VALUES (%s, %s)
                    ON CONFLICT (giveaway_id) DO NOTHING;
                """, (giveaway_id, title))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.debug(f"mark_user_alerted error: {e}")
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
