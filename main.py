import os
import sys
import logging
from keep_alive import keep_alive
from config import BOT_TOKEN
from database import DatabaseManager, setup_db_schema
from handlers import register_handlers
from telegram.ext import Application
from telegram import BotCommand

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
        
        # Public Media & Audio
        BotCommand("play", "Search and play songs as MP3"),
        BotCommand("video", "Search and download videos (max 50MB)"),
        BotCommand("kang", "Reply to media to make a sticker"),

        # Gaming, Steam & Deals
        BotCommand("game", "Search Steam game, price, SteamDB ATL & keys"),
        BotCommand("steam", "Search Steam game (alias)"),
        BotCommand("deals", "Browse top trending Steam & PC game deals"),
        BotCommand("newlow", "Check if game is at historical all-time low"),
        
        # Public Economy
        BotCommand("balance", "Check your wallet coin balance"),
        BotCommand("shop", "Open the group shop"),
        BotCommand("buy", "Purchase items from the shop"),
        BotCommand("pay", "Transfer coins to another user"),
        
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
        
        # Admin Settings
        BotCommand("setrules", "Update group rules (Admin)"),
        BotCommand("welcome", "Toggle welcome greeting (Admin)"),
        BotCommand("setwelcome", "Customize welcome greeting (Admin)"),
        BotCommand("filter", "Add keyword auto-reply (Admin)"),
        BotCommand("filters", "List active auto-replies (Admin)"),
        BotCommand("stopfilter", "Delete keyword auto-reply (Admin)"),
        BotCommand("afkstat", "Toggle AFK monitor alerts (Admin)"),
        BotCommand("tag", "Create #hashtag note (Admin)"),
        BotCommand("tags", "List active #hashtag notes (Admin)"),
        BotCommand("stoptag", "Delete #hashtag note (Admin)"),
        BotCommand("settag", "Set custom user title (Admin)"),
        BotCommand("setchar", "Swap active AI character (Admin)"),
        BotCommand("learn", "Ingest document facts to RAG (Admin)"),
        
        # Bot Owner & Super Admin
        BotCommand("giveaways", "View guarded Alienware/AMD/Medal/Steam giveaways (Super Admin)"),
        BotCommand("giveawaynotify", "Toggle 30m background giveaway alerts (Super Admin)"),
        BotCommand("botstats", "View bot stats (Owner)"),
        BotCommand("broadcast", "Broadcast message (Owner)"),
        BotCommand("add", "Mint coins to user/self (Owner)"),
        BotCommand("remove", "Confiscate coins (Owner)"),
        BotCommand("botbalance", "View treasury balance (Owner)"),
        BotCommand("leave", "Force bot to leave a chat (Owner)")
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Telegram UI autocomplete command menu registered successfully.")
    except Exception as e:
        logger.error(f"Failed to register Telegram UI commands: {e}")

async def post_init_callback(application: Application):
    """Asynchronous post-initialization callback to run startup tasks"""
    try:
        from services.ai_agent import AIAgent
        AIAgent().seed_bot_lore()
        logger.info("AIAgent: Bot lore seeding completed.")
    except Exception as e:
        logger.warning(f"AIAgent: Lore seeding failed on startup: {e}")

    try:
        from database import KnowledgeGraphRepository
        KnowledgeGraphRepository().seed_knowledge_graph()
        logger.info("KnowledgeGraphRepository: Seeding completed.")
    except Exception as e:
        logger.warning(f"KnowledgeGraphRepository: Seeding failed on startup: {e}")

    try:
        from handlers.admin_moderation import AdminModeration
        AdminModeration().schedule_pending_unmutes(application)
        logger.info("Re-scheduled pending temp-mutes successfully.")
    except Exception as e:
        logger.warning(f"Could not re-schedule pending temp-mutes: {e}")

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
        sys.exit(1)

    # 2. Verify Bot Token
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN not found in environment!")
        sys.exit(1)

    # 3. Initialize High-Performance Telegram Application
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init_callback)
        .concurrent_updates(True)  
        .connection_pool_size(256) 
        .pool_timeout(30.0)
        .build()
    )

    # 4. Register All Command & Message Handlers
    register_handlers(app)

    # 5. Environment checks for Webhook deployment with Auto-Typo Fixes
    port = int(os.environ.get("PORT", 8080))
    render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    custom_webhook_url = os.environ.get("WEBHOOK_URL", "").strip()

    # Clean up custom URL if it has typos (e.g., missing the double slash)
    if custom_webhook_url:
        if custom_webhook_url.startswith("https:/") and not custom_webhook_url.startswith("https://"):
            custom_webhook_url = custom_webhook_url.replace("https:/", "https://")
        webhook_domain = custom_webhook_url.rstrip("/")
    elif render_hostname:
        webhook_domain = f"https://{render_hostname}"
    else:
        webhook_domain = None

    if webhook_domain:
        webhook_path = f"/webhook/{BOT_TOKEN}"
        full_webhook_url = f"{webhook_domain}{webhook_path}"
        
        logger.info(f"Starting Giyu-Bot in WEBHOOK mode on port {port}...")
        logger.info(f"Listening URL: {full_webhook_url}")
        
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=full_webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "edited_message", "callback_query", "chat_member"]
        )
    else:
        logger.info("No Webhook URL detected. Starting Giyu-Bot in HIGH-SPEED POLLING mode...")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "edited_message", "callback_query", "chat_member"]
        )

if __name__ == "__main__":
    main()
