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
from handlers.game_deals_handler import GameDealsHandler
from handlers.giveaway_handler import GiveawayHandler
from handlers.games_handler import GamesHandler
from handlers.anime_handler import AnimeHandler
from handlers.utilities_handler import UtilitiesHandler
from handlers.inline_handler import InlineQueryEngine

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
        MediaHandler(),
        GameDealsHandler(),
        GiveawayHandler(),
        GamesHandler(),
        AnimeHandler(),
        UtilitiesHandler(),
        InlineQueryEngine()
    ]
    
    for handler in handlers:
        handler.register(app)
