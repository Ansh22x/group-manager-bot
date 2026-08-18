from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from handlers.base_handler import BaseHandler
from handlers.leveling_handler import LevelingHandler
from handlers.economy_handler import EconomyHandler
from database import (
    ChatRepository, AFKRepository, TagRepository, FilterRepository, UserRepository
)
from services.ai_agent import AIAgent
from config import is_bot_owner

class AIChatHandler(BaseHandler):
    def __init__(self):
        self.chat_repo = ChatRepository()
        self.afk_repo = AFKRepository()
        self.tag_repo = TagRepository()
        self.filter_repo = FilterRepository()
        self.user_repo = UserRepository()
        
        # Instantiate dependencies
        self.leveling_handler = LevelingHandler()
        self.economy_handler = EconomyHandler()
        self.ai_agent = AIAgent()

    def register(self, app: Application):
        # Command /ask
        app.add_handler(CommandHandler("ask", self.ask_cmd))
        # Status update (Welcome new users)
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.welcome_new_member))
        # General message parser
        app.add_handler(MessageHandler(
            (filters.TEXT | filters.Sticker.ALL | filters.ANIMATION | filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND,
            self.message_handler_hub
        ))

    async def message_handler_hub(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        
        # 1. Award XP and coins first
        await self.leveling_handler.award_xp(update, context)
        await self.economy_handler.award_coins(update, context)
        
        if not update.message.text: return

        message_text = update.message.text
        chat_id = update.message.chat_id
        user = update.message.from_user
        bot_username = context.bot.username
        bot_id = context.bot.id

        # Get settings
        settings = self.chat_repo.get_chat_settings(chat_id)
        afk_on = settings.get('afk_on', True)

        # 2. AFK Welcome Back check
        afk_users = self.afk_repo.get_afk_users()
        if user.id in afk_users and afk_on:
            self.afk_repo.remove_user_afk(user.id)
            await update.message.reply_text(f"Welcome back {user.first_name}. You are no longer AFK.")

        # 3. AFK Reply Warning check
        if update.message.reply_to_message and afk_on:
            replied_user = update.message.reply_to_message.from_user
            if replied_user.id in afk_users:
                reason = afk_users[replied_user.id]
                await update.message.reply_text(f"💤 {replied_user.first_name} is currently AFK: {reason}")

        # 4. Custom Hashtag Tags
        lower_text = message_text.lower()
        tags = self.tag_repo.get_tags(chat_id)
        for tag, reply in tags.items():
            if f"#{tag}" in lower_text:
                await update.message.reply_text(reply)
                return

        # 5. Custom Keyword Filters
        filters_dict = self.filter_repo.get_filters(chat_id)
        for keyword, reply in filters_dict.items():
            if keyword in lower_text:
                await update.message.reply_text(reply)
                return

        # 6. AI Giyu Chat Trigger Check
        is_private = update.message.chat.type == 'private'
        is_mention = f"@{bot_username}" in message_text
        is_reply_to_bot = (
            update.message.reply_to_message is not None 
            and update.message.reply_to_message.from_user.id == bot_id
        )

        if is_private or is_mention or is_reply_to_bot:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")

            # Clean prompt (remove bot handle if present)
            prompt = message_text.replace(f"@{bot_username}", "").strip()
            if not prompt:
                prompt = "Hello."

            # Fetch user's title tag
            user_stats = self.user_repo.get_user_stats(chat_id, user.id, user.first_name)
            user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

            # Ask Giyu Agent class
            response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt)
            
            try:
                await update.message.reply_text(response, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(response)

    async def ask_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Explicitly ask Giyu using the /ask command"""
        if not update.message or not update.message.text: return

        chat_id = update.message.chat_id
        user = update.message.from_user
        
        prompt = " ".join(context.args)
        if not prompt:
            await update.message.reply_text("Please provide a question. Example: `/ask How does this group work?`", parse_mode="Markdown")
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Fetch user's title tag
        user_stats = self.user_repo.get_user_stats(chat_id, user.id, user.first_name)
        user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

        response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt)
        
        try:
            await update.message.reply_text(response, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(response)

    async def welcome_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        settings = self.chat_repo.get_chat_settings(chat_id)
        if not settings.get('welcome_on', True): return
        
        for new_member in update.message.new_chat_members:
            if new_member.id != context.bot.id:
                greeting = settings.get('welcome_msg', "Welcome to the group, {name}!").replace("{name}", new_member.first_name)
                await update.message.reply_text(greeting)
