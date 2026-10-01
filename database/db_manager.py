import logging
try:
    import psycopg2
    from psycopg2 import pool
except ImportError:
    psycopg2 = None
    pool = None

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
        if psycopg2 is None:
            logger.warning("psycopg2 is not installed. Database features will be inactive.")
            return
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
                if conn and not getattr(conn, "closed", False):
                    return conn

                # Replace dead connection
                logger.warning("Pooled database connection was closed. Replacing...")
                try:
                    self._pool.putconn(conn, close=True)
                except Exception:
                    pass
                return self._pool.getconn()
            except Exception as e:
                logger.error(f"Exception fetching connection from pool: {e}")
                raise e
        raise Exception("Database connection pool not initialized.")

    def release_connection(self, conn):
        if self._pool and conn:
            try:
                if not getattr(conn, "closed", False):
                    self._pool.putconn(conn)
                else:
                    self._pool.putconn(conn, close=True)
            except Exception as e:
                # Catch unkeyed connection or closed pool gracefully
                logger.debug(f"DatabaseManager.release_connection notice: {e}")
