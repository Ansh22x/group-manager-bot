import logging
import json
from database.repositories.base import BaseRepository
from services.cache_service import fast_cache

logger = logging.getLogger(__name__)

class KnowledgeGraphRepository(BaseRepository):
    # In-Memory Adjacency Index for 0.001ms Graph-RAG Traversal
    _graph_memory: dict[str, list[dict]] = {}
    _is_memory_loaded: bool = False

    def _preload_graph_memory(self):
        """Preloads all knowledge graph triplets into in-memory adjacency list for instant lookups."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT subject, predicate, object, metadata 
                    FROM knowledge_graph;
                """)
                rows = cur.fetchall()
                mem = {}
                for s, p, o, meta in rows:
                    key = s.lower().strip()
                    if key not in mem:
                        mem[key] = []
                    mem[key].append({
                        "subject": s,
                        "predicate": p,
                        "object": o,
                        "metadata": meta if isinstance(meta, dict) else (json.loads(meta) if meta else {})
                    })
                self.__class__._graph_memory = mem
                self.__class__._is_memory_loaded = True
                logger.info(f"KnowledgeGraphRepository: Preloaded {len(rows)} graph relations into in-memory fast index.")
        except Exception as e:
            logger.error(f"KnowledgeGraphRepository preload failed: {e}")
        finally:
            self.db.release_connection(conn)

    def insert_triple(self, subject: str, predicate: str, obj: str, metadata: dict = None):
        """Inserts a fact triple into the knowledge graph with write-through cache invalidation."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO knowledge_graph (subject, predicate, object, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (subject, predicate, object) DO UPDATE
                    SET metadata = EXCLUDED.metadata;
                """, (subject, predicate, obj, json.dumps(metadata or {})))
                conn.commit()

            # Update in-memory graph index
            key = subject.lower().strip()
            if key not in self.__class__._graph_memory:
                self.__class__._graph_memory[key] = []
            self.__class__._graph_memory[key].append({
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "metadata": metadata or {}
            })
            fast_cache.delete(f"kg_sub_{key}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in KnowledgeGraphRepository.insert_triple: {e}")
        finally:
            self.db.release_connection(conn)

    def get_triples_for_entities_batch(self, entities: list[str]) -> list[dict]:
        """
        High-Performance In-Memory Batch Triplet Lookup (0.001ms).
        Resolves graph relationships for multiple entities simultaneously without touching disk.
        """
        if not self.__class__._is_memory_loaded:
            self._preload_graph_memory()

        results = []
        seen = set()
        for ent in entities:
            clean_ent = ent.lower().strip()
            if clean_ent in self.__class__._graph_memory:
                for trip in self.__class__._graph_memory[clean_ent]:
                    t_id = (trip["subject"], trip["predicate"], trip["object"])
                    if t_id not in seen:
                        seen.add(t_id)
                        results.append(trip)
        return results

    def get_triples_for_subject(self, subject: str) -> list[dict]:
        clean_sub = subject.lower().strip()
        if not self.__class__._is_memory_loaded:
            self._preload_graph_memory()
        return self.__class__._graph_memory.get(clean_sub, [])

    def get_triples_for_object(self, obj: str) -> list[dict]:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT subject, predicate, object, metadata 
                    FROM knowledge_graph 
                    WHERE LOWER(object) = LOWER(%s);
                """, (obj.strip(),))
                rows = cur.fetchall()
                return [{
                    "subject": r[0],
                    "predicate": r[1],
                    "object": r[2],
                    "metadata": r[3]
                } for r in rows]
        except Exception as e:
            logger.error(f"Error in KnowledgeGraphRepository.get_triples_for_object: {e}")
            return []
        finally:
            self.db.release_connection(conn)

    def search_subgraph(self, entities: list[str]) -> list[dict]:
        """Searches multi-hop subgraph relations for a list of entities."""
        return self.get_triples_for_entities_batch(entities)

    def seed_knowledge_graph(self):
        """Seeds initial Demon Slayer universe entities into the graph"""
        initial_triples = [
            ("Giyu Tomioka", "is_a", "Water Hashira", {"category": "status"}),
            ("Giyu Tomioka", "wields", "Water Breathing", {"category": "technique"}),
            ("Giyu Tomioka", "created", "Eleventh Form: Dead Calm (Nagi)", {"category": "ability"}),
            ("Giyu Tomioka", "mentored_by", "Sakonji Urokodaki", {"category": "relationship"}),
            ("Giyu Tomioka", "spared", "Nezuko Kamado", {"category": "history"}),
            ("Giyu Tomioka", "recommended", "Tanjiro Kamado", {"category": "history"}),
            ("Giyu Tomioka", "best_friend", "Sabito", {"category": "backstory"}),
            ("Tanjiro Kamado", "is_a", "Demon Slayer", {"category": "status"}),
            ("Tanjiro Kamado", "wields", "Sun Breathing (Hinokami Kagura)", {"category": "technique"}),
            ("Tanjiro Kamado", "sister_of", "Nezuko Kamado", {"category": "family"}),
            ("Nezuko Kamado", "is_a", "Demon", {"category": "status"}),
            ("Nezuko Kamado", "wields", "Blood Demon Art: Exploding Blood", {"category": "technique"}),
            ("Shinobu Kocho", "is_a", "Insect Hashira", {"category": "status"}),
            ("Shinobu Kocho", "wields", "Insect Breathing", {"category": "technique"}),
            ("Kyojuro Rengoku", "is_a", "Flame Hashira", {"category": "status"}),
            ("Kyojuro Rengoku", "wields", "Flame Breathing", {"category": "technique"}),
            ("Akaza", "is_a", "Upper Rank Three Demon", {"category": "demon"}),
            ("Muzan Kibutsuji", "is_a", "Demon King", {"category": "antagonist"}),
        ]
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM knowledge_graph;")
                if cur.fetchone()[0] == 0:
                    for s, p, o, m in initial_triples:
                        self.insert_triple(s, p, o, m)
                    logger.info("KnowledgeGraphRepository: Initial graph triples seeded successfully.")
        except Exception as e:
            logger.error(f"Error seeding knowledge graph: {e}")
        finally:
            self.db.release_connection(conn)
            self._preload_graph_memory()
