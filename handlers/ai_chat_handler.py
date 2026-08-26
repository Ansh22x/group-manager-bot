import json
import re
import os
import time
import logging
import asyncio

from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from handlers.base_handler import BaseHandler
from handlers.leveling_handler import LevelingHandler
from handlers.economy_handler import EconomyHandler
from database import (
    ChatRepository, AFKRepository, TagRepository, FilterRepository, UserRepository, TempMuteRepository, BlacklistRepository, CharacterRepository
)
from services.ai_agent import AIAgent
from services.voice_engine import VoiceEngine
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
        self.blacklist_repo = BlacklistRepository()
        self.character_repo = CharacterRepository()
        
        self.leveling_handler = LevelingHandler()
        self.economy_handler = EconomyHandler()
        self.ai_agent = AIAgent()

        self.rate_limit_tracker = {}  
        self.flood_tracker = {}        

    def register(self, app: Application):
        app.add_handler(CommandHandler(["ask", "ai"], self.ask_cmd))
        app.add_handler(CommandHandler("learn", self.learn_doc_cmd))
        app.add_handler(CommandHandler("purge", self.purge_cmd))
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

    async def _check_rate_limit(self, update: Update, user_id: int) -> bool:
        timestamps = self._get_window_timestamps(self.rate_limit_tracker, user_id, 10.0)
        if len(timestamps) > 3:
            await update.message.reply_text("Please slow down. You are sending queries too quickly. 🌊")
            return True
        return False

    def _get_user_tag(self, chat_id: int, user_id: int, first_name: str) -> str:
        if is_bot_owner(user_id): return "Bot Owner"
        return self.user_repo.get_user_stats(chat_id, user_id, first_name).get('tag', 'Member')

    async def _run_ai_task(self, coro_func, *args, **kwargs):
        """Runs heavy, blocking AI coroutines in a background thread."""
        def thread_worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro_func(*args, **kwargs))
            finally:
                loop.close()
        return await asyncio.to_thread(thread_worker)

    # -------------------------------------------

    async def message_handler_hub(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes core bot features (AFK, Economy, Filters) but DOES NOT auto-reply using AI."""
        if not update.message: return

        chat_id = update.message.chat_id
        user = update.message.from_user
        is_private = update.message.chat.type == 'private'
        is_user_admin = await self.is_admin(update, context)

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

            # Check Banned Words (Blacklist Auto-Censor)
            banned_words = self.blacklist_repo.get_blacklist(chat_id)
            if banned_words:
                for b_word in banned_words:
                    if re.search(rf"\b{re.escape(b_word)}\b", lower_text):
                        try:
                            await update.message.delete()
                            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ {user.first_name}, your message contained a blacklisted word and was removed.")
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

                # Notification check (Replies & Mentions)
                notified_afk_ids = set()
                
                if update.message.reply_to_message and update.message.reply_to_message.from_user:
                    replied_user = update.message.reply_to_message.from_user
                    if replied_user.id in afk_users and replied_user.id != user.id:
                        reason = afk_users[replied_user.id]
                        notified_afk_ids.add(replied_user.id)
                        await update.message.reply_text(f"💤 <b>{replied_user.first_name}</b> is currently AFK: {reason}", parse_mode="HTML")

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
            pattern = rf"\b{re.escape(keyword)}\b"
            if re.search(pattern, lower_text):
                try:
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
                    await update.message.reply_text(raw_reply)
                except Exception as e:
                    logger.error(f"Error processing filter media: {e}")
                    await update.message.reply_text(raw_reply)
                return
                
        # 5. Document Upload (Inline Learn) - Preserved for /learn usage
        if update.message.document:
            if "/learn" in lower_text:
                if not is_user_admin:
                    await update.message.reply_text("❌ Only group administrators can teach Giyu-Bot custom documents.")
                    return
                doc = update.message.document
                status = await update.message.reply_text("🪄 <i>Concentrating... Reading document...</i>", parse_mode="HTML")
                try:
                    file = await context.bot.get_file(doc.file_id)
                    file_bytes = await file.download_as_bytearray()
                    from services.document_rag import DocumentRAGService
                    chunks_learned = await self._run_ai_task(DocumentRAGService(self.ai_agent).learn_document, chat_id, file_bytes, doc.file_name)
                    await status.edit_text(f"✅ <b>Successfully learned!</b>\n\nIntegrated <b>{chunks_learned} facts</b> from <code>{doc.file_name}</code>.", parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Doc process error: {e}")
                    await status.edit_text("❌ Failed to learn document.")
            return

        # 6. Conversational AI Auto-Reply (Private DM, Reply-to-Bot, @Mention, or Name Trigger)
        is_reply_to_bot = (
            update.message.reply_to_message
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        
        # Ensure bot username is resolved accurately
        bot_username = (context.bot.username or "").lower()
        if not bot_username:
            try:
                me = await context.bot.get_me()
                bot_username = (me.username or "").lower()
            except Exception:
                pass

        is_bot_mentioned = False
        if bot_username and f"@{bot_username}" in lower_text:
            is_bot_mentioned = True
            
        if not is_bot_mentioned and update.message.entities:
            for ent in update.message.entities:
                if ent.type == "mention":
                    m_name = message_text[ent.offset:ent.offset + ent.length].lstrip("@").lower()
                    if bot_username and m_name == bot_username:
                        is_bot_mentioned = True
                        break
                elif ent.type == "text_mention" and ent.user:
                    if ent.user.id == context.bot.id:
                        is_bot_mentioned = True
                        break

        # Check active character name triggers (giyu, tomioka, tanjiro, nezuko, shinobu)
        active_char = self.character_repo.get_chat_character(chat_id)
        char_triggers = ["giyu", "tomioka"]
        if active_char == "tanjiro": char_triggers.extend(["tanjiro", "kamado"])
        elif active_char == "nezuko": char_triggers.extend(["nezuko"])
        elif active_char == "shinobu": char_triggers.extend(["shinobu", "kocho"])

        is_char_addressed = any(re.search(rf"\b{re.escape(trigger)}\b", lower_text) for trigger in char_triggers)

        should_reply = is_private or is_reply_to_bot or is_bot_mentioned or is_char_addressed

        if should_reply:
            # Clean prompt (remove bot mention)
            clean_prompt = message_text
            if bot_username:
                clean_prompt = re.sub(rf"@{re.escape(bot_username)}", "", clean_prompt, flags=re.IGNORECASE).strip()
            
            # If user replied to someone else's message with a mention of the bot, include that context
            replied = update.message.reply_to_message
            if replied and replied.text and replied.from_user and replied.from_user.id != context.bot.id:
                if clean_prompt:
                    clean_prompt = f"[Replied Message by {replied.from_user.first_name}]: \"{replied.text}\"\n\n[User Request]: {clean_prompt}"
                else:
                    clean_prompt = replied.text
            elif not clean_prompt and replied and replied.text:
                clean_prompt = replied.text

            # Multimodal Vision: Detect photo / static sticker in message or replied message
            base64_image = None
            image_mime = "image/jpeg"
            import base64

            try:
                if replied and replied.photo:
                    photo = replied.photo[-1]
                    file = await context.bot.get_file(photo.file_id)
                    photo_bytes = await file.download_as_bytearray()
                    base64_image = base64.b64encode(photo_bytes).decode("utf-8")
                    image_mime = "image/jpeg"
                    if not clean_prompt:
                        clean_prompt = replied.caption or "Analyze and describe this image."
                elif replied and replied.sticker and not replied.sticker.is_animated and not replied.sticker.is_video:
                    file = await context.bot.get_file(replied.sticker.file_id)
                    sticker_bytes = await file.download_as_bytearray()
                    base64_image = base64.b64encode(sticker_bytes).decode("utf-8")
                    image_mime = "image/webp"
                    if not clean_prompt:
                        emoji = replied.sticker.emoji or ""
                        clean_prompt = f"React to this sticker ({emoji}) naturally."
                elif update.message.photo:
                    photo = update.message.photo[-1]
                    file = await context.bot.get_file(photo.file_id)
                    photo_bytes = await file.download_as_bytearray()
                    base64_image = base64.b64encode(photo_bytes).decode("utf-8")
                    image_mime = "image/jpeg"
                    if not clean_prompt:
                        clean_prompt = update.message.caption or "Analyze and describe this image."
            except Exception as img_err:
                logger.warning(f"Error extracting image in auto-reply: {img_err}")

            if not clean_prompt and not base64_image:
                return

            if await self._check_rate_limit(update, user.id):
                return

            user_tag = self._get_user_tag(chat_id, user.id, user.first_name)
            is_user_admin = await self.is_admin(update, context)

            # Send typing action
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                pass

            response = await self._run_ai_task(
                self.ai_agent.ask,
                chat_id, user.id, user.first_name, user_tag, clean_prompt or "Hello",
                update=update, context=context, is_admin=is_user_admin,
                base64_image=base64_image, image_mime=image_mime
            )

            if response:
                # Check if voice reply requested or voice note received
                is_voice_input = bool(update.message.voice or update.message.audio or (replied and (replied.voice or replied.audio)))
                
                if is_voice_input:
                    chat_char = self.character_repo.get_character(chat_id)
                    voice_path = await VoiceEngine.generate_voice(response, chat_char)
                    if voice_path:
                        try:
                            with open(voice_path, "rb") as vf:
                                await update.message.reply_voice(voice=vf, caption=f"🎙️ <i>Spoken by {chat_char.title()}</i>", parse_mode="HTML")
                            return
                        except Exception as ve:
                            logger.debug(f"Failed to send voice reply: {ve}")
                        finally:
                            if os.path.exists(voice_path):
                                try: os.unlink(voice_path)
                                except Exception: pass

                try:
                    await update.message.reply_text(response, parse_mode="Markdown")
                except Exception:
                    try:
                        await update.message.reply_text(response, parse_mode="HTML")
                    except Exception:
                        await update.message.reply_text(response)

    # --- COMMANDS ---

    async def ask_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        chat_id = update.message.chat_id
        user = update.message.from_user

        prompt = " ".join(context.args).strip() if context.args else ""
        replied = update.message.reply_to_message

        # Detect replied text
        if not prompt and replied and replied.text:
            prompt = replied.text

        # Multimodal Vision: Detect attached or replied photos and static stickers
        base64_image = None
        image_mime = "image/jpeg"
        import base64

        try:
            if replied and replied.photo:
                photo = replied.photo[-1]
                file = await context.bot.get_file(photo.file_id)
                photo_bytes = await file.download_as_bytearray()
                base64_image = base64.b64encode(photo_bytes).decode("utf-8")
                image_mime = "image/jpeg"
                if not prompt:
                    prompt = replied.caption or "Describe and analyze this image."
            elif replied and replied.sticker and not replied.sticker.is_animated and not replied.sticker.is_video:
                file = await context.bot.get_file(replied.sticker.file_id)
                sticker_bytes = await file.download_as_bytearray()
                base64_image = base64.b64encode(sticker_bytes).decode("utf-8")
                image_mime = "image/webp"
                if not prompt:
                    emoji = replied.sticker.emoji or ""
                    prompt = f"React to this sticker ({emoji}) naturally."
            elif update.message.photo:
                photo = update.message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
                photo_bytes = await file.download_as_bytearray()
                base64_image = base64.b64encode(photo_bytes).decode("utf-8")
                image_mime = "image/jpeg"
                if not prompt:
                    prompt = update.message.caption or "Describe and analyze this image."
        except Exception as img_err:
            logger.warning(f"Error extracting image in ask_cmd: {img_err}")

        if not prompt:
            await update.message.reply_text(
                "🌊 <i>Please provide a question or reply to a message/image.</i>\n\n"
                "<b>Examples:</b>\n"
                "• <code>/ask How does Water Breathing work?</code>\n"
                "• Reply to any message or photo with <code>/ask</code>",
                parse_mode="HTML"
            )
            return

        if await self._check_rate_limit(update, user.id): return

        thinking_msg = await update.message.reply_text("🌊 <i>Concentrating...</i>", parse_mode="HTML")
        user_tag = self._get_user_tag(chat_id, user.id, user.first_name)
        is_user_admin = await self.is_admin(update, context)

        # RUN IN BACKGROUND THREAD
        response = await self._run_ai_task(
            self.ai_agent.ask,
            chat_id, user.id, user.first_name, user_tag, prompt,
            update=update, context=context, is_admin=is_user_admin,
            base64_image=base64_image, image_mime=image_mime
        )
        
        # Resilient message delivery
        try:
            await thinking_msg.edit_text(response, parse_mode="Markdown")
        except Exception:
            try:
                await thinking_msg.edit_text(response, parse_mode="HTML")
            except Exception:
                await thinking_msg.edit_text(response)

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
            
            chunks_learned = await self._run_ai_task(DocumentRAGService(self.ai_agent).learn_document, chat_id, file_bytes, doc.file_name)
            await status.edit_text(f"✅ <b>Successfully learned!</b>\n\nIntegrated <b>{chunks_learned} facts</b> from <code>{doc.file_name}</code>.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in learn_doc_cmd: {e}")
            await status.edit_text(f"❌ Failed to learn document: {e}")

    async def purge_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bulk deletes messages from the replied message down to the purge command."""
        if not update.message: return
        
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can use the purge command.")
            return

        if not update.message.reply_to_message:
            await update.message.reply_text(
                "🌊 <b>Usage:</b>\nReply to the message where you want the purge to start. "
                "Everything from that message down to here will be deleted.", 
                parse_mode="HTML"
            )
            return

        chat_id = update.message.chat_id
        start_id = update.message.reply_to_message.message_id
        end_id = update.message.message_id

        # Generate a list of all message IDs between the replied message and the command
        message_ids = list(range(start_id, end_id + 1))
        deleted_count = 0

        try:
            # Telegram limits bulk deletion to 100 messages at a time.
            for i in range(0, len(message_ids), 100):
                chunk = message_ids[i:i + 100]
                await context.bot.delete_messages(chat_id=chat_id, message_ids=chunk)
                deleted_count += len(chunk)
            
            confirm_msg = await context.bot.send_message(
                chat_id, 
                f"✅ <b>Purge Complete</b>\nSuccessfully deleted {deleted_count} messages.", 
                parse_mode="HTML"
            )
            # Delete the confirmation message after 4 seconds
            await asyncio.sleep(4)
            await confirm_msg.delete()
        except Exception as e:
            logger.error(f"Purge failed: {e}")
            await context.bot.send_message(chat_id, "❌ Purge interrupted. Note: Messages older than 48 hours cannot be bulk deleted by bots.")
