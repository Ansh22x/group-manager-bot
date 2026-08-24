import json
import re
import os
import time
import re
import base64
import tempfile
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
            (filters.TEXT | filters.Sticker.ALL | filters.ANIMATION | filters.Document.ALL | filters.PHOTO | filters.VOICE | filters.AUDIO) & ~filters.COMMAND,
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

    # --- NEW HELPER METHODS FOR OPTIMIZATION ---

    async def _check_rate_limit(self, update: Update, user_id: int) -> bool:
        """Checks if the user is spamming AI commands. Returns True if limited."""
        timestamps = self._get_window_timestamps(self.rate_limit_tracker, user_id, 10.0)
        if len(timestamps) > 3:
            await update.message.reply_text("Please slow down. You are sending queries too quickly. 🌊")
            return True
        return False

    def _get_user_tag(self, chat_id: int, user_id: int, first_name: str) -> str:
        """Helper to get user's title tag quickly."""
        if is_bot_owner(user_id): return "Bot Owner"
        return self.user_repo.get_user_stats(chat_id, user_id, first_name).get('tag', 'Member')

    # -------------------------------------------

    async def message_handler_hub(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        chat_id = update.message.chat_id
        user = update.message.from_user
        bot_username = context.bot.username
        bot_id = context.bot.id
        is_private = update.message.chat.type == 'private'
        is_user_admin = await self.is_admin(update, context)

        # Unified text field (combines regular text and media captions)
        message_text = update.message.text or update.message.caption or ""
        lower_text = message_text.lower()

        # 1. Moderation: Anti-Flood & Link Protection
        if not is_user_admin and not is_private:
            timestamps = self._get_window_timestamps(self.flood_tracker, user.id, 4.0)
            if len(timestamps) > 5:
                try:
                    await update.message.delete()
                    now = time.time()
                    perms = ChatPermissions(can_send_messages=False)
                    await context.bot.restrict_chat_member(chat_id, user.id, permissions=perms)
                    self.temp_mute_repo.add_temp_mute(chat_id, user.id, now + 300)

                    jobs = context.job_queue.get_jobs_by_name(f"tempmute_{chat_id}_{user.id}") if context.job_queue else []
                    for job in jobs: job.schedule_removal()

                    if context.job_queue:
                        context.job_queue.run_once(_unmute_callback, when=300, data={"chat_id": chat_id, "user_id": user.id, "user_name": user.first_name}, name=f"tempmute_{chat_id}_{user.id}")
                    await context.bot.send_message(chat_id=chat_id, text=f"🤐 <b>{user.first_name}</b> is flooding the chat and has been muted for 5 minutes.", parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Flood mute failed: {e}")
                return

            invite_pattern = r"(t\.me/joinchat|t\.me/\+|telegram\.me/joinchat|telegram\.me/\+|t\.me/c/)"
            if re.search(invite_pattern, lower_text):
                try:
                    await update.message.delete()
                    await context.bot.send_message(chat_id=chat_id, text=f"❌ {user.first_name}, invite links are not allowed in this group.")
                except Exception: pass
                return

        # 2. Economy & Leveling
        await self.leveling_handler.award_xp(update, context)
        await self.economy_handler.award_coins(update, context)

        # 3. AFK Feature Integration
        settings = self.chat_repo.get_chat_settings(chat_id)
        if settings.get('afk_on', True):
            afk_users = self.afk_repo.get_afk_users()
            if afk_users:
                # Welcome back check
                if user.id in afk_users:
                    self.afk_repo.remove_user_afk(user.id)
                    await update.message.reply_text(f"🌊 Welcome back {user.first_name}. You are no longer AFK.")

                # Notification check (Replies & Tags)
                notified_afk_ids = set()
                
                # Check Replies
                if update.message.reply_to_message and update.message.reply_to_message.from_user:
                    replied_user = update.message.reply_to_message.from_user
                    if replied_user.id in afk_users and replied_user.id != user.id:
                        reason = afk_users[replied_user.id]
                        notified_afk_ids.add(replied_user.id)
                        await update.message.reply_text(f"💤 <b>{replied_user.first_name}</b> is currently AFK: {reason}", parse_mode="HTML")

                # Check Mentions
                if update.message.entities:
                    for entity in update.message.entities:
                        if entity.type == "text_mention" and entity.user:
                            target = entity.user
                            if target.id in afk_users and target.id not in notified_afk_ids and target.id != user.id:
                                notified_afk_ids.add(target.id)
                                await update.message.reply_text(f"💤 <b>{target.first_name}</b> is currently AFK: {afk_users[target.id]}", parse_mode="HTML")
                        
                        elif entity.type == "mention":
                            tagged_username = message_text[entity.offset:entity.offset + entity.length].lstrip("@").lower()
                            for afk_id, reason in afk_users.items():
                                if afk_id in notified_afk_ids or afk_id == user.id: continue
                                try:
                                    member = await context.bot.get_chat_member(chat_id, afk_id)
                                    if member.user.username and member.user.username.lower() == tagged_username:
                                        notified_afk_ids.add(afk_id)
                                        await update.message.reply_text(f"💤 <b>{member.user.first_name}</b> is currently AFK: {reason}", parse_mode="HTML")
                                        break
                                except Exception: pass

       # 4. Custom Filters and Tags
        for tag, reply in self.tag_repo.get_tags(chat_id).items():
            if f"#{tag}" in lower_text:
                await update.message.reply_text(reply)
                return

        for keyword, raw_reply in self.filter_repo.get_filters(chat_id).items():
            # Check if keyword matches whole word or substring
            pattern = rf"\b{re.escape(keyword)}\b"
            if re.search(pattern, lower_text):
                try:
                    # Attempt to read the rich-media JSON data
                    data = json.loads(raw_reply)
                    media_type = data.get("type", "text")
                    file_id = data.get("file_id")
                    caption = data.get("caption", "")

                    if media_type == "photo":
                        await update.message.reply_photo(photo=file_id, caption=caption or None)
                    elif media_type == "animation":
                        await update.message.reply_animation(animation=file_id, caption=caption or None)
                    elif media_type == "sticker":
                        await update.message.reply_sticker(sticker=file_id)
                    elif media_type == "document":
                        await update.message.reply_document(document=file_id, caption=caption or None)
                    elif media_type == "audio":
                        await update.message.reply_audio(audio=file_id, caption=caption or None)
                    elif media_type == "voice":
                        await update.message.reply_voice(voice=file_id, caption=caption or None)
                    else:
                        await update.message.reply_text(data.get("text", raw_reply))
                except json.JSONDecodeError:
                    # If it's not JSON (like an old text filter), just send it normally
                    await update.message.reply_text(raw_reply)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Error processing filter media: {e}")
                    await update.message.reply_text(raw_reply)
                return
                
        # 5. Document Upload (Inline Learn)
        if update.message.document:
            is_tag = bot_username and f"@{bot_username.lower()}" in lower_text
            if is_tag or "/learn" in lower_text:
                if not is_user_admin:
                    await update.message.reply_text("❌ Only group administrators can teach Giyu-Bot custom documents.")
                    return
                doc = update.message.document
                status = await update.message.reply_text("🪄 <i>Concentrating... Reading document...</i>", parse_mode="HTML")
                try:
                    file = await context.bot.get_file(doc.file_id)
                    file_bytes = await file.download_as_bytearray()
                    from services.document_rag import DocumentRAGService
                    chunks_learned = await DocumentRAGService(self.ai_agent).learn_document(chat_id, file_bytes, doc.file_name)
                    await status.edit_text(f"✅ <b>Successfully learned!</b>\n\nIntegrated <b>{chunks_learned} facts</b> from <code>{doc.file_name}</code>.", parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Doc process error: {e}")
                    await status.edit_text("❌ Failed to learn document.")
            return

        # --- AI TRIGGER CHECKS ---
        is_reply_to_bot = bool(update.message.reply_to_message and update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.id == bot_id)
        is_mention = bot_username and f"@{bot_username.lower()}" in lower_text
        user_tag = self._get_user_tag(chat_id, user.id, user.first_name)

        # 6. Media AI Handling (Voice)
        if update.message.voice:
            if not (is_private or is_reply_to_bot): return
            if await self._check_rate_limit(update, user.id): return

            await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")
            try:
                voice = update.message.voice
                file = await context.bot.get_file(voice.file_id)
                ogg_path = os.path.join(tempfile.gettempdir(), f"voice_{voice.file_id}.ogg")
                with open(ogg_path, "wb") as f_ogg: f_ogg.write(await file.download_as_bytearray())

                prompt = await self.ai_agent.transcribe_voice(ogg_path)
                if os.path.exists(ogg_path): os.remove(ogg_path)

                if not prompt or not prompt.strip():
                    await update.message.reply_text("🌊 *Silence.* I could not transcribe that.", parse_mode="Markdown")
                    return

                response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt, update=update, context=context, is_admin=is_user_admin)
                active_char = self.chat_repo.get_chat_character(chat_id) or "giyu"
                speech_bytes = await self.ai_agent.text_to_speech(response, active_char)

                if speech_bytes:
                    mp3_path = os.path.join(tempfile.gettempdir(), f"reply_{voice.file_id}.mp3")
                    with open(mp3_path, "wb") as f_out: f_out.write(speech_bytes)
                    await update.message.reply_voice(voice=open(mp3_path, "rb"), caption=f"🗣️ <i>Transcribed request: \"{prompt}\"</i>", parse_mode="HTML")
                    if os.path.exists(mp3_path): os.remove(mp3_path)
                else:
                    await update.message.reply_text(response)
            except Exception as e:
                logger.error(f"Voice handler failed: {e}")
            return

        # 7. Media AI Handling (Photo)
        if update.message.photo:
            if not (is_private or is_mention or is_reply_to_bot): return
            if await self._check_rate_limit(update, user.id): return
            
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            try:
                file = await context.bot.get_file(update.message.photo[-1].file_id)
                base64_img = base64.b64encode(await file.download_as_bytearray()).decode('utf-8')
                
                clean_prompt = re.sub(rf"@{bot_username}", "", message_text, flags=re.IGNORECASE).strip() if bot_username else message_text
                prompt = clean_prompt or "Describe this image."
                
                response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt, update=update, context=context, is_admin=is_user_admin, base64_image=base64_img, image_mime="image/jpeg")
                await update.message.reply_text(response, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Photo handler failed: {e}")
            return

        # 8. Media AI Handling (Sticker)
        if update.message.sticker:
            if not (is_private or is_mention or is_reply_to_bot): return
            if await self._check_rate_limit(update, user.id): return
            
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            try:
                sticker = update.message.sticker
                base64_img = None
                if not sticker.is_animated and not sticker.is_video:
                    file = await context.bot.get_file(sticker.file_id)
                    base64_img = base64.b64encode(await file.download_as_bytearray()).decode('utf-8')

                prompt = (
                    f"The user sent a sticker (emoji: {sticker.emoji or ''}, file_id: '{sticker.file_id}'). "
                    f"React naturally as Giyu in 1-2 sentences. You may use save_sticker_to_stock if you like it, or send_sticker_reply."
                )
                
                response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt, update=update, context=context, is_admin=is_user_admin, base64_image=base64_img, image_mime="image/webp")
                if response and response.strip():
                    await update.message.reply_text(response, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Sticker handler failed: {e}")
            return

        # 9. Media AI Handling (Audio/Music)
        if update.message.audio:
            if not (is_private or is_mention or is_reply_to_bot): return
            if await self._check_rate_limit(update, user.id): return
            
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            try:
                audio = update.message.audio
                if audio.file_size and audio.file_size > 20 * 1024 * 1024:
                    await update.message.reply_text("❌ This audio track is too large to analyze. (Max limit: 20MB)")
                    return

                file = await context.bot.get_file(audio.file_id)
                ext = os.path.splitext(audio.file_name or "track.mp3")[1] or ".mp3"
                audio_path = os.path.join(tempfile.gettempdir(), f"audio_{audio.file_id}{ext}")
                with open(audio_path, "wb") as f_out: f_out.write(await file.download_as_bytearray())

                transcription = await self.ai_agent.transcribe_voice(audio_path)
                if os.path.exists(audio_path): os.remove(audio_path)

                clean_caption = re.sub(rf"@{bot_username}", "", message_text, flags=re.IGNORECASE).strip() if bot_username else message_text
                
                prompt = f"[SENT AUDIO FILE] File: {audio.file_name or 'track.mp3'}\n"
                prompt += f"Transcription:\n\"\"\"{transcription}\"\"\"\n" if transcription else "Note: No clear spoken vocals detected.\n"
                if clean_caption: prompt += f"\nUser Question/Comment: {clean_caption}"

                response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt, update=update, context=context, is_admin=is_user_admin)
                await update.message.reply_text(response, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Audio handler failed: {e}")
            return

        # 10. Text AI Handling (Direct Mention / Reply to Bot)
        if not message_text: return
        
        if is_private or is_mention or is_reply_to_bot:
            if await self._check_rate_limit(update, user.id): return
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            
            clean_prompt = re.sub(rf"@{bot_username}", "", message_text, flags=re.IGNORECASE).strip() if bot_username else message_text
            prompt = clean_prompt or "What do you think?"
            
            # Check for Vision context in reply
            replied = update.message.reply_to_message
            replied_base64, replied_mime, replied_extra = None, "image/jpeg", ""
            
            if replied:
                try:
                    if replied.photo:
                        file = await context.bot.get_file(replied.photo[-1].file_id)
                        replied_base64 = base64.b64encode(await file.download_as_bytearray()).decode()
                        replied_extra = "[User tagged you replying to a photo. Attached.]"
                    elif replied.sticker and not replied.sticker.is_animated and not replied.sticker.is_video:
                        file = await context.bot.get_file(replied.sticker.file_id)
                        replied_base64 = base64.b64encode(await file.download_as_bytearray()).decode()
                        replied_mime = "image/webp"
                        replied_extra = f"[User tagged you replying to a static sticker. Attached.]"
                    elif replied.sticker:
                        replied_extra = f"[User tagged you replying to an animated sticker (emoji: {replied.sticker.emoji}).]"
                    elif replied.voice or replied.audio:
                        replied_extra = "[User tagged you replying to an audio message.]"
                except Exception as e: logger.warning(f"Failed to extract replied media: {e}")

            if replied_extra: prompt = f"{replied_extra}\n\nUser: {prompt}"
            
            response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt, update=update, context=context, is_admin=is_user_admin, base64_image=replied_base64, image_mime=replied_mime)
            try: await update.message.reply_text(response, parse_mode="Markdown")
            except Exception: await update.message.reply_text(response)
            return

        # 11. Text AI Handling (Ambient Intent trigger)
        intent = detect_intent_fast(message_text, bot_username)
        if intent.triggered and intent.intent_type == "question":
            if await self._check_rate_limit(update, user.id): return
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            
            response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, intent.subject or message_text, update=update, context=context, is_admin=is_user_admin)
            try: await update.message.reply_text(response, parse_mode="Markdown")
            except Exception: await update.message.reply_text(response)

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

        if await self._check_rate_limit(update, user.id): return

        thinking_msg = await update.message.reply_text("🌊 <i>Concentrating...</i>", parse_mode="HTML")
        user_tag = self._get_user_tag(chat_id, user.id, user.first_name)
        is_user_admin = await self.is_admin(update, context)

        response = await self.ai_agent.ask(chat_id, user.id, user.first_name, user_tag, prompt, update=update, context=context, is_admin=is_user_admin)
        try: await thinking_msg.edit_text(response, parse_mode="Markdown")
        except Exception: await thinking_msg.edit_text(response)

    async def learn_doc_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        chat_id = update.message.chat_id
        
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
                "3. Giyu-Bot will analyze and save facts to memory for this chat.",
                parse_mode="HTML"
            )
            return
            
        doc = reply.document
        status = await update.message.reply_text("🪄 <i>Concentrating... Reading document and generating embeddings...</i>", parse_mode="HTML")
        
        try:
            file = await context.bot.get_file(doc.file_id)
            file_bytes = await file.download_as_bytearray()
            from services.document_rag import DocumentRAGService
            chunks_learned = await DocumentRAGService(self.ai_agent).learn_document(chat_id, file_bytes, doc.file_name)
            await status.edit_text(f"✅ <b>Successfully learned!</b>\n\nIntegrated <b>{chunks_learned} facts</b> from <code>{doc.file_name}</code>.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in learn_doc_cmd: {e}")
            await status.edit_text(f"❌ Failed to learn document: {e}")
