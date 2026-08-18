import os
import time
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

# Load secret variables from a .env file (Keeps your bot secure on GitHub)
load_dotenv()

# ==========================================
# 1. ISOLATED MEMORY (Multi-Group Security)
# ==========================================
# Because data is stored under chat_id, Group A can NEVER see Group B's data!
group_data = {}
afk_users = {} 

def get_chat_data(chat_id):
    if chat_id not in group_data:
        group_data[chat_id] = {
            'rules': "No rules set.",
            'welcome_msg': "Welcome, {name}!",
            'welcome_on': True,
            'warns': {},
            'filters': {},
            'tags': {},
            'afk_on': True,
            'users': {} # NEW: Tracks XP, Levels, and custom user tags
        }
    return group_data[chat_id]

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message.chat.type == 'private': return False
    chat_member = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
    return chat_member.status in ['administrator', 'creator']

# ==========================================
# 2. LEVELING & RANKING SYSTEM
# ==========================================
async def award_xp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Awards XP for chats and stickers, with a 60-second anti-spam cooldown"""
    if not update.message or update.message.chat.type == 'private': return
    
    user = update.message.from_user
    chat_data = get_chat_data(update.message.chat_id)
    current_time = time.time()
    
    # Create user profile if they don't have one
    if user.id not in chat_data['users']:
        chat_data['users'][user.id] = {'xp': 0, 'level': 1, 'last_xp_time': 0, 'tag': 'Member', 'name': user.first_name}
    
    user_stats = chat_data['users'][user.id]
    
    # ANTI-SPAM: Only award XP if 60 seconds have passed since their last message
    if current_time - user_stats['last_xp_time'] > 60:
        user_stats['xp'] += 15
        user_stats['last_xp_time'] = current_time
        
        # Calculate level (Level increases every time XP hits a threshold)
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
        
    # Sort users by XP descending
    sorted_users = sorted(users, key=lambda x: x['xp'], reverse=True)[:10] # Top 10
    
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
    
    # Ensure they exist in DB
    if target_user.id not in chat_data['users']:
        chat_data['users'][target_user.id] = {'xp': 0, 'level': 1, 'last_xp_time': 0, 'tag': 'Member', 'name': target_user.first_name}
        
    chat_data['users'][target_user.id]['tag'] = new_tag
    await update.message.reply_text(f"✅ Set {target_user.first_name}'s tag to: <b>{new_tag}</b>", parse_mode="HTML")

# ==========================================
# 3. EXISTING AUTOMATED LISTENERS
# ==========================================
async def message_handler_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles XP, AFK, Filters, and Tags all at once"""
    # 1. Award XP for text or stickers
    await award_xp(update, context)
    
    if not update.message or not update.message.text: return
    
    text = update.message.text
    lower_text = text.lower()
    user_id = update.message.from_user.id
    data = get_chat_data(update.message.chat_id)

    # 2. AFK Returns
    if user_id in afk_users and data.get('afk_on', True):
        del afk_users[user_id]
        await update.message.reply_text(f"Welcome back {update.message.from_user.first_name}! You are no longer AFK.")

    # 3. Replying to AFK users
    if update.message.reply_to_message and data.get('afk_on', True):
        replied_id = update.message.reply_to_message.from_user.id
        if replied_id in afk_users:
            await update.message.reply_text(f"💤 They are currently AFK: {afk_users[replied_id]}")

    # 4. Tags & Filters
    for tag, reply in data['tags'].items():
        if f"#{tag}" in lower_text: await update.message.reply_text(reply)
    for keyword, reply in data['filters'].items():
        if keyword in lower_text: await update.message.reply_text(reply)

# ==========================================
# RUN THE SECURE BOT
# ==========================================
if __name__ == "__main__":
    # SECURE TOKEN LOADING
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN not found in environment!")
        exit()
        
    app = Application.builder().token(token).build()

    # Register Level Commands
    app.add_handler(CommandHandler("rank", show_rank))
    app.add_handler(CommandHandler(["ranking", "levels"], show_leaderboard))
    app.add_handler(CommandHandler("settag", set_user_tag))

    # Single unified message listener for TEXT AND STICKERS
    app.add_handler(MessageHandler((filters.TEXT | filters.Sticker.ALL) & ~filters.COMMAND, message_handler_hub))

    # (Assume all your other app.add_handler lines for kick, ban, pin, kang, etc. are right here)

    print("Ultra-Secure 24/7 Bot is running...")
    app.run_polling()