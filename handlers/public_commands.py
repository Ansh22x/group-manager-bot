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
                ("<code>/start</code>", "Open the bot welcome menu and links"),
                ("<code>/help</code>", "Interactive command directory dashboard"),
                ("<code>/search &lt;query&gt;</code> <i>(or /google, /web)</i>", "Search live web results from the internet"),
                ("<code>/info</code> <i>(or /id, /whois)</i>", "Inspect user numeric ID, permissions, wallet & metadata"),
                ("<code>/rules</code>", "View the current group rules"),
                ("<code>/afk [reason]</code>", "Set AFK status (mentions notify callers)"),
                ("<code>/owner</code>", "View group owner & bot developer info"),
                ("<code>/report [reason]</code>", "Reply to report inappropriate content to admins"),
            ]
        },
        "gaming": {
            "title": "🎮 Steam, Deals & Giveaways",
            "emoji": "🎮",
            "label": "Gaming",
            "desc": "Real-time game search, SteamDB historical lows, keyshops, and freebie monitors.",
            "commands": [
                ("<code>/game &lt;title&gt;</code> <i>(or /steam)</i>", "Search Steam game, review scores, price & cover art"),
                ("<code>/newlow &lt;title&gt;</code>", "Check if a game is matching/breaking its historical all-time low"),
                ("<code>/deals</code> <i>(or /steamdeals)</i>", "Browse top trending discounted PC games"),
                ("<code>/gog</code>", "View active DRM-free GOG game giveaways"),
                ("<code>/giveaways [category]</code>", "Browse Alienware, AMD, Medal, Steam & Epic freebies"),
            ]
        },
        "economy": {
            "title": "💰 Economy, Shop & Leveling",
            "emoji": "💰",
            "label": "Economy",
            "desc": "Global Water Coin currency, shop catalog, XP ranking, and chat statistics.",
            "commands": [
                ("<code>/rank</code>", "View your current level rank and cumulative XP"),
                ("<code>/ranking</code> <i>(or /levels)</i>", "View the top 10 chat leaderboard"),
                ("<code>/balance</code> <i>(or /wallet, /coins)</i>", "Check your global Water Coin balance"),
                ("<code>/pay &lt;amount&gt;</code>", "Reply to transfer coins to another member"),
                ("<code>/shop</code>", "Browse items available in the group shop"),
                ("<code>/buy &lt;item_id&gt;</code>", "Purchase items (custom tags, warning cleanse) with coins"),
                ("<code>/chatstats</code>", "View overall group message & member activity stats"),
                ("<code>/chatters</code>", "View the top 5 most active chatters in this group"),
            ]
        },
        "ai_media": {
            "title": "🤖 AI Assistant & Media",
            "emoji": "🤖",
            "label": "AI / Media",
            "desc": "Mistral-powered conversational personas, multimodal vision, music, video & image generation.",
            "commands": [
                ("<code>/dl &lt;url&gt;</code>", "Universal video & file downloader (Insta, TikTok, FB, Terabox, YT, etc.)"),
                ("<code>/insta &lt;url&gt;</code>", "Download Instagram Reels, Stories & video posts"),
                ("<code>/tiktok &lt;url&gt;</code>", "Download HD TikTok videos without watermark"),
                ("<code>/fb &lt;url&gt;</code>", "Download Facebook Reels & Watch videos"),
                ("<code>/terabox &lt;url&gt;</code>", "Download Terabox videos & cloud files"),
                ("<code>/ask [question]</code>", "Direct agentic query (supports replies to photos & stickers)"),
                ("<code>/play &lt;song or URL&gt;</code>", "Download and play YouTube/SoundCloud audio as MP3"),
                ("<code>/video &lt;name or URL&gt;</code>", "Download and stream video (max 50MB)"),
                ("<code>/draw &lt;prompt&gt;</code>", "Generate AI artwork (Perchance + Pollinations fallback)"),
                ("<code>/kang</code>", "Reply to media/sticker to convert it into a Telegram sticker"),
                ("<code>/giyustats</code>", "View AI persona level, evolution traits & unlocked skills"),
            ]
        },
        "moderation": {
            "title": "🛡️ Group Moderation (Admins)",
            "emoji": "🛡️",
            "label": "Moderation",
            "desc": "Administrative moderation, automated rule enforcement, and user management.",
            "commands": [
                ("<code>/promote</code> / <code>/demote</code>", "Grant or revoke admin privileges"),
                ("<code>/kick</code> / <code>/unban</code>", "Remove or restore a user from the group"),
                ("<code>/mute</code> / <code>/unmute</code>", "Silence or restore chat permissions"),
                ("<code>/tempmute &lt;duration&gt;</code>", "Temporarily mute (e.g. <code>10m</code>, <code>2h</code>, <code>1d</code>) with auto-unmute"),
                ("<code>/warn</code> / <code>/dwarn</code>", "Issue or remove warning strikes (3 strikes = auto-ban)"),
                ("<code>/purge</code>", "Reply to bulk delete messages up to the current one"),
                ("<code>/pin</code> / <code>/unpin</code>", "Pin or unpin messages in the group"),
                ("<code>/admin_list</code>", "List all active group administrators"),
            ]
        },
        "settings": {
            "title": "⚙️ Group Settings & Personas",
            "emoji": "⚙️",
            "label": "Settings",
            "desc": "Configure group automation, auto-responders, welcome greetings, and AI personas.",
            "commands": [
                ("<code>/setchar &lt;giyu|tanjiro|nezuko|shinobu&gt;</code>", "Swap the active AI character persona"),
                ("<code>/setrules &lt;text&gt;</code>", "Configure the official group rules"),
                ("<code>/welcome [on/off]</code>", "Toggle automated join greeting cards"),
                ("<code>/setwelcome &lt;msg&gt;</code>", "Customize welcome message template (supports <code>{name}</code>)"),
                ("<code>/filter &lt;keyword&gt; &lt;reply&gt;</code>", "Set keyword auto-reply trigger"),
                ("<code>/stopfilter &lt;keyword&gt;</code>", "Remove a keyword auto-reply trigger"),
                ("<code>/addtag &lt;name&gt; &lt;text&gt;</code>", "Create a custom <code>#hashtag</code> note"),
                ("<code>/settag &lt;tag&gt;</code>", "Reply to assign a custom title tag to a user"),
                ("<code>/afkstat [on/off]</code>", "Toggle AFK mention alerts for this group"),
                ("<code>/learn</code>", "Reply to a document (.pdf, .txt, .md) to teach facts to RAG memory"),
            ]
        },
        "owner": {
            "title": "👑 Super Admin & Bot Owner",
            "emoji": "👑",
            "label": "Super Admin",
            "desc": "Global bot management, giveaway monitors, coin minting, and system analytics.",
            "commands": [
                ("<code>/giveaways [category]</code>", "Guarded Alienware, AMD, Medal, Steam & GOG key monitor"),
                ("<code>/giveawaynotify [on/off]</code>", "Toggle 60s real-time private DM freebie alerts"),
                ("<code>/botstats</code>", "View global system stats, active groups & memory logs"),
                ("<code>/broadcast &lt;message&gt;</code>", "Broadcast an announcement to all managed groups"),
                ("<code>/add &lt;amount&gt;</code>", "Mint coins to user or self from treasury"),
                ("<code>/remove &lt;amount&gt;</code>", "Confiscate coins from a user"),
                ("<code>/botbalance</code>", "View remaining central Bot Treasury balance"),
                ("<code>/leave</code>", "Force the bot to leave a specific group chat"),
            ]
        }
    }

    def _render_command_catalog(self, active_cat: str = "public") -> tuple[str, InlineKeyboardMarkup]:
        if active_cat not in self.COMMAND_CATEGORIES:
            active_cat = "public"
            
        data = self.COMMAND_CATEGORIES[active_cat]
        text = (
            f"🌊 <b>Giyu-Bot Command Center</b> • {data['title']}\n"
            f"<i>{data['desc']}</i>\n\n"
        )
        for cmd_name, cmd_desc in data["commands"]:
            text += f"🔹 {cmd_name} — {cmd_desc}\n"

        text += "\n💡 <i>Tap any category button below to browse more commands:</i>"

        # Build category selection keyboard
        buttons = []
        row1 = []
        row2 = []
        row3 = []
        row4 = []

        keys = list(self.COMMAND_CATEGORIES.keys())
        for idx, key in enumerate(keys):
            cat = self.COMMAND_CATEGORIES[key]
            label = f"• {cat['label']} •" if key == active_cat else f"{cat['emoji']} {cat['label']}"
            btn = InlineKeyboardButton(label, callback_data=f"cmdcat_{key}")
            
            if idx < 2:
                row1.append(btn)
            elif idx < 4:
                row2.append(btn)
            elif idx < 6:
                row3.append(btn)
            else:
                row4.append(btn)

        keyboard = [row for row in [row1, row2, row3, row4] if row]
        keyboard.append([
            InlineKeyboardButton("📢 Channel", url="https://t.me/+RKhH82C8mgw1M2Y1"),
            InlineKeyboardButton("👑 Owner", url=f"tg://user?id={BOT_OWNER_ID}")
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

