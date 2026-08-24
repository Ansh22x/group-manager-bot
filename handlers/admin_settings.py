import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from database.repositories import FilterRepository, TagRepository
from config import is_bot_owner

logger = logging.getLogger(__name__)

class AdminSettings(BaseHandler):
    def __init__(self):
        self.filter_repo = FilterRepository()
        self.tag_repo = TagRepository()

    def register(self, app: Application):
        # Filter Commands
        app.add_handler(CommandHandler("filter", self.add_filter))
        app.add_handler(CommandHandler("filters", self.list_filters))
        app.add_handler(CommandHandler(["stopfilter", "removefilter", "delfilter"], self.remove_filter))
        
        # Tag Commands
        app.add_handler(CommandHandler("tag", self.add_tag))
        app.add_handler(CommandHandler("tags", self.list_tags))
        app.add_handler(CommandHandler(["stoptag", "removetag", "deltag"], self.remove_tag))

    async def is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if not update.message or update.message.chat.type == 'private': 
            return False
        if is_bot_owner(update.message.from_user.id): 
            return True
        try:
            member = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
            return member.status in ['administrator', 'creator']
        except Exception:
            return False

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
