import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from database.repositories import FilterRepository, TagRepository, ChatRepository, UserRepository, CharacterRepository, BlacklistRepository
from config import is_bot_owner

from handlers.admin import check_admin_privileges

logger = logging.getLogger(__name__)

async def _reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data["chat_id"]
    user_name = job.data["user_name"]
    user_id = job.data["user_id"]
    message = job.data["message"]
    
    text = (
        f"⏰ <b>REMINDER FOR</b> <a href='tg://user?id={user_id}'>{user_name}</a>!\n\n"
        f"📝 <i>{message}</i>"
    )
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send reminder: {e}")

class AdminSettings(BaseHandler):
    def __init__(self):
        self.filter_repo = FilterRepository()
        self.tag_repo = TagRepository()
        self.chat_repo = ChatRepository()
        self.user_repo = UserRepository()
        self.character_repo = CharacterRepository()
        self.blacklist_repo = BlacklistRepository()

    def register(self, app: Application):
        # Filter Commands
        app.add_handler(CommandHandler("filter", self.add_filter))
        app.add_handler(CommandHandler("filters", self.list_filters))
        app.add_handler(CommandHandler(["stopfilter", "removefilter", "delfilter"], self.remove_filter))
        
        # Tag Commands
        app.add_handler(CommandHandler("tag", self.add_tag))
        app.add_handler(CommandHandler("tags", self.list_tags))
        app.add_handler(CommandHandler(["stoptag", "removetag", "deltag"], self.remove_tag))

        # Admin Group Settings & Customization Commands
        app.add_handler(CommandHandler("setrules", self.set_rules_cmd))
        app.add_handler(CommandHandler("welcome", self.toggle_welcome))
        app.add_handler(CommandHandler("setwelcome", self.set_welcome))
        app.add_handler(CommandHandler("afkstat", self.toggle_afk))
        app.add_handler(CommandHandler("settag", self.set_user_tag))
        app.add_handler(CommandHandler(["setchar", "character", "persona", "setcharacter"], self.set_chat_char))

        # Blacklist & Reminder Commands
        app.add_handler(CommandHandler(["blacklist", "bannedwords"], self.blacklist_cmd))
        app.add_handler(CommandHandler(["remind", "reminder", "timer"], self.remind_cmd))

    async def is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        return await check_admin_privileges(update, context)

    # ---------------- FILTERS (Rich Media & Text) ----------------

    async def add_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can set filters.")
            return

        if not context.args:
            await update.message.reply_text(
                "🌊 <b>How to set filters:</b>\n\n"
                "1. <b>Text Filter:</b> <code>/filter [keyword] [reply message]</code>\n"
                "2. <b>Media Filter:</b> Reply to any image, GIF, sticker, or document with <code>/filter [keyword] [optional caption]</code>",
                parse_mode="HTML"
            )
            return

        keyword = context.args[0].lower().strip()
        custom_caption = " ".join(context.args[1:]).strip() if len(context.args) > 1 else ""
        chat_id = update.message.chat_id
        replied = update.message.reply_to_message

        filter_payload = {}

        if replied:
            if replied.photo:
                filter_payload = {
                    "type": "photo",
                    "file_id": replied.photo[-1].file_id,
                    "caption": custom_caption or replied.caption or ""
                }
            elif replied.animation:
                filter_payload = {
                    "type": "animation",
                    "file_id": replied.animation.file_id,
                    "caption": custom_caption or replied.caption or ""
                }
            elif replied.sticker:
                filter_payload = {
                    "type": "sticker",
                    "file_id": replied.sticker.file_id
                }
            elif replied.document:
                filter_payload = {
                    "type": "document",
                    "file_id": replied.document.file_id,
                    "caption": custom_caption or replied.caption or ""
                }
            elif replied.audio:
                filter_payload = {
                    "type": "audio",
                    "file_id": replied.audio.file_id,
                    "caption": custom_caption or replied.caption or ""
                }
            elif replied.voice:
                filter_payload = {
                    "type": "voice",
                    "file_id": replied.voice.file_id,
                    "caption": custom_caption or ""
                }
            elif replied.text:
                filter_payload = {
                    "type": "text",
                    "text": custom_caption or replied.text
                }
            else:
                await update.message.reply_text("❌ Unsupported message type for filter.")
                return
        else:
            # Inline text filter
            if not custom_caption:
                await update.message.reply_text(
                    "❌ Please provide text for the filter, or reply to a media message.\n"
                    "Example: <code>/filter hello Hi there!</code>",
                    parse_mode="HTML"
                )
                return
            filter_payload = {
                "type": "text",
                "text": custom_caption
            }

        payload_str = json.dumps(filter_payload)
        self.filter_repo.add_filter(chat_id, keyword, payload_str)

        media_name = filter_payload.get("type", "text").capitalize()
        await update.message.reply_text(
            f"✅ <b>Filter Saved!</b>\n\n"
            f"🔑 <b>Keyword:</b> <code>{keyword}</code>\n"
            f"📦 <b>Type:</b> <code>{media_name}</code>",
            parse_mode="HTML"
        )

    async def list_filters(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        filters = self.filter_repo.get_filters(chat_id)
        
        if not filters:
            await update.message.reply_text("No custom filters are currently set for this group.")
            return

        msg = "📋 <b>Active Group Filters:</b>\n\n"
        for kw, raw_data in filters.items():
            filter_type = "Text"
            try:
                data = json.loads(raw_data)
                filter_type = data.get("type", "text").capitalize()
            except Exception:
                filter_type = "Text"
            msg += f"• <code>{kw}</code> (<i>{filter_type}</i>)\n"
        
        msg += "\n<i>Use <code>/stopfilter [keyword]</code> to remove one.</i>"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def remove_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can remove filters.")
            return
            
        if not context.args:
            await update.message.reply_text("Usage: <code>/stopfilter [keyword]</code>", parse_mode="HTML")
            return
            
        keyword = context.args[0].lower().strip()
        chat_id = update.message.chat_id

        conn = self.filter_repo.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM custom_filters WHERE chat_id = %s AND keyword = %s;", (chat_id, keyword))
                conn.commit()
            await update.message.reply_text(f"🗑️ Filter <code>{keyword}</code> removed.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error removing filter: {e}")
        finally:
            self.filter_repo.db.release_connection(conn)

    # ---------------- TAGS (#hashtags) ----------------

    async def add_tag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can set tags.")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: <code>/tag [word] [reply message]</code>\nExample: <code>/tag rules Read pinned message</code>", parse_mode="HTML")
            return

        tag = context.args[0].lower().replace("#", "")
        reply = " ".join(context.args[1:])
        chat_id = update.message.chat_id

        self.tag_repo.add_tag(chat_id, tag, reply)
        await update.message.reply_text(f"✅ Tag added! When someone types <code>#{tag}</code>, I will reply.", parse_mode="HTML")

    async def list_tags(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        tags = self.tag_repo.get_tags(chat_id)
        
        if not tags:
            await update.message.reply_text("No custom tags are set for this group.")
            return
            
        msg = "🏷️ <b>Active Group Tags:</b>\n\n"
        for t in tags.keys():
            msg += f"• <code>#{t}</code>\n"
        msg += "\nUse <code>/stoptag [tag]</code> to remove one."
        await update.message.reply_text(msg, parse_mode="HTML")

    async def remove_tag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can remove tags.")
            return
            
        if not context.args:
            await update.message.reply_text("Usage: <code>/stoptag [tag]</code>", parse_mode="HTML")
            return
            
        tag = context.args[0].lower().replace("#", "")
        chat_id = update.message.chat_id

        conn = self.tag_repo.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM custom_tags WHERE chat_id = %s AND tag = %s;", (chat_id, tag))
                conn.commit()
            await update.message.reply_text(f"🗑️ Tag <code>#{tag}</code> removed.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error removing tag: {e}")
        finally:
            self.tag_repo.db.release_connection(conn)

    # ---------------- GROUP RULES & WELCOME ----------------

    async def set_rules_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can update group rules.")
            return

        chat_id = update.message.chat_id
        if not context.args and not (update.message.reply_to_message and update.message.reply_to_message.text):
            await update.message.reply_text("Usage: <code>/setrules [rules text]</code> or reply to a rules message with <code>/setrules</code>.", parse_mode="HTML")
            return

        rules_text = " ".join(context.args) if context.args else update.message.reply_to_message.text
        self.chat_repo.update_chat_settings(chat_id, rules=rules_text)
        await update.message.reply_text("✅ <b>Group rules updated successfully!</b>\n\nMembers can view them anytime via <code>/rules</code>.", parse_mode="HTML")

    async def toggle_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can toggle welcome messages.")
            return

        chat_id = update.message.chat_id
        settings = self.chat_repo.get_chat_settings(chat_id)
        current = settings.get("welcome_on", True)
        new_val = not current
        self.chat_repo.update_chat_settings(chat_id, welcome_on=new_val)
        status = "ENABLED 🟢" if new_val else "DISABLED 🔴"
        await update.message.reply_text(f"👋 Welcome greetings are now <b>{status}</b> for this group.", parse_mode="HTML")

    async def set_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can customize welcome messages.")
            return

        chat_id = update.message.chat_id
        if not context.args and not (update.message.reply_to_message and update.message.reply_to_message.text):
            await update.message.reply_text(
                "Usage: <code>/setwelcome Welcome {name} to {chat}!</code>\n\n"
                "Supported placeholders:\n"
                "• <code>{name}</code> - Member's first name\n"
                "• <code>{chat}</code> - Group chat title",
                parse_mode="HTML"
            )
            return

        template = " ".join(context.args) if context.args else update.message.reply_to_message.text
        self.chat_repo.update_chat_settings(chat_id, welcome_template=template)
        await update.message.reply_text("✅ <b>Custom welcome template updated!</b>", parse_mode="HTML")

    async def toggle_afk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can toggle AFK monitoring.")
            return

        chat_id = update.message.chat_id
        settings = self.chat_repo.get_chat_settings(chat_id)
        current = settings.get("afk_on", True)
        new_val = not current
        self.chat_repo.update_chat_settings(chat_id, afk_on=new_val)
        status = "ENABLED 🟢" if new_val else "DISABLED 🔴"
        await update.message.reply_text(f"💤 AFK alert monitoring is now <b>{status}</b> for this group.", parse_mode="HTML")

    async def set_user_tag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can set custom user rank titles.")
            return

        if not update.message.reply_to_message:
            await update.message.reply_text("🌊 Reply to a user's message with <code>/settag [Custom Title]</code>", parse_mode="HTML")
            return

        new_tag = " ".join(context.args).strip() if context.args else ""
        if not new_tag:
            await update.message.reply_text("Please provide a title tag! Example: <code>/settag Water Pillar</code>", parse_mode="HTML")
            return

        target_user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        self.user_repo.update_user_stats(chat_id, target_user.id, tag=new_tag)
        await update.message.reply_text(f"✅ Set <b>{target_user.first_name}</b>'s title rank tag to: <code>{new_tag}</code>", parse_mode="HTML")

    async def set_chat_char(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can change the active AI character persona.")
            return

        allowed_chars = ["giyu", "tanjiro", "nezuko", "shinobu"]
        char_name = context.args[0].lower() if context.args else ""

        if not char_name:
            await update.message.reply_text(
                "💬 <b>AI Character Persona Selection</b>\n\n"
                "Please choose which character you would like to activate for this group:\n"
                "• <code>giyu</code> - Giyu Tomioka (Water Hashira, Stoic & Direct)\n"
                "• <code>tanjiro</code> - Tanjiro Kamado (Earnest & Warm)\n"
                "• <code>nezuko</code> - Nezuko Kamado (Childlike Demon)\n"
                "• <code>shinobu</code> - Shinobu Kocho (Insect Hashira, Sarcastic & Witty)\n\n"
                "<b>Example:</b> <code>/setchar tanjiro</code>",
                parse_mode="HTML"
            )
            return

        if char_name not in allowed_chars:
            await update.message.reply_text(
                f"❌ Character <code>{char_name}</code> is not recognized.\n"
                f"Please choose from: <code>{', '.join(allowed_chars)}</code>.",
                parse_mode="HTML"
            )
            return

        self.character_repo.set_chat_character(update.message.chat_id, char_name)
        char_labels = {
            "giyu": "Giyu Tomioka (Water Hashira 🌊)",
            "tanjiro": "Tanjiro Kamado (Sun Breathing ☀️)",
            "nezuko": "Nezuko Kamado (Exploding Blood 🌸)",
            "shinobu": "Shinobu Kocho (Insect Hashira 🦋)"
        }
        await update.message.reply_text(
            f"🌊 <b>AI Persona Swapped!</b>\n\n"
            f"Active persona is now set to <b>{char_labels[char_name]}</b>.\n"
            f"All future <code>/ask</code> conversations in this group will reflect this character.",
            parse_mode="HTML"
        )

    async def blacklist_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or update.message.chat.type == 'private':
            await update.message.reply_text("This command must be run inside a group chat!")
            return

        chat_id = update.message.chat_id
        is_admin = await self.is_admin(update, context)

        if not context.args or context.args[0].lower() in ["list", "show"]:
            banned = self.blacklist_repo.get_blacklist(chat_id)
            if not banned:
                await update.message.reply_text("🛡️ <b>Word Blacklist:</b>\n\nNo banned words set for this group.", parse_mode="HTML")
            else:
                words_str = ", ".join([f"<code>{w}</code>" for w in sorted(banned)])
                await update.message.reply_text(f"🛡️ <b>Banned Words ({len(banned)}):</b>\n\n{words_str}", parse_mode="HTML")
            return

        if not is_admin:
            await update.message.reply_text("❌ Only group administrators can manage the word blacklist.")
            return

        action = context.args[0].lower()
        if action == "add" and len(context.args) > 1:
            word = " ".join(context.args[1:]).strip().lower()
            self.blacklist_repo.add_word(chat_id, word)
            await update.message.reply_text(f"✅ Added <code>{word}</code> to group blacklist. Messages containing this word will be auto-deleted.", parse_mode="HTML")
        elif action in ["del", "delete", "remove", "rem"] and len(context.args) > 1:
            word = " ".join(context.args[1:]).strip().lower()
            self.blacklist_repo.remove_word(chat_id, word)
            await update.message.reply_text(f"✅ Removed <code>{word}</code> from group blacklist.", parse_mode="HTML")
        else:
            await update.message.reply_text(
                "🛡️ <b>Word Blacklist Usage:</b>\n\n"
                "• <code>/blacklist add &lt;word&gt;</code> - Ban a word/phrase\n"
                "• <code>/blacklist del &lt;word&gt;</code> - Remove a word/phrase\n"
                "• <code>/blacklist list</code> - View active banned words",
                parse_mode="HTML"
            )

    async def remind_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user
        chat_id = update.message.chat_id

        if len(context.args) < 2:
            await update.message.reply_text(
                "⏰ <b>Timer & Reminder:</b>\n\n"
                "<i>Usage:</i> <code>/remind &lt;time&gt; &lt;message&gt;</code>\n\n"
                "<b>Examples:</b>\n"
                "• <code>/remind 10m check game deals</code>\n"
                "• <code>/remind 1h tournament match begins</code>\n"
                "• <code>/remind 30s quick check</code>",
                parse_mode="HTML"
            )
            return

        time_str = context.args[0].lower()
        reminder_msg = " ".join(context.args[1:])

        import re
        match = re.match(r"^(\d+)([smhd])$", time_str)
        if not match:
            await update.message.reply_text("❌ Invalid time format! Use e.g. <code>30s</code>, <code>10m</code>, <code>2h</code>, <code>1d</code>.", parse_mode="HTML")
            return

        val, unit = int(match.group(1)), match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = val * multipliers[unit]

        if seconds > 86400 * 7:
            await update.message.reply_text("❌ Reminders cannot exceed 7 days.")
            return

        if context.job_queue:
            context.job_queue.run_once(
                _reminder_callback,
                when=seconds,
                data={
                    "chat_id": chat_id,
                    "user_name": user.first_name,
                    "user_id": user.id,
                    "message": reminder_msg
                }
            )
            await update.message.reply_text(f"⏰ <b>Reminder Set!</b> I will remind you in <b>{time_str}</b>: <i>\"{reminder_msg}\"</i>", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Job queue is not initialized. Cannot schedule reminder.")

