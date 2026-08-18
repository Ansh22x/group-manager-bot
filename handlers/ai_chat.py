from telegram import Update
from telegram.ext import ContextTypes
from database.models import (
    get_chat_settings, get_afk_users, remove_user_afk,
    get_tags, get_filters, get_user_stats
)
from handlers.leveling import award_xp
from services.ai_agent import ask_hinata
from config import is_bot_owner

async def message_handler_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    
    # Award XP for levels first
    await award_xp(update, context)
    
    if not update.message.text: return

    message_text = update.message.text
    chat_id = update.message.chat_id
    user = update.message.from_user
    bot_username = context.bot.username
    bot_id = context.bot.id

    # Get group settings
    settings = get_chat_settings(chat_id)
    afk_on = settings.get('afk_on', True)

    # 1. AFK Welcome Back check
    afk_users = get_afk_users()
    if user.id in afk_users and afk_on:
        remove_user_afk(user.id)
        await update.message.reply_text(f"Welcome back {user.first_name}-kun! You are no longer AFK. 🌸")

    # 2. AFK Reply Warning check
    if update.message.reply_to_message and afk_on:
        replied_user = update.message.reply_to_message.from_user
        if replied_user.id in afk_users:
            reason = afk_users[replied_user.id]
            await update.message.reply_text(f"💤 {replied_user.first_name}-san is currently AFK: {reason}")

    # 3. Custom Hashtag Tags
    lower_text = message_text.lower()
    tags = get_tags(chat_id)
    for tag, reply in tags.items():
        if f"#{tag}" in lower_text:
            await update.message.reply_text(reply)
            return

    # 4. Custom Keyword Filters
    filters = get_filters(chat_id)
    for keyword, reply in filters.items():
        if keyword in lower_text:
            await update.message.reply_text(reply)
            return

    # 5. AI Hinata Chat Trigger Check
    is_private = update.message.chat.type == 'private'
    is_mention = f"@{bot_username}" in message_text
    is_reply_to_bot = (
        update.message.reply_to_message is not None 
        and update.message.reply_to_message.from_user.id == bot_id
    )

    if is_private or is_mention or is_reply_to_bot:
        # Show typing activity to make it feel natural
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Clean prompt (remove bot handle if present)
        prompt = message_text.replace(f"@{bot_username}", "").strip()
        if not prompt:
            prompt = "Hello!"

        # Fetch user's title tag
        user_stats = get_user_stats(chat_id, user.id, user.first_name)
        user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

        # Ask Mistral Agent
        response = await ask_hinata(chat_id, user.id, user.first_name, user_tag, prompt)
        
        # Robust Markdown parsing check
        try:
            await update.message.reply_text(response, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(response)

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explicitly ask Hinata using the /ask command"""
    if not update.message or not update.message.text: return

    chat_id = update.message.chat_id
    user = update.message.from_user
    
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("a-ano... please provide a question! Example: `/ask How does this group work?` 🌸", parse_mode="Markdown")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Fetch user's title tag
    user_stats = get_user_stats(chat_id, user.id, user.first_name)
    user_tag = "Bot Owner" if is_bot_owner(user.id) else user_stats.get('tag', 'Member')

    response = await ask_hinata(chat_id, user.id, user.first_name, user_tag, prompt)
    
    try:
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(response)

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    settings = get_chat_settings(chat_id)
    if not settings.get('welcome_on', True): return
    
    for new_member in update.message.new_chat_members:
        if new_member.id != context.bot.id:
            greeting = settings.get('welcome_msg', "Welcome to the group, {name}!").replace("{name}", new_member.first_name)
            await update.message.reply_text(greeting)
