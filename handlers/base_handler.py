from abc import ABC, abstractmethod
from telegram.ext import Application

class BaseHandler(ABC):
    @abstractmethod
    def register(self, app: Application):
        """Abstract method to register commands and listeners to the telegram bot Application"""
        pass
