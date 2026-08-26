from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from handlers.base_handler import BaseHandler
from services.game_deals_service import GameDealsService
from services.gaming.steam_reviews_service import SteamReviewsService

logger = logging.getLogger(__name__)

class GameDealsHandler(BaseHandler):
    def __init__(self):
        self.deals_service = GameDealsService()
        self.reviews_service = SteamReviewsService()

    def register(self, app: Application):
        app.add_handler(CommandHandler(["game", "steam"], self.game_search_cmd))
        app.add_handler(CommandHandler(["deals", "steamdeals", "gamedeals"], self.deals_cmd))
        app.add_handler(CommandHandler(["newlow", "islow", "atl"], self.new_low_cmd))
        app.add_handler(CommandHandler(["reviews", "steamreviews", "review", "steamreview", "gamereviews"], self.reviews_cmd))
        app.add_handler(CallbackQueryHandler(self.reviews_callback, pattern=r"^rev_"))

    async def game_search_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        query = " ".join(context.args).strip() if context.args else ""
        if not query and update.message.reply_to_message and update.message.reply_to_message.text:
            query = update.message.reply_to_message.text.strip()

        if not query:
            await update.message.reply_text(
                "🎮 <b>Steam & Key Deals Search</b>\n\n"
                "<b>Usage:</b> <code>/game [game name]</code> or <code>/steam [game name]</code>\n"
                "<b>Example:</b> <code>/game Elden Ring</code>\n\n"
                "<i>I will pull live Steam prices, historical all-time lows (SteamDB), reviews, and keyshop deals (GG.deals).</i>",
                parse_mode="HTML"
            )
            return

        chat_id = update.message.chat_id
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            game = await self.deals_service.search_game(query)
            if not game:
                await update.message.reply_text(
                    f"❌ <b>Game Not Found:</b> Could not retrieve details for <code>{query}</code>.\n\n"
                    f"💡 <i>Try searching with the exact title or check spelling.</i>",
                    parse_mode="HTML"
                )
                return

            # Format Discount Tag
            discount_tag = ""
            if game.get("steam_discount") and int(game["steam_discount"]) > 0:
                discount_tag = f"🔥 <b>(-{game['steam_discount']}%)</b> <s>{game.get('steam_initial')}</s>"

            # Format ATL Tag
            atl_tag = ""
            if game.get("is_new_low"):
                atl_tag = "🚨 <b>[NEW ALL-TIME LOW RECORD!]</b>"
            elif game.get("historical_low_date"):
                rel = f" • {game['historical_low_relative']}" if game.get("historical_low_relative") else ""
                atl_tag = f"<i>(Last hit: {game['historical_low_date']}{rel})</i>"

            # Format Review line
            review_parts = []
            if game.get("steam_rating_text"):
                pct = f" ({game['steam_rating_percent']}%)" if game.get("steam_rating_percent") else ""
                review_parts.append(f"👍 <b>Steam:</b> {game['steam_rating_text']}{pct}")
            if game.get("metacritic"):
                review_parts.append(f"Ⓜ️ <b>Metacritic:</b> {game['metacritic']}/100")
            review_str = " | ".join(review_parts) if review_parts else "⭐ <b>Rating:</b> Not yet rated"

            # Format Key Deal
            if game.get("best_key_price") and game.get("best_key_store"):
                key_deal_str = f"<code>{game['best_key_price']}</code> on <b>{game['best_key_store']}</b>"
            else:
                key_deal_str = "<i>Check GG.deals below</i>"

            # Format Live Players
            players_str = f"👥 <b>Active Players:</b> <code>{game['live_players']:,}</code> playing right now\n" if game.get("live_players") is not None else ""

            caption = (
                f"🎮 <b>{game['title']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ <b>Genres:</b> {game.get('genres', 'N/A')}\n"
                f"🏢 <b>Developer:</b> {game.get('developer', 'N/A')}\n"
                f"📅 <b>Release:</b> {game.get('release_date', 'N/A')}\n"
                f"{review_str}\n"
                f"{players_str}\n"
                f"💵 <b>Steam Price:</b> <code>{game.get('steam_price', 'N/A')}</code> {discount_tag}\n"
                f"📉 <b>Historical Low (ATL):</b> <code>{game.get('historical_low', 'N/A')}</code> {atl_tag}\n"
                f"🔑 <b>Best Key Price:</b> {key_deal_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <i>{game.get('description', '')}</i>"
            )

            # Build Inline Keyboard with direct store & deep links
            keyboard = []
            if game.get("best_key_deal_url") and game.get("best_key_store"):
                keyboard.append([
                    InlineKeyboardButton(f"🔑 Buy on {game['best_key_store']} ({game['best_key_price']})", url=game["best_key_deal_url"])
                ])
            
            nav_row = [
                InlineKeyboardButton("🛒 Steam Store", url=game["steam_url"]),
                InlineKeyboardButton("📊 SteamDB", url=game["steamdb_url"]),
                InlineKeyboardButton("🏷️ GG.deals Keys", url=game["ggdeals_url"]),
            ]
            keyboard.append(nav_row)

            if game.get("appid"):
                keyboard.append([
                    InlineKeyboardButton("📝 AI Player Reviews Summary", callback_data=f"rev_{game['appid']}")
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send as photo with fallback
            if game.get("header_image"):
                try:
                    await update.message.reply_photo(
                        photo=game["header_image"],
                        caption=caption[:1024],
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    return
                except Exception as img_err:
                    logger.debug(f"Photo delivery failed ({img_err}), falling back to text message...")

            await update.message.reply_text(
                text=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=False
            )

        except Exception as e:
            logger.error(f"Error in game_search_cmd: {e}", exc_info=True)
            await update.message.reply_text("🌊 *Silence.* An error occurred while fetching game details.")

    async def deals_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        chat_id = update.message.chat_id
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            deals = await self.deals_service.get_top_deals(limit=6)
            if not deals:
                await update.message.reply_text("❌ No active trending deals found at this moment.")
                return

            msg = "🔥 <b>Top Trending Game Deals & Historical Lows</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            keyboard = []

            for idx, d in enumerate(deals, 1):
                rating_str = f" ⭐ {d['steam_rating']}" if d.get("steam_rating") else ""
                msg += (
                    f"<b>{idx}. {d['title']}</b>\n"
                    f"   💰 <b>{d['sale_price']}</b> <s>{d['normal_price']}</s> <b>({d['savings']})</b> on <i>{d['store']}</i>{rating_str}\n"
                    f"   🔗 <a href='{d['steam_url']}'>Steam</a> • <a href='{d['steamdb_url']}'>SteamDB</a> • <a href='{d['ggdeals_url']}'>GG.deals</a>\n\n"
                )

            msg += "💡 <i>Use <code>/game [title]</code> to inspect detailed historical low data for any game!</i>"

            await update.message.reply_text(
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        except Exception as e:
            logger.error(f"Error in deals_cmd: {e}", exc_info=True)
            await update.message.reply_text("❌ Could not load game deals right now.")

    async def new_low_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        query = " ".join(context.args).strip() if context.args else ""
        if not query:
            await update.message.reply_text("Usage: <code>/newlow [game title]</code>\nExample: <code>/newlow Cyberpunk 2077</code>", parse_mode="HTML")
            return

        chat_id = update.message.chat_id
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            game = await self.deals_service.search_game(query)
            if not game:
                await update.message.reply_text(f"❌ Could not find game <code>{query}</code>.", parse_mode="HTML")
                return

            key_str = f"<code>{game.get('best_key_price')}</code> on <b>{game.get('best_key_store')}</b>" if game.get('best_key_price') and game.get('best_key_store') else "<i>Check GG.deals below</i>"

            if game.get("is_new_low"):
                status_text = (
                    f"🚨 <b>YES! {game['title']} is currently at / near its ALL-TIME LOW!</b>\n\n"
                    f"💵 <b>Current Steam Price:</b> <code>{game.get('steam_price')}</code>\n"
                    f"📉 <b>Historical Low (ATL):</b> <code>{game.get('historical_low')}</code>\n"
                    f"🔑 <b>Best Key Price:</b> {key_str}\n\n"
                    f"<i>Grab it now before the sale ends!</i>"
                )
            else:
                rel = f" • {game['historical_low_relative']}" if game.get("historical_low_relative") else ""
                status_text = (
                    f"ℹ️ <b>{game['title']} is NOT at its historical all-time low right now.</b>\n\n"
                    f"💵 <b>Current Steam Price:</b> <code>{game.get('steam_price')}</code> (Discount: {game.get('steam_discount', 0)}%)\n"
                    f"📉 <b>Historical All-Time Low:</b> <code>{game.get('historical_low')}</code> <i>(Last hit: {game.get('historical_low_date', '')}{rel})</i>\n"
                    f"🔑 <b>Cheapest Key Right Now:</b> {key_str}\n\n"
                    f"💡 <i>Tip: Check <a href='{game['ggdeals_url']}'>GG.deals</a> or <a href='{game['steamdb_url']}'>SteamDB</a> to see upcoming sale cycles!</i>"
                )

            keyboard = []
            if game.get("best_key_deal_url") and game.get("best_key_store"):
                keyboard.append([
                    InlineKeyboardButton(f"🔑 Buy on {game['best_key_store']} ({game['best_key_price']})", url=game["best_key_deal_url"])
                ])
            keyboard.append([
                InlineKeyboardButton("🛒 Steam", url=game["steam_url"]),
                InlineKeyboardButton("📊 SteamDB", url=game["steamdb_url"]),
                InlineKeyboardButton("🏷️ GG.deals", url=game["ggdeals_url"]),
            ])
            await update.message.reply_text(
                text=status_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )

        except Exception as e:
            logger.error(f"Error in new_low_cmd: {e}", exc_info=True)
            await update.message.reply_text("❌ Error checking historical low.")

    async def reviews_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        query = " ".join(context.args).strip() if context.args else ""
        if not query and update.message.reply_to_message and update.message.reply_to_message.text:
            query = update.message.reply_to_message.text.strip()

        if not query:
            await update.message.reply_text(
                "🎮 <b>Steam Player Reviews AI Digest</b>\n\n"
                "Extracts and synthesizes authentic player reviews, pros/cons, and optimization status.\n\n"
                "<b>Usage:</b> <code>/reviews [game name or appid]</code>\n"
                "<b>Example:</b> <code>/reviews Elden Ring</code>\n"
                "<b>Example:</b> <code>/reviews 1091500</code>",
                parse_mode="HTML"
            )
            return

        status = await update.message.reply_text("📖 <i>Analyzing Steam player reviews & synthesizing digest...</i>", parse_mode="HTML")

        try:
            review_data = await self.reviews_service.get_reviews_summary(query)
            if not review_data or not review_data.get("summary"):
                await status.edit_text(f"❌ Could not retrieve player reviews for <code>{query}</code>. Please check the spelling or game title.", parse_mode="HTML")
                return

            caption = (
                f"🎮 <b>Steam Reviews Digest:</b> <a href='{review_data['store_url']}'>{review_data['game_title']}</a>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{review_data['summary']}"
            )

            keyboard = [
                [
                    InlineKeyboardButton("🛒 Open Steam Store Page", url=review_data["store_url"])
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if review_data.get("header_image"):
                try:
                    await update.message.reply_photo(
                        photo=review_data["header_image"],
                        caption=caption[:1024],
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    await status.delete()
                    return
                except Exception:
                    pass

            await status.edit_text(caption, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"reviews_cmd error: {e}")
            await status.edit_text("❌ Failed to synthesize Steam player reviews.")

    async def reviews_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer("Fetching & analyzing Steam reviews...")

        appid_str = query.data.replace("rev_", "").strip()
        review_data = await self.reviews_service.get_reviews_summary(appid_str)
        if not review_data or not review_data.get("summary"):
            await query.message.reply_text("❌ Could not retrieve player reviews for this game.", parse_mode="HTML")
            return

        caption = (
            f"🎮 <b>Steam Reviews Digest:</b> <a href='{review_data['store_url']}'>{review_data['game_title']}</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{review_data['summary']}"
        )

        keyboard = [
            [
                InlineKeyboardButton("🛒 Steam Store Page", url=review_data["store_url"])
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if review_data.get("header_image"):
            try:
                await query.message.reply_photo(
                    photo=review_data["header_image"],
                    caption=caption[:1024],
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                return
            except Exception:
                pass

        await query.message.reply_text(caption, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
