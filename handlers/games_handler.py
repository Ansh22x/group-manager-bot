import random
import asyncio
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from handlers.base_handler import BaseHandler
from database import EconomyRepository, DailyStreakRepository, UserRepository
from handlers.leveling_handler import LevelingHandler

logger = logging.getLogger(__name__)

TRIVIA_QUESTIONS = [
    {
        "question": "What is the Eleventh Form of Water Breathing created exclusively by Giyu Tomioka?",
        "options": ["Constant Flux", "Dead Calm (Lull)", "Water Wheel", "Drop Ripple Thrust"],
        "correct": 1,
        "category": "Demon Slayer"
    },
    {
        "question": "What kind of flower repels demons and is toxic to them?",
        "options": ["Blue Spider Lily", "Wisteria", "Nightshade", "Sakura"],
        "correct": 1,
        "category": "Demon Slayer"
    },
    {
        "question": "Which Upper Moon demon uses the Blood Demon Art: Destructive Death?",
        "options": ["Doma", "Akaza", "Kokushibo", "Gyokko"],
        "correct": 1,
        "category": "Demon Slayer"
    },
    {
        "question": "What color did Tanjiro Kamado's Nichirin Blade turn when he first drew it?",
        "options": ["Crimson Red", "Jet Black", "Deep Blue", "Bright Yellow"],
        "correct": 1,
        "category": "Demon Slayer"
    },
    {
        "question": "In gaming, what was the first commercial home video game console released in 1972?",
        "options": ["Atari 2600", "Magnavox Odyssey", "Nintendo NES", "Coleco Telstar"],
        "correct": 1,
        "category": "Gaming"
    },
    {
        "question": "Which game won Game of the Year at The Game Awards 2022?",
        "options": ["God of War Ragnarok", "Elden Ring", "Horizon Forbidden West", "Stray"],
        "correct": 1,
        "category": "Gaming"
    },
    {
        "question": "In Minecraft, what ore is required to upgrade Diamond gear to the highest tier?",
        "options": ["Nether Quartz", "Netherite", "Obsidian", "Amethyst"],
        "correct": 1,
        "category": "Gaming"
    },
    {
        "question": "Who created the anime masterpiece 'Spirited Away' and Studio Ghibli?",
        "options": ["Makoto Shinkai", "Hayao Miyazaki", "Satoshi Kon", "Mamoru Hosoda"],
        "correct": 1,
        "category": "Anime"
    }
]

