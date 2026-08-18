import psycopg2
from psycopg2 import pool
from config import DATABASE_URL

class DatabaseManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._pool = None
        return cls._instance

    def initialize(self):
        if not DATABASE_URL:
            print("WARNING: DATABASE_URL not set in environment. Database features will fail.")
            return
        if self._pool is None:
            try:
                self._pool = psycopg2.pool.ThreadedConnectionPool(1, 20, DATABASE_URL)
                print("Database connection pool initialized successfully via DatabaseManager.")
            except Exception as e:
                print(f"Error initializing connection pool: {e}")
                raise e

    def get_connection(self):
        if self._pool is None:
            self.initialize()
        if self._pool:
            return self._pool.getconn()
        raise Exception("Database connection pool not initialized.")

    def release_connection(self, conn):
        if self._pool and conn:
            self._pool.putconn(conn)
