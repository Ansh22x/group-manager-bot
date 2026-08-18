import sys
from keep_alive import keep_alive
from config import BOT_TOKEN
from database.models import init_db
from handlers import register_handlers
from telegram.ext import Application

def main():
    print("Starting Hinata Hyuga Group Manager Bot...")

    # 1. Initialize Database
    try:
        init_db()
    except Exception as e:
        print(f"CRITICAL: Failed to initialize database: {e}")
        print("Please check your DATABASE_URL environment variable and database connectivity.")
        sys.exit(1)

    # 2. Start Keep Alive Server (for Render / Replit hosting)
    try:
        keep_alive()
        print("Keep Alive server is active.")
    except Exception as e:
        print(f"WARNING: Could not start keep-alive server: {e}")

    # 3. Verify Bot Token
    if not BOT_TOKEN:
        print("CRITICAL: BOT_TOKEN not found in environment!")
        sys.exit(1)

    # 4. Initialize Telegram Application
    app = Application.builder().token(BOT_TOKEN).build()

    # 5. Register All Command & Message Handlers
    register_handlers(app)

    # 6. Start Polling
    print("Hinata Hyuga is online & polling for updates...")
    app.run_polling()

if __name__ == "__main__":
    main()
