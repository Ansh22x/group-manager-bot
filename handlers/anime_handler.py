import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from services.anime_service import AnimeService
from services.trace_anime_service import TraceAnimeService

logger = logging.getLogger(__name__)

class AnimeHandler(BaseHandler):
    def __init__(self):
        self.anime_service = AnimeService()
        self.trace_service = TraceAnimeService()

    def register(self, app: Application):
        app.add_handler(CommandHandler(["anime", "ani"], self.anime_cmd))
        app.add_handler(CommandHandler(["manga", "manhwa"], self.manga_cmd))
        app.add_handler(CommandHandler(["quote", "animequote"], self.quote_cmd))
        app.add_handler(CommandHandler(["sauce", "whatanime", "findanime"], self.sauce_cmd))

    async def anime_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        query = " ".join(context.args).strip()
        if not query:
            await update.message.reply_text(
                "🌸 <b>Anime Lookup:</b>\n\n"
                "Please provide an anime name.\n"
                "• <i>Example:</i> <code>/anime Demon Slayer</code>\n"
                "• <i>Example:</i> <code>/anime Attack on Titan</code>",
                parse_mode="HTML"
            )
            return

        status = await update.message.reply_text("🌸 <i>Searching anime database...</i>", parse_mode="HTML")
        anime = await self.anime_service.search_anime(query)
        if not anime:
            await status.edit_text(f"❌ Could not find any anime matching '<b>{query}</b>'.", parse_mode="HTML")
            return

        caption = (
            f"🌸 <b>{anime['title']}</b>\n"
            f"<i>{anime['native']} • {anime['romaji']}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐ <b>Rating:</b> {anime['score']}\n"
            f"📺 <b>Episodes:</b> {anime['episodes']} ({anime['duration']})\n"
            f"📅 <b>Year:</b> {anime['year']} | <b>Status:</b> {anime['status']}\n"
            f"🏢 <b>Studio:</b> {anime['studio']}\n"
            f"🎭 <b>Genres:</b> {anime['genres']}\n\n"
            f"📖 <b>Synopsis:</b>\n"
            f"{anime['synopsis']}\n"
        )

        keyboard = []
        if anime.get("url"):
            keyboard.append([InlineKeyboardButton("🌐 AniList Page", url=anime["url"])])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        try:
            await status.delete()
            if anime.get("cover"):
                await update.message.reply_photo(photo=anime["cover"], caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending anime card: {e}")
            await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML")

    async def manga_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        query = " ".join(context.args).strip()
        if not query:
            await update.message.reply_text(
                "📖 <b>Manga Lookup:</b>\n\n"
                "Please provide a manga or manhwa name.\n"
                "• <i>Example:</i> <code>/manga Solo Leveling</code>\n"
                "• <i>Example:</i> <code>/manga Berserk</code>",
                parse_mode="HTML"
            )
            return

        status = await update.message.reply_text("📖 <i>Searching manga database...</i>", parse_mode="HTML")
        manga = await self.anime_service.search_manga(query)
        if not manga:
            await status.edit_text(f"❌ Could not find any manga matching '<b>{query}</b>'.", parse_mode="HTML")
            return

        caption = (
            f"📖 <b>{manga['title']}</b>\n"
            f"<i>{manga['native']} • {manga['romaji']}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐ <b>Rating:</b> {manga['score']}\n"
            f"📚 <b>Chapters:</b> {manga['chapters']} | <b>Volumes:</b> {manga['volumes']}\n"
            f"📅 <b>Year:</b> {manga['year']} | <b>Status:</b> {manga['status']}\n"
            f"✍️ <b>Author:</b> {manga['author']}\n"
            f"🎭 <b>Genres:</b> {manga['genres']}\n\n"
            f"📖 <b>Synopsis:</b>\n"
            f"{manga['synopsis']}\n"
        )

        keyboard = []
        if manga.get("url"):
            keyboard.append([InlineKeyboardButton("🌐 AniList Page", url=manga["url"])])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        try:
            await status.delete()
            if manga.get("cover"):
                await update.message.reply_photo(photo=manga["cover"], caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending manga card: {e}")
            await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML")

    async def quote_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        q = self.anime_service.get_random_quote()
        text = (
            f"⚔️ <i>\"{q['quote']}\"</i>\n\n"
            f"— <b>{q['character']}</b> ({q['anime']})"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    async def sauce_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        replied = update.message.reply_to_message

        target_msg = replied if replied else update.message
        photo_target = target_msg.photo or target_msg.sticker or target_msg.animation or target_msg.document

        if not photo_target:
            await update.message.reply_text(
                "🔍 <b>Reverse Anime Screenshot Search</b>\n\n"
                "Reply to any <b>anime screenshot, photo, meme, or sticker</b> with <code>/sauce</code> to identify the exact anime, episode, and timestamp!\n\n"
                "<b>Example:</b> Reply to an anime image with <code>/sauce</code>",
                parse_mode="HTML"
            )
            return

        status = await update.message.reply_text("🔍 <i>Scanning frame against trace.moe anime database...</i>", parse_mode="HTML")

        try:
            # Extract highest resolution file id
            file_id = None
            if target_msg.photo:
                file_id = target_msg.photo[-1].file_id
            elif target_msg.sticker:
                file_id = target_msg.sticker.file_id
            elif target_msg.animation:
                file_id = target_msg.animation.file_id
            elif target_msg.document and target_msg.document.mime_type and "image" in target_msg.document.mime_type:
                file_id = target_msg.document.file_id

            if not file_id:
                await status.edit_text("❌ Please reply to a valid image, screenshot, or sticker.", parse_mode="HTML")
                return

            file = await context.bot.get_file(file_id)
            img_bytes = await file.download_as_bytearray()

            sauce = await self.trace_service.search_anime_by_image(bytes(img_bytes))
            if not sauce:
                await status.edit_text("❌ <b>No matching anime found.</b>\n\nEnsure the screenshot is a clean, uncropped anime scene frame.", parse_mode="HTML")
                return

            caption = (
                f"🌸 <b>{sauce['title_romaji']}</b>\n"
                f"<i>{sauce.get('title_native') or ''}</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎬 <b>Episode:</b> {sauce['episode']}\n"
                f"⏱️ <b>Timestamp:</b> <code>{sauce['timestamp']}</code>\n"
                f"🎯 <b>Similarity:</b> <b>{sauce['similarity']}%</b>\n"
            )
            if sauce.get("is_adult"):
                caption += "🔞 <b>Content Rating:</b> 18+ (NSFW)\n"

            keyboard = []
            if sauce.get("anilist_url"):
                keyboard.append([InlineKeyboardButton("🌐 AniList Page", url=sauce["anilist_url"])])
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            # If video preview is available, send video
            if sauce.get("video_preview"):
                try:
                    await update.message.reply_video(
                        video=sauce["video_preview"],
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                    await status.delete()
                    return
                except Exception:
                    pass

            if sauce.get("image_preview"):
                await update.message.reply_photo(
                    photo=sauce["image_preview"],
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                await status.delete()
            else:
                await status.edit_text(caption, reply_markup=reply_markup, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Sauce command error: {e}")
            await status.edit_text("❌ Failed to analyze image screenshot.")
