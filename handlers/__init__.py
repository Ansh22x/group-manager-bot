from telegram.ext import Application
from handlers.public_commands import PublicCommands
from handlers.admin_moderation import AdminModeration
from handlers.admin_settings import AdminSettings
from handlers.owner_commands import OwnerCommands
from handlers.leveling_handler import LevelingHandler
from handlers.ai_chat_handler import AIChatHandler
from handlers.captcha_handler import CaptchaHandler
from handlers.economy_handler import EconomyHandler
from handlers.media_handler import MediaHandler
from telegram.ext import Application, CommandHandler
from handlers.ai_chat import ask_command

def register_handlers(app: Application):
    app.add_handler(CommandHandler("ask", ask_command)

def register_handlers(app: Application):
    """Instantiates and registers all BaseHandler subclasses to the bot application"""
    handlers = [
        PublicCommands(),
        AdminModeration(),
        AdminSettings(),
        OwnerCommands(),
        LevelingHandler(),
        AIChatHandler(),
        CaptchaHandler(),
        EconomyHandler(),
        MediaHandler()
    ]
    
    for handler in handlers:
        handler.register(app)