class GamesHandler(BaseHandler):
    def __init__(self):
        self.economy_repo = EconomyRepository()
        self.streak_repo = DailyStreakRepository()
        self.user_repo = UserRepository()
        self.leveling_handler = LevelingHandler()
        self.active_trivias = {}  # msg_id -> {correct_idx, answered, reward}

    def register(self, app: Application):
        app.add_handler(CommandHandler("daily", self.daily_cmd))
        app.add_handler(CommandHandler(["gamble", "bet"], self.gamble_cmd))
        app.add_handler(CommandHandler(["coinflip", "cf", "flip"], self.coinflip_cmd))
        app.add_handler(CommandHandler("dice", self.dice_cmd))
        app.add_handler(CommandHandler(["slots", "slot"], self.slots_cmd))
        app.add_handler(CommandHandler(["duel", "fight"], self.duel_cmd))
        app.add_handler(CommandHandler("trivia", self.trivia_cmd))
        app.add_handler(CallbackQueryHandler(self.trivia_callback, pattern=r"^trivia_"))

    async def daily_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user
        
        success, streak, coins = self.streak_repo.claim_daily(user.id)
        if not success:
            info = self.streak_repo.get_streak_info(user.id)
            rem = info["remaining_seconds"]
            hours = rem // 3600
            mins = (rem % 3600) // 60
            await update.message.reply_text(
                f"⏳ <b>{user.first_name}</b>, you have already claimed your daily reward today!\n\n"
                f"🔥 <b>Current Streak:</b> {info['streak']} Day(s)\n"
                f"⏰ <b>Next Claim in:</b> {hours}h {mins}m\n"
                f"💰 <b>Next Reward:</b> +{info['reward']} Water Coins",
                parse_mode="HTML"
            )
            return

        # Bonus XP for daily
        bonus_xp = streak * 25
        self.user_repo.update_xp(update.message.chat_id, user.id, bonus_xp, user.first_name)
        new_balance = self.economy_repo.get_balance(0, user.id)

        msg = (
            f"🎁 <b>Daily Streak Reward Claimed!</b>\n\n"
            f"👤 <b>Player:</b> {user.first_name}\n"
            f"🔥 <b>Daily Streak:</b> {streak} Day(s) in a row!\n"
            f"💰 <b>Coins Received:</b> +{coins} Water Coins 🪙\n"
            f"✨ <b>Bonus XP:</b> +{bonus_xp} XP\n"
            f"💳 <b>New Balance:</b> {new_balance:,} Water Coins"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def gamble_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user
        chat_id = update.message.chat_id

        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("🎲 <i>Usage:</i> <code>/gamble &lt;amount&gt;</code> (e.g. <code>/gamble 50</code>)", parse_mode="HTML")
            return

        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Bet amount must be greater than 0.")
            return

        bal = self.economy_repo.get_balance(0, user.id)
        if bal < amount:
            await update.message.reply_text(f"❌ You do not have enough coins! Your balance: <b>{bal:,}</b> coins.", parse_mode="HTML")
            return

        # 46% win rate, 2x payout
        win = random.random() < 0.46
        if win:
            self.economy_repo.add_coins(0, user.id, amount)
            new_bal = bal + amount
            await update.message.reply_text(
                f"🎉 <b>LUCKY WIN!</b>\n\n"
                f"👤 <b>{user.first_name}</b> gambled <code>{amount:,}</code> coins and <b>WON!</b>\n"
                f"💰 <b>Profit:</b> +{amount:,} Water Coins 🪙\n"
                f"💳 <b>New Balance:</b> {new_bal:,} coins",
                parse_mode="HTML"
            )
        else:
            self.economy_repo.deduct_coins(0, user.id, amount)
            new_bal = bal - amount
            await update.message.reply_text(
                f"💀 <b>UNLUCKY LOSS!</b>\n\n"
                f"👤 <b>{user.first_name}</b> gambled <code>{amount:,}</code> coins and lost.\n"
                f"💳 <b>Remaining Balance:</b> {new_bal:,} coins",
                parse_mode="HTML"
            )

    async def coinflip_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user

        if len(context.args) < 2 or context.args[0].lower() not in ["heads", "tails", "h", "t"] or not context.args[1].isdigit():
            await update.message.reply_text(
                "🪙 <b>Coinflip Game:</b>\n\n"
                "<i>Usage:</i> <code>/coinflip &lt;heads|tails&gt; &lt;amount&gt;</code>\n"
                "• <i>Example:</i> <code>/cf heads 100</code>",
                parse_mode="HTML"
            )
            return

        choice = "heads" if context.args[0].lower() in ["heads", "h"] else "tails"
        amount = int(context.args[1])
        if amount <= 0: return

        bal = self.economy_repo.get_balance(0, user.id)
        if bal < amount:
            await update.message.reply_text(f"❌ You only have <b>{bal:,}</b> coins.", parse_mode="HTML")
            return

        status = await update.message.reply_text("🪙 <i>Flipping the coin into the air...</i>", parse_mode="HTML")
        await asyncio.sleep(1.2)

        outcome = random.choice(["heads", "tails"])
        if outcome == choice:
            self.economy_repo.add_coins(0, user.id, amount)
            new_bal = bal + amount
            await status.edit_text(
                f"🪙 <b>Coin Landed on: {outcome.upper()}!</b>\n\n"
                f"🎉 <b>{user.first_name}</b> predicted correctly!\n"
                f"💰 <b>Reward:</b> +{amount:,} Water Coins\n"
                f"💳 <b>New Balance:</b> {new_bal:,} coins",
                parse_mode="HTML"
            )
        else:
            self.economy_repo.deduct_coins(0, user.id, amount)
            new_bal = bal - amount
            await status.edit_text(
                f"🪙 <b>Coin Landed on: {outcome.upper()}!</b>\n\n"
                f"❌ <b>{user.first_name}</b> chose {choice.upper()} and lost <code>{amount:,}</code> coins.\n"
                f"💳 <b>New Balance:</b> {new_bal:,} coins",
                parse_mode="HTML"
            )

    async def dice_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user
        
        amount = 50
        if context.args and context.args[0].isdigit():
            amount = int(context.args[0])

        bal = self.economy_repo.get_balance(0, user.id)
        if bal < amount:
            await update.message.reply_text(f"❌ You need at least <b>{amount:,}</b> coins to roll.", parse_mode="HTML")
            return

        # Send Telegram animated dice
        msg = await update.message.reply_dice(emoji="🎲")
        dice_val = msg.dice.value
        await asyncio.sleep(2.5)

        # 4, 5, 6 is win
        if dice_val >= 4:
            multiplier = 2 if dice_val in [4, 5] else 3
            profit = amount * (multiplier - 1)
            self.economy_repo.add_coins(0, user.id, profit)
            new_bal = bal + profit
            await update.message.reply_text(
                f"🎲 <b>Rolled a {dice_val}! YOU WIN!</b>\n\n"
                f"👤 <b>{user.first_name}</b> won with a {multiplier}x payout!\n"
                f"💰 <b>Profit:</b> +{profit:,} coins\n"
                f"💳 <b>New Balance:</b> {new_bal:,} coins",
                parse_mode="HTML"
            )
        else:
            self.economy_repo.deduct_coins(0, user.id, amount)
            new_bal = bal - amount
            await update.message.reply_text(
                f"🎲 <b>Rolled a {dice_val}! YOU LOST.</b>\n\n"
                f"👤 <b>{user.first_name}</b> lost <code>{amount:,}</code> coins (rolls under 4 lose).\n"
                f"💳 <b>New Balance:</b> {new_bal:,} coins",
                parse_mode="HTML"
            )

    async def slots_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        user = update.message.from_user
        
        amount = 50
        if context.args and context.args[0].isdigit():
            amount = int(context.args[0])

        bal = self.economy_repo.get_balance(0, user.id)
        if bal < amount:
            await update.message.reply_text(f"❌ You need at least <b>{amount:,}</b> coins to spin.", parse_mode="HTML")
            return

        msg = await update.message.reply_dice(emoji="🎰")
        val = msg.dice.value
        await asyncio.sleep(2.5)

        # Telegram slot values: 64 = 777 (Jackpot), 1 = BAR/BAR/BAR, etc.
        if val == 64:
            payout = amount * 10
            self.economy_repo.add_coins(0, user.id, payout)
            await update.message.reply_text(f"🎰 <b>JACKPOT 777!</b>\n\n🎉 <b>{user.first_name}</b> hit the 10x Grand Jackpot! Won <b>+{payout:,}</b> coins!", parse_mode="HTML")
        elif val in [1, 22, 43]:
            payout = amount * 3
            self.economy_repo.add_coins(0, user.id, payout)
            await update.message.reply_text(f"🎰 <b>TRIPLE MATCH!</b>\n\nWon <b>+{payout:,}</b> coins (3x multiplier)!", parse_mode="HTML")
        else:
            self.economy_repo.deduct_coins(0, user.id, amount)
            await update.message.reply_text(f"🎰 <b>No match!</b> Lost <code>{amount:,}</code> coins.", parse_mode="HTML")

    async def duel_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        challenger = update.message.from_user
        target_msg = update.message.reply_to_message

        if not target_msg or not target_msg.from_user or target_msg.from_user.is_bot or target_msg.from_user.id == challenger.id:
            await update.message.reply_text(
                "⚔️ <b>Demon Slayer Duel:</b>\n\n"
                "Reply to another member's message with <code>/duel &lt;bet_amount&gt;</code> to challenge them to a Water Breathing battle!",
                parse_mode="HTML"
            )
            return

        target = target_msg.from_user
        amount = 100
        if context.args and context.args[0].isdigit():
            amount = int(context.args[0])

        c_bal = self.economy_repo.get_balance(0, challenger.id)
        t_bal = self.economy_repo.get_balance(0, target.id)
        if c_bal < amount:
            await update.message.reply_text(f"❌ You do not have <b>{amount:,}</b> coins to wager.", parse_mode="HTML")
            return
        if t_bal < amount:
            await update.message.reply_text(f"❌ <b>{target.first_name}</b> does not have enough coins to match the duel bet.", parse_mode="HTML")
            return

        techniques = [
            "First Form: Water Surface Slash 🌊",
            "Second Form: Water Wheel 🌀",
            "Third Form: Flowing Dance 💃",
            "Fourth Form: Striking Tide 🌊",
            "Fifth Form: Blessed Rain After the Drought 🌧️",
            "Eighth Form: Waterfall Basin 💥",
            "Tenth Form: Constant Flux 🐉",
            "Eleventh Form: Dead Calm 🧊"
        ]

        tech1 = random.choice(techniques)
        tech2 = random.choice(techniques)

        status = await update.message.reply_text(
            f"⚔️ <b>WATER HASHIRA DUEL INITIATED!</b>\n\n"
            f"🥋 <b>{challenger.first_name}</b> unleashes <i>{tech1}</i>!\n"
            f"🥋 <b>{target.first_name}</b> counters with <i>{tech2}</i>!\n\n"
            f"<i>Blades clashing...</i>",
            parse_mode="HTML"
        )
        await asyncio.sleep(2.0)

        winner, loser = (challenger, target) if random.random() < 0.5 else (target, challenger)
        self.economy_repo.add_coins(0, winner.id, amount)
        self.economy_repo.deduct_coins(0, loser.id, amount)

        await status.edit_text(
            f"⚔️ <b>DUEL COMPLETE!</b>\n\n"
            f"👑 <b>Victor:</b> {winner.first_name}\n"
            f"💀 <b>Defeated:</b> {loser.first_name}\n\n"
            f"💰 <b>Spoils of War:</b> <b>+{amount:,}</b> Water Coins claimed from the loser!",
            parse_mode="HTML"
        )

    async def trivia_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        
        q_item = random.choice(TRIVIA_QUESTIONS)
        question = q_item["question"]
        options = q_item["options"]
        correct_idx = q_item["correct"]
        cat = q_item["category"]

        keyboard = []
        for idx, opt in enumerate(options):
            keyboard.append([InlineKeyboardButton(opt, callback_data=f"trivia_{idx}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(
            f"🧠 <b>Giyu-Bot Trivia Challenge</b> • <i>{cat}</i>\n\n"
            f"❓ <b>{question}</b>\n\n"
            f"💰 <i>First to tap the correct answer wins <b>100 Water Coins + 50 XP</b>!</i>",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        self.active_trivias[msg.message_id] = {
            "correct": correct_idx,
            "answered": False,
            "correct_text": options[correct_idx]
        }

    async def trivia_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = query.from_user
        msg_id = query.message.message_id

        if msg_id not in self.active_trivias:
            await query.answer("This trivia round has already concluded!", show_alert=True)
            return

        t_data = self.active_trivias[msg_id]
        if t_data["answered"]:
            await query.answer("Someone already won this question!", show_alert=True)
            return

        selected = int(query.data.replace("trivia_", ""))
        if selected == t_data["correct"]:
            t_data["answered"] = True
            del self.active_trivias[msg_id]
            
            self.economy_repo.add_coins(0, user.id, 100)
            self.user_repo.update_xp(query.message.chat_id, user.id, 50, user.first_name)
            
            await query.answer("🎉 Correct! You won 100 Coins + 50 XP!", show_alert=True)
            await query.edit_message_text(
                f"🧠 <b>Trivia Round Finished!</b>\n\n"
                f"🏆 <b>Winner:</b> {user.first_name}\n"
                f"✅ <b>Correct Answer:</b> {t_data['correct_text']}\n"
                f"💰 <b>Reward:</b> +100 Water Coins 🪙 & +50 XP",
                parse_mode="HTML"
            )
        else:
            await query.answer("❌ Incorrect answer! Try again or let someone else guess.", show_alert=False)
