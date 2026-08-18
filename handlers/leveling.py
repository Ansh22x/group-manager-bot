import time
from telegram import Update
from telegram.ext import ContextTypes
from database.models import get_user_stats, update_user_stats, get_top_users

async def award_xp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type == 'private': return

    user = update.message.from_user
    chat_id = update.message.chat_id
    current_time = time.time()
    user_name = user.first_name

    stats = get_user_stats(chat_id, user.id, user_name)
    last_xp_time = stats.get('last_xp_time', 0)

    if current_time - last_xp_time > 60:
        new_xp = stats.get('xp', 0) + 15
        new_level = int((new_xp / 100) ** 0.6) + 1
        
        updates = {
            'xp': new_xp,
            'last_xp_time': current_time,
            'name': user_name
        }

        old_level = stats.get('level', 1)
        if new_level > old_level:
            updates['level'] = new_level
            await update.message.reply_text(
                f"🎉 <b>{user_name}</b> leveled up to <b>Level {new_level}!</b>", 
                parse_mode="HTML"
            )
            
        update_user_stats(chat_id, user.id, **updates)

async def show_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.message.from_user
    chat_id = update.message.chat_id
    
    stats = get_user_stats(chat_id, target_user.id, target_user.first_name)

    rank_card = (
        f"📊 <b>Stats for {target_user.first_name}</b>\n"
        f"🏷 <b>Title:</b> {stats.get('tag', 'Member')}\n"
        f"⭐ <b>Level:</b> {stats.get('level', 1)}\n"
        f"✨ <b>XP:</b> {stats.get('xp', 0)}"
    )
    await update.message.reply_text(rank_card, parse_mode="HTML")

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    top_users = get_top_users(chat_id, 10)

    if not top_users:
        await update.message.reply_text("No one has gained any XP yet!")
        return

    board = "🏆 <b>Group Leaderboard</b> 🏆\n\n"
    for i, u in enumerate(top_users, 1):
        board += f"{i}. <b>{u['name']}</b> (Lvl {u['level']}) - <i>{u['tag']}</i>\n"

    await update.message.reply_text(board, parse_mode="HTML")
