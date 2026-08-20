import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import is_bot_owner, BOT_OWNER_ID
from database.db_manager import DatabaseManager
from database.repositories import EconomyRepository

logger = logging.getLogger(__name__)

class OwnerCommands(BaseHandler):
    def __init__(self):
        self.db = DatabaseManager()
        self.economy_repo = EconomyRepository()

    def register(self, app: Application):
        app.add_handler(CommandHandler("botstats", self.bot_stats))
        app.add_handler(CommandHandler("broadcast", self.broadcast_message))
        # New Economy Owner Commands
        app.add_handler(CommandHandler("add", self.add_coins_cmd))
        app.add_handler(CommandHandler(["botbal", "botbalance"], self.bot_balance_cmd))

    async def add_coins_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user

        if not is_bot_owner(user.id):
            await update.message.reply_text("⛔ <b>Access Denied:</b> Only the Bot Owner can mint or allocate coins.", parse_mode="HTML")
            return

        chat_id = update.message.chat_id
        target_user = None
        amount = None

        # Determine target user (self vs replied user)
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            target_user = update.message.reply_to_message.from_user
            if context.args:
                try: amount = int(context.args[0])
                except ValueError: pass
        elif context.args:
            try:
                amount = int(context.args[0])
                target_user = user
            except ValueError: pass

        if amount is None or target_user is None:
            await update.message.reply_text(
                "🌊 <b>Usage:</b>\n"
                "• <code>/add 5000</code> <i>(Add coins to yourself)</i>\n"
                "• Reply to a user with <code>/add 5000</code> <i>(Add coins to them)</i>",
                parse_mode="HTML"
            )
            return

        # Ensure treasury has enough funds
        treasury_balance = self.economy_repo.get_bot_wallet_balance()
        if treasury_balance < amount:
            await update.message.reply_text("❌ <b>Insufficient Treasury Funds!</b> The Bot Wallet has run out of coins.", parse_mode="HTML")
            return

        # Transfer coins
        new_balance = self.economy_repo.add_coins(chat_id, target_user.id, amount)
        self.economy_repo.modify_bot_wallet(-amount)

        await update.message.reply_text(
            f"💰 <b>Treasury Transfer Successful!</b>\n\n"
            f"👤 <b>Recipient:</b> {target_user.first_name}\n"
            f"💵 <b>Amount Transferred:</b> <code>+{amount:,}</code> coins\n"
            f"📊 <b>New Wallet Balance:</b> <code>{new_balance:,}</code> coins",
            parse_mode="HTML"
        )

    async def bot_balance_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user

        if not is_bot_owner(user.id):
            await update.message.reply_text("⛔ <b>Access Denied.</b>", parse_mode="HTML")
            return

        # Fetch central treasury balance (Chat ID 0)
        balance = self.economy_repo.get_bot_wallet_balance()

        await update.message.reply_text(
            f"🏦 <b>Giyu-Bot Central Treasury</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Total Reserves:</b> <code>{balance:,}</code> coins\n"
            f"👑 <b>Authorized Controller:</b> {user.first_name}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Use <code>/add [amount]</code> to disburse funds to members.</i>",
            parse_mode="HTML"
        )

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
                await context.bot.send_message(chat_id=chat_id, text=f"📢 <b>Global Announcement:</b>\n\n{message}", parse_mode="HTML")
                sent_count += 1
            except Exception:
                continue

        await update.message.reply_text(f"✅ Announcement sent to <b>{sent_count}</b> group(s).", parse_mode="HTML")
