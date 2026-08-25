import logging
import datetime
from database.repositories.base import BaseRepository
from config import is_bot_owner

logger = logging.getLogger(__name__)

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
            logger.error(f"Error in AFKRepository.get_afk_users: {e}")
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
            logger.error(f"Error in AFKRepository.set_user_afk: {e}")
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
            logger.error(f"Error in AFKRepository.remove_user_afk: {e}")
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
            logger.error(f"Error in WarningRepository.get_warnings: {e}")
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
            logger.error(f"Error in WarningRepository.add_warning: {e}")
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
            logger.error(f"Error in WarningRepository.remove_warning: {e}")
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
            logger.error(f"Error in WarningRepository.reset_warnings: {e}")
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
            logger.error(f"Error in TempMuteRepository.add_temp_mute: {e}")
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
            logger.error(f"Error in TempMuteRepository.remove_temp_mute: {e}")
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
            logger.error(f"Error in TempMuteRepository.get_expired_mutes: {e}")
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
            logger.error(f"Error in TempMuteRepository.get_all_pending_mutes: {e}")
            return []
        finally:
            self.db.release_connection(conn)
