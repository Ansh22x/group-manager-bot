from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from config import is_bot_owner, BOT_OWNER_ID
from database.models import (
    get_chat_settings, update_chat_settings,
    add_warning, remove_warning, reset_warnings, get_warnings,
    add_tag, get_tags, add_filter, update_user_stats, get_db_connection, release_db_connection
)

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or update.message.chat.type == 'private': 
        return False
    if is_bot_owner(update.message.from_user.id):
        return True
    try:
        chat_member = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
        return chat_member.status in ['administrator', 'creator']
    except Exception:
        return False

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
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

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
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

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.ban_chat_member(update.message.chat_id, user.id)
            await context.bot.unban_chat_member(update.message.chat_id, user.id)
            await update.message.reply_text(f"Kicked {user.first_name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to kick user: {e}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.unban_chat_member(update.message.chat_id, user.id, only_if_banned=True)
            await update.message.reply_text(f"Unbanned {user.first_name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to unban user: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            perms = ChatPermissions(can_send_messages=False)
            await context.bot.restrict_chat_member(update.message.chat_id, user.id, permissions=perms)
            await update.message.reply_text(f"Muted {user.first_name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to mute user: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            perms = ChatPermissions(
                can_send_messages=True, can_send_audios=True, 
                can_send_documents=True, can_send_photos=True, 
                can_send_videos=True, can_send_other_messages=True
            )
            await context.bot.restrict_chat_member(update.message.chat_id, user.id, permissions=perms)
            await update.message.reply_text(f"Unmuted {user.first_name}.")
        except Exception as e:
            await update.message.reply_text(f"Failed to unmute user: {e}")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        
        warn_count = add_warning(chat_id, user.id)
        if warn_count >= 3:
            try:
                await context.bot.ban_chat_member(chat_id, user.id)
                await update.message.reply_text(f"{user.first_name} reached 3 warnings and was banned.")
                reset_warnings(chat_id, user.id)
            except Exception as e:
                await update.message.reply_text(f"Banning user failed: {e}")
        else:
            await update.message.reply_text(f"{user.first_name} has been warned. ({warn_count}/3)")

async def dwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        
        new_warn_count = remove_warning(chat_id, user.id)
        await update.message.reply_text(f"Removed a warning from {user.first_name}. ({new_warn_count}/3)")

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        try:
            await context.bot.pin_chat_message(update.message.chat_id, update.message.reply_to_message.message_id)
        except Exception:
            pass

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        try:
            await context.bot.unpin_chat_message(update.message.chat_id, update.message.reply_to_message.message_id)
        except Exception:
            pass

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private': return
    admins = await context.bot.get_chat_administrators(update.message.chat_id)
    admin_names = [f"- {admin.user.first_name}" for admin in admins]
    await update.message.reply_text("👮‍♂️ <b>Group Admins:</b>\n" + "\n".join(admin_names), parse_mode="HTML")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    new_rules = " ".join(context.args)
    if new_rules:
        update_chat_settings(update.message.chat_id, rules=new_rules)
        await update.message.reply_text("Rules updated successfully!")

async def toggle_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    chat_id = update.message.chat_id
    settings = get_chat_settings(chat_id)
    new_welcome_on = not settings.get('welcome_on', True)
    update_chat_settings(chat_id, welcome_on=new_welcome_on)
    status = "ON" if new_welcome_on else "OFF"
    await update.message.reply_text(f"Welcome messages are now {status}.")

async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    new_welcome = " ".join(context.args)
    if new_welcome:
        update_chat_settings(update.message.chat_id, welcome_msg=new_welcome)
        await update.message.reply_text("Welcome message updated! (Use {name} to insert the user's name).")

async def add_filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if len(context.args) >= 2:
        keyword = context.args[0].lower()
        reply_text = " ".join(context.args[1:])
        add_filter(update.message.chat_id, keyword, reply_text)
        await update.message.reply_text(f"Filter added! When someone says '{keyword}', I will reply.")

async def toggle_afkstat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    chat_id = update.message.chat_id
    settings = get_chat_settings(chat_id)
    new_afk_on = not settings.get('afk_on', True)
    update_chat_settings(chat_id, afk_on=new_afk_on)
    status = "ON" if new_afk_on else "OFF"
    await update.message.reply_text(f"AFK monitoring is now {status} for this group.")

async def add_tag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if len(context.args) >= 2:
        tag = context.args[0].lower().replace('#', '')
        reply_text = " ".join(context.args[1:])
        add_tag(update.message.chat_id, tag, reply_text)
        await update.message.reply_text(f"Tag added! Anyone can now type #{tag} to see it.")

async def edit_tag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if len(context.args) >= 2:
        tag = context.args[0].lower().replace('#', '')
        reply_text = " ".join(context.args[1:])
        chat_id = update.message.chat_id
        tags_dict = get_tags(chat_id)
        if tag in tags_dict:
            add_tag(chat_id, tag, reply_text)
            await update.message.reply_text(f"Tag #{tag} updated!")
        else:
            await update.message.reply_text(f"Tag #{tag} doesn't exist. Use /addtag to create it.")

async def set_user_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to set their tag!")
        return

    new_tag = " ".join(context.args)
    if not new_tag:
        await update.message.reply_text("Please provide a tag! Example: /settag VIP Member")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    
    update_user_stats(chat_id, target_user.id, tag=new_tag)
    await update.message.reply_text(f"✅ Set {target_user.first_name}'s tag to: <b>{new_tag}</b>", parse_mode="HTML")

# --- OWNER COMMANDS ---
async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_bot_owner(user_id):
        await update.message.reply_text("⛔ <b>Access Denied:</b> This command is reserved exclusively for the Bot Owner.", parse_mode="HTML")
        return

    conn = get_db_connection()
    total_groups = 0
    total_afk = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chats;")
            total_groups = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM afk_users;")
            total_afk = cur.fetchone()[0]
    except Exception as e:
        print(f"Error getting botstats: {e}")
    finally:
        release_db_connection(conn)

    stats_msg = (
        "⚙️ <b>Bot Owner Dashboard</b>\n\n"
        f"📊 <b>Active Managed Groups:</b> {total_groups}\n"
        f"💤 <b>Total AFK Users:</b> {total_afk}\n"
        f"🛡️ <b>Owner ID:</b> <code>{BOT_OWNER_ID}</code>\n"
        f"🟢 <b>Status:</b> Online & Polling 24/7"
    )
    await update.message.reply_text(stats_msg, parse_mode="HTML")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_owner(update.message.from_user.id):
        await update.message.reply_text("⛔ <b>Access Denied.</b>", parse_mode="HTML")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("Usage: <code>/broadcast Your message here</code>", parse_mode="HTML")
        return

    conn = get_db_connection()
    chat_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM chats;")
            chat_ids = [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error fetching chats for broadcast: {e}")
    finally:
        release_db_connection(conn)

    sent_count = 0
    for chat_id in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"📢 <b>Global Announcement:</b>\n\n{message}", 
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception:
            continue

    await update.message.reply_text(f"✅ Announcement sent to <b>{sent_count}</b> group(s).", parse_mode="HTML")
