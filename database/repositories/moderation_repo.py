import logging
from datetime import datetime, timedelta, timezone

from database.repositories.base import BaseRepository
from services.cache_service import fast_cache

logger = logging.getLogger(__name__)

# A registry entry older than this is refreshed lazily before use.
CHAT_STALE_AFTER = timedelta(hours=24)


class ModerationRepository(BaseRepository):
    """Global ban list + self-healing registry of chats the bot occupies."""

    # ------------------------------------------------------------------
    # Global bans
    # ------------------------------------------------------------------
    def add_global_ban(self, user_id: int, full_name: str, username: str,
                       reason: str, banned_by: int) -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO global_bans (user_id, full_name, username, reason, banned_by, banned_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        username = EXCLUDED.username,
                        reason = EXCLUDED.reason,
                        banned_by = EXCLUDED.banned_by,
                        banned_at = NOW();
                """, (user_id, full_name or "", username or "", reason or "No reason provided.", banned_by))
                conn.commit()
                fast_cache.delete("global_bans_all")
                fast_cache.delete(f"gban_{user_id}")
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"add_global_ban error: {e}")
            return False
        finally:
            self.db.release_connection(conn)

    def remove_global_ban(self, user_id: int) -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM global_bans WHERE user_id = %s;", (user_id,))
                deleted = cur.rowcount > 0
                conn.commit()
                fast_cache.delete("global_bans_all")
                fast_cache.delete(f"gban_{user_id}")
                return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"remove_global_ban error: {e}")
            return False
        finally:
            self.db.release_connection(conn)

    def is_globally_banned(self, user_id: int) -> bool:
        cached = fast_cache.get(f"gban_{user_id}")
        if cached is not None:
            return cached

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM global_bans WHERE user_id = %s;", (user_id,))
                banned = cur.fetchone() is not None
                fast_cache.set(f"gban_{user_id}", banned, ttl_seconds=300.0)
                return banned
        except Exception as e:
            logger.error(f"is_globally_banned error: {e}")
            return False
        finally:
            self.db.release_connection(conn)

    def get_global_ban(self, user_id: int) -> dict | None:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id, full_name, username, reason, banned_by, banned_at
                    FROM global_bans WHERE user_id = %s;
                """, (user_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "user_id": row[0], "full_name": row[1], "username": row[2],
                    "reason": row[3], "banned_by": row[4], "banned_at": row[5],
                }
        except Exception as e:
            logger.error(f"get_global_ban error: {e}")
            return None
        finally:
            self.db.release_connection(conn)

    def list_global_bans(self, limit: int = 50) -> list[dict]:
        cached = fast_cache.get("global_bans_all")
        if cached:
            return cached

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id, full_name, username, reason, banned_by, banned_at
                    FROM global_bans ORDER BY banned_at DESC LIMIT %s;
                """, (limit,))
                rows = cur.fetchall()
                result = [
                    {
                        "user_id": r[0], "full_name": r[1], "username": r[2],
                        "reason": r[3], "banned_by": r[4], "banned_at": r[5],
                    } for r in rows
                ]
                fast_cache.set("global_bans_all", result, ttl_seconds=120.0)
                return result
        except Exception as e:
            logger.error(f"list_global_bans error: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    # ------------------------------------------------------------------
    # Bot chat registry (self-healing)
    # ------------------------------------------------------------------
    def upsert_bot_chat(self, chat_id: int, title: str, chat_type: str,
                        bot_is_admin: bool, member_count: int = 0) -> None:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_chats (chat_id, title, chat_type, bot_is_admin, member_count, last_seen)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (chat_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        chat_type = EXCLUDED.chat_type,
                        bot_is_admin = EXCLUDED.bot_is_admin,
                        member_count = COALESCE(NULLIF(EXCLUDED.member_count, 0), bot_chats.member_count),
                        last_seen = NOW();
                """, (chat_id, title or "", chat_type or "group", bool(bot_is_admin), member_count or 0))
                conn.commit()
                fast_cache.delete("bot_chats_all")
        except Exception as e:
            conn.rollback()
            logger.error(f"upsert_bot_chat error: {e}")
        finally:
            self.db.release_connection(conn)

    def mark_chat_seen(self, chat_id: int) -> None:
        """Lightweight heartbeat: only updates last_seen (and inserts a stub)."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_chats (chat_id, last_seen) VALUES (%s, NOW())
                    ON CONFLICT (chat_id) DO UPDATE SET last_seen = NOW();
                """, (chat_id,))
                conn.commit()
                fast_cache.delete("bot_chats_all")
        except Exception as e:
            conn.rollback()
            logger.debug(f"mark_chat_seen error: {e}")
        finally:
            self.db.release_connection(conn)

    def touch_chats(self, chat_ids: list[int]) -> None:
        """Batch heartbeat for many chats at once (used by the watchdog)."""
        if not chat_ids:
            return
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE bot_chats SET last_seen = NOW()
                    WHERE chat_id = ANY(%s);
                """, (chat_ids,))
                conn.commit()
                fast_cache.delete("bot_chats_all")
        except Exception as e:
            conn.rollback()
            logger.debug(f"touch_chats error: {e}")
        finally:
            self.db.release_connection(conn)

    def list_bot_chats(self, only_admin: bool = False, max_age: timedelta | None = None) -> list[dict]:
        cache_key = f"bot_chats_all_{only_admin}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT chat_id, title, chat_type, bot_is_admin, member_count, last_seen
                    FROM bot_chats
                """
                conditions, params = [], []
                if only_admin:
                    conditions.append("bot_is_admin = TRUE")
                if max_age is not None:
                    conditions.append("last_seen > NOW() - %s")
                    params.append(max_age)
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                query += " ORDER BY last_seen DESC;"
                cur.execute(query, params)
                rows = cur.fetchall()
                result = [
                    {
                        "chat_id": r[0], "title": r[1], "chat_type": r[2],
                        "bot_is_admin": r[3], "member_count": r[4], "last_seen": r[5],
                    } for r in rows
                ]
                fast_cache.set(cache_key, result, ttl_seconds=60.0)
                return result
        except Exception as e:
            logger.error(f"list_bot_chats error: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    def remove_bot_chat(self, chat_id: int) -> None:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bot_chats WHERE chat_id = %s;", (chat_id,))
                conn.commit()
                fast_cache.delete("bot_chats_all")
        except Exception as e:
            conn.rollback()
            logger.debug(f"remove_bot_chat error: {e}")
        finally:
            self.db.release_connection(conn)
