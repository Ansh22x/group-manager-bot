from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import BOT_OWNER_ID
from database import ChatRepository, AFKRepository, UserRepository
from services.sticker_engine import StickerEngine

class PublicCommands(BaseHandler):
    def __init__(self):
        self.chat_repo = ChatRepository()
        self.afk_repo = AFKRepository()
        self.user_repo = UserRepository()

    def register(self, app: Application):
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(CommandHandler("help", self.help_menu))
        app.add_handler(CommandHandler("rules", self.show_rules))
        app.add_handler(CommandHandler("afk", self.set_afk))
        app.add_handler(CommandHandler("owner", self.show_owner))
        app.add_handler(CommandHandler("list_commands", self.list_commands_cmd))
        app.add_handler(CommandHandler("kang", self.kang_sticker))
        app.add_handler(CommandHandler("chatstats", self.chat_stats_cmd))
        app.add_handler(CommandHandler("chatters", self.chatters_list_cmd))

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        bot_username = context.bot.username
        keyboard = [
            [
                InlineKeyboardButton("📢 Support Channel", url="https://t.me/+RKhH82C8mgw1M2Y1"),
                InlineKeyboardButton("👑 Owner", url=f"tg://user?id={BOT_OWNER_ID}")
            ],
            [
                InlineKeyboardButton("➕ Add me to your GC", url=f"https://t.me/{bot_username}?startgroup=true")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_text = (
            "👋 <b>Hello. I am Giyu Tomioka, the Water Hashira and your Group Manager Bot.</b>\n\n"
            "I can help you manage your group with XP leveling, automated moderation, AFK tracking, custom tags, and much more.\n\n"
            "I am also powered by Mistral AI, so you can mention me or reply to my messages to chat with me. 🌊"
        )
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")

    async def show_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.chat_repo.get_chat_settings(update.message.chat_id)
        rules = settings.get('rules', 'No rules have been set for this group yet.')
        await update.message.reply_text(f"📜 <b>Group Rules:</b>\n\n{rules}", parse_mode="HTML")

    async def set_afk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        reason = " ".join(context.args) or "No reason provided"
        self.afk_repo.set_user_afk(update.message.from_user.id, reason)
        await update.message.reply_text(f"💤 {update.message.from_user.first_name} is now AFK. Reason: {reason}")

    async def show_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.chat.type == 'private':
            await update.message.reply_text("This command is meant to be used inside a group!")
            return

        chat_id = update.message.chat_id
        administrators = await context.bot.get_chat_administrators(chat_id)

        group_owner = "Unknown"
        for admin in administrators:
            if admin.status == 'creator':
                group_owner = admin.user.first_name
                break

        response_text = (
            f"👑 <b>Group Owner:</b> {group_owner}\n"
            f"💻 <b>Bot Developer:</b> <a href='tg://user?id={BOT_OWNER_ID}'>Developer</a>"
        )
        await update.message.reply_text(response_text, parse_mode="HTML")

    async def help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
    🛠 <b>Core Bot Commands:</b>
    /start - Show welcome menu and links
    /help - Quick command help overview
    /list_commands - View all 40+ commands in detail
    /rules - View the group rules
    /afk [reason] - Set status to sleeping/busy
    /balance - Check wallet coin balance
    /shop, /buy - View group shop & buy items
    /rank, /ranking - View level & leaderboard
    /ask, /ai [query] - Query the active AI assistant
    /play, /video [query] - Play music/video from YouTube
    /kang - Reply to media to make sticker
    /chatstats, /chatters - View group stats
    
    🛡️ <b>Key Admin Commands:</b>
    /promote, /demote - Manage admin privileges
    /kick, /unban - Remove or restore users
    /mute, /unmute, /tempmute - Restrict talking
    /warn, /dwarn - Manage warning strikes (3 = ban)
    /setchar [giyu|tanjiro...] - Swap active AI character
    /learn - Reply to a document to teach the bot
        """
        await update.message.reply_text(help_text, parse_mode="HTML")

    async def list_commands_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        commands_text = """
    📜 <b>Complete Command List</b>
 
    👥 <b>Public Commands:</b>
    /start - Show bot welcome menu and links
    /help - Quick command list overview
    /rules - Read the active group rules
    /owner - See group owner and bot developer
    /afk [reason] - Set your status to sleeping/busy
    /balance (or /wallet, /coins) - View your wallet coin balance
    /shop - View items available in the group shop
    /buy [item_id] [args] - Purchase items from the group shop
    /rank - View your current level rank and cumulative XP
    /ranking (or /levels) - View the top 10 leaderboard of the chat
    /chatstats - View overall group activity statistics
    /chatters - View the top 5 most active chatters in this group
    /ask (or /ai) [query] - Query Giyu Tomioka directly
    /play [song name or link] - Download and play YouTube audio
    /video [video name or link] - Download and play YouTube video
    /kang - Reply to an image/sticker to format it as sticker
    /list_commands - Show this detailed, complete list
 
    🛡️ <b>Admin Commands:</b>
    /promote, /demote - Manage admin privileges of users
    /kick, /unban - Remove or restore users
    /mute, /unmute - Restrict talking in the chat
    /tempmute [duration] - Mute a user temporarily (e.g., 30s, 10m, 2h)
    /warn, /dwarn - Manage warning strikes (3 strikes = automatic ban)
    /pin, /unpin - Pin or unpin group messages
    /admin_list - View list of all group admins
    /setrules [text] - Update the group rules
    /welcome [on/off] - Toggle welcome greeting cards on join
    /setwelcome [text] - Customize welcome greeting template
    /filter [keyword] [reply] - Add an auto-responder filter
    /afkstat [on/off] - Toggle AFK monitor alerts
    /addtag [hashtag] [reply] - Create a #hashtag note
    /edit_tag [hashtag] [reply] - Edit a #hashtag note
    /settag [tag] - Give a user a custom title tag
    /setchar [giyu|tanjiro|nezuko|shinobu] - Swap the active AI character persona
    /learn - Reply to a document (.txt, .pdf, .md) with /learn to teach the bot
 
    💻 <b>Bot Owner Commands:</b>
    /botstats - View active groups and bot status
    /broadcast [message] - Send a message to all groups
        """
        await update.message.reply_text(commands_text, parse_mode="HTML")

    async def chat_stats_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.chat.type == 'private':
            await update.message.reply_text("This command must be run inside a group chat!")
            return
        chat_id = update.message.chat_id
        stats = self.user_repo.get_chat_summary_stats(chat_id)
        
        summary = (
            f"📊 <b>Group Chat Analytics Logs</b>\n\n"
            f"👥 <b>Tracked Members:</b> {stats['total_members']}\n"
            f"📈 <b>Max Member Level:</b> Level {stats['max_level']}\n"
            f"✨ <b>Total Cumulative XP:</b> {stats['total_xp']} XP\n"
            f"💬 <b>Total Messages Logged:</b> {stats['total_messages']} messages\n"
        )
        await update.message.reply_text(summary, parse_mode="HTML")

    async def chatters_list_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.chat.type == 'private':
            await update.message.reply_text("This command must be run inside a group chat!")
            return
        chat_id = update.message.chat_id
        top_users = self.user_repo.get_top_users(chat_id, 5)
        
        if not top_users:
            await update.message.reply_text("No active chatters found yet!")
            return

        msg = "💬 <b>Top 5 Active Chatters</b> 💬\n\n"
        for i, u in enumerate(top_users, 1):
            msg += f"{i}. <b>{u['name']}</b>: {u.get('message_count', 0)} messages (Level {u['level']})\n"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def kang_sticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message.reply_to_message
        if not msg:
            await update.message.reply_text("Please reply to a photo, sticker, video, gif, or document to kang it!")
            return

        is_video = False
        file_id = None

        if msg.photo:
            file_id = msg.photo[-1].file_id
            is_video = False
        elif msg.sticker:
            file_id = msg.sticker.file_id
            is_video = msg.sticker.is_video or msg.sticker.is_animated
        elif msg.animation:
            file_id = msg.animation.file_id
            is_video = True
        elif msg.video:
            file_id = msg.video.file_id
            is_video = True
        elif msg.document:
            file_id = msg.document.file_id
            mime = (msg.document.mime_type or "").lower()
            file_name = (msg.document.file_name or "").lower()
            is_video = "video" in mime or "gif" in mime or file_name.endswith(('.mp4', '.gif', '.webm', '.mkv', '.avi'))
        else:
            await update.message.reply_text("Unsupported media format! Please reply to a photo, sticker, video, gif, or video file.")
            return

        processing_msg = await update.message.reply_text("🪄 Kanging media... formatting to sticker...")

        try:
            file = await context.bot.get_file(file_id)
            file_bytes = await file.download_as_bytearray()

            bio, filename = StickerEngine.process(file_bytes, is_video)

            await context.bot.send_sticker(chat_id=update.message.chat_id, sticker=bio)
            await processing_msg.delete() 
        except Exception as e:
            await processing_msg.edit_text(f"Oops! Format unsupported or an error occurred: {e}")
