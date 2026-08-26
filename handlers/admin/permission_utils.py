import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import is_bot_owner

logger = logging.getLogger(__name__)

async def check_admin_privileges(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if message sender is group admin, creator, or bot owner."""
    if not update.message or update.message.chat.type == "private":
        return False
    if is_bot_owner(update.message.from_user.id):
        return True
    try:
        chat_member = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
        return chat_member.status in ["administrator", "creator"]
    except Exception:
        return False

async def resolve_target_and_args(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Resolve target user from reply-to, @username arg, or numeric ID arg.
    Returns (User | None, user_id | None, remaining_args | list).
    """
    if update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        return u, u.id, context.args
        
    if context.args:
        arg = context.args[0]
        remaining = context.args[1:]
        if arg.startswith("@"):
            username = arg[1:]
            try:
                chat_member = await context.bot.get_chat_member(update.message.chat_id, username)
                return chat_member.user, chat_member.user.id, remaining
            except Exception:
                try:
                    chat = await context.bot.get_chat(f"@{username}")
                    return None, chat.id, remaining
                except Exception:
                    pass
        elif arg.lstrip("-").isdigit():
            user_id = int(arg)
            try:
                chat_member = await context.bot.get_chat_member(update.message.chat_id, user_id)
                return chat_member.user, user_id, remaining
            except Exception:
                return None, user_id, remaining
    return None, None, []

def parse_time_duration(time_str: str) -> int | None:
    """Parses duration string like '10m', '2h', '1d' into seconds."""
    match = re.match(r"^(\d+)([smhd])$", time_str.strip().lower())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * multipliers[unit]
