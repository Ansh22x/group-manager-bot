import logging
from database.repositories.base import BaseRepository

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

    def get_similar_lore(self, embedding: list, character_name: str = "giyu", limit: int = 4) -> list[str]:
        conn = self.db.get_connection()
        try:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT content FROM bot_lore 
                    WHERE character_name = %s
                    ORDER BY embedding <=> %s::vector 
                    LIMIT %s;
                """, (character_name.lower(), embedding_str, limit))
                results = [r[0] for r in cur.fetchall()]
                return results
        except Exception as e:
            logger.error(f"Error in LoreRepository.get_similar_lore: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    def get_unified_similar_lore(self, embedding: list, chat_id: int, character_name: str = "giyu", limit: int = 5) -> list[str]:
        """
        Unified Vector Search:
        Retrieves top similar lore by combining official character knowledge + custom group document chunks
        in a single optimized PostgreSQL pgvector query.
        """
        conn = self.db.get_connection()
        try:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT content, 0 AS priority FROM bot_lore 
                    WHERE character_name = %s
                    UNION ALL
                    SELECT chunk_content AS content, 1 AS priority FROM custom_documents 
                    WHERE chat_id = %s
                    ORDER BY priority DESC
                    LIMIT %s;
                """, (character_name.lower(), chat_id, limit))
                results = [r[0] for r in cur.fetchall()]
                return results
        except Exception as e:
            logger.error(f"Error in LoreRepository.get_unified_similar_lore: {e}")
            return self.get_similar_lore(embedding, character_name, limit)
        finally:
            self.db.release_connection(conn)
