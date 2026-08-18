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
