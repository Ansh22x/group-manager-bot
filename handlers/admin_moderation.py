import time
import re
import logging
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import is_bot_owner
from database import WarningRepository, TempMuteRepository

logger = logging.getLogger(__name__)

class AdminModeration(BaseHandler):
    def __init__(self):
        self.warning_repo = WarningRepository()
        self.temp_mute_repo = TempMuteRepository()
        self._report_cooldowns: dict = {}  # user_id → last report timestamp
        self._REPORT_COOLDOWN_SECS = 300   # 5 minutes between reports per user

    def register(self, app: Application):
        app.add_handler(CommandHandler("promote", self.promote_user))
        app.add_handler(CommandHandler("demote", self.demote_user))
        app.add_handler(CommandHandler("kick", self.kick_user))
        app.add_handler(CommandHandler("ban", self.ban_user))
        app.add_handler(CommandHandler("unban", self.unban_user))
        app.add_handler(CommandHandler("mute", self.mute_user))
        app.add_handler(CommandHandler("unmute", self.unmute_user))
        app.add_handler(CommandHandler("tempmute", self.tempmute_user))
        app.add_handler(CommandHandler("warn", self.warn_user))
        app.add_handler(CommandHandler("dwarn", self.dwarn_user))
        app.add_handler(CommandHandler("pin", self.pin_msg))
        app.add_handler(CommandHandler("unpin", self.unpin_msg))
        app.add_handler(CommandHandler("admin_list", self.admin_list))
        app.add_handler(CommandHandler("report", self.report_cmd))

    async def is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if not update.message or update.message.chat.type == 'private': 
            return False
        if is_bot_owner(update.message.from_user.id):
            return True
        try:
            chat_member = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
            return chat_member.status in ['administrator', 'creator']
        except Exception:
            return False

    async def _resolve_target_and_args(self, update, context):
        """
        Resolve target user from reply-to, @username arg, or numeric ID arg.
        Returns (User | None, user_id | None, remaining_args | list).
        """
        # Reply-to takes priority
        if update.message.reply_to_message:
            u = update.message.reply_to_message.from_user
            return u, u.id, context.args
            
        if context.args:
            arg = context.args[0]
            remaining = context.args[1:]
            if arg.startswith('@'):
                username = arg[1:]
                try:
                    chat_member = await context.bot.get_chat_member(update.message.chat_id, username)
                    return chat_member.user, chat_member.user.id, remaining
                except Exception:
                    try:
                        # Try resolving via get_chat
                        chat = await context.bot.get_chat(f"@{username}")
                        return None, chat.id, remaining
                    except Exception:
                        pass
            elif arg.lstrip('-').isdigit():
                user_id = int(arg)
                try:
                    chat_member = await context.bot.get_chat_member(update.message.chat_id, user_id)
                    return chat_member.user, user_id, remaining
                except Exception:
                    return None, user_id, remaining
        return None, None, []

    async def promote_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /promote @username or /promote USER_ID")
            return
        name = user.first_name if user else f"User {user_id}"
        try:
            await context.bot.promote_chat_member(
                update.message.chat_id, user_id,
                can_pin_messages=True, can_delete_messages=True,
                can_invite_users=True, can_restrict_members=True,
                can_manage_chat=True, can_manage_video_chats=True
            )
            await update.message.reply_text(f"🛡️ Promoted {name} to Admin!")
        except Exception:
            await update.message.reply_text("I can't promote them. Make sure I have the 'Add New Admins' permission!")

    async def demote_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /demote @username or /demote USER_ID")
            return
        name = user.first_name if user else f"User {user_id}"
        try:
            await context.bot.promote_chat_member(
                update.message.chat_id, user_id,
                is_anonymous=False, can_manage_chat=False,
                can_post_messages=False, can_edit_messages=False,
                can_delete_messages=False, can_manage_video_chats=False,
                can_restrict_members=False, can_promote_members=False,
                can_change_info=False, can_invite_users=False,
                can_pin_messages=False, can_manage_topics=False
            )
            await update.message.reply_text(f"Demoted {name}. They are now a normal member.")
        except Exception:
            await update.message.reply_text("Failed to demote. I might not have permission, or the user is the group creator.")

    async def kick_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /kick @username or /kick USER_ID")
            return
        name = user.first_name if user else f"User {user_id}"
        try:
            await context.bot.ban_chat_member(update.message.chat_id, user_id)
            await context.bot.unban_chat_member(update.message.chat_id, user_id)
            await update.message.reply_text(f"👢 Kicked {name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to kick: {e}")

    async def ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /ban @username or /ban USER_ID")
            return
        name = user.first_name if user else f"User {user_id}"
        try:
            await context.bot.ban_chat_member(update.message.chat_id, user_id)
            await update.message.reply_text(f"🚫 Banned {name} forever.")
        except Exception as e:
            await update.message.reply_text(f"Failed to ban: {e}")

    async def unban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /unban @username or /unban USER_ID")
            return
        name = user.first_name if user else f"User {user_id}"
        try:
            await context.bot.unban_chat_member(update.message.chat_id, user_id, only_if_banned=True)
            await update.message.reply_text(f"✅ Unbanned {name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to unban: {e}")

    async def mute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /mute @username or /mute USER_ID")
            return
        name = user.first_name if user else f"User {user_id}"
        try:
            perms = ChatPermissions(can_send_messages=False)
            await context.bot.restrict_chat_member(update.message.chat_id, user_id, permissions=perms)
            await update.message.reply_text(f"🤐 Muted {name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to mute: {e}")

    async def unmute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /unmute @username or /unmute USER_ID")
            return
        name = user.first_name if user else f"User {user_id}"
        try:
            perms = ChatPermissions(
                can_send_messages=True, can_send_audios=True, 
                can_send_documents=True, can_send_photos=True, 
                can_send_videos=True, can_send_other_messages=True
            )
            await context.bot.restrict_chat_member(update.message.chat_id, user_id, permissions=perms)
            # Cleanup temp mutes if unmuted manually
            self.temp_mute_repo.remove_temp_mute(update.message.chat_id, user_id)
            if context.job_queue:
                jobs = context.job_queue.get_jobs_by_name(f"tempmute_{update.message.chat_id}_{user_id}")
                for job in jobs:
                    job.schedule_removal()
            await update.message.reply_text(f"🔊 Unmuted {name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to unmute: {e}")

    async def tempmute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, remaining_args = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /tempmute @username [duration] or /tempmute USER_ID [duration]")
            return

        chat_id = update.message.chat_id
        name = user.first_name if user else f"User {user_id}"

        # Parse duration
        duration_str = remaining_args[0] if remaining_args else "10m"
        match = re.match(r"^(\d+)([smhd])$", duration_str.lower())
        if not match:
            await update.message.reply_text("Invalid duration format! Use e.g. <code>30s</code>, <code>10m</code>, <code>2h</code>, <code>1d</code>.", parse_mode="HTML")
            return

        amount = int(match.group(1))
        unit = match.group(2)

        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = amount * multipliers[unit]

        try:
            # Mute user
            perms = ChatPermissions(can_send_messages=False)
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=perms)
            
            # Save to DB
            unmute_at = time.time() + seconds
            self.temp_mute_repo.add_temp_mute(chat_id, user_id, unmute_at)

            if context.job_queue:
                # Cancel any existing mute job for this user
                jobs = context.job_queue.get_jobs_by_name(f"tempmute_{chat_id}_{user_id}")
                for job in jobs:
                    job.schedule_removal()

                # Schedule auto-unmute
                context.job_queue.run_once(
                    self.temp_unmute_callback,
                    when=seconds,
                    data={"chat_id": chat_id, "user_id": user_id, "user_name": name},
                    name=f"tempmute_{chat_id}_{user_id}"
                )

            await update.message.reply_text(f"🤐 Muted <b>{name}</b> for <b>{duration_str}</b>.", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"Failed to execute temp-mute: {e}")

    async def temp_unmute_callback(self, context: ContextTypes.DEFAULT_TYPE):
        job = context.job
        chat_id = job.data["chat_id"]
        user_id = job.data["user_id"]
        user_name = job.data["user_name"]

        try:
            perms = ChatPermissions(
                can_send_messages=True, can_send_audios=True, 
                can_send_documents=True, can_send_photos=True, 
                can_send_videos=True, can_send_other_messages=True
            )
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=perms)
            self.temp_mute_repo.remove_temp_mute(chat_id, user_id)
            await context.bot.send_message(chat_id, f"🔊 <b>{user_name}</b> has been unmuted (temp-mute expired).", parse_mode="HTML")
        except Exception as e:
            logger.error(f"AdminModeration callback: Could not automatically unmute user {user_id}: {e}")

    def schedule_pending_unmutes(self, app: Application):
        """Scans the database on startup and re-schedules pending unmutes"""
        pending = self.temp_mute_repo.get_all_pending_mutes()
        logger.info(f"AdminModeration: Found {len(pending)} pending temp mutes to schedule.")
        
        for item in pending:
            chat_id = item["chat_id"]
            user_id = item["user_id"]
            unmute_at = item["unmute_at"]
            
            user_name = "Member"
            try:
                from database import UserRepository
                user_stats = UserRepository().get_user_stats(chat_id, user_id)
                user_name = user_stats.get('name', 'Member')
            except Exception:
                pass
                
            time_left = unmute_at - time.time()
            if time_left <= 0:
                app.job_queue.run_once(
                    self.temp_unmute_callback,
                    when=1,
                    data={"chat_id": chat_id, "user_id": user_id, "user_name": user_name}
                )
            else:
                app.job_queue.run_once(
                    self.temp_unmute_callback,
                    when=time_left,
                    data={"chat_id": chat_id, "user_id": user_id, "user_name": user_name},
                    name=f"tempmute_{chat_id}_{user_id}"
                )

    async def warn_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /warn @username or /warn USER_ID")
            return
        
        chat_id = update.message.chat_id
        name = user.first_name if user else f"User {user_id}"
        
        warn_count = self.warning_repo.add_warning(chat_id, user_id)
        if warn_count >= 3:
            try:
                await context.bot.ban_chat_member(chat_id, user_id)
                await update.message.reply_text(f"⚠️ {name} reached 3 warnings and was banned.")
                self.warning_repo.reset_warnings(chat_id, user_id)
            except Exception as e:
                await update.message.reply_text(f"Banning user failed: {e}")
        else:
            await update.message.reply_text(f"⚠️ {name} has been warned. ({warn_count}/3)")

    async def dwarn_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        user, user_id, _ = await self._resolve_target_and_args(update, context)
        if not user_id:
            await update.message.reply_text("Reply to a user or use /dwarn @username or /dwarn USER_ID")
            return
        
        chat_id = update.message.chat_id
        name = user.first_name if user else f"User {user_id}"
        
        new_warn_count = self.warning_repo.remove_warning(chat_id, user_id)
        await update.message.reply_text(f"Removed a warning from {name}. ({new_warn_count}/3)")

    async def pin_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(update.message.chat_id, update.message.reply_to_message.message_id)
            except Exception:
                pass

    async def unpin_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            try:
                await context.bot.unpin_chat_message(update.message.chat_id, update.message.reply_to_message.message_id)
            except Exception:
                pass

    async def admin_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.chat.type == 'private': return
        admins = await context.bot.get_chat_administrators(update.message.chat_id)
        admin_names = [f"- {admin.user.first_name}" for admin in admins]
        await update.message.reply_text("👮‍♂️ <b>Group Admins:</b>\n" + "\n".join(admin_names), parse_mode="HTML")

    async def report_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /report [reason] — Reply to any message to report it to all group admins.
        Rate-limited to 1 report per user per 5 minutes.
        Admins receive a DM with full context; falls back to in-group mention if DMs are blocked.
        """
        if not update.message:
            return
        if update.message.chat.type == 'private':
            await update.message.reply_text("⚠️ Reports can only be made inside a group chat.")
            return
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "↩️ <b>Reply to the message you want to report</b>, then use <code>/report [reason]</code>.",
                parse_mode="HTML"
            )
            return

        reporter = update.message.from_user
        reported_msg = update.message.reply_to_message
        reported_user = reported_msg.from_user
        chat = update.message.chat
        chat_id = chat.id
        reason = " ".join(context.args).strip() if context.args else "No reason provided."

        # Don't allow reporting bot messages
        if reported_user and reported_user.is_bot:
            await update.message.reply_text("🤖 You can't report bot messages.")
            return

        # Don't allow self-reports
        if reported_user and reported_user.id == reporter.id:
            await update.message.reply_text("🤦 You can't report yourself.")
            return

        # Rate-limit: 1 report per user per 5 minutes
        now = time.time()
        last = self._report_cooldowns.get(reporter.id, 0)
        if now - last < self._REPORT_COOLDOWN_SECS:
            remaining = int(self._REPORT_COOLDOWN_SECS - (now - last))
            await update.message.reply_text(
                f"⏳ You can send another report in <b>{remaining}s</b>.",
                parse_mode="HTML"
            )
            return
        self._report_cooldowns[reporter.id] = now

        # Build message excerpt (truncated to 300 chars)
        msg_text = reported_msg.text or reported_msg.caption or "[non-text content]"
        excerpt = msg_text[:300] + ("…" if len(msg_text) > 300 else "")

        # Build jump link if possible
        jump_link = ""
        if chat.username:
            jump_link = f"\n🔗 <a href='https://t.me/{chat.username}/{reported_msg.message_id}'>Jump to message</a>"
        elif str(chat_id).startswith("-100"):
            # Supergroup numeric ID
            short_id = str(chat_id)[4:]
            jump_link = f"\n🔗 <a href='https://t.me/c/{short_id}/{reported_msg.message_id}'>Jump to message</a>"

        reported_name = reported_user.first_name if reported_user else "Unknown"
        reported_mention = f"<a href='tg://user?id={reported_user.id}'>{reported_name}</a>" if reported_user else reported_name
        reporter_mention = f"<a href='tg://user?id={reporter.id}'>{reporter.first_name}</a>"

        admin_notification = (
            f"🚨 <b>Report Received</b>\n\n"
            f"👤 <b>Reporter:</b> {reporter_mention} (<code>{reporter.id}</code>)\n"
            f"🎯 <b>Reported:</b> {reported_mention} (<code>{reported_user.id if reported_user else '?'}</code>)\n"
            f"💬 <b>Group:</b> {chat.title}\n"
            f"📝 <b>Reason:</b> {reason}\n\n"
            f"<b>Reported message:</b>\n<blockquote>{excerpt}</blockquote>"
            f"{jump_link}"
        )

        # Notify all admins
        admins = await context.bot.get_chat_administrators(chat_id)
        notified = 0
        for admin in admins:
            if admin.user.is_bot:
                continue
            try:
                await context.bot.send_message(
                    chat_id=admin.user.id,
                    text=admin_notification,
                    parse_mode="HTML"
                )
                notified += 1
            except Exception:
                pass  # Admin has DMs closed — handled below

        # If no admin could be DMed, fall back to in-group mention
        if notified == 0:
            human_admins = [a for a in admins if not a.user.is_bot]
            admin_tags = " ".join(
                f"<a href='tg://user?id={a.user.id}'>{a.user.first_name}</a>"
                for a in human_admins[:5]
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚨 <b>Report flagged for admins:</b> {admin_tags}\n\n{admin_notification}",
                parse_mode="HTML"
            )

        # Confirm to reporter (delete the /report command message for cleanliness)
        try:
            await update.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ {reporter_mention}, your report has been sent to the admins.",
            parse_mode="HTML"
        )
        logger.info(
            f"Report: {reporter.first_name}({reporter.id}) reported {reported_name} in {chat.title}({chat_id}). "
            f"Notified {notified} admin(s). Reason: {reason}"
        )
