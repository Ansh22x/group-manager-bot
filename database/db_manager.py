import logging
import psycopg2
from psycopg2 import pool
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._pool = None
        return cls._instance

    def initialize(self):
        if not DATABASE_URL:
            logger.warning("DATABASE_URL not set in environment. Database features will fail.")
            return
        if self._pool is None:
            try:
                self._pool = psycopg2.pool.ThreadedConnectionPool(1, 20, DATABASE_URL)
                logger.info("Database connection pool initialized successfully via DatabaseManager.")
            except Exception as e:
                logger.error(f"Error initializing connection pool: {e}")
                raise e

    def _is_connection_alive(self, conn) -> bool:
        """Executes a simple test query to verify if the pooled connection is alive"""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
        except Exception:
            return False

    def get_connection(self):
        if self._pool is None:
            self.initialize()
        if self._pool:
            try:
                conn = self._pool.getconn()
                if self._is_connection_alive(conn):
                    return conn
                
                # Connection is dead (timeout/idle drop): close and discard it, then fetch a fresh one
                logger.warning("Pooled database connection is dead. Discarding and replacing...")
                self._pool.putconn(conn, close=True)
                return self._pool.getconn()
            except Exception as e:
                logger.error(f"Exception fetching connection from pool: {e}")
                raise e
        raise Exception("Database connection pool not initialized.")

    def release_connection(self, conn):
        if self._pool and conn:
            try:
                self._pool.putconn(conn)
            except Exception as e:
                logger.error(f"Error releasing connection back to pool: {e}")
