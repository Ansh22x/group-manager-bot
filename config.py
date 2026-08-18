import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

def is_bot_owner(user_id: int) -> bool:
    return user_id == BOT_OWNER_ID
