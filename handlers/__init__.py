from telegram.ext import Application, CommandHandler, MessageHandler, filters

from handlers.public import (
    start_cmd, show_rules, set_afk, show_owner, help_menu, list_commands_cmd, kang_sticker
)
from handlers.admin import (
    promote_user, demote_user, kick_user, unban_user, mute_user, unmute_user,
    warn_user, dwarn_user, pin_msg, unpin_msg, admin_list, set_rules,
    toggle_welcome, set_welcome, add_filter_cmd, toggle_afkstat, add_tag_cmd,
    edit_tag_cmd, set_user_tag, bot_stats, broadcast_message
)
from handlers.leveling import show_rank, show_leaderboard
from handlers.ai_chat import message_handler_hub, ask_cmd, welcome_new_member

def register_handlers(app: Application):
    # Public Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_menu))
    app.add_handler(CommandHandler("afk", set_afk))
    app.add_handler(CommandHandler("rules", show_rules))
    app.add_handler(CommandHandler("owner", show_owner))
    app.add_handler(CommandHandler("list_commands", list_commands_cmd))
    app.add_handler(CommandHandler("kang", kang_sticker))
    
    # Leveling Commands
    app.add_handler(CommandHandler("rank", show_rank))
    app.add_handler(CommandHandler(["ranking", "levels"], show_leaderboard))
    
    # Admin Commands
    app.add_handler(CommandHandler("promote", promote_user))
    app.add_handler(CommandHandler("demote", demote_user))
    app.add_handler(CommandHandler("kick", kick_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("dwarn", dwarn_user))
    app.add_handler(CommandHandler("pin", pin_msg))
    app.add_handler(CommandHandler("unpin", unpin_msg))
    app.add_handler(CommandHandler("admin_list", admin_list))
    app.add_handler(CommandHandler("setrules", set_rules))
    app.add_handler(CommandHandler("welcome", toggle_welcome))
    app.add_handler(CommandHandler("setwelcome", set_welcome))
    app.add_handler(CommandHandler("filter", add_filter_cmd))
    app.add_handler(CommandHandler("afkstat", toggle_afkstat))
    app.add_handler(CommandHandler("addtag", add_tag_cmd))
    app.add_handler(CommandHandler("edit_tag", edit_tag_cmd))
    app.add_handler(CommandHandler("settag", set_user_tag))
    
    # AI Chat Agent Commands
    app.add_handler(CommandHandler("ask", ask_cmd))
    
    # Bot Owner Commands
    app.add_handler(CommandHandler("botstats", bot_stats))
    app.add_handler(CommandHandler("broadcast", broadcast_message))

    # Event Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # Central Hub for message texts & media (triggers AFK, Filters, Tags, and AI Agent)
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.Sticker.ALL | filters.ANIMATION | filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND, 
        message_handler_hub
    ))
