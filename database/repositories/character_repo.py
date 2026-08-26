import logging
import json
from database.repositories.base import BaseRepository
from services.cache_service import fast_cache

logger = logging.getLogger(__name__)

class CharacterRepository(BaseRepository):
    def get_chat_character(self, chat_id: int) -> str:
        """Retrieves the active persona character for this chat (default 'giyu'). FastCache powered."""
        cache_key = f"chat_char_{chat_id}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT character_name FROM chat_characters WHERE chat_id = %s;", (chat_id,))
                res = cur.fetchone()
                char_name = res[0] if res else "giyu"
                fast_cache.set(cache_key, char_name, ttl_seconds=86400.0)
                return char_name
        except Exception as e:
            logger.error(f"Error in CharacterRepository.get_chat_character: {e}")
            return "giyu"
        finally:
            self.db.release_connection(conn)

    def set_chat_character(self, chat_id: int, character_name: str):
        """Sets the active persona character for this chat and updates cache."""
        clean_name = character_name.lower().strip()
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_characters (chat_id, character_name)
                    VALUES (%s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET character_name = EXCLUDED.character_name;
                """, (chat_id, clean_name))
                conn.commit()
                fast_cache.set(f"chat_char_{chat_id}", clean_name, ttl_seconds=86400.0)
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in CharacterRepository.set_chat_character: {e}")
        finally:
            self.db.release_connection(conn)

    def get_character_evolution(self, character_name: str = "giyu") -> dict:
        """Retrieves dynamic evolution stats: level, traits, and unlocked skills."""
        cache_key = f"char_evo_{character_name.lower()}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT level, traits, unlocked_skills 
                    FROM character_evolution 
                    WHERE character_name = %s;
                """, (character_name.lower(),))
                res = cur.fetchone()
                if res:
                    traits = res[1] if isinstance(res[1], dict) else json.loads(res[1])
                    skills = res[2] if isinstance(res[2], list) else (res[2].split(",") if isinstance(res[2], str) else [])
                    data = {"level": res[0], "traits": traits, "skills": skills}
                else:
                    data = {"level": 1, "traits": {"stoic": 80, "friendly": 20, "energy": 50}, "skills": []}
                fast_cache.set(cache_key, data, ttl_seconds=3600.0)
                return data
        except Exception as e:
            logger.error(f"Error in CharacterRepository.get_character_evolution: {e}")
            return {"level": 1, "traits": {"stoic": 80, "friendly": 20, "energy": 50}, "skills": []}
        finally:
            self.db.release_connection(conn)

    def update_character_evolution(self, character_name: str, level: int, traits: dict, skills: list):
        """Updates character dynamic evolution attributes and invalidates cache."""
        clean_name = character_name.lower().strip()
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO character_evolution (character_name, level, traits, unlocked_skills)
                    VALUES (%s, %s, %s::jsonb, %s)
                    ON CONFLICT (character_name) DO UPDATE SET
                        level = EXCLUDED.level,
                        traits = EXCLUDED.traits,
                        unlocked_skills = EXCLUDED.unlocked_skills,
                        updated_at = NOW();
                """, (clean_name, level, json.dumps(traits), ",".join(skills)))
                conn.commit()
                fast_cache.delete(f"char_evo_{clean_name}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in CharacterRepository.update_character_evolution: {e}")
        finally:
            self.db.release_connection(conn)
