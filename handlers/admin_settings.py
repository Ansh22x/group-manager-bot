from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import is_bot_owner
from database import ChatRepository, TagRepository, FilterRepository, UserRepository

class AdminSettings(BaseHandler):
    def __init__(self):
        self.chat_repo = ChatRepository()
        self.tag_repo = TagRepository()
        self.filter_repo = FilterRepository()
        self.user_repo = UserRepository()

    def register(self, app: Application):
        app.add_handler(CommandHandler("setrules", self.set_rules))
        app.add_handler(CommandHandler("welcome", self.toggle_welcome))
        app.add_handler(CommandHandler("setwelcome", self.set_welcome))
        app.add_handler(CommandHandler("filter", self.add_filter_cmd))
        app.add_handler(CommandHandler("afkstat", self.toggle_afkstat))
        app.add_handler(CommandHandler("addtag", self.add_tag_cmd))
        app.add_handler(CommandHandler("edit_tag", self.edit_tag_cmd))
        app.add_handler(CommandHandler("settag", self.set_user_tag))

    async def is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if not update.message or update.message.chat.type == 'private': 
            return False
        if is_bot_owner(update.message.from_user.id):
            return True
        try:
            chat_member = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
            return chat_member.status in ['administrator', 'creator']
        except Exception:
            return False

    async def set_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        new_rules = " ".join(context.args)
        if new_rules:
            self.chat_repo.update_chat_settings(update.message.chat_id, rules=new_rules)
            await update.message.reply_text("Rules updated successfully!")

    async def toggle_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        chat_id = update.message.chat_id
        settings = self.chat_repo.get_chat_settings(chat_id)
        new_welcome_on = not settings.get('welcome_on', True)
        self.chat_repo.update_chat_settings(chat_id, welcome_on=new_welcome_on)
        status = "ON" if new_welcome_on else "OFF"
        await update.message.reply_text(f"Welcome messages are now {status}.")

    async def set_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        new_welcome = " ".join(context.args)
        if new_welcome:
            self.chat_repo.update_chat_settings(update.message.chat_id, welcome_msg=new_welcome)
            await update.message.reply_text("Welcome message updated! (Use {name} to insert the user's name).")

    async def add_filter_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if len(context.args) >= 2:
            keyword = context.args[0].lower()
            reply_text = " ".join(context.args[1:])
            self.filter_repo.add_filter(update.message.chat_id, keyword, reply_text)
            await update.message.reply_text(f"Filter added! When someone says '{keyword}', I will reply.")

    async def toggle_afkstat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        chat_id = update.message.chat_id
        settings = self.chat_repo.get_chat_settings(chat_id)
        new_afk_on = not settings.get('afk_on', True)
        self.chat_repo.update_chat_settings(chat_id, afk_on=new_afk_on)
        status = "ON" if new_afk_on else "OFF"
        await update.message.reply_text(f"AFK monitoring is now {status} for this group.")

    async def add_tag_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if len(context.args) >= 2:
            tag = context.args[0].lower().replace('#', '')
            reply_text = " ".join(context.args[1:])
            self.tag_repo.add_tag(update.message.chat_id, tag, reply_text)
            await update.message.reply_text(f"Tag added! Anyone can now type #{tag} to see it.")

    async def edit_tag_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if len(context.args) >= 2:
            tag = context.args[0].lower().replace('#', '')
            reply_text = " ".join(context.args[1:])
            chat_id = update.message.chat_id
            tags_dict = self.tag_repo.get_tags(chat_id)
            if tag in tags_dict:
                self.tag_repo.add_tag(chat_id, tag, reply_text)
                await update.message.reply_text(f"Tag #{tag} updated!")
            else:
                await update.message.reply_text(f"Tag #{tag} doesn't exist. Use /addtag to create it.")

    async def set_user_tag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if not update.message.reply_to_message:
            await update.message.reply_text("Reply to a user's message to set their tag!")
            return

        new_tag = " ".join(context.args)
        if not new_tag:
            await update.message.reply_text("Please provide a tag! Example: /settag VIP Member")
            return

        target_user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        
        self.user_repo.update_user_stats(chat_id, target_user.id, tag=new_tag)
        await update.message.reply_text(f"✅ Set {target_user.first_name}'s tag to: <b>{new_tag}</b>", parse_mode="HTML")
