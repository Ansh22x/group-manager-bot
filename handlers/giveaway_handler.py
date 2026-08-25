import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from handlers.base_handler import BaseHandler
from services.giveaway_service import GiveawayService
from config import is_super_admin, is_bot_owner, SUPER_ADMIN_ID

logger = logging.getLogger(__name__)

class GiveawayHandler(BaseHandler):
    def __init__(self):
        self.giveaway_service = GiveawayService()
        self._notify_enabled = True

    def register(self, app: Application):
        # Super-Admin-Only Giveaway Commands
        app.add_handler(CommandHandler(["giveaways", "giveaway", "freebies", "freegames", "gog", "alienware"], self.list_giveaways_cmd))
        app.add_handler(CommandHandler(["giveawaynotify", "notifygiveaways"], self.toggle_notifications_cmd))
        app.add_handler(CallbackQueryHandler(self.giveaway_callback, pattern=r"^gw_"))

        # Schedule automatic background giveaway monitor every 30 minutes
        if app.job_queue:
            app.job_queue.run_repeating(
                self.auto_giveaway_check_job,
                interval=1800,  # 30 minutes
                first=60,       # 1 minute after boot
                name="giveaway_auto_monitor"
            )
            logger.info("GiveawayHandler: Scheduled 30-minute auto-giveaway alert job.")

    def _build_filter_keyboard(self, current_source: str = "all") -> InlineKeyboardMarkup:
        buttons = [
            [
                InlineKeyboardButton(f"{'👉 ' if current_source == 'all' else ''}🌐 All", callback_data="gw_all"),
                InlineKeyboardButton(f"{'👉 ' if current_source == 'alienware' else ''}👽 Alienware", callback_data="gw_alienware"),
                InlineKeyboardButton(f"{'👉 ' if current_source == 'gog' else ''}🎮 GOG", callback_data="gw_gog"),
            ],
            [
                InlineKeyboardButton(f"{'👉 ' if current_source == 'steam' else ''}🚂 Steam 100%", callback_data="gw_steam"),
                InlineKeyboardButton(f"{'👉 ' if current_source == 'epic' else ''}⚡ Epic Games", callback_data="gw_epic"),
            ],
            [
                InlineKeyboardButton(f"{'👉 ' if current_source == 'amd' else ''}🔴 AMD Rewards", callback_data="gw_amd"),
                InlineKeyboardButton(f"{'👉 ' if current_source == 'medal' else ''}🏅 Medal.tv", callback_data="gw_medal"),
            ]
        ]
        return InlineKeyboardMarkup(buttons)

    async def _format_giveaway_message(self, source: str) -> tuple[str, InlineKeyboardMarkup]:
        giveaways = await self.giveaway_service.get_giveaways(source=source, limit=5)
        source_title = source.upper() if source != "all" else "ALL PLATFORMS"

        if not giveaways:
            msg = (
                f"🎁 <b>Active Guarded Giveaways & Keys ({source_title})</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"ℹ️ <i>No active giveaways found for <b>{source_title}</b> right now.</i>\n\n"
                f"💡 <i>Click a platform button below to browse other categories.</i>"
            )
            return msg, self._build_filter_keyboard(source)

        msg = f"🎁 <b>Active Guarded Giveaways & Keys ({source_title})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"

        for idx, g in enumerate(giveaways, 1):
            worth_str = f" <i>(Worth: {g['worth']})</i>" if g.get("worth") and g["worth"] != "N/A" else ""
            msg += (
                f"<b>{idx}. {g['title']}</b>{worth_str}\n"
                f"   🕹️ <b>Platform:</b> <code>{g['platforms']}</code> | <b>Type:</b> {g['type']}\n"
                f"   🔗 <a href='{g['url']}'>Claim Key / Game</a>\n"
            )
            if g.get("instructions"):
                msg += f"   📝 <i>{g['instructions']}</i>\n"
            msg += "\n"

        msg += "💡 <i>Select a category below to switch platform filters:</i>"
        return msg, self._build_filter_keyboard(source)

    async def list_giveaways_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user

        # ── STRICT ACCESS GUARD: SUPER ADMIN ONLY ──
        if not is_super_admin(user.id) and not is_bot_owner(user.id):
            await update.message.reply_text(
                "⛔ <b>Access Denied:</b> This giveaway feed & key drop monitor is strictly guarded for the <b>Super Admin</b>.",
                parse_mode="HTML"
            )
            return

        cmd_name = update.message.text.split()[0].lstrip("/").split("@")[0].lower() if update.message.text else ""
        if cmd_name in ("gog", "alienware"):
            source = cmd_name
        else:
            source = context.args[0].lower() if context.args else "all"

        chat_id = update.message.chat_id
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        valid_sources = ["all", "alienware", "amd", "medal", "steam", "epic", "gog"]
        if source not in valid_sources:
            source = "all"

        msg, keyboard = await self._format_giveaway_message(source)

        await update.message.reply_text(
            text=msg,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    async def giveaway_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query: return

        user = query.from_user
        if not is_super_admin(user.id) and not is_bot_owner(user.id):
            await query.answer("⛔ Access Denied: Super Admin only.", show_alert=True)
            return

        await query.answer()
        source = query.data.replace("gw_", "")

        msg, keyboard = await self._format_giveaway_message(source)

        try:
            await query.edit_message_text(
                text=msg,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.debug(f"Error editing giveaway message: {e}")

    async def toggle_notifications_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user

        if not is_super_admin(user.id) and not is_bot_owner(user.id):
            await update.message.reply_text("⛔ <b>Access Denied.</b> Only the Super Admin can configure giveaway notifications.", parse_mode="HTML")
            return

        if context.args:
            arg = context.args[0].lower()
            if arg in ("on", "enable", "true"):
                self._notify_enabled = True
            elif arg in ("off", "disable", "false"):
                self._notify_enabled = False
        else:
            self._notify_enabled = not self._notify_enabled

        status = "ENABLED 🟢" if self._notify_enabled else "DISABLED 🔴"
        await update.message.reply_text(
            f"🔔 <b>Guarded Giveaway Auto-Alerts:</b> <b>{status}</b>\n\n"
            f"<i>When newly dropped Alienware, AMD, Medal, or Steam freebies appear, I will dispatch private alerts directly to Super Admin ID <code>{SUPER_ADMIN_ID}</code>.</i>",
            parse_mode="HTML"
        )

    async def auto_giveaway_check_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Background job to broadcast new giveaways to Super Admin private DM."""
        if not self._notify_enabled or not SUPER_ADMIN_ID:
            return

        try:
            new_drops = await self.giveaway_service.get_new_giveaways()
            if not new_drops:
                return

            for drop in new_drops[:3]:  # max 3 alerts per cycle to avoid flooding
                worth_str = f" (Value: <b>{drop['worth']}</b>)" if drop.get("worth") and drop["worth"] != "N/A" else ""
                caption = (
                    f"🚨 <b>NEW FREE GAME / KEY GIVEAWAY DROPPED!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎮 <b>{drop['title']}</b>{worth_str}\n"
                    f"🕹️ <b>Platform:</b> <code>{drop['platforms']}</code>\n\n"
                    f"📝 <i>{drop['description'][:250]}</i>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔑 <b>Claim URL:</b> {drop['url']}"
                )
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Claim Giveaway Now", url=drop["url"])]])

                try:
                    if drop.get("image"):
                        await context.bot.send_photo(
                            chat_id=SUPER_ADMIN_ID,
                            photo=drop["image"],
                            caption=caption[:1024],
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=SUPER_ADMIN_ID,
                            text=caption,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                            disable_web_page_preview=False
                        )
                except Exception as send_err:
                    logger.debug(f"Could not deliver private giveaway alert to {SUPER_ADMIN_ID}: {send_err}")

        except Exception as e:
            logger.error(f"Error in auto_giveaway_check_job: {e}")
