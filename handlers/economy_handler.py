import time
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from database import EconomyRepository, UserRepository, WarningRepository

class EconomyHandler(BaseHandler):
    def __init__(self):
        self.economy_repo = EconomyRepository()
        self.user_repo = UserRepository()
        self.warning_repo = WarningRepository()

    def register(self, app: Application):
        app.add_handler(CommandHandler(["balance", "wallet", "coins"], self.show_balance))
        app.add_handler(CommandHandler("shop", self.show_shop))
        app.add_handler(CommandHandler("buy", self.buy_item))
        # New Pay Command
        app.add_handler(CommandHandler(["pay", "transfer"], self.pay_cmd))

    async def award_coins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Awards coins to active chat users, synchronized with the XP leveling cooldown"""
        if not update.message or update.message.chat.type == 'private': return
        
        user = update.message.from_user
        chat_id = update.message.chat_id
        
        # Check cooldown matching the XP leveling timer (1 minute cooldown)
        stats = self.user_repo.get_user_stats(chat_id, user.id)
        last_xp_time = stats.get('last_xp_time', 0)
        
        current_time = time.time()
        if current_time - last_xp_time > 60:
            reward = random.randint(5, 10)
            self.economy_repo.add_coins(chat_id, user.id, reward)

    async def show_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        target_user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.message.from_user
        
        balance = self.economy_repo.get_balance(chat_id, target_user.id)
        
        await update.message.reply_text(
            f"💰 <b>{target_user.first_name}'s Wallet</b>\n\n"
            f"🏦 <b>Balance:</b> <code>{balance:,}</code> Water Coins",
            parse_mode="HTML"
        )

    async def show_shop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        items = self.economy_repo.get_shop_items()
        
        shop_msg = "🛒 <b>Giyu-Bot Shop</b> 🛒\n\n"
        for item in items:
            shop_msg += (
                f"📦 <b>{item['name']}</b> (ID: <code>{item['item_id']}</code>)\n"
                f"💰 <b>Cost:</b> {item['cost']:,} coins\n"
                f"📝 <i>{item['description']}</i>\n\n"
            )
        shop_msg += "To buy an item, type: <code>/buy [item_id] [arguments]</code>\nExample: <code>/buy 1 Slayer Captain</code>"
        await update.message.reply_text(shop_msg, parse_mode="HTML")

    async def buy_item(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Usage: <code>/buy [item_id] [optional args]</code>\nExample: <code>/buy 1 Slayer Captain</code>", parse_mode="HTML")
            return

        chat_id = update.message.chat_id
        user_id = update.message.from_user.id
        
        try:
            item_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid Item ID! Please specify a number.")
            return

        item = self.economy_repo.get_shop_item(item_id)
        if not item:
            await update.message.reply_text("Item not found! Check `/shop` for valid ID listings.", parse_mode="HTML")
            return

        cost = item["cost"]
        balance = self.economy_repo.get_balance(chat_id, user_id)
        
        if balance < cost:
            await update.message.reply_text(f"❌ You do not have enough coins! Costs <b>{cost:,}</b> but you only have <b>{balance:,}</b>.", parse_mode="HTML")
            return

        # Buy logic
        if item_id == 1:
            # Custom Title Tag: requires name input
            tag_name = " ".join(context.args[1:]).strip()
            if not tag_name:
                await update.message.reply_text("Please specify your desired tag! Usage: <code>/buy 1 VIP Member</code>", parse_mode="HTML")
                return
            
            # Deduct coins and update tag
            self.economy_repo.deduct_coins(chat_id, user_id, cost)
            self.user_repo.update_user_stats(chat_id, user_id, tag=tag_name)
            await update.message.reply_text(f"🎉 Purchase successful! Your rank title has been set to: <b>{tag_name}</b>", parse_mode="HTML")

        elif item_id == 2:
            # Warning Cleanse: removes 1 warning strike
            warn_count = self.warning_repo.get_warnings(chat_id, user_id)
            if warn_count <= 0:
                await update.message.reply_text("You do not have any warnings to cleanse!")
                return
                
            self.economy_repo.deduct_coins(chat_id, user_id, cost)
            self.warning_repo.remove_warning(chat_id, user_id)
            await update.message.reply_text("🧼 Purchase successful! Removed 1 warning strike from your profile.")

        elif item_id == 3:
            # Water Breathing License
            self.economy_repo.deduct_coins(chat_id, user_id, cost)
            self.user_repo.update_user_stats(chat_id, user_id, tag="Water Breathing User")
            await update.message.reply_text("🌊 <b>Purchase successful!</b> You have earned a licensed title: <b>Water Breathing User</b>.", parse_mode="HTML")
        
        else:
            await update.message.reply_text("This item is currently out of stock.")

    async def pay_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Allows users to transfer coins to each other."""
        if not update.message: return
        sender = update.message.from_user
        chat_id = update.message.chat_id

        if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
            await update.message.reply_text("🌊 Please reply to the user you want to pay.\nExample: <code>/pay 100</code>", parse_mode="HTML")
            return

        target = update.message.reply_to_message.from_user
        
        if target.id == sender.id:
            await update.message.reply_text("❌ You cannot pay yourself.")
            return
            
        if target.is_bot:
            await update.message.reply_text("❌ You cannot transfer coins to a bot.")
            return

        try:
            amount = int(context.args[0])
            if amount <= 0: raise ValueError
        except (IndexError, ValueError):
            await update.message.reply_text("❌ Invalid amount.\nUsage: <code>/pay 100</code>", parse_mode="HTML")
            return

        # Deduct from Sender first (fails safely if they are broke)
        success = self.economy_repo.deduct_coins(chat_id, sender.id, amount)
        
        if success:
            # Give to Target
            self.economy_repo.add_coins(chat_id, target.id, amount)
            sender_bal = self.economy_repo.get_balance(chat_id, sender.id)
            
            await update.message.reply_text(
                f"💸 <b>Transfer Successful!</b>\n\n"
                f"📤 <b>From:</b> {sender.first_name} (<i>Remains: {sender_bal:,}</i>)\n"
                f"📥 <b>To:</b> {target.first_name}\n"
                f"🪙 <b>Amount:</b> <code>{amount:,}</code> coins\n",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ <b>Insufficient Funds!</b> You don't have
