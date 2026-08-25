import logging
import json
from database.repositories.base import BaseRepository
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class LoreRepository(BaseRepository):
    def is_lore_empty(self) -> bool:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bot_lore;")
                count = cur.fetchone()[0]
                return count == 0
        except Exception as e:
            logger.error(f"Error in LoreRepository.is_lore_empty: {e}")
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
                logger.info(f"LoreRepository: Cleared bot_lore table for character '{character_name}'.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in LoreRepository.clear_lore: {e}")
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
            logger.error(f"Error in LoreRepository.get_first_lore_chunk: {e}")
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
            logger.error(f"Error in LoreRepository.insert_lore: {e}")
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
            logger.error(f"Error in LoreRepository.get_similar_lore: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    def get_similar_lore_with_scores(self, embedding: list, character_name: str = "giyu", limit: int = 5) -> list:
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
            logger.error(f"Error in LoreRepository.get_similar_lore_with_scores: {e}")
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
            logger.error(f"Error in CharacterRepository.get_chat_character: {e}")
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
            logger.error(f"Error in CharacterRepository.set_chat_character: {e}")
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
            logger.error(f"Error in KnowledgeGraphRepository.add_triple: {e}")
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
            logger.error(f"Error in KnowledgeGraphRepository.get_triples_for_entity: {e}")
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
            logger.error(f"Error in KnowledgeGraphRepository.is_empty: {e}")
            return True
        finally:
            self.db.release_connection(conn)

    def seed_knowledge_graph(self):
        """Seeds the database with personality relationships triplets for all supported characters"""
        if not self.is_empty("giyu"):
            return
            
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
