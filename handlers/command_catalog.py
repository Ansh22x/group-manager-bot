from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_OWNER_ID

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
        "title": "🎮 Steam, Anime & Freebies",
        "emoji": "🎮",
        "label": "Gaming & Anime",
        "desc": "Steam game search, deals, historical lows, freebies, and AniList anime/manga lookup.",
        "commands": [
            ("/game <title>", "or /steam", "Search Steam game, review rating, live CCU players & price in INR"),
            ("/newlow <title>", "or /islow, /atl", "Check if a game matches or breaks its all-time historical low price"),
            ("/deals", "or /steamdeals, /gamedeals", "Browse top trending discounted PC games (CheapShark + Steam Specials)"),
            ("/giveaways [category]", "or /giveaway, /freebies, /freegames", "Browse active Alienware, AMD, Medal, Steam & Epic freebies"),
            ("/gog", "", "Instant lookup of active DRM-free GOG game giveaways"),
            ("/giveawaynotify [on/off]", "or /notifygiveaways", "Toggle real-time private DM notifications for new free games"),
            ("/anime <title>", "or /ani", "Search AniList anime synopsis, score, studio, episodes & cover"),
            ("/manga <title>", "or /manhwa", "Search AniList manga chapters, score, author & synopsis"),
            ("/sauce", "or /whatanime, /findanime", "Reply to anime image/meme to find exact anime, episode & timestamp"),
            ("/quote", "or /animequote", "Get an iconic Demon Slayer voice line & anime quote"),
        ]
    },
    "economy": {
        "title": "💰 Economy, Activity & Mini-Games",
        "emoji": "💰",
        "label": "Games & Activity",
        "desc": "Global Water Coin currency, daily streaks, activity heatmaps, weekly digests, and ranking.",
        "commands": [
            ("/daily", "", "Claim your daily streak reward (+100 to +750 coins & level XP)"),
            ("/rank", "", "View your personal chat level rank card and cumulative XP"),
            ("/ranking", "or /levels", "View the top 10 chat XP leaderboard"),
            ("/activity", "or /heatmap", "Render visual hourly activity heatmap of chat engagement"),
            ("/weeklydigest", "or /digest, /gazette", "AI-curated 'The Corps Gazette' weekly newspaper issue"),
            ("/balance", "or /wallet, /coins", "Check your global Water Coin balance"),
            ("/pay <amount>", "or /transfer", "Reply to a user to transfer coins to them"),
            ("/gamble <amount>", "or /bet", "Gamble Water Coins for a 2x payout (46% win rate)"),
            ("/coinflip <heads|tails> <amt>", "or /cf, /flip", "Animated 50/50 coinflip with 2x payout"),
            ("/dice [amount]", "", "Roll animated Telegram dice (rolling 4, 5, 6 wins!)"),
            ("/slots [amount]", "or /slot", "Spin the animated slot machine for up to 10x jackpot!"),
            ("/duel <amount>", "or /fight", "Reply to challenge a member to a Water Breathing RPG battle!"),
            ("/trivia [category]", "", "Interactive timed quiz (first correct answer wins 100 coins + 50 XP!)"),
            ("/shop", "", "Browse available items & custom title badges in the group shop"),
            ("/buy <item_id>", "", "Purchase shop items (custom tags, warning cleanse) with coins"),
            ("/chatstats", "", "View group analytics: total messages, members, max level & total XP"),
            ("/chatters", "", "View the top 5 most active chat members in this group"),
        ]
    },
    "ai_media": {
        "title": "🤖 AI Assistant, Voice & Utilities",
        "emoji": "🤖",
        "label": "AI & Voice",
        "desc": "Mistral AI conversational persona, Hashira voice notes, vision, music identifier, summarizer & downloads.",
        "commands": [
            ("/ask [prompt]", "or /ai", "Ask Giyu a question (supports replies to photos, stickers & voice)"),
            ("/tts <text>", "or /voice, /speak", "Generate speech voice note in the character's voice"),
            ("/shazam", "or /identify, /whatsong", "Reply to any audio/video clip to identify song title, artist & links"),
            ("/summarize <url>", "or /summary, /tldr", "AI executive 3-bullet takeaway digest of any web article"),
            ("/tr <lang> <text>", "or /translate", "Translate text and generate native spoken voice note"),
            ("/dl <url>", "or /download, /insta, /tiktok, /fb, /terabox", "Universal media & file downloader (1,800+ hosts)"),
            ("/play <query or URL>", "", "Download and stream audio from YouTube / SoundCloud as MP3"),
            ("/video <query or URL>", "", "Download and stream direct video (max 50MB)"),
            ("/draw <prompt>", "", "Generate AI artwork (Perchance + Pollinations fallback)"),
            ("/kang [emoji]", "", "Reply to media/sticker to convert it into a Telegram sticker"),
            ("/giyustats", "", "View AI persona memory level, evolutionary traits & unlocked skills"),
            ("@bot_username <search>", "", "Inline query mode: search anime, games & quotes in any chat!"),
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
        "label": "Settings & Security",
        "desc": "Configure group automation, auto-responders, word blacklist, reminders & AI personas.",
        "commands": [
            ("/setchar <giyu|tanjiro|nezuko|shinobu>", "", "Swap the active AI character persona"),
            ("/blacklist <add|del|list> <word>", "or /bannedwords", "Auto-censor and delete messages containing banned words"),
            ("/remind <time> <msg>", "or /reminder, /timer", "Schedule a group or personal reminder (e.g. 10m, 2h, 1d)"),
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
            ("🎮 Gaming & Anime", "", "<code>/game</code>, <code>/newlow</code>, <code>/deals</code>, <code>/giveaways</code>, <code>/gog</code>, <code>/anime</code>, <code>/manga</code>, <code>/sauce</code>, <code>/quote</code>"),
            ("💰 Economy & Activity", "", "<code>/daily</code>, <code>/rank</code>, <code>/activity</code>, <code>/weeklydigest</code>, <code>/balance</code>, <code>/pay</code>, <code>/gamble</code>, <code>/coinflip</code>, <code>/dice</code>, <code>/slots</code>, <code>/duel</code>, <code>/trivia</code>, <code>/shop</code>"),
            ("🤖 AI & Voice Utilities", "", "<code>/ask</code>, <code>/tts</code>, <code>/shazam</code>, <code>/summarize</code>, <code>/tr</code>, <code>/dl</code>, <code>/play</code>, <code>/video</code>, <code>/draw</code>, <code>/kang</code>, <code>@bot</code>"),
            ("🛡️ Moderation", "", "<code>/promote</code>, <code>/demote</code>, <code>/kick</code>, <code>/ban</code>, <code>/mute</code>, <code>/tempmute</code>, <code>/warn</code>, <code>/purge</code>, <code>/pin</code>"),
            ("⚙️ Group Settings", "", "<code>/setchar</code>, <code>/blacklist</code>, <code>/remind</code>, <code>/setrules</code>, <code>/welcome</code>, <code>/filter</code>, <code>/tag</code>, <code>/learn</code>"),
            ("👑 Super Admin", "", "<code>/botstats</code>, <code>/broadcast</code>, <code>/add</code>, <code>/remove</code>, <code>/botbal</code>, <code>/leave</code>"),
        ]
    }
}

def render_command_catalog(active_cat: str = "public") -> tuple[str, InlineKeyboardMarkup]:
    """Renders formatted command directory text and interactive inline keyboard."""
    if active_cat not in COMMAND_CATEGORIES:
        active_cat = "public"
        
    data = COMMAND_CATEGORIES[active_cat]
    
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
    for key, cat in COMMAND_CATEGORIES.items():
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
