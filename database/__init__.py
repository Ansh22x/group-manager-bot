import os
import psycopg2
from psycopg2 import pool
from config import DATABASE_URL

db_pool = None

def init_db_pool():
    global db_pool
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL not set in environment. Database features will fail.")
        return
    try:
        db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, DATABASE_URL)
        print("Database connection pool initialized successfully.")
    except Exception as e:
        print(f"Error initializing connection pool: {e}")

def get_db_connection():
    if db_pool is None:
        init_db_pool()
    if db_pool:
        return db_pool.getconn()
    raise Exception("Database connection pool is not initialized.")

def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)
