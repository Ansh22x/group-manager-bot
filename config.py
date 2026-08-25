import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_OWNER_ID = int(os.getenv("OWNER_ID", "0"))
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", str(BOT_OWNER_ID)))
DATABASE_URL = os.getenv("DATABASE_URL")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

def is_bot_owner(user_id: int) -> bool:
    return user_id != 0 and (user_id == BOT_OWNER_ID or user_id == SUPER_ADMIN_ID)

def is_super_admin(user_id: int) -> bool:
    return user_id != 0 and (user_id == SUPER_ADMIN_ID or user_id == BOT_OWNER_ID)
