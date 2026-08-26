import json
import logging
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

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
