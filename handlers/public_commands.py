import logging
import urllib.parse
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import BOT_OWNER_ID, is_super_admin, is_bot_owner
from database import ChatRepository, AFKRepository, UserRepository, WarningRepository, EconomyRepository
from services.sticker_engine import StickerEngine
from services.search_service import SearchService

logger = logging.getLogger(__name__)

class PublicCommands(BaseHandler):
    def __init__(self):
        self.chat_repo = ChatRepository()
        self.afk_repo = AFKRepository()
        self.user_repo = UserRepository()
        self.warning_repo = WarningRepository()
        self.economy_repo = EconomyRepository()
        self.search_service = SearchService()

    def register(self, app: Application):
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(CommandHandler("help", self.help_menu))
        app.add_handler(CommandHandler(["info", "id", "userinfo", "whois"], self.info_cmd))
        app.add_handler(CommandHandler(["search", "google", "web", "bing"], self.web_search_cmd))
        app.add_handler(CommandHandler("rules", self.show_rules))
        app.add_handler(CommandHandler("afk", self.set_afk))
        app.add_handler(CommandHandler("owner", self.show_owner))
        app.add_handler(CommandHandler("list_commands", self.list_commands_cmd))
        app.add_handler(CommandHandler("kang", self.kang_sticker))
        app.add_handler(CommandHandler("chatstats", self.chat_stats_cmd))
        app.add_handler(CommandHandler("chatters", self.chatters_list_cmd))
        app.add_handler(CommandHandler("giyustats", self.giyustats_cmd))
        app.add_handler(CallbackQueryHandler(self.command_catalog_callback, pattern=r"^cmdcat_"))

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

    COMMAND_CATEGORIES = {
        "public": {
            "title": "🌐 Public Utility & Identity",
            "emoji": "🌐",
            "label": "Public",
            "desc": "Core utilities and identity inspection tools for all group members.",
            "commands": [
                ("/start", "", "Open the bot welcome banner and navigation menu"),
                ("/help", "or /list_commands", "Interactive command directory dashboard"),
                ("/search <query>", "or /google, /web, /bing", "Search live web results from the internet + Wikipedia answers"),
                ("/info", "or /id, /userinfo, /whois", "Inspect user numeric ID, permissions, wallet & metadata"),
                ("/rules", "", "View the official rules configured for this group"),
                ("/afk [reason]", "", "Set AFK status (notifies callers when they reply or mention you)"),
                ("/owner", "", "View group owner & bot developer info"),
                ("/report [reason]", "", "Reply to a message to report inappropriate content to all admins"),
            ]
        },
        "gaming": {
            "title": "🎮 Steam, Deals & Giveaways",
            "emoji": "🎮",
            "label": "Gaming",
            "desc": "Real-time game search, SteamDB historical lows, keyshops, and freebie monitors.",
            "commands": [
                ("/game <title>", "or /steam", "Search Steam game, review rating, live CCU players & price"),
                ("/newlow <title>", "or /islow, /atl", "Check if a game matches or breaks its all-time historical low price"),
                ("/deals", "or /steamdeals, /gamedeals", "Browse top trending discounted PC games (CheapShark + Steam Specials)"),
                ("/giveaways [category]", "or /giveaway, /freebies, /freegames", "Browse active Alienware, AMD, Medal, Steam & Epic freebies"),
                ("/gog", "", "Instant lookup of active DRM-free GOG game giveaways"),
                ("/giveawaynotify [on/off]", "or /notifygiveaways", "Toggle real-time private DM notifications for new free games"),
            ]
        },
        "economy": {
            "title": "💰 Economy, Shop & Leveling",
            "emoji": "💰",
            "label": "Economy",
            "desc": "Global Water Coin currency, shop catalog, XP ranking, and chat statistics.",
            "commands": [
                ("/rank", "", "View your personal chat level rank card and cumulative XP"),
                ("/ranking", "or /levels", "View the top 10 chat XP leaderboard"),
                ("/balance", "or /wallet, /coins", "Check your global Water Coin balance"),
                ("/pay <amount>", "or /transfer", "Reply to a user to transfer coins to them"),
                ("/shop", "", "Browse available items & custom title badges in the group shop"),
                ("/buy <item_id>", "", "Purchase shop items (custom tags, warning cleanse) with coins"),
                ("/chatstats", "", "View group analytics: total messages, members, max level & total XP"),
                ("/chatters", "", "View the top 5 most active chat members in this group"),
            ]
        },
        "ai_media": {
            "title": "🤖 AI Assistant & Media Downloader",
            "emoji": "🤖",
            "label": "AI / Media",
            "desc": "Mistral-powered conversational AI, multimodal vision, music, video & image generation.",
            "commands": [
                ("/ask [prompt]", "or /ai", "Ask Giyu a question (supports replies to photos & stickers)"),
                ("/dl <url>", "or /download, /insta, /tiktok, /fb, /terabox", "Universal media & file downloader (1,800+ hosts)"),
                ("/play <query or URL>", "", "Download and stream audio from YouTube / SoundCloud as MP3"),
                ("/video <query or URL>", "", "Download and stream direct video (max 50MB)"),
                ("/draw <prompt>", "", "Generate AI artwork (Perchance + Pollinations fallback)"),
                ("/kang [emoji]", "", "Reply to media/sticker to convert it into a Telegram sticker"),
                ("/giyustats", "", "View AI persona memory level, evolutionary traits & unlocked skills"),
            ]
        },
        "moderation": {
            "title": "🛡️ Group Moderation (Admins)",
            "emoji": "🛡️",
            "label": "Moderation",
            "desc": "Administrative moderation, automated rule enforcement, and user management.",
            "commands": [
                ("/promote", "/demote", "Grant or revoke administrator privileges"),
                ("/kick", "", "Remove a user from the group"),
                ("/ban", "/unban", "Permanently ban or unban a user from the group"),
                ("/mute", "/unmute", "Silence or restore a user's chat permissions"),
                ("/tempmute <duration>", "", "Temporarily mute a user (e.g. 10m, 2h, 1d) with auto-unmute"),
                ("/warn", "/dwarn", "Issue strike or remove warning (3 strikes = auto-ban)"),
                ("/purge", "", "Reply to bulk delete messages up to the current one"),
                ("/pin", "/unpin", "Pin or unpin important messages in the group"),
                ("/admin_list", "", "List all active group administrators"),
            ]
        },
        "settings": {
            "title": "⚙️ Group Settings & Automation",
            "emoji": "⚙️",
            "label": "Settings",
            "desc": "Configure group automation, auto-responders, welcome greetings, and AI personas.",
            "commands": [
                ("/setchar <giyu|tanjiro|nezuko|shinobu>", "", "Swap the active AI character persona"),
                ("/setrules <text>", "", "Configure the official group rules"),
                ("/welcome [on/off]", "", "Toggle automated join greeting cards"),
                ("/setwelcome <msg>", "", "Customize welcome message template (supports {name} & {chat})"),
                ("/filter <keyword> <reply>", "", "Set keyword auto-reply trigger (text/photo/sticker/voice)"),
                ("/filters", "", "View all active keyword auto-reply triggers"),
                ("/stopfilter <keyword>", "or /removefilter, /delfilter", "Remove an auto-reply trigger"),
                ("/tag <name> <text>", "", "Create a custom #hashtag note"),
                ("/tags", "", "List all active #hashtag notes"),
                ("/stoptag <name>", "or /removetag, /deltag", "Delete a #hashtag note"),
                ("/settag <tag>", "", "Reply to assign a custom badge/title to a user"),
                ("/afkstat [on/off]", "", "Toggle AFK mention alerts for this group"),
                ("/learn", "", "Reply to a document (.pdf, .txt, .md) to teach facts to RAG memory"),
            ]
        },
        "owner": {
            "title": "👑 Super Admin & Bot Owner",
            "emoji": "👑",
            "label": "Super Admin",
            "desc": "Global bot management, giveaway monitors, coin minting, and system analytics.",
            "commands": [
                ("/botstats", "", "View global system stats, active groups, CPU/RAM & DB memory"),
                ("/broadcast <message>", "", "Broadcast an announcement to all managed groups"),
                ("/add <amount>", "", "Mint coins to user or self from central treasury"),
                ("/remove <amount>", "or /take", "Confiscate coins from a user"),
                ("/botbal", "or /botbalance", "View remaining central Bot Treasury balance"),
                ("/leave", "", "Force the bot to leave a specific group chat"),
            ]
        },
        "all": {
            "title": "📜 Complete Commands Directory",
            "emoji": "📜",
            "label": "All Summary",
            "desc": "Quick overview index of all command modules available in Giyu-Bot.",
            "commands": [
                ("🌐 Public Utilities", "", "<code>/start</code>, <code>/help</code>, <code>/search</code>, <code>/info</code>, <code>/rules</code>, <code>/afk</code>, <code>/owner</code>, <code>/report</code>"),
                ("🎮 Gaming & Freebies", "", "<code>/game</code>, <code>/newlow</code>, <code>/deals</code>, <code>/giveaways</code>, <code>/gog</code>, <code>/giveawaynotify</code>"),
                ("💰 Economy & Levels", "", "<code>/rank</code>, <code>/ranking</code>, <code>/balance</code>, <code>/pay</code>, <code>/shop</code>, <code>/buy</code>, <code>/chatstats</code>, <code>/chatters</code>"),
                ("🤖 AI & Media", "", "<code>/ask</code>, <code>/dl</code>, <code>/play</code>, <code>/video</code>, <code>/draw</code>, <code>/kang</code>, <code>/giyustats</code>"),
                ("🛡️ Moderation", "", "<code>/promote</code>, <code>/demote</code>, <code>/kick</code>, <code>/ban</code>, <code>/mute</code>, <code>/tempmute</code>, <code>/warn</code>, <code>/purge</code>, <code>/pin</code>"),
                ("⚙️ Group Settings", "", "<code>/setchar</code>, <code>/setrules</code>, <code>/welcome</code>, <code>/filter</code>, <code>/tag</code>, <code>/settag</code>, <code>/afkstat</code>, <code>/learn</code>"),
                ("👑 Super Admin", "", "<code>/botstats</code>, <code>/broadcast</code>, <code>/add</code>, <code>/remove</code>, <code>/botbal</code>, <code>/leave</code>"),
            ]
        }
    }

    def _render_command_catalog(self, active_cat: str = "public") -> tuple[str, InlineKeyboardMarkup]:
        if active_cat not in self.COMMAND_CATEGORIES:
            active_cat = "public"
            
        data = self.COMMAND_CATEGORIES[active_cat]
        
        text = (
            f"🌊 <b>Giyu-Bot Command Center</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📂 <b>Module:</b> {data['title']}\n"
            f"ℹ️ <i>{data['desc']}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        if active_cat == "all":
            for cat_title, _, cmd_list in data["commands"]:
                text += f"<b>{cat_title}</b>\n↳ {cmd_list}\n\n"
        else:
            for cmd_syntax, aliases, cmd_desc in data["commands"]:
                alias_str = f" <i>({aliases})</i>" if aliases else ""
                text += f"• <code>{cmd_syntax}</code>{alias_str}\n  ↳ <i>{cmd_desc}</i>\n\n"

        text += "💡 <i>Tap any category below to switch views:</i>"

        # Build clean 2-column category keyboard
        keyboard = []
        row = []
        for key, cat in self.COMMAND_CATEGORIES.items():
            label = f"• {cat['label']} •" if key == active_cat else f"{cat['emoji']} {cat['label']}"
            btn = InlineKeyboardButton(label, callback_data=f"cmdcat_{key}")
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([
            InlineKeyboardButton("📢 Support Channel", url="https://t.me/+RKhH82C8mgw1M2Y1"),
            InlineKeyboardButton("👑 Developer", url=f"tg://user?id={BOT_OWNER_ID}")
        ])
        
        return text, InlineKeyboardMarkup(keyboard)

    async def help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text, reply_markup = self._render_command_catalog("public")
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

    async def list_commands_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text, reply_markup = self._render_command_catalog("public")
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

    async def command_catalog_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace("cmdcat_", "")
        text, reply_markup = self._render_command_catalog(category)
        
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            pass

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

    async def web_search_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        query = " ".join(context.args).strip() if context.args else ""
        if not query and update.message.reply_to_message and update.message.reply_to_message.text:
            query = update.message.reply_to_message.text.strip()

        if not query:
            await update.message.reply_text(
                "🌐 <b>Internet Web Search</b>\n\n"
                "<b>Usage:</b> <code>/search [query]</code> or <code>/google [query]</code>\n"
                "<b>Example:</b> <code>/search latest NASA space discoveries</code>\n\n"
                "<i>Or reply to any text message with /search to search it directly!</i>",
                parse_mode="HTML"
            )
            return

        chat_id = update.message.chat_id
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            results_text = await self.search_service.search_duckduckgo(query, limit=5)
            wiki_summary = await self.search_service.search_wikipedia(query)

            encoded_q = urllib.parse.quote_plus(query)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔍 Google", url=f"https://www.google.com/search?q={encoded_q}"),
                    InlineKeyboardButton("🦆 DuckDuckGo", url=f"https://duckduckgo.com/?q={encoded_q}"),
                ]
            ])

            response_parts = [
                f"🌐 <b>Web Search Results for:</b> <code>{query}</code>\n━━━━━━━━━━━━━━━━━━━━"
            ]

            if wiki_summary and "No Wikipedia summary found" not in wiki_summary:
                response_parts.append(f"📚 {wiki_summary}\n━━━━━━━━━━━━━━━━━━━━")

            response_parts.append(results_text)

            final_msg = "\n\n".join(response_parts)
            await update.message.reply_text(
                text=final_msg[:4000],
                parse_mode="Markdown",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )

        except Exception as e:
            logger.error(f"Error in web_search_cmd: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Web search failed: {e}")

