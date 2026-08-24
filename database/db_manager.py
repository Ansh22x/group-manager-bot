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
                # 5 min, 20 max threaded connections
                self._pool = psycopg2.pool.ThreadedConnectionPool(5, 20, DATABASE_URL)
                logger.info("Database connection pool initialized successfully via DatabaseManager.")
            except Exception as e:
                logger.error(f"Error initializing connection pool: {e}")
                raise e

    def get_connection(self):
        if self._pool is None:
            self.initialize()
        if self._pool:
            try:
                conn = self._pool.getconn()
                # Instant in-memory check (0ms) instead of executing 'SELECT 1' over the internet
                if conn and not conn.closed:
                    return conn

                # Replace dead connection
                logger.warning("Pooled database connection was closed. Replacing...")
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
