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
from services.intent_detector import detect_intent_fast
from config import is_bot_owner

logger = logging.getLogger(__name__)

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

        self.rate_limit_tracker = {}  
        self.flood_tracker = {}       

    def register(self, app: Application):
        app.add_handler(CommandHandler(["ask", "ai"], self.ask_cmd))
        app.add_handler(CommandHandler("learn", self.learn_doc_cmd))
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
        now = time.time()
        clean = [t for t in tracker.get(user_id, []) if now - t < window]
        clean.append(now)
        tracker[user_id] = clean
        return clean

    async def message_handler_hub(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        chat_id = update.message.chat_id
        user = update.message.from_user

        is_user_admin = await self.is_admin(update, context)
        if not is_user_admin and update.message.chat.type != 'private':
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
                    await context.bot.send_message(chat_id=chat_id, text=f"🤐 <b>{user.first_name}</b> is flooding the chat and has been muted for 5 minutes.", parse_mode="HTML")
                except Exception as e:
                    logger.error(f"AIChatHandler flood mute failed: {e}")
                return

            message_text_raw = update.message.text or ""
            invite_pattern = r"(t\.me/joinchat|t\.me/\+|telegram\.me/joinchat|telegram\.me/\+|t\.me/c/)"
            if re.search(invite_pattern, message_text_raw.lower()):
                try:
                    await update.message.delete()
                    await context.bot.send_message(chat_id=chat_id, text=f"❌ {user.first_name}, invite links are not allowed in this group.")
                except Exception as e:
                    logger.error(f"AIChatHandler invite link protection failed: {e}")
                return

        await self.leveling_handler.award_xp(update, context)
        await self.economy_handler.award_coins(update, context)

        # Check for inline document upload + caption tag/command
        if update.message.document:
            caption = update.message.caption or ""
            bot_username = context.bot.username
            is_tag = bot_username and f"@{bot_username.lower()}" in caption.lower()
            is_learn_cmd = "/learn" in caption.lower()
            
            if is_tag or is_learn_cmd:
                is_user_admin = await self.is_admin(update, context)
                if not is_user_admin:
                    await update.message.reply_text("❌ Only group administrators can teach Giyu-Bot custom documents.")
                    return
                    
                doc = update.message.document
                status = await update.message.reply_text("🪄 <i>Concentrating... Reading document and generating embeddings...</i>", parse_mode="HTML")
                try:
                    file = await context.bot.get_file(doc.file_id)
                    file_bytes = await file.download_as_bytearray()
                    
                    from services.document_rag import DocumentRAGService
                    rag_service = DocumentRAGService(self.ai_agent)
                    
                    chunks_learned = await rag_service.learn_document(chat_id, file_bytes, doc.file_name)
                    await status.edit_text(
                        f"✅ <b>Successfully learned!</b>\n\n"
                        f"Giyu-Bot has extracted, vectorized, and integrated <b>{chunks_learned} facts</b> from <code>{doc.file_name}</code> into its active memory context for this group chat. 🌊",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error in message_handler_hub doc process: {e}", exc_info=True)
                    await status.edit_text(f"❌ Failed to learn document: {e}")
                return

        if not update.message.text: return

        message_text = update.message.text
        bot_username = context.bot.username
        bot_id = context.bot.id

        settings = self.chat_repo.get_chat_settings(chat_id)
        afk_on = settings.get('afk_on', True)

        afk_users = self.afk_repo.get_afk_users()
        if user.id in afk_users and afk_on:
            self.afk_repo.remove_user_afk(user.id)
            await update.message.reply_text(f"Welcome back {user.first_name}. You are no longer AFK.")

        if update.message.reply_to_message and afk_on:
            replied_user = update.message.reply_to_message.from_user
            if replied_user and replied_user.id in afk_users:
                reason = afk_users[replied_user.id]
                await update.message.reply_text(f"💤 {replied_user.first_name} is currently AFK: {reason}")

        lower_text = message_text.lower()
        tags = self.tag_repo.get_tags(chat_id)
        for tag, reply in tags.items():
            if f"#{tag}" in lower_text:
                await update.message.reply_text(reply)
                return

        filters_dict = self.filter_repo.get_filters(chat_id)
        for keyword, reply in filters_dict.items():
            if keyword in lower_text:
                await update.message.reply_text(reply)
                return

        is_private = update.message.chat.type == 'private'
        is_mention = bot_username and f"@{bot_username.lower()}" in lower_text
        is_reply_to_bot = (
            update.message.reply_to_message is not None
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.id == bot_id
        )

        if is_private or is_mention or is_reply_to_bot:
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

            response = await self.ai_agent.ask(
                chat_id, user.id, user.first_name, user_tag, prompt,
                update=update, context=context, is_admin=is_user_admin
            )
            try:
                await update.message.reply_text(response, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(response)
            return

        # --- Ambient Autonomous Agent: keyword + bot-name triggers ---
        intent = detect_intent_fast(message_text, bot_username)
        if intent.triggered and intent.intent_type != "none":
            ai_timestamps = self._get_window_timestamps(self.rate_limit_tracker, user.id, 10.0)
            if len(ai_timestamps) > 3:
                return  # Silently rate-limit ambient triggers

            user_stats = self.user_repo.get_user_stats(chat_id, user.id, user.first_name)
            user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

            if intent.intent_type == "play_audio" and intent.subject:
                # Direct fast-path: skip LLM, spawn download task immediately
                from handlers.media_handler import MediaHandler
                import asyncio
                handler = MediaHandler()
                context.args = intent.subject.split()
                asyncio.create_task(handler._do_play(update, context))
            elif intent.intent_type == "play_video" and intent.subject:
                from handlers.media_handler import MediaHandler
                import asyncio
                handler = MediaHandler()
                context.args = intent.subject.split()
                asyncio.create_task(handler._do_video(update, context))
            else:
                # Route to full agentic loop for question/moderation
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                response = await self.ai_agent.ask(
                    chat_id, user.id, user.first_name, user_tag, intent.subject or message_text,
                    update=update, context=context, is_admin=is_user_admin
                )
                try:
                    await update.message.reply_text(response, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(response)

    async def ask_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        chat_id = update.message.chat_id
        user = update.message.from_user

        prompt = " ".join(context.args).strip() if context.args else ""
        if not prompt and update.message.reply_to_message and update.message.reply_to_message.text:
            prompt = update.message.reply_to_message.text

        if not prompt:
            await update.message.reply_text("🌊 <i>Please provide a question.</i>\n\nExample: <code>/ask How does this group work?</code> or reply to any message with <code>/ask</code>.", parse_mode="HTML")
            return

        ai_timestamps = self._get_window_timestamps(self.rate_limit_tracker, user.id, 10.0)
        if len(ai_timestamps) > 3:
            await update.message.reply_text("Please slow down. You are sending queries too quickly. 🌊")
            return

        thinking_msg = await update.message.reply_text("🌊 <i>Concentrating...</i>", parse_mode="HTML")

        user_stats = self.user_repo.get_user_stats(chat_id, user.id, user.first_name)
        user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

        response = await self.ai_agent.ask(
            chat_id, user.id, user.first_name, user_tag, prompt,
            update=update, context=context, is_admin=is_user_admin
        )
        try:
            await thinking_msg.edit_text(response, parse_mode="Markdown")
        except Exception:
            await thinking_msg.edit_text(response)

    async def learn_doc_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        
        chat_id = update.message.chat_id
        user = update.message.from_user
        
        is_user_admin = await self.is_admin(update, context)
        if not is_user_admin:
            await update.message.reply_text("❌ Only group administrators can teach Giyu-Bot custom documents.")
            return
            
        reply = update.message.reply_to_message
        if not reply or not reply.document:
            await update.message.reply_text(
                "ℹ️ <b>How to teach Giyu-Bot documents:</b>\n\n"
                "1. Upload a document (<code>.txt</code>, <code>.pdf</code>, or <code>.md</code>) to the chat.\n"
                "2. Reply to that document message with the command <code>/learn</code>.\n"
                "3. Giyu-Bot will download, analyze, and save its facts to memory for this chat.",
                parse_mode="HTML"
            )
            return
            
        doc = reply.document
        status = await update.message.reply_text("🪄 <i>Concentrating... Reading document and generating embeddings...</i>", parse_mode="HTML")
        
        try:
            file = await context.bot.get_file(doc.file_id)
            file_bytes = await file.download_as_bytearray()
            
            from services.document_rag import DocumentRAGService
            rag_service = DocumentRAGService(self.ai_agent)
            
            chunks_learned = await rag_service.learn_document(chat_id, file_bytes, doc.file_name)
            
            await status.edit_text(
                f"✅ <b>Successfully learned!</b>\n\n"
                f"Giyu-Bot has extracted, vectorized, and integrated <b>{chunks_learned} facts</b> from <code>{doc.file_name}</code> into its active memory context for this group chat. 🌊",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error in learn_doc_cmd: {e}", exc_info=True)
            await status.edit_text(f"❌ Failed to learn document: {e}")
