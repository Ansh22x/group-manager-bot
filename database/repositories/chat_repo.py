import logging
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

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
            logger.error(f"Error in ChatRepository.get_chat_settings: {e}")
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
            logger.error(f"Error in ChatRepository.update_chat_settings: {e}")
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
            logger.error(f"Error in TagRepository.get_tags: {e}")
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
            logger.error(f"Error in TagRepository.add_tag: {e}")
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
            logger.error(f"Error in FilterRepository.get_filters: {e}")
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
            logger.error(f"Error in FilterRepository.add_filter: {e}")
        finally:
            self.db.release_connection(conn)


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
            logger.error(f"Error in CaptchaRepository.add_captcha_log: {e}")
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
            logger.error(f"Error in CaptchaRepository.get_captcha_log: {e}")
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
            logger.error(f"Error in CaptchaRepository.remove_captcha_log: {e}")
        finally:
            self.db.release_connection(conn)


class BlacklistRepository(BaseRepository):
    def get_blacklist(self, chat_id: int) -> set[str]:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT word FROM chat_blacklist WHERE chat_id = %s;", (chat_id,))
                return {r[0].lower() for r in cur.fetchall()}
        except Exception as e:
            logger.error(f"Error in BlacklistRepository.get_blacklist: {e}")
            return set()
        finally:
            self.db.release_connection(conn)

    def add_word(self, chat_id: int, word: str) -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_blacklist (chat_id, word)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (chat_id, word.strip().lower()))
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in BlacklistRepository.add_word: {e}")
            return False
        finally:
            self.db.release_connection(conn)

    def remove_word(self, chat_id: int, word: str) -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_blacklist WHERE chat_id = %s AND word = %s;", (chat_id, word.strip().lower()))
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in BlacklistRepository.remove_word: {e}")
            return False
        finally:
            self.db.release_connection(conn)
