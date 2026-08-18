import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import is_bot_owner, BOT_OWNER_ID
from database import DatabaseManager

logger = logging.getLogger(__name__)

class OwnerCommands(BaseHandler):
    def __init__(self):
        self.db = DatabaseManager()

    def register(self, app: Application):
        app.add_handler(CommandHandler("botstats", self.bot_stats))
        app.add_handler(CommandHandler("broadcast", self.broadcast_message))

    async def bot_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.from_user.id
        if not is_bot_owner(user_id):
            await update.message.reply_text("⛔ <b>Access Denied:</b> This command is reserved exclusively for the Bot Owner.", parse_mode="HTML")
            return

        conn = self.db.get_connection()
        total_groups = 0
        total_afk = 0
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chats;")
                total_groups = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM afk_users;")
                total_afk = cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting botstats: {e}")
        finally:
            self.db.release_connection(conn)

        stats_msg = (
            "⚙️ <b>Bot Owner Dashboard</b>\n\n"
            f"📊 <b>Active Managed Groups:</b> {total_groups}\n"
            f"💤 <b>Total AFK Users:</b> {total_afk}\n"
            f"🛡️ <b>Owner ID:</b> <code>{BOT_OWNER_ID}</code>\n"
            f"🟢 <b>Status:</b> Online & Polling 24/7"
        )
        await update.message.reply_text(stats_msg, parse_mode="HTML")

    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_bot_owner(update.message.from_user.id):
            await update.message.reply_text("⛔ <b>Access Denied.</b>", parse_mode="HTML")
            return

        message = " ".join(context.args)
        if not message:
            await update.message.reply_text("Usage: <code>/broadcast Your message here</code>", parse_mode="HTML")
            return

        conn = self.db.get_connection()
        chat_ids = []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM chats;")
                chat_ids = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching chats for broadcast: {e}")
        finally:
            self.db.release_connection(conn)

        sent_count = 0
        for chat_id in chat_ids:
            try:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=f"📢 <b>Global Announcement:</b>\n\n{message}", 
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception:
                continue

        await update.message.reply_text(f"✅ Announcement sent to <b>{sent_count}</b> group(s).", parse_mode="HTML")
