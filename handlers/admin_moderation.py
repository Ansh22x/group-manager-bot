import time
import re
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from config import is_bot_owner
from database import WarningRepository, TempMuteRepository

class AdminModeration(BaseHandler):
    def __init__(self):
        self.warning_repo = WarningRepository()
        self.temp_mute_repo = TempMuteRepository()

    def register(self, app: Application):
        app.add_handler(CommandHandler("promote", self.promote_user))
        app.add_handler(CommandHandler("demote", self.demote_user))
        app.add_handler(CommandHandler("kick", self.kick_user))
        app.add_handler(CommandHandler("unban", self.unban_user))
        app.add_handler(CommandHandler("mute", self.mute_user))
        app.add_handler(CommandHandler("unmute", self.unmute_user))
        app.add_handler(CommandHandler("tempmute", self.tempmute_user))
        app.add_handler(CommandHandler("warn", self.warn_user))
        app.add_handler(CommandHandler("dwarn", self.dwarn_user))
        app.add_handler(CommandHandler("pin", self.pin_msg))
        app.add_handler(CommandHandler("unpin", self.unpin_msg))
        app.add_handler(CommandHandler("admin_list", self.admin_list))

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

    async def promote_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            try:
                await context.bot.promote_chat_member(
                    update.message.chat_id, user.id,
                    can_pin_messages=True, can_delete_messages=True,
                    can_invite_users=True, can_restrict_members=True,
                    can_manage_chat=True, can_manage_video_chats=True
                )
                await update.message.reply_text(f"Promoted {user.first_name} to Admin! 🛡️")
            except Exception:
                await update.message.reply_text("I can't promote them. Make sure I have the 'Add New Admins' permission!")

    async def demote_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            try:
                await context.bot.promote_chat_member(
                    update.message.chat_id, user.id,
                    is_anonymous=False, can_manage_chat=False,
                    can_post_messages=False, can_edit_messages=False,
                    can_delete_messages=False, can_manage_video_chats=False,
                    can_restrict_members=False, can_promote_members=False,
                    can_change_info=False, can_invite_users=False,
                    can_pin_messages=False, can_manage_topics=False
                )
                await update.message.reply_text(f"Demoted {user.first_name}. They are now a normal member.")
            except Exception:
                await update.message.reply_text("Failed to demote. I might not have permission, or the user is the group creator.")

    async def kick_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            try:
                await context.bot.ban_chat_member(update.message.chat_id, user.id)
                await context.bot.unban_chat_member(update.message.chat_id, user.id)
                await update.message.reply_text(f"Kicked {user.first_name}.")
            except Exception as e:
                await update.message.reply_text(f"Failed to kick user: {e}")

    async def unban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            try:
                await context.bot.unban_chat_member(update.message.chat_id, user.id, only_if_banned=True)
                await update.message.reply_text(f"Unbanned {user.first_name}.")
            except Exception as e:
                await update.message.reply_text(f"Failed to unban user: {e}")

    async def mute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            try:
                perms = ChatPermissions(can_send_messages=False)
                await context.bot.restrict_chat_member(update.message.chat_id, user.id, permissions=perms)
                await update.message.reply_text(f"Muted {user.first_name}.")
            except Exception as e:
                await update.message.reply_text(f"Failed to mute user: {e}")

    async def unmute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            try:
                perms = ChatPermissions(
                    can_send_messages=True, can_send_audios=True, 
                    can_send_documents=True, can_send_photos=True, 
                    can_send_videos=True, can_send_other_messages=True
                )
                await context.bot.restrict_chat_member(update.message.chat_id, user.id, permissions=perms)
                # Cleanup temp mutes if unmuted manually
                self.temp_mute_repo.remove_temp_mute(update.message.chat_id, user.id)
                jobs = context.job_queue.get_jobs_by_name(f"tempmute_{update.message.chat_id}_{user.id}")
                for job in jobs:
                    job.schedule_removal()
                await update.message.reply_text(f"Unmuted {user.first_name}.")
            except Exception as e:
                await update.message.reply_text(f"Failed to unmute user: {e}")

    async def tempmute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if not update.message.reply_to_message:
            await update.message.reply_text("Please reply to a user's message to temp-mute them!")
            return

        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id

        # Parse duration
        duration_str = context.args[0] if context.args else "10m"
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
            await context.bot.restrict_chat_member(chat_id, user.id, permissions=perms)
            
            # Save to DB
            unmute_at = time.time() + seconds
            self.temp_mute_repo.add_temp_mute(chat_id, user.id, unmute_at)

            # Cancel any existing mute job
            jobs = context.job_queue.get_jobs_by_name(f"tempmute_{chat_id}_{user.id}")
            for job in jobs:
                job.schedule_removal()

            # Schedule unmute
            context.job_queue.run_once(
                self.temp_unmute_callback,
                when=seconds,
                data={"chat_id": chat_id, "user_id": user.id, "user_name": user.first_name},
                name=f"tempmute_{chat_id}_{user.id}"
            )

            await update.message.reply_text(f"🤐 Muted <b>{user.first_name}</b> for <b>{duration_str}</b>.", parse_mode="HTML")
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
            print(f"AdminModeration callback: Could not automatically unmute user {user_id}: {e}")

    def schedule_pending_unmutes(self, app: Application):
        """Scans the database on startup and re-schedules pending unmutes"""
        pending = self.temp_mute_repo.get_all_pending_mutes()
        print(f"AdminModeration: Found {len(pending)} pending temp mutes to schedule.")
        
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
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            chat_id = update.message.chat_id
            
            warn_count = self.warning_repo.add_warning(chat_id, user.id)
            if warn_count >= 3:
                try:
                    await context.bot.ban_chat_member(chat_id, user.id)
                    await update.message.reply_text(f"{user.first_name} reached 3 warnings and was banned.")
                    self.warning_repo.reset_warnings(chat_id, user.id)
                except Exception as e:
                    await update.message.reply_text(f"Banning user failed: {e}")
            else:
                await update.message.reply_text(f"{user.first_name} has been warned. ({warn_count}/3)")

    async def dwarn_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update, context): return
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            chat_id = update.message.chat_id
            
            new_warn_count = self.warning_repo.remove_warning(chat_id, user.id)
            await update.message.reply_text(f"Removed a warning from {user.first_name}. ({new_warn_count}/3)")

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
