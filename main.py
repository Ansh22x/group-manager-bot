import sys
import logging
from keep_alive import keep_alive
from config import BOT_TOKEN
from database import DatabaseManager, setup_db_schema
from handlers import register_handlers
from telegram.ext import Application
from telegram import BotCommand
# Giyu-Bot Telegram Group Manager - Dynamic RAG & Knowledge Graph Engine (v2.1)

# Configure global structured logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def set_bot_commands(app: Application):
    """Sets Giyu-Bot's public commands list in the Telegram UI autocomplete menu"""
    commands = [
        BotCommand("start", "Start Giyu-Bot and view links"),
        BotCommand("help", "Quick command help overview"),
        BotCommand("rules", "Read the group guidelines"),
        BotCommand("afk", "Set your status to busy/sleeping"),
        BotCommand("kang", "Reply to media to make a sticker"),
        BotCommand("rank", "View your level rank and XP stats"),
        BotCommand("ranking", "View the top 10 group leaderboard"),
        BotCommand("balance", "Check your wallet balance"),
        BotCommand("shop", "Open the group shop"),
        BotCommand("ask", "Query Giyu Tomioka directly"),
        BotCommand("ai", "Chat with AI character assistant"),
        BotCommand("play", "Search and play songs as MP3"),
        BotCommand("video", "Search and download YouTube videos (max 50MB)")
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
