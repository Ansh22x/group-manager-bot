import logging
from database.db_manager import DatabaseManager
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

def setup_db_schema():
    """Bootstraps the database tables and pgvector/pgcrypto extensions if not exists"""
    db = DatabaseManager()
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            # Enable pgvector extension for Supabase
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                conn.commit()
                print("pgvector extension ensured in database.")
            except Exception as ve:
                conn.rollback()
                print(f"WARNING: Could not create pgvector extension: {ve}. Vector search might fail.")

            # Enable pgcrypto extension for data encryption at rest
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                conn.commit()
                print("pgcrypto extension ensured in database.")
            except Exception as pe:
                conn.rollback()
                print(f"WARNING: Could not create pgcrypto extension: {pe}. Data encryption might fail.")

            # Create chats table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id BIGINT PRIMARY KEY,
                    rules TEXT DEFAULT 'No rules have been set for this group yet.',
                    welcome_msg TEXT DEFAULT 'Welcome to the group, {name}!',
                    welcome_on BOOLEAN DEFAULT TRUE,
                    afk_on BOOLEAN DEFAULT TRUE
                );
            """)
            # Create warnings table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    chat_id BIGINT,
                    user_id BIGINT,
                    warn_count INT DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create custom_tags table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS custom_tags (
                    chat_id BIGINT,
                    tag VARCHAR(100),
                    reply TEXT,
                    PRIMARY KEY (chat_id, tag)
                );
            """)
            # Create custom_filters table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS custom_filters (
                    chat_id BIGINT,
                    keyword VARCHAR(255),
                    reply TEXT,
                    PRIMARY KEY (chat_id, keyword)
                );
            """)
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id BIGINT,
                    user_id BIGINT,
                    xp INT DEFAULT 0,
                    level INT DEFAULT 1,
                    last_xp_time DOUBLE PRECISION DEFAULT 0,
                    tag VARCHAR(100) DEFAULT 'Member',
                    name VARCHAR(255),
                    message_count INT DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create afk_users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS afk_users (
                    user_id BIGINT PRIMARY KEY,
                    reason TEXT
                );
            """)
            # Create bot_lore table for character traits RAG system
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_lore (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector(1024),
                    character_name VARCHAR(100) DEFAULT 'giyu'
                );
            """)
            
            # Recreate chat_history with BYTEA format if it is currently text
            cur.execute("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = 'chat_history' AND column_name = 'content';
            """)
            col_type = cur.fetchone()
            if col_type and col_type[0] != 'bytea':
                print("setup_db_schema: Migrating chat_history content column to BYTEA...")
                cur.execute("DROP TABLE IF EXISTS chat_history;")
                conn.commit()

            # Create chat_history table for bot conversational memory (encrypting content as BYTEA)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    content BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Create captcha_logs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS captcha_logs (
                    chat_id BIGINT,
                    user_id BIGINT,
                    correct_answer VARCHAR(50),
                    message_id INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create temp_mutes table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS temp_mutes (
                    chat_id BIGINT,
                    user_id BIGINT,
                    unmute_at TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create chat_characters table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_characters (
                    chat_id BIGINT PRIMARY KEY,
                    character_name VARCHAR(100) DEFAULT 'giyu'
                );
            """)
            # Create economy_wallets table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS economy_wallets (
                    chat_id BIGINT,
                    user_id BIGINT,
                    balance INT DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            # Create shop_items table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    item_id INT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    cost INT NOT NULL,
                    description TEXT
                );
            """)
            # Seed default shop items if empty
            cur.execute("SELECT COUNT(*) FROM shop_items;")
            if cur.fetchone()[0] == 0:
                cur.execute("""
                    INSERT INTO shop_items (item_id, name, cost, description) VALUES
                    (1, 'Custom Title Tag', 200, 'Changes your leveling rank title/tag to anything you choose!'),
                    (2, 'Warning Cleanse', 150, 'Removes 1 warning strike from your profile.'),
                    (3, 'Water Breathing License', 100, 'Unlocks special Giyu Water Breathing stickers!');
                """)
            
            # Alter bot_lore to add character_name column
            cur.execute("ALTER TABLE bot_lore ADD COLUMN IF NOT EXISTS character_name VARCHAR(100) DEFAULT 'giyu';")

            # Alter users to add message_count column for analytics
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS message_count INT DEFAULT 0;")
            
            # Create giveaway_alerts table for persistent real-time freebie alerts
            cur.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_alerts (
                    giveaway_id INT PRIMARY KEY,
                    title TEXT,
                    alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create user_giveaway_alerts for per-user deduplication
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_giveaway_alerts (
                    user_id BIGINT,
                    giveaway_id BIGINT,
                    title TEXT,
                    alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, giveaway_id)
                );
            """)
            
            # --- ENABLE ROW LEVEL SECURITY (RLS) ---
            cur.execute("ALTER TABLE chats ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE warnings ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;")

            # Create default RLS access policies for authenticated dashboard web-panel users
            cur.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'authenticated_chats_policy') THEN
                        CREATE POLICY authenticated_chats_policy ON chats
                        FOR ALL TO authenticated
                        USING (chat_id IN (SELECT chat_id FROM users WHERE user_id = auth.uid()::text::bigint));
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'authenticated_users_policy') THEN
                        CREATE POLICY authenticated_users_policy ON users
                        FOR ALL TO authenticated
                        USING (chat_id IN (SELECT chat_id FROM users WHERE user_id = auth.uid()::text::bigint));
                    END IF;
                END $$;
            """)

            # Create knowledge_graph table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    id SERIAL PRIMARY KEY,
                    subject VARCHAR(255) NOT NULL,
                    predicate VARCHAR(100) NOT NULL,
                    object VARCHAR(255) NOT NULL,
                    character_name VARCHAR(100) DEFAULT 'giyu'
                );
            """)
            # Create bot_memories table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_memories (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT,
                    memory_key VARCHAR(255) NOT NULL,
                    memory_value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_chat_user_mem UNIQUE (chat_id, user_id, memory_key)
                );
            """)

            # Create bot_stats table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_stats (
                    chat_id BIGINT PRIMARY KEY,
                    xp INT DEFAULT 0,
                    level INT DEFAULT 1,
                    unlocked_skills TEXT DEFAULT 'water_breathing_1',
                    traits TEXT DEFAULT '{"stoic": 80, "friendly": 20, "energy": 50}'
                );
            """)

            # Create bot_sticker_stock table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_sticker_stock (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    file_id VARCHAR(255) NOT NULL,
                    emoji VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_chat_sticker UNIQUE (chat_id, file_id)
                );
            """)

            # Create daily_streaks table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_streaks (
                    user_id BIGINT PRIMARY KEY,
                    streak INT DEFAULT 1,
                    last_claimed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create chat_blacklist table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_blacklist (
                    chat_id BIGINT,
                    word VARCHAR(100),
                    PRIMARY KEY (chat_id, word)
                );
            """)

            conn.commit()
            print("Database schema and security constraints verified and loaded.")
    except Exception as e:
        conn.rollback()
        print(f"Error seeding database schema: {e}")
        raise e
    finally:
        db.release_connection(conn)


class BaseRepository:
    def __init__(self):
        self.db = DatabaseManager()
        self.master_key = BOT_TOKEN if BOT_TOKEN else "GiyuWaterBreathingMasterKey123"
