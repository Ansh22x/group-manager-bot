import logging
import datetime
from database.db_manager import DatabaseManager
from services.cache_service import fast_cache
from mistralai.client import Mistral
from config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

class ActivityDigestService:
    def __init__(self):
        self.db = DatabaseManager()
        self.client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None

    def get_group_activity_heatmap(self, chat_id: int) -> dict:
        """
        Calculates time-of-day activity distribution and member engagement metrics.
        """
        cached = fast_cache.get(f"activity_metrics_{chat_id}")
        if cached:
            return cached

        conn = self.db.get_connection()
        distribution = {
            "Night (00:00 - 06:00)": 0,
            "Morning (06:00 - 12:00)": 0,
            "Afternoon (12:00 - 18:00)": 0,
            "Evening (18:00 - 00:00)": 0
        }
        total_recent_msgs = 0

        try:
            with conn.cursor() as cur:
                # 1. Fetch hour distribution from chat history
                cur.execute("""
                    SELECT EXTRACT(HOUR FROM created_at) AS hr, COUNT(*)
                    FROM chat_history
                    WHERE chat_id = %s
                    GROUP BY hr;
                """, (chat_id,))
                
                rows = cur.fetchall()
                for hr, count in rows:
                    total_recent_msgs += count
                    hr = int(hr)
                    if 0 <= hr < 6:
                        distribution["Night (00:00 - 06:00)"] += count
                    elif 6 <= hr < 12:
                        distribution["Morning (06:00 - 12:00)"] += count
                    elif 12 <= hr < 18:
                        distribution["Afternoon (12:00 - 18:00)"] += count
                    else:
                        distribution["Evening (18:00 - 00:00)"] += count

                # 2. Get top members and overall level stats
                cur.execute("""
                    SELECT COUNT(*), COALESCE(SUM(xp), 0), COALESCE(MAX(level), 1), COALESCE(SUM(message_count), 0)
                    FROM users
                    WHERE chat_id = %s;
                """, (chat_id,))
                user_summary = cur.fetchone()

                cur.execute("""
                    SELECT name, level, xp, tag
                    FROM users
                    WHERE chat_id = %s
                    ORDER BY xp DESC LIMIT 3;
                """, (chat_id,))
                top_members = [{"name": r[0], "level": r[1], "xp": r[2], "tag": r[3]} for r in cur.fetchall()]

            data = {
                "distribution": distribution,
                "total_msgs_sample": total_recent_msgs,
                "total_members": user_summary[0] if user_summary else 0,
                "total_xp": user_summary[1] if user_summary else 0,
                "max_level": user_summary[2] if user_summary else 1,
                "total_messages_all_time": user_summary[3] if user_summary else 0,
                "top_members": top_members
            }
            fast_cache.set(f"activity_metrics_{chat_id}", data, ttl_seconds=600.0) # 10m cache
            return data
        except Exception as e:
            logger.error(f"ActivityDigestService.get_group_activity_heatmap error: {e}")
            return {
                "distribution": distribution,
                "total_msgs_sample": 0,
                "total_members": 0,
                "total_xp": 0,
                "max_level": 1,
                "total_messages_all_time": 0,
                "top_members": []
            }
        finally:
            self.db.release_connection(conn)

    async def generate_weekly_digest(self, chat_id: int, chat_title: str) -> str:
        """
        Generates an AI-curated 'Demon Slayer Corps Gazette' weekly digest newspaper for the group.
        """
        cached = fast_cache.get(f"weekly_digest_{chat_id}")
        if cached:
            return cached

        metrics = self.get_group_activity_heatmap(chat_id)
        top_str = "\n".join([f"- {m['name']} (Lvl {m['level']}, {m['xp']} XP, Badge: {m['tag']})" for m in metrics["top_members"]]) or "No leveled members yet."

        if not self.client:
            return (
                f"📰 <b>THE CORPS GAZETTE • WEEKLY REPORT</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏰 <b>Group:</b> {chat_title}\n"
                f"👥 <b>Active Slayers:</b> {metrics['total_members']}\n"
                f"✨ <b>Total Cumulative XP:</b> {metrics['total_xp']} XP\n"
                f"💬 <b>All-Time Messages:</b> {metrics['total_messages_all_time']}\n\n"
                f"🏆 <b>Top Hashira Members:</b>\n{top_str}\n\n"
                f"🌊 <i>\"Continue your training. Do not slack off.\" — Giyu Tomioka</i>"
            )

        prompt = (
            f"You are Giyu Tomioka editing the official Demon Slayer Corps Weekly Newspaper for the Telegram group '{chat_title}'.\n"
            f"Write a witty, entertaining, and structured weekly digest issue in clean Telegram HTML format:\n\n"
            f"Group Stats:\n"
            f"- Members: {metrics['total_members']}\n"
            f"- Cumulative XP: {metrics['total_xp']}\n"
            f"- Top Active Slayers:\n{top_str}\n\n"
            f"Format requirements:\n"
            f"1. Headline banner: '📰 <b>THE CORPS GAZETTE • ISSUE #{datetime.datetime.now().strftime('%U')}</b>'\n"
            f"2. Section 1: 🏆 <b>Hashira of the Week</b> (Praise top members)\n"
            f"3. Section 2: ⚔️ <b>Battle & Training Highlights</b> (XP and message milestones)\n"
            f"4. Section 3: 🌊 <b>Giyu's Stoic Editorial</b> (A short, blunt piece of advice from Giyu Tomioka)\n"
            f"Keep it under 300 words. Use emojis like 🌊, ⚔️, 🏆, 📜. Output valid HTML tags (<b>, <i>, <code>) only."
        )

        try:
            response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                messages=[
                    {"role": "system", "content": "You are Giyu Tomioka formatting a high quality Telegram HTML newspaper summary."},
                    {"role": "user", "content": prompt}
                ]
            )
            digest_html = response.choices[0].message.content.strip()
            fast_cache.set(f"weekly_digest_{chat_id}", digest_html, ttl_seconds=14400.0) # 4 hours cache
            return digest_html
        except Exception as e:
            logger.error(f"ActivityDigestService LLM error: {e}")
            return (
                f"📰 <b>THE CORPS GAZETTE • WEEKLY REPORT</b>\n\n"
                f"🏰 <b>Group:</b> {chat_title}\n"
                f"👥 <b>Active Members:</b> {metrics['total_members']}\n"
                f"✨ <b>Total XP:</b> {metrics['total_xp']}\n\n"
                f"🏆 <b>Top Members:</b>\n{top_str}"
            )
