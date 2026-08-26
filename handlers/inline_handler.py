import logging
import hashlib
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, InlineQueryHandler, ContextTypes
from handlers.base_handler import BaseHandler
from services.anime_service import AnimeService
from services.game_deals_service import GameDealsService

logger = logging.getLogger(__name__)

class InlineQueryEngine(BaseHandler):
    def __init__(self):
        self.anime_service = AnimeService()
        self.game_service = GameDealsService()

    def register(self, app: Application):
        app.add_handler(InlineQueryHandler(self.inline_query_handler))

    async def inline_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes real-time inline queries from any chat."""
        query = update.inline_query.query.strip()
        results = []

        if not query:
            # 1. Default Quick Cards when query is empty
            quote = self.anime_service.get_random_quote()
            results.append(
                InlineQueryResultArticle(
                    id=hashlib.md5("quote_default".encode()).hexdigest(),
                    title="🌊 Demon Slayer Quote of the Day",
                    description=f'"{quote["quote"][:60]}..." — {quote["character"]}',
                    thumb_url="https://raw.githubusercontent.com/GuruMachanica/Giyu-Bot/main/docs/assets/banner.png",
                    input_message_content=InputTextMessageContent(
                        f"💬 <b>Demon Slayer Quote:</b>\n\n"
                        f"<i>\"{quote['quote']}\"</i>\n\n"
                        f"— <b>{quote['character']}</b> ({quote['anime']})",
                        parse_mode="HTML"
                    )
                )
            )

            results.append(
                InlineQueryResultArticle(
                    id=hashlib.md5("help_card".encode()).hexdigest(),
                    title="⚔️ Giyu-Bot Features & Commands",
                    description="Tap to send the full Giyu-Bot feature overview.",
                    thumb_url="https://raw.githubusercontent.com/GuruMachanica/Giyu-Bot/main/docs/assets/banner.png",
                    input_message_content=InputTextMessageContent(
                        "🌊 <b>Giyu-Bot — Advanced Group Management & AI Assistant</b>\n\n"
                        "• 🎙️ <b>Neural Voice TTS:</b> <code>/tts [text]</code>, <code>/tr [lang] [text]</code>\n"
                        "• 🌸 <b>Anime & Manga:</b> <code>/anime [title]</code>, <code>/manga [title]</code>\n"
                        "• 🎮 <b>Steam Deals in INR:</b> <code>/deals</code>, <code>/steam [title]</code>\n"
                        "• 🎵 <b>Shazam Identifier:</b> Reply with <code>/shazam</code>\n"
                        "• 📰 <b>AI Web Summarizer:</b> <code>/summarize [url]</code>\n"
                        "• 📥 <b>Universal Downloader:</b> <code>/dl [url]</code>\n"
                        "• 🎰 <b>Daily Streaks & Mini-Games:</b> <code>/daily</code>, <code>/gamble</code>, <code>/duel</code>",
                        parse_mode="HTML"
                    )
                )
            )

            await update.inline_query.answer(results, cache_time=60, is_personal=True)
            return

        # 2. Quote Query
        if query.lower() in ["quote", "quotes", "kds", "slayer"]:
            quote = self.anime_service.get_random_quote()
            results.append(
                InlineQueryResultArticle(
                    id=hashlib.md5(f"quote_{hash(quote['quote'])}".encode()).hexdigest(),
                    title=f"Quote by {quote['character']}",
                    description=quote["quote"][:80],
                    input_message_content=InputTextMessageContent(
                        f"💬 <i>\"{quote['quote']}\"</i>\n\n— <b>{quote['character']}</b>",
                        parse_mode="HTML"
                    )
                )
            )

        # 3. Anime Search Query
        try:
            anime = await self.anime_service.search_anime(query)
            if anime:
                msg_content = (
                    f"🌸 <b>{anime['title_romaji']}</b>\n"
                    f"<i>{anime.get('title_english') or ''}</i>\n\n"
                    f"📊 <b>Score:</b> {anime['score']}/100 • <b>Episodes:</b> {anime['episodes']}\n"
                    f"🏷️ <b>Genres:</b> {', '.join(anime['genres'][:3])}\n"
                    f"🏢 <b>Studio:</b> {anime['studio']}\n\n"
                    f"📖 <b>Synopsis:</b>\n{anime['description'][:400]}...\n\n"
                    f"🔗 <a href='{anime['site_url']}'>View on AniList</a>"
                )
                results.append(
                    InlineQueryResultArticle(
                        id=hashlib.md5(f"anime_{anime['title_romaji']}".encode()).hexdigest(),
                        title=f"🌸 {anime['title_romaji']}",
                        description=f"Score: {anime['score']}% • Episodes: {anime['episodes']} • {anime['studio']}",
                        thumb_url=anime.get("cover_image"),
                        input_message_content=InputTextMessageContent(
                            msg_content,
                            parse_mode="HTML"
                        )
                    )
                )
        except Exception as e:
            logger.warning(f"Inline anime query error: {e}")

        # 4. Steam Game Deals Query
        try:
            game = await self.game_service.search_game_with_fallbacks(query)
            if game:
                deal_status = f"🚨 {game['discount_percent']}% OFF!" if game.get("discount_percent", 0) > 0 else "Full Price"
                game_msg = (
                    f"🎮 <b>{game['title']}</b>\n\n"
                    f"💰 <b>Price (INR):</b> {game['price_inr']}\n"
                    f"🏷️ <b>Price (USD):</b> {game['price_usd']}\n"
                    f"🔥 <b>Status:</b> {deal_status}\n"
                    f"⭐ <b>Steam Reviews:</b> {game.get('steam_rating_text', 'N/A')}\n"
                    f"📉 <b>SteamDB All-Time Low:</b> {game.get('atl_price_usd', 'N/A')}\n\n"
                    f"🔗 <a href='{game['steam_url']}'>Open on Steam Store</a>"
                )
                results.append(
                    InlineQueryResultArticle(
                        id=hashlib.md5(f"game_{game['title']}".encode()).hexdigest(),
                        title=f"🎮 {game['title']} ({game['price_inr']})",
                        description=f"Steam Price: {game['price_inr']} ({deal_status})",
                        thumb_url=game.get("header_image"),
                        input_message_content=InputTextMessageContent(
                            game_msg,
                            parse_mode="HTML"
                        )
                    )
                )
        except Exception as e:
            logger.warning(f"Inline game query error: {e}")

        await update.inline_query.answer(results, cache_time=120, is_personal=True)
