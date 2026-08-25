import logging
from telegram import Update, User
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[User | None, int | None, str]:
    """
    Resolves the target user from a Telegram update:
    1. If the message is a reply to another user -> returns that user.
    2. If an argument is provided (numeric user ID) -> queries get_chat_member.
    3. If no target specified -> returns None.
    
    Returns: (User object if found, user_id, user_display_name)
    """
    if not update.message:
        return None, None, ""

    chat_id = update.message.chat_id

    # 1. Replying to a user
    if update.message.reply_to_message:
        replied = update.message.reply_to_message
        if replied.from_user:
            user = replied.from_user
            return user, user.id, user.first_name

    # 2. Argument provided
    if context.args:
        arg = context.args[0].strip()
        if arg.isdigit() or (arg.startswith("-") and arg[1:].isdigit()):
            uid = int(arg)
            try:
                member = await context.bot.get_chat_member(chat_id, uid)
                if member and member.user:
                    return member.user, member.user.id, member.user.first_name
            except Exception:
                return None, uid, f"User {uid}"

    return None, None, ""


async def is_user_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """Checks whether the given user is an administrator or creator of the chat."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception as e:
        logger.debug(f"is_user_admin check failed for user {user_id} in {chat_id}: {e}")
        return False
