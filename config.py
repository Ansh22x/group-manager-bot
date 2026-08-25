import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

def _parse_id_list(var_name: str, fallback: str = "0") -> set[int]:
    raw = os.getenv(var_name, fallback).strip()
    parsed = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            parsed.add(int(part))
    return parsed

OWNER_IDS = _parse_id_list("OWNER_ID", "0")
BOT_OWNER_ID = next(iter(OWNER_IDS)) if OWNER_IDS else 0

SUPER_ADMIN_IDS = _parse_id_list("SUPER_ADMIN_ID", str(BOT_OWNER_ID))
if not SUPER_ADMIN_IDS and OWNER_IDS:
    SUPER_ADMIN_IDS = OWNER_IDS.copy()
SUPER_ADMIN_ID = next(iter(SUPER_ADMIN_IDS)) if SUPER_ADMIN_IDS else BOT_OWNER_ID

DATABASE_URL = os.getenv("DATABASE_URL")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

def is_bot_owner(user_id: int) -> bool:
    return user_id != 0 and (user_id in OWNER_IDS or user_id in SUPER_ADMIN_IDS)

def is_super_admin(user_id: int) -> bool:
    return user_id != 0 and (user_id in SUPER_ADMIN_IDS or user_id in OWNER_IDS)
