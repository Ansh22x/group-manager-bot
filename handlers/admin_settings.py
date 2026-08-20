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
        app.add_handler(CommandHandler(["stopfilter", "removefilter"], self.remove_filter))
        
        # Tag Commands 
        app.add_handler(CommandHandler("tag", self.add_tag))
        app.add_handler(CommandHandler("tags", self.list_tags))
        app.add_handler(CommandHandler(["stoptag", "removetag"], self.remove_tag))

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

    # ---------------- FILTERS ----------------

    async def add_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can set filters.")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: `/filter [keyword] [reply message]`\nExample: `/filter hello Hi there!`", parse_mode="Markdown")
            return

        keyword = context.args[0].lower()
        reply = " ".join(context.args[1:])
        chat_id = update.message.chat_id

        self.filter_repo.add_filter(chat_id, keyword, reply)
        await update.message.reply_text(f"✅ Filter added!\nWhen someone says `{keyword}`, I will reply.", parse_mode="Markdown")

    async def list_filters(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        filters = self.filter_repo.get_filters(chat_id)
        
        if not filters:
            await update.message.reply_text("No custom filters are set for this group.")
            return
            
        msg = "📋 **Active Group Filters:**\n\n"
        for kw in filters.keys():
            msg += f"• `{kw}`\n"
        msg += "\nUse `/stopfilter [keyword]` to remove one."
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def remove_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can remove filters.")
            return
            
        if not context.args:
            await update.message.reply_text("Usage: `/stopfilter [keyword]`", parse_mode="Markdown")
            return
            
        keyword = context.args[0].lower()
        chat_id = update.message.chat_id

        # Directly executing the delete query to avoid needing to edit repositories.py again
        conn = self.filter_repo.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM custom_filters WHERE chat_id = %s AND keyword = %s;", (chat_id, keyword))
                conn.commit()
            await update.message.reply_text(f"🗑️ Filter `{keyword}` removed.", parse_mode="Markdown")
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
            await update.message.reply_text("Usage: `/tag [word] [reply message]`\nExample: `/tag rules Read the pinned message!`", parse_mode="Markdown")
            return

        tag = context.args[0].lower().replace("#", "")
        reply = " ".join(context.args[1:])
        chat_id = update.message.chat_id

        self.tag_repo.add_tag(chat_id, tag, reply)
        await update.message.reply_text(f"✅ Tag added!\nWhen someone types `#{tag}`, I will reply.", parse_mode="Markdown")

    async def list_tags(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        tags = self.tag_repo.get_tags(chat_id)
        
        if not tags:
            await update.message.reply_text("No custom tags are set for this group.")
            return
            
        msg = "🏷️ **Active Group Tags:**\n\n"
        for t in tags.keys():
            msg += f"• `#{t}`\n"
        msg += "\nUse `/stoptag [tag]` to remove one."
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def remove_tag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context):
            await update.message.reply_text("❌ Only admins can remove tags.")
            return
            
        if not context.args:
            await update.message.reply_text("Usage: `/stoptag [tag]`", parse_mode="Markdown")
            return
            
        tag = context.args[0].lower().replace("#", "")
        chat_id = update.message.chat_id

        conn = self.tag_repo.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM custom_tags WHERE chat_id = %s AND tag = %s;", (chat_id, tag))
                conn.commit()
            await update.message.reply_text(f"🗑️ Tag `#{tag}` removed.", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error removing tag: {e}")
        finally:
            self.tag_repo.db.release_connection(conn)
