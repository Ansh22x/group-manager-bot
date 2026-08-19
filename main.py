import sys
import logging
from keep_alive import keep_alive
from config import BOT_TOKEN
from database import DatabaseManager, setup_db_schema
from handlers import register_handlers
from telegram.ext import Application
from telegram import BotCommand
# Giyu-Bot Telegram Group Manager - Dynamic RAG & Knowledge Graph Engine (v2.1)

# Configure global structured logging with both Console and File handlers
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

async def set_bot_commands(app: Application):
    """Sets Giyu-Bot's public commands list in the Telegram UI autocomplete menu"""
    commands = [
        # Public Utility & Information
        BotCommand("start", "Start Giyu-Bot and view links"),
        BotCommand("help", "Quick command help overview"),
        BotCommand("list_commands", "Complete detailed command list"),
        BotCommand("rules", "Read the group rules"),
        BotCommand("owner", "See group owner and developer"),
        BotCommand("afk", "Set status to sleeping/busy"),
        
        # Public Stats & Leaderboards
        BotCommand("rank", "View your level and XP stats"),
        BotCommand("ranking", "View top 10 chat leaderboard"),
        BotCommand("levels", "View top 10 chat leaderboard (alias)"),
        BotCommand("chatstats", "View group activity stats"),
        BotCommand("chatters", "View top active chatters"),
        
        # Public Media & Fun
        BotCommand("play", "Search and play songs as MP3"),
        BotCommand("video", "Search and download videos (max 50MB)"),
        BotCommand("kang", "Reply to media to make a sticker"),
        
        # Public Economy
        BotCommand("balance", "Check your wallet coin balance"),
        BotCommand("shop", "Open the group shop"),
        BotCommand("buy", "Purchase items from the shop"),
        
        # Public AI Chat
        BotCommand("ask", "Query AI character directly"),
        BotCommand("ai", "Query AI character directly (alias)"),
        
        # Admin Moderation
        BotCommand("promote", "Promote user to admin (Admin)"),
        BotCommand("demote", "Demote admin to user (Admin)"),
        BotCommand("kick", "Kick user from group (Admin)"),
        BotCommand("unban", "Unban user from group (Admin)"),
        BotCommand("mute", "Mute user in chat (Admin)"),
        BotCommand("unmute", "Unmute user in chat (Admin)"),
        BotCommand("tempmute", "Mute user temporarily (Admin)"),
        BotCommand("warn", "Warn a user (Admin)"),
        BotCommand("dwarn", "Delete warning strike (Admin)"),
        BotCommand("pin", "Pin group message (Admin)"),
        BotCommand("unpin", "Unpin group message (Admin)"),
        BotCommand("admin_list", "View group admins (Admin)"),
        
        # Admin Settings & Lore Ingestion
        BotCommand("setrules", "Update group rules (Admin)"),
        BotCommand("welcome", "Toggle welcome greeting (Admin)"),
        BotCommand("setwelcome", "Customize welcome greeting (Admin)"),
        BotCommand("filter", "Add keyword auto-reply (Admin)"),
        BotCommand("afkstat", "Toggle AFK monitor alerts (Admin)"),
        BotCommand("addtag", "Create #hashtag note (Admin)"),
        BotCommand("edit_tag", "Edit #hashtag note (Admin)"),
        BotCommand("settag", "Set custom user title (Admin)"),
        BotCommand("setchar", "Swap active AI character (Admin)"),
        BotCommand("learn", "Ingest document facts to RAG (Admin)"),
        BotCommand("ytest", "Run player client test (Admin)"),
        
        # Bot Owner
        BotCommand("botstats", "View bot stats (Owner)"),
        BotCommand("broadcast", "Broadcast message (Owner)")
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Telegram UI autocomplete command menu registered successfully.")
    except Exception as e:
        logger.error(f"Failed to register Telegram UI commands: {e}")

async def post_init_callback(application: Application):
    """Asynchronous post-initialization callback to run startup tasks"""
    # 1. Seed bot lore vectors once on startup (not per-message)
    try:
        from services.ai_agent import AIAgent
        AIAgent().seed_bot_lore()
        logger.info("AIAgent: Bot lore seeding completed on startup.")
    except Exception as e:
        logger.warning(f"AIAgent: Lore seeding failed on startup: {e}")

    # 2. Seed Knowledge Graph triplets once on startup
    try:
        from database import KnowledgeGraphRepository
        KnowledgeGraphRepository().seed_knowledge_graph()
        logger.info("KnowledgeGraphRepository: Seeding completed on startup.")
    except Exception as e:
        logger.warning(f"KnowledgeGraphRepository: Seeding failed on startup: {e}")

    # 3. Re-schedule any active temp-mutes from database
    try:
        from handlers.admin_moderation import AdminModeration
        AdminModeration().schedule_pending_unmutes(application)
        logger.info("Re-scheduled pending temp-mutes successfully.")
    except Exception as e:
        logger.warning(f"Could not re-schedule pending temp-mutes: {e}")

    # 4. Register Telegram UI command list autocomplete
    await set_bot_commands(application)

def main():
    logger.info("Starting Giyu Tomioka Group Manager Bot (Giyu-Bot)...")

    # 1. Initialize Database
    try:
        db_manager = DatabaseManager()
        db_manager.initialize()
        setup_db_schema()
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        logger.info("Please check your DATABASE_URL environment variable and database connectivity.")
        sys.exit(1)

    # 2. Start Keep Alive Server (for Render / Replit hosting)
    try:
        keep_alive()
        logger.info("Keep Alive server is active.")
    except Exception as e:
        logger.warning(f"Could not start keep-alive server: {e}")

    # 3. Verify Bot Token
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN not found in environment!")
        sys.exit(1)

    # 4. Initialize Telegram Application with post_init callback
    app = Application.builder().token(BOT_TOKEN).post_init(post_init_callback).build()

    # 5. Register All Command & Message Handlers
    register_handlers(app)

    # 6. Start Polling
    logger.info("Giyu Tomioka (Giyu-Bot) is online & polling for updates...")
    app.run_polling()

if __name__ == "__main__":
    main()
