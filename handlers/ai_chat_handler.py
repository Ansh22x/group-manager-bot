import time
import re
import logging
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from handlers.base_handler import BaseHandler
from handlers.leveling_handler import LevelingHandler
from handlers.economy_handler import EconomyHandler
from database import (
    ChatRepository, AFKRepository, TagRepository, FilterRepository, UserRepository, TempMuteRepository
)
from services.ai_agent import AIAgent
from config import is_bot_owner

logger = logging.getLogger(__name__)

# Shared unmute callback reference to avoid circular imports and repeated instantiation
async def _unmute_callback(context):
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    user_name = job.data["user_name"]
    try:
        perms = ChatPermissions(
            can_send_messages=True, can_send_audios=True,
            can_send_documents=True, can_send_photos=True,
            can_send_videos=True, can_send_other_messages=True
        )
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=perms)
        TempMuteRepository().remove_temp_mute(chat_id, user_id)
        await context.bot.send_message(chat_id, f"🔊 <b>{user_name}</b> has been unmuted (flood auto-mute expired).", parse_mode="HTML")
    except Exception as e:
        logger.error(f"_unmute_callback: Could not unmute user {user_id}: {e}")

class AIChatHandler(BaseHandler):
    def __init__(self):
        self.chat_repo = ChatRepository()
        self.afk_repo = AFKRepository()
        self.tag_repo = TagRepository()
        self.filter_repo = FilterRepository()
        self.user_repo = UserRepository()
        self.temp_mute_repo = TempMuteRepository()
        
        self.leveling_handler = LevelingHandler()
        self.economy_handler = EconomyHandler()
        self.ai_agent = AIAgent()

        # In-memory sliding window trackers - lazily cleaned on each access
        self.rate_limit_tracker = {}  # AI query limiter: {user_id: [timestamps]}
        self.flood_tracker = {}       # General flood limiter: {user_id: [timestamps]}

    def register(self, app: Application):
        app.add_handler(CommandHandler(["ask", "ai"], self.ask_cmd))
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

    def _get_window_timestamps(self, tracker: dict, user_id: int, window: float) -> list:
        """Returns cleaned list of timestamps within the given window; updates tracker in place"""
        now = time.time()
        clean = [t for t in tracker.get(user_id, []) if now - t < window]
        clean.append(now)
        tracker[user_id] = clean
        return clean

    async def message_handler_hub(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        chat_id = update.message.chat_id
        user = update.message.from_user

        # 1. Anti-Flood & Link Protection for normal group members only
        is_user_admin = await self.is_admin(update, context)
        if not is_user_admin and update.message.chat.type != 'private':
            # A. Anti-Flood Check (max 5 messages in 4 seconds)
            timestamps = self._get_window_timestamps(self.flood_tracker, user.id, 4.0)
            if len(timestamps) > 5:
                try:
                    await update.message.delete()
                except Exception:
                    pass
                try:
                    now = time.time()
                    perms = ChatPermissions(can_send_messages=False)
                    await context.bot.restrict_chat_member(chat_id, user.id, permissions=perms)
                    self.temp_mute_repo.add_temp_mute(chat_id, user.id, now + 300)

                    jobs = context.job_queue.get_jobs_by_name(f"tempmute_{chat_id}_{user.id}")
                    for job in jobs:
                        job.schedule_removal()

                    context.job_queue.run_once(
                        _unmute_callback,
                        when=300,
                        data={"chat_id": chat_id, "user_id": user.id, "user_name": user.first_name},
                        name=f"tempmute_{chat_id}_{user.id}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🤐 <b>{user.first_name}</b> is flooding the chat and has been muted for 5 minutes.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"AIChatHandler flood mute failed: {e}")
                return

            # B. Invite Link Protection
            message_text_raw = update.message.text or ""
            invite_pattern = r"(t\.me/joinchat|t\.me/\+|telegram\.me/joinchat|telegram\.me/\+|t\.me/c/)"
            if re.search(invite_pattern, message_text_raw.lower()):
                try:
                    await update.message.delete()
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ {user.first_name}, invite links are not allowed in this group."
                    )
                except Exception as e:
                    logger.error(f"AIChatHandler invite link protection failed: {e}")
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
            if replied_user and replied_user.id in afk_users:
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
        is_mention = bot_username and f"@{bot_username.lower()}" in lower_text
        is_reply_to_bot = (
            update.message.reply_to_message is not None
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.id == bot_id
        )

        if is_private or is_mention or is_reply_to_bot:
            # AI Rate Limiting: max 3 requests per 10 seconds
            ai_timestamps = self._get_window_timestamps(self.rate_limit_tracker, user.id, 10.0)
            if len(ai_timestamps) > 3:
                await update.message.reply_text("Please slow down. You are sending queries too quickly. 🌊")
                return

            await context.bot.send_chat_action(chat_id=chat_id, action="typing")

            clean_prompt = message_text
            if bot_username:
                clean_prompt = re.sub(rf"@{bot_username}", "", clean_prompt, flags=re.IGNORECASE).strip()
            prompt = clean_prompt or "Hello."

            user_stats = self.user_repo.get_user_stats(chat_id, user.id, user.first_name)
            user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

            response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt)
            try:
                await update.message.reply_text(response, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(response)

    async def ask_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Explicitly ask Giyu using the /ask or /ai command"""
        if not update.message: return

        chat_id = update.message.chat_id
        user = update.message.from_user

        # Extract prompt from command arguments or from a replied message
        prompt = " ".join(context.args).strip() if context.args else ""
        if not prompt and update.message.reply_to_message and update.message.reply_to_message.text:
            prompt = update.message.reply_to_message.text

        if not prompt:
            await update.message.reply_text(
                "🌊 <i>Please provide a question.</i>\n\n"
                "Example: <code>/ask How does this group work?</code> or reply to any message with <code>/ask</code>.",
                parse_mode="HTML"
            )
            return

        ai_timestamps = self._get_window_timestamps(self.rate_limit_tracker, user.id, 10.0)
        if len(ai_timestamps) > 3:
            await update.message.reply_text("Please slow down. You are sending queries too quickly. 🌊")
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        user_stats = self.user_repo.get_user_stats(chat_id, user.id, user.first_name)
        user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

        response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt)
        try:
            await update.message.reply_text(response, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(response)
