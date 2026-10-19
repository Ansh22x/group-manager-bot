import os
import sys
import time
import signal
import asyncio
import logging
from keep_alive import keep_alive
from config import BOT_TOKEN
from database import DatabaseManager, setup_db_schema
from handlers import register_handlers
from telegram.ext import Application
from telegram import BotCommand

# Configure high-performance event loop for Linux/Docker production
if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
        print("⚡ uvloop C event loop engine activated successfully.")
    except Exception:
        pass

# Configure global structured logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

async def set_bot_commands(app: Application):
    """Sets Giyu-Bot's public commands list in the Telegram UI autocomplete menu"""
    commands = [
        # Public Utility & Information
        BotCommand("start", "Start Giyu-Bot and view links"),
        BotCommand("help", "Quick command help overview"),
        BotCommand("search", "Search Google & DuckDuckGo internet web results"),
        BotCommand("info", "View user numeric ID, stats & full data card"),
        BotCommand("list_commands", "Complete detailed command list"),
        BotCommand("afk", "Set status to sleeping/busy"),
        
        # Public Stats & Leaderboards
        BotCommand("rank", "View your level and XP stats"),
        BotCommand("ranking", "View top 10 chat leaderboard"),
        BotCommand("levels", "View top 10 chat leaderboard (alias)"),
        BotCommand("chatstats", "View group activity stats"),
        BotCommand("chatters", "View top active chatters"),
        
        # Public Media, Voice & Utilities
        BotCommand("dl", "Universal downloader (Insta, TikTok, FB, Terabox, YT)"),
        BotCommand("tts", "Synthesize character voice audio"),
        BotCommand("shazam", "Identify song from audio/video reply"),
        BotCommand("summarize", "AI executive summary of web article"),
        BotCommand("tr", "Translate text with native voice pronunciation"),
        BotCommand("play", "Search and play songs as MP3"),
        BotCommand("video", "Search and download videos (max 50MB)"),
        BotCommand("kang", "Reply to media to make a sticker"),

        # Anime & Manga
        BotCommand("anime", "Search anime synopsis & score on AniList"),
        BotCommand("manga", "Search manga details on AniList"),
        BotCommand("sauce", "Reverse anime frame & scene search"),
        BotCommand("quote", "Iconic Demon Slayer anime quote"),

        # Gaming, Steam & Deals
        BotCommand("game", "Search Steam game, price, SteamDB ATL & keys"),
        BotCommand("reviews", "AI summary of authentic Steam player reviews"),
        BotCommand("deals", "Browse top trending Steam & PC game deals"),
        BotCommand("newlow", "Check if game is at historical all-time low"),
        
        # Public Economy & Casino Mini-Games
        BotCommand("daily", "Claim daily streak coin & XP bonus"),
        BotCommand("balance", "Check your wallet coin balance"),
        BotCommand("activity", "Visual hourly chat activity heatmap"),
        BotCommand("weeklydigest", "AI Demon Slayer weekly newspaper issue"),
        BotCommand("gamble", "Bet coins in multiplier dice"),
        BotCommand("coinflip", "Double or nothing coin flip"),
        BotCommand("slots", "Animated 3-reel casino slots"),
        BotCommand("duel", "Turn-based PvP RPG duel with another player"),
        BotCommand("trivia", "Answer anime/gaming trivia for coin reward"),
        BotCommand("shop", "Open the group shop"),
        BotCommand("buy", "Purchase items from the shop"),
        BotCommand("pay", "Transfer coins to another user"),
        
        # Public AI Chat
        BotCommand("ask", "Query AI character directly (Hermes agent engine)"),
        BotCommand("provider", "Change AI engine (Hermes, Groq, Gemini, Mistral, Pollinations)"),
        BotCommand("model", "Change AI model / provider (alias)"),
        BotCommand("draw", "Generate custom AI artwork"),
        
        # Bot Owner & Super Admin
        BotCommand("giveaways", "View guarded Alienware/AMD/Medal/Steam giveaways (Super Admin)"),
        BotCommand("giveawaynotify", "Toggle 60s background giveaway alerts (Super Admin)"),
        BotCommand("botstats", "View bot stats (Owner)"),
        BotCommand("broadcast", "Broadcast message (Owner)"),
        BotCommand("add", "Mint coins to user/self (Owner)"),
        BotCommand("remove", "Confiscate coins (Owner)"),
        BotCommand("botbalance", "View treasury balance (Owner)"),
        BotCommand("leave", "Force bot to leave a chat (Owner)"),
        BotCommand("gban", "Globally ban a user ID anywhere (Owner/Dev)"),
        BotCommand("gunban", "Lift a global ban (Owner/Dev)"),
        BotCommand("groups", "View groups the bot is in (Owner/Dev)"),
        BotCommand("banhere", "Ban an ID from this group (Admin/Owner)"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Telegram UI autocomplete command menu registered successfully.")
    except Exception as e:
        logger.error(f"Failed to register Telegram UI commands: {e}")

async def global_error_handler(update: object, context) -> None:
    """Catches uncaught handler errors so they don't break polling or crash the process"""
    logger.error("Unhandled exception occurred in Telegram update handler:", exc_info=context.error)

async def post_init_callback(application: Application):
    """Asynchronous post-initialization callback to run startup tasks"""
    try:
        from services.ai_agent import AIAgent
        agent = AIAgent()
        agent.seed_bot_lore()
        logger.info("AIAgent: Bot lore seeding completed.")
        # Hermes cold-start warmup: probe the engine in the background so the
        # first real user message doesn't pay the CLI spawn + model cold-start.
        asyncio.create_task(agent.hermes_service.warmup())
    except Exception as e:
        logger.warning(f"AIAgent: Lore seeding failed on startup: {e}")

    try:
        from database import KnowledgeGraphRepository
        KnowledgeGraphRepository().seed_knowledge_graph()
        logger.info("KnowledgeGraphRepository: Seeding completed.")
    except Exception as e:
        logger.warning(f"KnowledgeGraphRepository: Seeding failed on startup: {e}")

    await set_bot_commands(application)

def run_telegram_bot():
    """Runs the Telegram bot polling engine with automated self-healing and conflict backoff."""
    retry_delay = 5
    while True:
        if not BOT_TOKEN:
            logger.critical("BOT_TOKEN is not configured in environment! Telegram polling paused. Add BOT_TOKEN in Render environment.")
            time.sleep(30)
            continue

        try:
            logger.info("Initializing Telegram Application builder...")
            app = (
                Application.builder()
                .token(BOT_TOKEN)
                .post_init(post_init_callback)
                .concurrent_updates(True)
                .connection_pool_size(256)
                .pool_timeout(30.0)
                .build()
            )

            app.add_error_handler(global_error_handler)
            register_handlers(app)

            # Moderation watchdog: self-healing chat registry + global ban re-sweep
            try:
                from handlers.moderation_handler import ModerationHandler
                if app.job_queue:
                    app.job_queue.run_repeating(
                        ModerationHandler().registry_watchdog, interval=1800, first=120
                    )
                    logger.info("Moderation watchdog scheduled (registry healing + ban re-sweep every 30 min).")
            except Exception as e:
                logger.warning(f"Could not schedule moderation watchdog: {e}")

            logger.info("Starting Giyu-Bot in HIGH-SPEED POLLING mode with Keep-Alive Dashboard...")
            # bootstrap_retries=-1 ensures startup retries forever on temporary network/Telegram glitches instead of failing with exit status 1
            app.run_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "edited_message", "callback_query", "chat_member"],
                bootstrap_retries=-1,
                close_loop=False
            )
            logger.warning("Telegram polling engine stopped normally. Restarting in 5s...")
            time.sleep(5)
            retry_delay = 5
        except Exception as e:
            err_msg = str(e).lower()
            if "conflict" in err_msg or "terminated by other getupdates" in err_msg:
                # Common on Render during rolling restarts or when previous instance is shutting down
                logger.warning(f"Telegram polling conflict detected (another instance is active): {e}. Waiting 15s for previous instance to exit...")
                time.sleep(15)
            elif "unauthorized" in err_msg or "invalid token" in err_msg:
                logger.critical(f"Invalid BOT_TOKEN: {e}. Please check BOT_TOKEN in Render environment variables. Retrying in 60s...")
                time.sleep(60)
            else:
                logger.error(f"Telegram polling engine encountered an error: {e}. Retrying in {retry_delay}s...", exc_info=True)
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

def handle_shutdown(signum, frame):
    """Graceful shutdown handler for Render/Docker signals"""
    logger.info(f"Received shutdown signal ({signum}). Exiting cleanly with status 0...")
    sys.exit(0)

def main():
    logger.info("Starting Giyu Tomioka Bot (Giyu-Bot)...")

    # Register OS signals for clean container termination
    try:
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
    except Exception as e:
        logger.debug(f"Signal registration notice: {e}")

    # 1. Start Flask Web Dashboard & Keep-Alive Daemon IMMEDIATELY (Binds port for Render)
    try:
        keep_alive()
        logger.info("⚡ Keep-Alive Web Dashboard & Self-Pinger daemon initialized.")
    except Exception as e:
        logger.warning(f"Could not start Keep-Alive dashboard: {e}")

    # 2. Initialize Database
    try:
        db_manager = DatabaseManager()
        db_manager.initialize()
        setup_db_schema()
    except Exception as e:
        logger.error(f"Database initialization warning (will retry on demand): {e}")

    # 3. Supervised Telegram Polling Engine
    run_telegram_bot()

if __name__ == "__main__":
    main()
