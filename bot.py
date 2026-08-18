import os
import time
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

# Load secret variables
load_dotenv()

# ==========================================
# 0. BOT OWNER CONFIGURATION
# ==========================================
# Fetches your Owner ID from Render/Env. Defaults to 0 if not set.
BOT_OWNER_ID = int(os.getenv("OWNER_ID", "0"))

def is_bot_owner(user_id: int) -> bool:
    return user_id == BOT_OWNER_ID

# ==========================================
# 1. BASIC MEMORY & AFK SYSTEM
# ==========================================
group_data = {}
afk_users = {} 

def get_chat_data(chat_id):
    if chat_id not in group_data:
        group_data[chat_id] = {
            'rules': "No rules have been set for this group yet.",
            'welcome_msg': "Welcome to the group, {name}!",
            'welcome_on': True,
            'warns': {},
            'filters': {},
            'tags': {}, 
            'afk_on': True,
            'users': {} # Tracks XP, Levels, and custom user tags
        }
    return group_data[chat_id]

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message.chat.type == 'private': return False
    # If YOU are using the command, automatically grant access everywhere
    if is_bot_owner(update.message.from_user.id):
        return True
    chat_member = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
    return chat_member.status in ['administrator', 'creator']

# ==========================================
# 2. START MENU & BUTTONS
# ==========================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username
    
    # Building the inline keyboard buttons
    keyboard = [
        [
            # CHANGE THIS LINK TO YOUR ACTUAL SUPPORT CHANNEL
            InlineKeyboardButton("📢 Support Channel", url="https://t.me/+RKhH82C8mgw1M2Y1"),
            InlineKeyboardButton("👑 Owner", url=f"tg://user?id={BOT_OWNER_ID}")
        ],
        [
            InlineKeyboardButton("➕ Add me to your GC", url=f"https://t.me/{bot_username}?startgroup=true")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "👋 <b>Hello! I am your Advanced Group Manager Bot.</b>\n\n"
        "I can help you manage your group with XP leveling, automated moderation, AFK tracking, custom tags, and much more!\n\n"
        "Click the buttons below to connect with my creator or add me to your group."
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")

# ==========================================
# 3. PROMOTIONS & MODERATION
# ==========================================
async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.promote_chat_member(
                update.message.chat_id, user.id,
                can_pin_messages=True, can_delete_messages=True,
                can_invite_users=True, can_restrict_members=True,
                can_manage_chat=True, can_manage_video_chats=True
            )
            await update.message.reply_text(f"Promoted {user.first_name} to Admin! 🛡️")
        except Exception:
            await update.message.reply_text("I can't promote them. Make sure I have the 'Add New Admins' permission!")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.promote_chat_member(
                update.message.chat_id, user.id,
                is_anonymous=False, can_manage_chat=False,
                can_post_messages=False, can_edit_messages=False,
                can_delete_messages=False, can_manage_video_chats=False,
                can_restrict_members=False, can_promote_members=False,
                can_change_info=False, can_invite_users=False,
                can_pin_messages=False, can_manage_topics=False
            )
            await update.message.reply_text(f"Demoted {user.first_name}. They are now a normal member.")
        except Exception:
            await update.message.reply_text("Failed to demote. I might not have permission, or the user is the group creator.")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        await context.bot.ban_chat_member(update.message.chat_id, user.id)
        await context.bot.unban_chat_member(update.message.chat_id, user.id)
        await update.message.reply_text(f"Kicked {user.first_name}.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        await context.bot.unban_chat_member(update.message.chat_id, user.id, only_if_banned=True)
        await update.message.reply_text(f"Unbanned {user.first_name}.")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        perms = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(update.message.chat_id, user.id, permissions=perms)
        await update.message.reply_text(f"Muted {user.first_name}.")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        perms = ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_other_messages=True)
        await context.bot.restrict_chat_member(update.message.chat_id, user.id, permissions=perms)
        await update.message.reply_text(f"Unmuted {user.first_name}.")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        data = get_chat_data(chat_id)
        data['warns'][user.id] = data['warns'].get(user.id, 0) + 1
        warn_count = data['warns'][user.id]
        if warn_count >= 3:
            await context.bot.ban_chat_member(chat_id, user.id)
            await update.message.reply_text(f"{user.first_name} reached 3 warnings and was banned.")
            data['warns'][user.id] = 0
        else:
            await update.message.reply_text(f"{user.first_name} has been warned. ({warn_count}/3)")

async def dwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        data = get_chat_data(update.message.chat_id)
        if user.id in data['warns'] and data['warns'][user.id] > 0:
            data['warns'][user.id] -= 1
            await update.message.reply_text(f"Removed a warning from {user.first_name}. ({data['warns'][user.id]}/3)")

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        await context.bot.pin_chat_message(update.message.chat_id, update.message.reply_to_message.message_id)

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        await context.bot.unpin_chat_message(update.message.chat_id, update.message.reply_to_message.message_id)

# ==========================================
# 4. AFK & TAGS COMMANDS
# ==========================================
async def set_afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = " ".join(context.args) or "No reason provided"
    afk_users[update.message.from_user.id] = reason
    await update.message.reply_text(f"💤 {update.message.from_user.first_name} is now AFK. Reason: {reason}")

async def toggle_afkstat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    data = get_chat_data(update.message.chat_id)
    data['afk_on'] = not data.get('afk_on', True)
    status = "ON" if data['afk_on'] else "OFF"
    await update.message.reply_text(f"AFK monitoring is now {status} for this group.")

async def add_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if len(context.args) >= 2:
        tag = context.args[0].lower().replace('#', '')
        reply_text = " ".join(context.args[1:])
        get_chat_data(update.message.chat_id)['tags'][tag] = reply_text
        await update.message.reply_text(f"Tag added! Anyone can now type #{tag} to see it.")

async def edit_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if len(context.args) >= 2:
        tag = context.args[0].lower().replace('#', '')
        reply_text = " ".join(context.args[1:])
        tags_dict = get_chat_data(update.message.chat_id)['tags']
        if tag in tags_dict:
            tags_dict[tag] = reply_text
            await update.message.reply_text(f"Tag #{tag} updated!")
        else:
            await update.message.reply_text(f"Tag #{tag} doesn't exist. Use /addtag to create it.")

# ==========================================
# 5. ADMIN TOOLS & SETTINGS
# ==========================================
async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private': return
    admins = await context.bot.get_chat_administrators(update.message.chat_id)
    admin_names = [f"- {admin.user.first_name}" for admin in admins]
    await update.message.reply_text("👮‍♂️ <b>Group Admins:</b>\n" + "\n".join(admin_names), parse_mode="HTML")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    new_rules = " ".join(context.args)
    if new_rules:
        get_chat_data(update.message.chat_id)['rules'] = new_rules
        await update.message.reply_text("Rules updated successfully!")

async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = get_chat_data(update.message.chat_id)['rules']
    await update.message.reply_text(f"📜 <b>Group Rules:</b>\n\n{rules}", parse_mode="HTML")

async def toggle_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    data = get_chat_data(update.message.chat_id)
    data['welcome_on'] = not data['welcome_on']
    status = "ON" if data['welcome_on'] else "OFF"
    await update.message.reply_text(f"Welcome messages are now {status}.")

async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    new_welcome = " ".join(context.args)
    if new_welcome:
        get_chat_data(update.message.chat_id)['welcome_msg'] = new_welcome
        await update.message.reply_text("Welcome message updated! (Use {name} to insert the user's name).")

async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if len(context.args) >= 2:
        keyword = context.args[0].lower()
        reply_text = " ".join(context.args[1:])
        get_chat_data(update.message.chat_id)['filters'][keyword] = reply_text
        await update.message.reply_text(f"Filter added! When someone says '{keyword}', I will reply.")

# ==========================================
# 6. THE KANG COMMAND (Image to Sticker)
# ==========================================
async def kang_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Please reply to a photo to kang it!")
        return

    msg = update.message.reply_to_message
    processing_msg = await update.message.reply_text("🪄 Kanging image... resizing to 512px...")

    try:
        file_id = msg.photo[-1].file_id
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        
        img = Image.open(BytesIO(file_bytes))
        ratio = 512 / max(img.width, img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        bio = BytesIO()
        bio.name = 'kang.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        
        await context.bot.send_sticker(chat_id=update.message.chat_id, sticker=bio)
        await processing_msg.delete() 
    except Exception as e:
        await processing_msg.edit_text(f"Oops! Something went wrong: {e}")

# ==========================================
# 7. LEVELING & RANKING SYSTEM
# ==========================================
async def award_xp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type == 'private': return
    
    user = update.message.from_user
    chat_data = get_chat_data(update.message.chat_id)
    current_time = time.time()
    
    if user.id not in chat_data['users']:
        chat_data['users'][user.id] = {'xp': 0, 'level': 1, 'last_xp_time': 0, 'tag': 'Member', 'name': user.first_name}
    
    user_stats = chat_data['users'][user.id]
    
    if current_time - user_stats['last_xp_time'] > 60:
        user_stats['xp'] += 15
        user_stats['last_xp_time'] = current_time
        
        new_level = int((user_stats['xp'] / 100) ** 0.6) + 1
        
        if new_level > user_stats['level']:
            user_stats['level'] = new_level
            await update.message.reply_text(f"🎉 <b>{user.first_name}</b> leveled up to <b>Level {new_level}!</b>", parse_mode="HTML")

async def show_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.message.from_user
    chat_data = get_chat_data(update.message.chat_id)
    stats = chat_data['users'].get(target_user.id, {'xp': 0, 'level': 1, 'tag': 'Member'})
    
    rank_card = (
        f"📊 <b>Stats for {target_user.first_name}</b>\n"
        f"🏷 <b>Title:</b> {stats['tag']}\n"
        f"⭐ <b>Level:</b> {stats['level']}\n"
        f"✨ <b>XP:</b> {stats['xp']}"
    )
    await update.message.reply_text(rank_card, parse_mode="HTML")

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = get_chat_data(update.message.chat_id)
    users = chat_data['users'].values()
    
    if not users:
        await update.message.reply_text("No one has gained any XP yet!")
        return
        
    sorted_users = sorted(users, key=lambda x: x['xp'], reverse=True)[:10] 
    
    board = "🏆 <b>Group Leaderboard</b> 🏆\n\n"
    for i, u in enumerate(sorted_users, 1):
        board += f"{i}. <b>{u['name']}</b> (Lvl {u['level']}) - <i>{u['tag']}</i>\n"
        
    await update.message.reply_text(board, parse_mode="HTML")

async def set_user_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to set their tag!")
        return
        
    new_tag = " ".join(context.args)
    if not new_tag:
        await update.message.reply_text("Please provide a tag! Example: /settag VIP Member")
        return
        
    target_user = update.message.reply_to_message.from_user
    chat_data = get_chat_data(update.message.chat_id)
    
    if target_user.id not in chat_data['users']:
        chat_data['users'][target_user.id] = {'xp': 0, 'level': 1, 'last_xp_time': 0, 'tag': 'Member', 'name': target_user.first_name}
        
    chat_data['users'][target_user.id]['tag'] = new_tag
    await update.message.reply_text(f"✅ Set {target_user.first_name}'s tag to: <b>{new_tag}</b>", parse_mode="HTML")

# ==========================================
# 8. OWNER COMMANDS (New!)
# ==========================================
async def show_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"💻 <b>Bot Developer:</b> <a href='tg://user?id={BOT_OWNER_ID}'>@sylveon_clone02</a>"
    )
    await update.message.reply_text(response_text, parse_mode="HTML")

async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if not is_bot_owner(user_id):
        await update.message.reply_text("⛔ <b>Access Denied:</b> This command is reserved exclusively for the Bot Owner.", parse_mode="HTML")
        return

    total_groups = len(group_data)
    total_afk = len(afk_users)

    stats_msg = (
        "⚙️ <b>Bot Owner Dashboard</b>\n\n"
        f"📊 <b>Active Managed Groups:</b> {total_groups}\n"
        f"💤 <b>Total AFK Users:</b> {total_afk}\n"
        f"🛡️ <b>Owner ID:</b> <code>{BOT_OWNER_ID}</code>\n"
        f"🟢 <b>Status:</b> Online & Polling 24/7"
    )
    await update.message.reply_text(stats_msg, parse_mode="HTML")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_owner(update.message.from_user.id):
        await update.message.reply_text("⛔ <b>Access Denied.</b>", parse_mode="HTML")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("Usage: <code>/broadcast Your message here</code>", parse_mode="HTML")
        return

    sent_count = 0
    for chat_id in group_data.keys():
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"📢 <b>Global Announcement:</b>\n\n{message}", 
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception:
            continue

    await update.message.reply_text(f"✅ Announcement sent to <b>{sent_count}</b> group(s).", parse_mode="HTML")

# ==========================================
# 9. AUTOMATED LISTENERS & HELP
# ==========================================
async def message_handler_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await award_xp(update, context)
    if not update.message or not update.message.text: return
    
    text = update.message.text
    lower_text = text.lower()
    user_id = update.message.from_user.id
    data = get_chat_data(update.message.chat_id)

    if user_id in afk_users and data.get('afk_on', True):
        del afk_users[user_id]
        await update.message.reply_text(f"Welcome back {update.message.from_user.first_name}! You are no longer AFK.")

    if update.message.reply_to_message and data.get('afk_on', True):
        replied_id = update.message.reply_to_message.from_user.id
        if replied_id in afk_users:
            await update.message.reply_text(f"💤 They are currently AFK: {afk_users[replied_id]}")

    for tag, reply in data['tags'].items():
        if f"#{tag}" in lower_text: await update.message.reply_text(reply)
    for keyword, reply in data['filters'].items():
        if keyword in lower_text: await update.message.reply_text(reply)

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_chat_data(update.message.chat_id)
    if not data['welcome_on']: return
    for new_member in update.message.new_chat_members:
        if new_member.id != context.bot.id:
            greeting = data['welcome_msg'].replace("{name}", new_member.first_name)
            await update.message.reply_text(greeting)

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    🛠 <b>Bot Commands:</b>
    /start - Show bot menu and links
    /kick, /unban - Remove or restore users
    /mute, /unmute - Restrict talking
    /promote, /demote - Manage admins
    /warn, /dwarn - 3 strikes = ban
    /afk, /afkstat - AFK system
    /addtag, /edit_tag - Create #hashtag notes
    /rules, /welcome, /filter - Chat setup
    /kang - Reply to an image to make a sticker!
    /rank, /ranking, /settag - View & manage XP
    /owner - See group owner and bot developer
    """
    await update.message.reply_text(help_text, parse_mode="HTML")

async def list_commands_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands_text = """
    📜 <b>Complete Command List</b>

    👥 <b>Public Commands:</b>
    /start - Show bot menu and links
    /help - Quick command overview
    /afk - Set your status to sleeping/busy
    /kang - Reply to an image to make a sticker
    /rank - View your level and XP
    /ranking (or /levels) - View the top 10 leaderboard
    /rules - Read the group rules
    /owner - See group owner and bot developer
    /list_commands - Show this detailed list

    🛡️ <b>Admin Commands:</b>
    /kick, /unban - Remove or restore users
    /mute, /unmute - Restrict talking
    /warn, /dwarn - Manage warning strikes (3 = ban)
    /promote, /demote - Manage admin privileges
    /pin, /unpin - Manage pinned messages
    /admin_list - View group admins
    /setrules - Update the rules
    /welcome, /setwelcome - Toggle and edit welcome messages
    /filter - Add a keyword auto-reply
    /afkstat - Toggle AFK monitoring
    /addtag, /edit_tag - Manage #hashtag notes
    /settag - Give a user a custom title

    💻 <b>Bot Owner Commands:</b>
    /botstats - View active groups and bot status
    /broadcast - Send a message to all groups
    """
    await update.message.reply_text(commands_text, parse_mode="HTML")
    
# ==========================================
# 10. RUN THE SECURE BOT
# ==========================================
if __name__ == "__main__":
    # 1. Start the web server instantly so Render sees the port
    from keep_alive import keep_alive
    keep_alive()

    # 2. THEN load the bot token and setup
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN not found in environment!")
        exit()
        
    app = Application.builder().token(token).build()

    commands = [
        ("start", start_cmd),
        ("kick", kick_user), ("unban", unban_user), 
        ("mute", mute_user), ("unmute", unmute_user),
        ("warn", warn_user), ("dwarn", dwarn_user),
        ("promote", promote_user), ("demote", demote_user),
        ("pin", pin_msg), ("unpin", unpin_msg),
        ("admin_list", admin_list),
        ("rules", show_rules), ("setrules", set_rules),
        ("welcome", toggle_welcome), ("setwelcome", set_welcome),
        ("filter", add_filter), 
        ("afk", set_afk), ("afkstat", toggle_afkstat),
        ("addtag", add_tag), ("edit_tag", edit_tag),
        ("kang", kang_sticker), ("help", help_menu),
        ("rank", show_rank), ("settag", set_user_tag),
        ("owner", show_owner), ("botstats", bot_stats), 
        ("broadcast", broadcast_message)
        ("list_commands", list_commands_cmd)
    ]
    
    for cmd, func in commands:
        app.add_handler(CommandHandler(cmd, func))
        
    app.add_handler(CommandHandler(["ranking", "levels"], show_leaderboard))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler((filters.TEXT | filters.Sticker.ALL) & ~filters.COMMAND, message_handler_hub))

    print("Ultra-Secure Master Bot is running...")
    app.run_polling()
