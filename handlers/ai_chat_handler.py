import time
import re
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from handlers.base_handler import BaseHandler
from handlers.leveling_handler import LevelingHandler
from handlers.economy_handler import EconomyHandler
from database import (
    ChatRepository, AFKRepository, TagRepository, FilterRepository, UserRepository, TempMuteRepository
)
from services.ai_agent import AIAgent
from services.welcome_card import WelcomeCard
from config import is_bot_owner

class AIChatHandler(BaseHandler):
    def __init__(self):
        self.chat_repo = ChatRepository()
        self.afk_repo = AFKRepository()
        self.tag_repo = TagRepository()
        self.filter_repo = FilterRepository()
        self.user_repo = UserRepository()
        self.temp_mute_repo = TempMuteRepository()
        
        # Instantiate dependencies
        self.leveling_handler = LevelingHandler()
        self.economy_handler = EconomyHandler()
        self.ai_agent = AIAgent()

        # In-memory sliding window trackers
        self.rate_limit_tracker = {}  # AI query limiter
        self.flood_tracker = {}       # General flood limiter: {user_id: [timestamps]}

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

    async def message_handler_hub(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        
        chat_id = update.message.chat_id
        user = update.message.from_user
        
        # 1. Anti-Flood & Link Protection for normal members
        is_user_admin = await self.is_admin(update, context)
        if not is_user_admin and update.message.chat.type != 'private':
            # A. Anti-Flood Check (max 5 messages in 4 seconds)
            now = time.time()
            user_id = user.id
            all_timestamps = [t for t in self.flood_tracker.get(user_id, []) if now - t < 4]
            all_timestamps.append(now)
            self.flood_tracker[user_id] = all_timestamps

            if len(all_timestamps) > 5:
                try:
                    await update.message.delete()
                except Exception:
                    pass
                
                # Temp mute user for 5 minutes (300 seconds)
                try:
                    perms = ChatPermissions(can_send_messages=False)
                    await context.bot.restrict_chat_member(chat_id, user_id, permissions=perms)
                    self.temp_mute_repo.add_temp_mute(chat_id, user_id, now + 300)

                    # Cancel any active temp-mute jobs
                    jobs = context.job_queue.get_jobs_by_name(f"tempmute_{chat_id}_{user_id}")
                    for job in jobs:
                        job.schedule_removal()

                    # Schedule automatic unmute callback (from AdminModeration)
                    from handlers.admin_moderation import AdminModeration
                    context.job_queue.run_once(
                        AdminModeration().temp_unmute_callback,
                        when=300,
                        data={"chat_id": chat_id, "user_id": user_id, "user_name": user.first_name},
                        name=f"tempmute_{chat_id}_{user_id}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🤐 <b>{user.first_name}</b> is flooding the chat and has been muted for 5 minutes.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"AIChatHandler flood mute failed: {e}")
                return

            # B. Invite Link Protection
            message_text = update.message.text or ""
            invite_pattern = r"(t\.me/joinchat|t\.me/\+|telegram\.me/joinchat|telegram\.me/\+|t\.me/c/)"
            if re.search(invite_pattern, message_text.lower()):
                try:
                    await update.message.delete()
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ {user.first_name}, invite links are not allowed in this group."
                    )
                except Exception as e:
                    print(f"AIChatHandler invite link protection failed: {e}")
                return

        # 2. Award XP and coins
        await self.leveling_handler.award_xp(update, context)
        await self.economy_handler.award_coins(update, context)
        
        if not update.message.text: return

        message_text = update.message.text
        bot_username = context.bot.username
        bot_id = context.bot.id

        # Get settings
        settings = self.chat_repo.get_chat_settings(chat_id)
        afk_on = settings.get('afk_on', True)

        # 3. AFK Welcome Back check
        afk_users = self.afk_repo.get_afk_users()
        if user.id in afk_users and afk_on:
            self.afk_repo.remove_user_afk(user.id)
            await update.message.reply_text(f"Welcome back {user.first_name}. You are no longer AFK.")

        # 4. AFK Reply Warning check
        if update.message.reply_to_message and afk_on:
            replied_user = update.message.reply_to_message.from_user
            if replied_user.id in afk_users:
                reason = afk_users[replied_user.id]
                await update.message.reply_text(f"💤 {replied_user.first_name} is currently AFK: {reason}")

        # 5. Custom Hashtag Tags
        lower_text = message_text.lower()
        tags = self.tag_repo.get_tags(chat_id)
        for tag, reply in tags.items():
            if f"#{tag}" in lower_text:
                await update.message.reply_text(reply)
                return

        # 6. Custom Keyword Filters
        filters_dict = self.filter_repo.get_filters(chat_id)
        for keyword, reply in filters_dict.items():
            if keyword in lower_text:
                await update.message.reply_text(reply)
                return

        # 7. AI Giyu Chat Trigger Check
        is_private = update.message.chat.type == 'private'
        is_mention = f"@{bot_username}" in message_text
        is_reply_to_bot = (
            update.message.reply_to_message is not None 
            and update.message.reply_to_message.from_user.id == bot_id
        )

        if is_private or is_mention or is_reply_to_bot:
            # Flood Rate Limiting check: max 3 requests in 10 seconds
            now = time.time()
            user_id = user.id
            
            user_timestamps = [t for t in self.rate_limit_tracker.get(user_id, []) if now - t < 10]
            user_timestamps.append(now)
            self.rate_limit_tracker[user_id] = user_timestamps
            
            if len(user_timestamps) > 3:
                await update.message.reply_text("Please slow down. You are sending queries too quickly. 🌊")
                return

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

        # Flood Rate Limiting check: max 3 requests in 10 seconds
        now = time.time()
        user_id = user.id
        
        user_timestamps = [t for t in self.rate_limit_tracker.get(user_id, []) if now - t < 10]
        user_timestamps.append(now)
        self.rate_limit_tracker[user_id] = user_timestamps
        
        if len(user_timestamps) > 3:
            await update.message.reply_text("Please slow down. You are sending queries too quickly. 🌊")
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
            if new_member.id == context.bot.id:
                continue
                
            greeting = settings.get('welcome_msg', "Welcome to the group, {name}!").replace("{name}", new_member.first_name)
            
            # Download profile avatar bytes if available
            avatar_bytes = None
            try:
                photos = await context.bot.get_user_profile_photos(new_member.id, limit=1)
                if photos and photos.photos:
                    photo_file = await context.bot.get_file(photos.photos[0][-1].file_id)
                    avatar_bytes = await photo_file.download_as_bytearray()
            except Exception as e:
                print(f"AIChatHandler welcome card: Could not fetch avatar: {e}")

            try:
                # Render visual Welcome Card using Pillow
                card_stream = WelcomeCard.generate(avatar_bytes, new_member.first_name, update.message.chat.title)
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=card_stream,
                    caption=greeting
                )
            except Exception as e:
                print(f"AIChatHandler: Welcome card failed, falling back to text: {e}")
                await update.message.reply_text(greeting)
