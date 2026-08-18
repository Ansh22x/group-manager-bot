-- Giyu-Bot Supabase Schema Initialization Migration SQL
-- You can run this directly in the Supabase SQL Editor to bootstrap your database.

-- 1. Enable Required PostgreSQL Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 2. Create Chats Settings Table
CREATE TABLE IF NOT EXISTS chats (
    chat_id BIGINT PRIMARY KEY,
    rules TEXT DEFAULT 'No rules have been set for this group yet.',
    welcome_msg TEXT DEFAULT 'Welcome to the group, {name}!',
    welcome_on BOOLEAN DEFAULT TRUE,
    afk_on BOOLEAN DEFAULT TRUE
);

-- 3. Create Warnings Strike Tracker Table
CREATE TABLE IF NOT EXISTS warnings (
    chat_id BIGINT,
    user_id BIGINT,
    warn_count INT DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

-- 4. Create Custom Hashtag Tags Table
CREATE TABLE IF NOT EXISTS custom_tags (
    chat_id BIGINT,
    tag VARCHAR(100),
    reply TEXT,
    PRIMARY KEY (chat_id, tag)
);

-- 5. Create Custom Keyword Filters Table
CREATE TABLE IF NOT EXISTS custom_filters (
    chat_id BIGINT,
    keyword VARCHAR(255),
    reply TEXT,
    PRIMARY KEY (chat_id, keyword)
);

-- 6. Create Users Leveling & Stats Table
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

-- 7. Create AFK Status Monitor Table
CREATE TABLE IF NOT EXISTS afk_users (
    user_id BIGINT PRIMARY KEY,
    reason TEXT
);

-- 8. Create Bot Lore Vector Embeddings Table (RAG Identity)
CREATE TABLE IF NOT EXISTS bot_lore (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1024),
    character_name VARCHAR(100) DEFAULT 'giyu'
);

-- 9. Create Chat History Table for Conversational Logs (Symmetric pgcrypto BYTEA Storage)
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    role VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Create Captcha Verification Logs Table
CREATE TABLE IF NOT EXISTS captcha_logs (
    chat_id BIGINT,
    user_id BIGINT,
    correct_answer VARCHAR(50),
    message_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, user_id)
);

-- 11. Create Persistent Temporary Mutes Table
CREATE TABLE IF NOT EXISTS temp_mutes (
    chat_id BIGINT,
    user_id BIGINT,
    unmute_at TIMESTAMP,
    PRIMARY KEY (chat_id, user_id)
);

-- 12. Create Active Character Persona Map Table
CREATE TABLE IF NOT EXISTS chat_characters (
    chat_id BIGINT PRIMARY KEY,
    character_name VARCHAR(100) DEFAULT 'giyu'
);

-- 13. Create Economy Wallets Table
CREATE TABLE IF NOT EXISTS economy_wallets (
    chat_id BIGINT,
    user_id BIGINT,
    balance INT DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

-- 14. Create Group Shop Items Table
CREATE TABLE IF NOT EXISTS shop_items (
    item_id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    cost INT NOT NULL,
    description TEXT
);

-- 15. Seed Default Shop Items Configuration
INSERT INTO shop_items (item_id, name, cost, description) VALUES
(1, 'Custom Title Tag', 200, 'Changes your leveling rank title/tag to anything you choose!'),
(2, 'Warning Cleanse', 150, 'Removes 1 warning strike from your profile.'),
(3, 'Water Breathing License', 100, 'Unlocks special Giyu Water Breathing stickers!')
ON CONFLICT (item_id) DO NOTHING;

-- 16. Enable Row Level Security (RLS) on Sensitive Tables
ALTER TABLE chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE warnings ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

-- 17. Create Default RLS Access Policies for Authenticated Dashboard Roles
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
