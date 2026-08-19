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
    """Retrieves real-time counts from the database tables for the dashboard metrics"""
    db = DatabaseManager()
    stats = {
        "chats": 0,
        "users": 0,
        "lore": 0,
        "triples": 0
    }
    try:
        conn = db.get_connection()
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT COUNT(*) FROM chats;")
                stats["chats"] = cur.fetchone()[0]
            except Exception:
                pass
            
            try:
                cur.execute("SELECT COUNT(*) FROM users;")
                stats["users"] = cur.fetchone()[0]
            except Exception:
                pass
                
            try:
                cur.execute("SELECT COUNT(*) FROM bot_lore;")
                stats["lore"] = cur.fetchone()[0]
            except Exception:
                pass

            try:
                cur.execute("SELECT COUNT(*) FROM knowledge_graph;")
                stats["triples"] = cur.fetchone()[0]
            except Exception:
                pass
        db.release_connection(conn)
    except Exception as e:
        logger.error(f"Keep-Alive: Failed to fetch database stats: {e}")
    return stats
