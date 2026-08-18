import random
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from handlers.base_handler import BaseHandler
from database import CaptchaRepository

class CaptchaHandler(BaseHandler):
    def __init__(self):
        self.captcha_repo = CaptchaRepository()

    def register(self, app: Application):
        # Trigger when new members join
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.new_member_join, group=-1))
        # Handle inline button clicks for captcha
        app.add_handler(CallbackQueryHandler(self.handle_captcha_click, pattern=r"^captcha_(correct|incorrect):"))

    async def new_member_join(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        chat_id = update.message.chat_id
        
        for new_member in update.message.new_chat_members:
            if new_member.is_bot:
                continue
            
            user_id = new_member.id
            user_name = new_member.first_name

            # 1. Mute the user immediately
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
            except Exception as e:
                print(f"CaptchaHandler: Could not mute user {user_id}: {e}")
                continue

            # 2. Generate a random addition problem
            num1 = random.randint(1, 9)
            num2 = random.randint(1, 9)
            correct_val = num1 + num2
            
            # Generate 3 incorrect options
            incorrect_options = set()
            while len(incorrect_options) < 3:
                val = random.randint(2, 18)
                if val != correct_val:
                    incorrect_options.add(val)
            
            options = list(incorrect_options) + [correct_val]
            random.shuffle(options)

            # 3. Create inline buttons
            keyboard = []
            row = []
            for opt in options:
                if opt == correct_val:
                    cb_data = f"captcha_correct:{user_id}:{opt}"
                else:
                    cb_data = f"captcha_incorrect:{user_id}:{opt}"
                row.append(InlineKeyboardButton(str(opt), callback_data=cb_data))
            keyboard.append(row)
            reply_markup = InlineKeyboardMarkup(keyboard)

            # 4. Send the captcha message
            captcha_msg = await update.message.reply_text(
                f"🛡️ <b>Security Verification for {new_member.mention_html()}</b>\n\n"
                f"Please solve this within 2 minutes to gain permission to speak:\n"
                f"<code>{num1} + {num2} = ?</code>",
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

            # 5. Store in database
            self.captcha_repo.add_captcha_log(chat_id, user_id, str(correct_val), captcha_msg.message_id)

            # 6. Schedule auto-kick in 120 seconds
            context.job_queue.run_once(
                self.captcha_timeout_callback,
                when=120,
                data={"chat_id": chat_id, "user_id": user_id, "user_name": user_name},
                name=f"captcha_{chat_id}_{user_id}"
            )

    async def handle_captcha_click(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data.split(":")
        action = data[0] # "captcha_correct" or "captcha_incorrect"
        user_id = int(data[1])
        chat_id = query.message.chat_id

        # Make sure only the joined user can solve this captcha
        if query.from_user.id != user_id:
            await query.answer("This verification prompt is not for you! 🗡️", show_alert=True)
            return

        await query.answer()

        if action == "captcha_correct":
            # Success: Unmute user
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_other_messages=True,
                        can_send_polls=True,
                        can_add_web_page_previews=True
                    )
                )
            except Exception as e:
                print(f"CaptchaHandler: Could not unmute user {user_id}: {e}")

            self.captcha_repo.remove_captcha_log(chat_id, user_id)
            await query.message.delete()
            
            # Cancel timeout job
            jobs = context.job_queue.get_jobs_by_name(f"captcha_{chat_id}_{user_id}")
            for job in jobs:
                job.schedule_removal()

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Verification successful. Welcome to the group, {query.from_user.mention_html()}!",
                parse_mode="HTML"
            )
        else:
            # Failure: Kick user
            self.captcha_repo.remove_captcha_log(chat_id, user_id)
            await query.message.delete()

            # Cancel timeout job
            jobs = context.job_queue.get_jobs_by_name(f"captcha_{chat_id}_{user_id}")
            for job in jobs:
                job.schedule_removal()

            try:
                await context.bot.ban_chat_member(chat_id, user_id)
                await context.bot.unban_chat_member(chat_id, user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ {query.from_user.mention_html()} clicked the wrong answer and was kicked.",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"CaptchaHandler: Failed to kick user {user_id}: {e}")

    async def captcha_timeout_callback(self, context: ContextTypes.DEFAULT_TYPE):
        job = context.job
        chat_id = job.data["chat_id"]
        user_id = job.data["user_id"]
        user_name = job.data["user_name"]

        log = self.captcha_repo.get_captcha_log(chat_id, user_id)
        if not log:
            return # User solved captcha or got kicked already

        # Timeout: remove log, delete message, kick user
        self.captcha_repo.remove_captcha_log(chat_id, user_id)
        
        try:
            await context.bot.delete_message(chat_id, log["message_id"])
        except Exception:
            pass

        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.unban_chat_member(chat_id, user_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ <b>Verification Timed Out:</b> <b>{user_name}</b> failed to solve the captcha in time and was kicked."
            )
        except Exception as e:
            print(f"CaptchaHandler: Failed to ban user on timeout: {e}")
