import time
import logging
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

def get_uptime_string(start_time: float) -> str:
    """Calculates and formats the system uptime duration"""
    uptime_seconds = int(time.time() - start_time)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

def check_database_connection() -> tuple[bool, str]:
    """Tests connection health status against the Database pooler"""
    db = DatabaseManager()
    try:
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        db.release_connection(conn)
        return True, "Connected"
    except Exception as e:
        logger.error(f"Keep-Alive: Database status check failed: {e}")
        return False, "Disconnected"

def get_database_stats() -> dict:
    """Retrieves rich real-time metrics, knowledge graph relations, and RAG stats from the database"""
    db = DatabaseManager()
    stats = {
        "chats": 0,
        "users": 0,
        "lore": 0,
        "triples": 0,
        "total_coins": 0,
        "daily_streaks_count": 0,
        "warnings_count": 0,
        "sample_triples": [],
        "sample_lore": [],
        "personas_distribution": {},
        "bot_level": 1,
        "bot_xp": 0,
        "bot_traits": {"stoic": 85, "friendly": 15, "energy": 60},
        "bot_skills": "water_breathing_1"
    }
    try:
        conn = db.get_connection()
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT COUNT(*) FROM chats;")
                stats["chats"] = cur.fetchone()[0]
            except Exception: pass
            
            try:
                cur.execute("SELECT COUNT(*) FROM users;")
                stats["users"] = cur.fetchone()[0]
            except Exception: pass
                
            try:
                cur.execute("SELECT COUNT(*) FROM bot_lore;")
                stats["lore"] = cur.fetchone()[0]
            except Exception: pass

            try:
                cur.execute("SELECT COUNT(*) FROM knowledge_graph;")
                stats["triples"] = cur.fetchone()[0]
            except Exception: pass

            try:
                cur.execute("SELECT COALESCE(SUM(balance), 0) FROM economy_wallets;")
                stats["total_coins"] = cur.fetchone()[0]
            except Exception: pass

            try:
                cur.execute("SELECT COUNT(*) FROM daily_streaks;")
                stats["daily_streaks_count"] = cur.fetchone()[0]
            except Exception: pass

            try:
                cur.execute("SELECT COUNT(*) FROM warnings;")
                stats["warnings_count"] = cur.fetchone()[0]
            except Exception: pass

            # Sample Knowledge Graph triplets
            try:
                cur.execute("SELECT subject, predicate, object, character_name FROM knowledge_graph ORDER BY id DESC LIMIT 8;")
                stats["sample_triples"] = [{"subject": r[0], "predicate": r[1], "object": r[2], "character": r[3]} for r in cur.fetchall()]
            except Exception: pass

            # Sample RAG vector lore chunks
            try:
                cur.execute("SELECT character_name, content FROM bot_lore ORDER BY id DESC LIMIT 4;")
                stats["sample_lore"] = [{"character": r[0], "content": (r[1][:120] + "..." if len(r[1]) > 120 else r[1])} for r in cur.fetchall()]
            except Exception: pass

            # Persona Distribution
            try:
                cur.execute("SELECT character_name, COUNT(*) FROM chat_characters GROUP BY character_name;")
                stats["personas_distribution"] = {r[0]: r[1] for r in cur.fetchall()}
            except Exception: pass

            # Bot Evolutionary Stats
            try:
                cur.execute("SELECT level, xp, traits, unlocked_skills FROM bot_stats LIMIT 1;")
                r = cur.fetchone()
                if r:
                    stats["bot_level"] = r[0]
                    stats["bot_xp"] = r[1]
                    import json
                    try: stats["bot_traits"] = json.loads(r[2]) if isinstance(r[2], str) else r[2]
                    except Exception: pass
                    stats["bot_skills"] = r[3]
            except Exception: pass

        db.release_connection(conn)
    except Exception as e:
        logger.error(f"Keep-Alive: Failed to fetch database stats: {e}")
    return stats
