import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import BOT_OWNER_ID, is_super_admin, is_bot_owner
from database import ChatRepository, AFKRepository, UserRepository, WarningRepository, EconomyRepository
from services.sticker_engine import StickerEngine

logger = logging.getLogger(__name__)

class PublicCommands(BaseHandler):
    def __init__(self):
        self.chat_repo = ChatRepository()
        self.afk_repo = AFKRepository()
        self.user_repo = UserRepository()
        self.warning_repo = WarningRepository()
        self.economy_repo = EconomyRepository()

    def register(self, app: Application):
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(CommandHandler("help", self.help_menu))
        app.add_handler(CommandHandler(["info", "id", "userinfo", "whois"], self.info_cmd))
        app.add_handler(CommandHandler("rules", self.show_rules))
        app.add_handler(CommandHandler("afk", self.set_afk))
        app.add_handler(CommandHandler("owner", self.show_owner))
        app.add_handler(CommandHandler("list_commands", self.list_commands_cmd))
        app.add_handler(CommandHandler("kang", self.kang_sticker))
        app.add_handler(CommandHandler("chatstats", self.chat_stats_cmd))
        app.add_handler(CommandHandler("chatters", self.chatters_list_cmd))
        app.add_handler(CommandHandler("giyustats", self.giyustats_cmd))

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
        try:
            await update.message.reply_text(response_text, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(update.message.chat_id, response_text, parse_mode="HTML")

    async def help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
    🛠 <b>Core Bot Commands:</b>
    /start - Show welcome menu and links
    /help - Quick command help overview
    /info (or /id) - View Telegram numeric ID & full user data card
    /list_commands - View all 40+ commands in detail
    /rules - View the group rules
    /afk [reason] - Set status to sleeping/busy
    /balance - Check wallet coin balance
    /pay [amount] - Transfer coins to another member
    /shop, /buy - View group shop & buy items
    /game, /steam [name] - Search Steam, SteamDB ATL & keyshop deals
    /deals - Browse top trending PC game discounts
    /newlow [name] - Check if a game is at historical all-time low
    /rank, /ranking - View level & leaderboard
    /ask, /ai [query] - Query the active AI assistant
    /play, /video [query] - Play music/video from YouTube
    /draw [prompt] - Generate an AI image (Perchance with Pollinations fallback)
    /kang - Reply to media to make sticker
    /chatstats, /chatters - View group stats
    /giyustats - View active AI character level, traits & skills
    
    🛡️ <b>Key Admin Commands:</b>
    /promote, /demote - Manage admin privileges
    /kick, /unban - Remove or restore users
    /mute, /unmute, /tempmute - Restrict talking
    /warn, /dwarn - Manage warning strikes (3 = ban)
    /setchar [giyu|tanjiro...] - Swap active AI character
    /filter, /filters, /stopfilter - Manage auto-replies
    /tag, /tags, /stoptag - Manage #hashtags
    /purge - Bulk delete messages
    /learn - Reply to a document to teach the bot
        """
        await update.message.reply_text(help_text, parse_mode="HTML")

    async def list_commands_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        commands_text = """
    📜 <b>Complete Command List</b>
 
    👥 <b>Public Commands:</b>
    /start - Show bot welcome menu and links
    /help - Quick command help overview
    /info (or /id, /whois) - View Telegram numeric ID & full user data card
    /rules - Read the active group rules
    /owner - See group owner and bot developer
    /afk [reason] - Set your status to sleeping/busy
    /balance (or /wallet, /coins) - View your wallet coin balance
    /pay [amount] - Transfer coins to another member (reply to user)
    /shop - View items available in the group shop
    /buy [item_id] [args] - Purchase items from the group shop
    /game (or /steam) [name] - Search Steam game, SteamDB ATL & keyshop deals
    /deals (or /steamdeals) - Browse top trending PC game discounts
    /newlow [name] - Check if game is currently at historical all-time low
    /rank - View your current level rank and cumulative XP
    /ranking (or /levels) - View the top 10 leaderboard of the chat
    /chatstats - View overall group activity statistics
    /chatters - View the top 5 most active chatters in this group
    /ask (or /ai) [query] - Query Giyu Tomioka directly
    /play [song name or link] - Download and play YouTube audio
    /video [video name or link] - Download and play YouTube video
    /draw [prompt] - Generate an AI image (Perchance with Pollinations fallback)
    /kang - Reply to an image/sticker to format it as sticker
    /giyustats - View active AI character level, evolved traits & skills
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
        if not update.message:
            return
            
        msg = update.message.reply_to_message
        if not msg:
            await update.message.reply_text("Please reply to a photo, sticker, video, gif, or document to kang it!")
            return

        user = update.message.from_user
        user_id = user.id
        bot_username = context.bot.username

        emoji = "🌊"
        if context.args:
            emoji = context.args[0]
        elif msg.sticker and msg.sticker.emoji:
            emoji = msg.sticker.emoji

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

        processing_msg = await update.message.reply_text("🪄 Formatting media to sticker formats...")

        try:
            file = await context.bot.get_file(file_id)
            file_bytes = await file.download_as_bytearray()

            bio, filename = StickerEngine.process(file_bytes, is_video)
            sticker_format = "video" if filename.endswith(".webm") else "static"
            
            pack_name = f"giyu_u_{user_id}_by_{bot_username}"
            pack_title = f"@{user.username or user.first_name}'s Kanged Pack"
            
            from telegram import InputSticker
            input_sticker = InputSticker(sticker=bio.getvalue(), emoji_list=[emoji], format=sticker_format)
            
            await processing_msg.edit_text("⚡ Adding sticker to your Telegram pack...")
            
            success = False
            try:
                await context.bot.add_sticker_to_set(
                    user_id=user_id,
                    name=pack_name,
                    sticker=input_sticker
                )
                success = True
            except Exception as add_err:
                logger.info(f"add_sticker_to_set failed: {add_err}. Attempting to create new sticker set...")
                try:
                    await context.bot.create_new_sticker_set(
                        user_id=user_id,
                        name=pack_name,
                        title=pack_title,
                        stickers=[input_sticker]
                    )
                    success = True
                except Exception as create_err:
                    err_msg = str(create_err).lower()
                    if "peer" in err_msg or "unauthorized" in err_msg or "chat not found" in err_msg:
                        await processing_msg.edit_text(
                            f"⚠️ <b>Private Chat Required</b>\n\n"
                            f"To let me create sticker packs for you, Telegram requires you to start a private chat with me first.\n\n"
                            f"👉 Please open t.me/{bot_username} and click <b>Start</b>, then try again!",
                            parse_mode="HTML"
                        )
                        return
                    else:
                        raise create_err

            if success:
                pack_url = f"https://t.me/addstickers/{pack_name}"
                sticker_set = await context.bot.get_sticker_set(pack_name)
                new_sticker_file_id = sticker_set.stickers[-1].file_id
                
                await update.message.reply_sticker(sticker=new_sticker_file_id)
                await processing_msg.edit_text(
                    f"✅ <b>Kanged Successfully!</b>\n\n"
                    f"Sticker added with emoji {emoji}.\n"
                    f"📦 <b>Sticker Pack:</b> <a href='{pack_url}'>Click here to Add Pack</a>",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Kang command failed: {e}", exc_info=True)
            await processing_msg.edit_text(f"❌ Error occurred while kanging sticker: {e}")

    async def giyustats_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        chat_id = update.message.chat_id
        
        from database.repositories import BotStatsRepository
        repo = BotStatsRepository()
        stats = repo.get_bot_stats(chat_id)
        
        import json
        try:
            traits = json.loads(stats["traits"])
        except Exception:
            traits = {"stoic": 80, "friendly": 20, "energy": 50}
            
        traits_str = "\n".join([f"• <b>{k.title()}</b>: {v}%" for k, v in traits.items()])
        skills_str = ", ".join([f"`{s.strip()}`" for s in stats["unlocked_skills"].split(",")])
        
        # Calculate progress to next level
        current_xp = stats["xp"]
        current_level = stats["level"]
        xp_needed = current_level * 100
        progress_pct = min(100, int((current_xp / xp_needed) * 100)) if xp_needed > 0 else 0
        
        # Simple text progress bar
        bar_length = 10
        filled = int((progress_pct / 100) * bar_length)
        bar = "🟦" * filled + "⬜" * (bar_length - filled)
        
        stats_text = (
            f"🌊 <b>Active AI Persona Status & Evolution</b>\n\n"
            f"📊 <b>Bot Level:</b> {current_level}\n"
            f"✨ <b>Evolution XP:</b> {current_xp}/{xp_needed} XP\n"
            f"<code>[{bar}] {progress_pct}%</code>\n\n"
            f"🧠 <b>Evolving Personality Traits:</b>\n{traits_str}\n\n"
            f"🗡️ <b>Unlocked Skills & Techniques:</b>\n{skills_str}\n\n"
            f"💡 <i>Tip: Interacting with the AI persona grants experience points (XP), allowing Giyu-Bot to level up, dynamically adjust traits, and unlock legendary breathing skills!</i>"
        )
        await update.message.reply_text(stats_text, parse_mode="HTML")

    async def info_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays user's full Telegram numeric ID, group permissions, economy, warnings, and metadata."""
        if not update.message: return

        chat = update.message.chat
        chat_id = chat.id
        sender = update.message.from_user

        target_user = None

        # 1. Target from reply
        if update.message.reply_to_message:
            replied = update.message.reply_to_message
            if replied.from_user:
                target_user = replied.from_user
            elif replied.sender_chat:
                await update.message.reply_text(
                    f"📢 <b>Channel / Anonymous Sender Info</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• <b>Title:</b> {replied.sender_chat.title}\n"
                    f"• <b>Chat ID:</b> <code>{replied.sender_chat.id}</code>\n"
                    f"• <b>Username:</b> @{replied.sender_chat.username or 'None'}\n"
                    f"• <b>Type:</b> {replied.sender_chat.type.capitalize()}\n"
                    f"━━━━━━━━━━━━━━━━━━━━",
                    parse_mode="HTML"
                )
                return

        # 2. Target from argument (@username or numeric ID)
        elif context.args:
            arg = context.args[0].strip()
            if arg.isdigit() or (arg.startswith("-") and arg[1:].isdigit()):
                uid = int(arg)
                try:
                    chat_member = await context.bot.get_chat_member(chat_id, uid)
                    target_user = chat_member.user
                except Exception:
                    pass

        # 3. Default to sender
        if not target_user:
            target_user = sender

        target_id = target_user.id
        first_name = target_user.first_name or "Unknown"
        last_name = target_user.last_name or ""
        full_name = f"{first_name} {last_name}".strip()
        username = f"@{target_user.username}" if target_user.username else "<i>None</i>"
        is_bot = "🤖 Yes" if target_user.is_bot else "👤 No"
        is_premium = "⭐ Telegram Premium" if getattr(target_user, "is_premium", False) else "Standard"
        lang_code = target_user.language_code or "N/A"
        user_link = f"<a href='tg://user?id={target_id}'>{full_name}</a>"

        # Group Role & Custom Title
        chat_status = "N/A (Private Chat)"
        custom_title = ""
        if chat.type != 'private':
            try:
                member = await context.bot.get_chat_member(chat_id, target_id)
                status_map = {
                    "creator": "👑 Group Creator / Owner",
                    "administrator": "🛡️ Administrator",
                    "member": "👤 Member",
                    "restricted": "🤐 Restricted",
                    "left": "🚪 Left",
                    "kicked": "⛔ Banned"
                }
                chat_status = status_map.get(member.status, member.status.capitalize())
                if getattr(member, "custom_title", None):
                    custom_title = f" (<code>{member.custom_title}</code>)"
            except Exception:
                chat_status = "👤 Member"

        # Super Admin / Owner Badge
        super_badge = "👑 <b>[SUPER ADMIN / BOT OWNER]</b>\n" if is_super_admin(target_id) else ""

        # Database Stats
        stats = self.user_repo.get_user_stats(chat_id, target_id, first_name)
        user_tag = stats.get("tag", "Member")
        level = stats.get("level", 1)
        xp = stats.get("xp", 0)
        messages_count = stats.get("message_count", 0)

        # Global Wallet Balance
        balance = self.economy_repo.get_balance(chat_id, target_id)

        # Warnings
        warnings = self.warning_repo.get_warnings(chat_id, target_id)

        # AFK Status
        afk_users = self.afk_repo.get_afk_users()
        afk_status = f"💤 AFK (<code>{afk_users[target_id]}</code>)" if target_id in afk_users else "Active"

        msg = (
            f"👤 <b>User Identity & Data Card</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{super_badge}"
            f"• <b>Full Name:</b> {user_link}\n"
            f"• <b>User ID:</b> <code>{target_id}</code>\n"
            f"• <b>Username:</b> {username}\n"
            f"• <b>Account Type:</b> {is_premium} | {is_bot}\n"
            f"• <b>Language Code:</b> <code>{lang_code}</code>\n"
            f"• <b>Permanent Link:</b> <code>tg://user?id={target_id}</code>\n\n"
            f"🛡️ <b>Group Permissions ({chat.title or 'Chat'}):</b>\n"
            f"• <b>Group Role:</b> {chat_status}{custom_title}\n"
            f"• <b>Rank Title Tag:</b> <code>{user_tag}</code>\n"
            f"• <b>Warning Strikes:</b> <code>{warnings}/3</code>\n"
            f"• <b>AFK Status:</b> {afk_status}\n\n"
            f"📊 <b>Activity & Economy:</b>\n"
            f"• <b>Level:</b> <code>{level}</code> (XP: <code>{xp:,}</code>)\n"
            f"• <b>Messages Logged:</b> <code>{messages_count:,}</code>\n"
            f"• <b>Global Wallet:</b> <code>{balance:,}</code> Water Coins\n\n"
            f"🏢 <b>Current Context:</b>\n"
            f"• <b>Chat ID:</b> <code>{chat_id}</code>\n"
            f"• <b>Message ID:</b> <code>{update.message.message_id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)

