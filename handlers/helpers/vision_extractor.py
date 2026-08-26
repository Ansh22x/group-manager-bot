import base64
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def extract_multimodal_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, str, str]:
    """
    Extracts base64 encoded image and MIME type from message or replied message.
    Returns (base64_image, image_mime, clean_prompt_fallback).
    """
    base64_image = None
    image_mime = "image/jpeg"
    fallback_prompt = ""

    replied = update.message.reply_to_message if update.message else None
    
    try:
        if replied and replied.photo:
            photo = replied.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            photo_bytes = await file.download_as_bytearray()
            base64_image = base64.b64encode(photo_bytes).decode("utf-8")
            image_mime = "image/jpeg"
            fallback_prompt = replied.caption or "Analyze and describe this image."

        elif replied and replied.sticker and not replied.sticker.is_animated and not replied.sticker.is_video:
            file = await context.bot.get_file(replied.sticker.file_id)
            sticker_bytes = await file.download_as_bytearray()
            base64_image = base64.b64encode(sticker_bytes).decode("utf-8")
            image_mime = "image/webp"
            emoji = replied.sticker.emoji or ""
            fallback_prompt = f"React to this sticker ({emoji}) naturally."

        elif update.message and update.message.photo:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            photo_bytes = await file.download_as_bytearray()
            base64_image = base64.b64encode(photo_bytes).decode("utf-8")
            image_mime = "image/jpeg"
            fallback_prompt = update.message.caption or "Analyze and describe this image."

    except Exception as e:
        logger.warning(f"extract_multimodal_media error: {e}")

    return base64_image, image_mime, fallback_prompt
