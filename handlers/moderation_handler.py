import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters, ChatMemberHandler
)

from handlers.base_handler import BaseHandler
from config import is_bot_owner, OWNER_IDS, SUPER_ADMIN_IDS
from database import ModerationRepository, ChatRepository

logger = logging.getLogger(__name__)


def _parse_target(text: str) -> tuple[int | None, str]:
    """Extract a user target from '@username', a raw numeric ID, or a
    t.me link. Returns (user_id, reason) — user_id is None when only a
    username was given (username-only bans need a prior sighting)."""
    parts = text.split(None, 1)
    if not parts:
        return None, ""
    token = parts[0].strip().lstrip("@")
    reason = parts[1].strip() if len(parts) > 1 else ""
    if token.isdigit():
        return int(token), reason
    # t.me / telegram.me link with numeric id embedded (e.g. tg://user?id=123)
    import re
    m = re.search(r"id=(\d+)", token)
    if m:
        return int(m.group(1)), reason
    return None, reason


async def _resolve_display_name(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    """Best-effort display name for a user the bot may have never met."""
    try:
        # Works in some cases if the bot shares any chat with the user
        info = await context.bot.get_chat(user_id)
        name = getattr(info, "full_name", None) or getattr(info, "first_name", None)
        if name:
            return name
    except Exception:
        pass
    return f"User {user_id}"


def _is_privileged(user_id: int) -> bool:
    """Bot Owner OR Developer (super admin)."""
    return is_bot_owner(user_id)


class ModerationHandler(BaseHandler):
    """Global ban system + bot group registry.

    Powers:
    - /gban <id|reply|@user> [reason] — globally ban anyone (owner/dev). Works
      even when the target has never been in any chat with the bot: the ID is
      stored and enforced everywhere the bot is admin.
    - /gunban <id|reply> — lift a global ban.
    - /gbanlist — paginated global ban list.
    - /banhere <id> [reason] — ban an ID from the CURRENT group right now
      (requires bot admin in this group), even if the user already left.
    - /banall <id> [reason] — ban an ID from EVERY registered group where the
      bot is admin (used by /gban automatically too).
    - /groups — list the groups the bot is in + admin status (owner/dev).
    """

    def __init__(self):
        self.mod_repo = ModerationRepository()
        self.chat_repo = ChatRepository()

    def register(self, app: Application):
        app.add_handler(CommandHandler(["gban", "globalban"], self.gban_cmd))
        # GroupHandlerValue tracks bots being added/removed; ChatMemberHandler
        # with MY_CHAT_MEMBER catches rank changes (bot promoted to admin)
        app.add_handler(ChatMemberHandler(self.chat_membership_tracker, ChatMemberHandler.MY_CHAT_MEMBER))
        app.add_handler(CommandHandler(["gunban", "unglobalban"], self.gunban_cmd))
        app.add_handler(CommandHandler(["gbanlist", "bans"], self.gbanlist_cmd))
        app.add_handler(CommandHandler("banhere", self.banhere_cmd))
        app.add_handler(CommandHandler("banall", self.banall_cmd))
        app.add_handler(CommandHandler(["groups", "grouplist", "chats"], self.groups_cmd))
        app.add_handler(CallbackQueryHandler(self.gbanlist_page, pattern=r"^gbanlist_page_"))
        app.add_handler(MessageHandler((filters.GroupType.GROUPS | filters.SUPERGROUP) & ~filters.COMMAND, self.enforcement_hook))

    # ------------------------------------------------------------------
    # Enforcement helpers
    # ------------------------------------------------------------------
    async def _ban_in_chat(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                           user_id: int) -> tuple[bool, str]:
        """Attempt an actual Telegram ban in one chat. Works with any numeric
        user ID — Telegram allows banning users not currently in the chat."""
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            return True, "banned"
        except Exception as e:
            msg = str(e)
            if "not enough rights" in msg.lower() or "admin" in msg.lower():
                return False, "bot lacks admin/ban rights in this group"
            if "user is an administrator" in msg.lower():
                return False, "target is an admin there"
            return False, msg[:120]

    async def _enforce_everywhere(self, context: ContextTypes.DEFAULT_TYPE,
                                  user_id: int) -> list[dict]:
        """Ban user_id in every registered chat where the bot is admin.
        Returns per-chat results for reporting."""
        results = []
        chats = self.mod_repo.list_bot_chats(only_admin=True)
        for chat in chats:
            ok, detail = await self._ban_in_chat(context, chat["chat_id"], user_id)
            results.append({"chat_id": chat["chat_id"], "title": chat["title"], "ok": ok, "detail": detail})
        return results

    async def enforcement_hook(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Silent global-ban enforcement on every incoming message: if a
        globally-banned user shows up anywhere, ban & delete immediately."""
        msg = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        if not msg or not user or not chat or chat.type == "private":
            return

        # Heartbeat keeps the chat registry self-healing
        try:
            self.mod_repo.mark_chat_seen(chat.id)
        except Exception:
            pass

        try:
            if self.mod_repo.is_globally_banned(user.id):
                ok, detail = await self._ban_in_chat(context, chat.id, user.id)
                try:
                    await msg.delete()
                except Exception:
                    pass
                logger.info(f"Global-ban enforcement: user {user.id} in chat {chat.id} ({detail})")
        except Exception as e:
            logger.debug(f"gban enforcement error: {e}")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def gban_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not _is_privileged(update.message.from_user.id):
            await update.message.reply_text("⛔ Only the Bot Owner and Developers can use global bans.")
            return

        user_id, reason = None, ""
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            user_id = update.message.reply_to_message.from_user.id
            reason = " ".join(context.args).strip()
            target_name = update.message.reply_to_message.from_user.first_name
            username = update.message.reply_to_message.from_user.username or ""
        elif context.args:
            user_id, reason = _parse_target(update.message.text)
            target_name = None
            username = ""
        if user_id is None:
            await update.message.reply_text(
                "🌊 <b>Usage:</b>\n"
                "• <code>/gban 123456789 spamming</code> — ban by numeric ID (works even if the user was never in this group)\n"
                "• Reply to a user with <code>/gban spamming</code>",
                parse_mode="HTML",
            )
            return

        if is_bot_owner(user_id):
            await update.message.reply_text("⛔ You cannot globally ban a bot owner/developer.")
            return

        if not reason:
            reason = "No reason provided."

        display = target_name or await _resolve_display_name(context, user_id)
        self.mod_repo.add_global_ban(user_id, display, username, reason, update.message.from_user.id)

        status = await update.message.reply_text(
            f"⚔️ <b>Global ban issued.</b>\n"
            f"👤 <b>{display}</b> (<code>{user_id}</code>)\n"
            f"📄 {reason}\n\n⏳ Sweeping every group where I am admin…",
            parse_mode="HTML",
        )

        results = await self._enforce_everywhere(context, user_id)
        ok_chats = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]

        report = (
            f"✅ <b>Global Ban Active</b>\n\n"
            f"👤 <b>{display}</b> (<code>{user_id}</code>)\n"
            f"📄 {reason}\n\n"
            f"🔨 <b>Enforced in {len(ok_chats)} group(s)</b>"
        )
        if failed:
            report += f"\n⚠️ {len(failed)} group(s) skipped (no rights):"
            for r in failed[:5]:
                report += f"\n  • {r['title'] or r['chat_id']}: {r['detail']}"
        report += "\n\n<i>They will be auto-banned on sight in any chat, including groups they join later.</i>"

        if len(report) > 4000:
            report = report[:4000] + "…"
        try:
            await status.edit_text(report, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(report, parse_mode="HTML")

    async def gunban_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not _is_privileged(update.message.from_user.id):
            await update.message.reply_text("⛔ Only the Bot Owner and Developers can lift global bans.")
            return

        user_id = None
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            user_id = update.message.reply_to_message.from_user.id
        elif context.args:
            user_id, _ = _parse_target(update.message.text)
        if user_id is None:
            await update.message.reply_text("🌊 Usage: <code>/gunban 123456789</code> or reply to a user.", parse_mode="HTML")
            return

        if self.mod_repo.remove_global_ban(user_id):
            await update.message.reply_text(
                f"✅ Global ban lifted for <code>{user_id}</code>. They can rejoin groups normally.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(f"ℹ️ <code>{user_id}</code> was not on the global ban list.", parse_mode="HTML")

    async def gbanlist_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not _is_privileged(update.message.from_user.id):
            await update.message.reply_text("⛔ Only the Bot Owner and Developers can view the ban list.")
            return
        await self._send_gbanlist_page(update.message.chat_id, 0, reply_to=None, context=context)

    async def _send_gbanlist_page(self, chat_id: int, page: int, reply_to, context):
        bans = self.mod_repo.list_global_bans(limit=200)
        if not bans:
            text = "🕊️ The global ban list is empty."
            await context.bot.send_message(chat_id, text)
            return

        per_page = 15
        pages = max(1, (len(bans) + per_page - 1) // per_page)
        page = max(0, min(page, pages - 1))
        chunk = bans[page * per_page:(page + 1) * per_page]

        lines = [f"⛔ <b>Global Bans</b> — page {page + 1}/{pages} ({len(bans)} total)\n"]
        for b in chunk:
            uname = f" @{b['username']}" if b.get("username") else ""
            lines.append(
                f"• <b>{b['full_name'] or 'Unknown'}</b>{uname} — <code>{b['user_id']}</code>\n"
                f"  <i>{b['reason']}</i>"
            )
        keyboard = None
        if pages > 1:
            row = []
            if page > 0:
                row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"gbanlist_page_{page - 1}"))
            if page < pages - 1:
                row.append(InlineKeyboardButton("Next ▶️", callback_data=f"gbanlist_page_{page + 1}"))
            keyboard = InlineKeyboardMarkup([row])

        if reply_to is not None:
            await reply_to.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
        else:
            await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=keyboard)

    async def gbanlist_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not _is_privileged(query.from_user.id):
            await query.answer("⛔ Not authorized.", show_alert=True)
            return
        await query.answer()
        page = int(query.data.replace("gbanlist_page_", ""))
        await self._send_gbanlist_page(query.message.chat_id, page, reply_to=None, context=context)
        try:
            await query.message.delete()
        except Exception:
            pass

    async def banhere_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ban a numeric ID from the CURRENT group — even if they never joined
        or already left. Requires the bot to be admin here; usable by group
        admins AND bot owner/devs."""
        if not update.message:
            return
        chat = update.effective_chat
        if chat.type == "private":
            await update.message.reply_text("This command only works inside a group.")
            return
        caller = update.message.from_user
        if not (_is_privileged(caller.id) or await self._is_chat_admin(update, context, caller.id)):
            await update.message.reply_text("⛔ Group admins, developers, or the bot owner only.")
            return

        user_id, reason = (None, "")
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            user_id = update.message.reply_to_message.from_user.id
            reason = " ".join(context.args).strip()
        elif context.args:
            user_id, reason = _parse_target(update.message.text)
        if user_id is None:
            await update.message.reply_text(
                "🌊 Usage: <code>/banhere 123456789 reason</code> — bans that ID from this group (works even if they aren't in it).",
                parse_mode="HTML",
            )
            return

        ok, detail = await self._ban_in_chat(context, chat.id, user_id)
        if ok:
            await update.message.reply_text(
                f"🔨 <b>Banned from this group.</b>\n👤 <code>{user_id}</code>{(' — ' + reason) if reason else ''}",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(f"❌ Failed: {detail}", parse_mode="HTML")

    async def banall_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Owner/dev: ban an ID from EVERY registered group where the bot is admin."""
        if not update.message:
            return
        if not _is_privileged(update.message.from_user.id):
            await update.message.reply_text("⛔ Only the Bot Owner and Developers can use /banall.")
            return

        user_id, reason = (None, "")
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            user_id = update.message.reply_to_message.from_user.id
            reason = " ".join(context.args).strip()
        elif context.args:
            user_id, reason = _parse_target(update.message.text)
        if user_id is None:
            await update.message.reply_text("🌊 Usage: <code>/banall 123456789 reason</code>", parse_mode="HTML")
            return

        results = await self._enforce_everywhere(context, user_id)
        ok = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]
        text = f"🔨 <b>Banned <code>{user_id}</code> in {len(ok)} group(s)</code></b>"
        if reason:
            text += f"\n📄 {reason}"
        if failed:
            text += f"\n⚠️ Skipped {len(failed)} (no rights)."
        await update.message.reply_text(text, parse_mode="HTML")

    async def groups_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Owner/dev: see every group the bot is in, with admin status."""
        if not update.message:
            return
        if not _is_privileged(update.message.from_user.id):
            await update.message.reply_text("⛔ Only the Bot Owner and Developers can view the group list.")
            return

        chats = self.mod_repo.list_bot_chats()
        groups = [c for c in chats if c["chat_type"] in ("group", "supergroup")]
        if not groups:
            await update.message.reply_text("ℹ️ I haven't seen any groups yet. Send a message in your groups and run this again.")
            return

        lines = [f"🏘️ <b>Groups I'm in ({len(groups)})</b>\n"]
        for c in groups[:30]:
            badge = "🛡️ admin" if c["bot_is_admin"] else "👤 member"
            stale = "" if c.get("last_seen") else " ⚠️"
            lines.append(f"• <b>{c['title'] or 'Unnamed'}</b> — <code>{c['chat_id']}</code> ({badge}){stale}")
        if len(groups) > 30:
            lines.append(f"\n…and {len(groups) - 30} more.")
        lines.append("\n<i>Registry is self-healing: refreshed on every message & membership change.</i>")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def chat_membership_tracker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Self-healing registry: Telegram tells us when the bot is added,
        removed, or (un)promoted in any chat. No polling needed."""
        try:
            cmu = update.my_chat_member
            chat = cmu.chat
            if chat.type == "private":
                return
            is_admin = cmu.new_chat_member.status in ("administrator", "creator")
            still_member = cmu.new_chat_member.status not in ("left", "kicked")
            if still_member:
                member_count = 0
                try:
                    member_count = await context.bot.get_chat_member_count(chat.id)
                except Exception:
                    pass
                self.mod_repo.upsert_bot_chat(chat.id, chat.title or "", chat.type, is_admin, member_count)
            else:
                self.mod_repo.remove_bot_chat(chat.id)
            logger.info(f"Chat registry update: {chat.id} '{chat.title}' admin={is_admin} member={still_member}")
        except Exception as e:
            logger.debug(f"chat_membership_tracker error: {e}")

    async def registry_watchdog(self, context: ContextTypes.DEFAULT_TYPE):
        """Periodic self-healing job (runs every 30 min via JobQueue):
        1. Verifies registered groups are still real by fetching metadata
           (drops dead entries, refreshes admin status & member counts).
        2. Re-sweeps the global ban list across all groups — catches anyone
           banned while the bot was offline or lacked rights at the time.
        """
        try:
            chats = self.mod_repo.list_bot_chats()
            alive_ids = []
            for chat in chats:
                try:
                    info = await context.bot.get_chat(chat["chat_id"])
                    member_count = 0
                    try:
                        member_count = await context.bot.get_chat_member_count(chat["chat_id"])
                    except Exception:
                        pass
                    # bot's own admin status:
                    bot_is_admin = False
                    try:
                        me = await context.bot.get_me()
                        member = await context.bot.get_chat_member(chat["chat_id"], me.id)
                        bot_is_admin = member.status in ("administrator", "creator")
                    except Exception:
                        pass
                    self.mod_repo.upsert_bot_chat(
                        chat["chat_id"], getattr(info, "title", "") or chat["title"],
                        chat["chat_type"], bot_is_admin, member_count
                    )
                    alive_ids.append(chat["chat_id"])
                except Exception:
                    # Bot can no longer see this chat — it was kicked/left/deleted
                    self.mod_repo.remove_bot_chat(chat["chat_id"])
                    logger.info(f"Watchdog: removed dead chat {chat['chat_id']} from registry")

            # Re-enforce global bans everywhere the bot is currently admin
            banned_ids = [b["user_id"] for b in self.mod_repo.list_global_bans(limit=500)]
            if banned_ids and alive_ids:
                admin_chats = [c for c in self.mod_repo.list_bot_chats(only_admin=True)]
                for chat in admin_chats:
                    for uid in banned_ids:
                        try:
                            await context.bot.ban_chat_member(chat_id=chat["chat_id"], user_id=uid)
                        except Exception:
                            continue
                logger.info(f"Watchdog: re-enforced {len(banned_ids)} global bans across {len(admin_chats)} groups")
        except Exception as e:
            logger.error(f"registry_watchdog error: {e}", exc_info=True)

    async def _is_chat_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
            return member.status in ("administrator", "creator")
        except Exception:
            return False
