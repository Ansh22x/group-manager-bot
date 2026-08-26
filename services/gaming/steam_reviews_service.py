import logging
import hashlib
from services.http_client import shared_http_client
from services.cache_service import fast_cache
from mistralai.client import Mistral
from config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

class SteamReviewsService:
    def __init__(self):
        self.client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None

    async def resolve_game(self, query: str) -> tuple[int, str, str | None] | None:
        """
        Resolves a game title or numeric ID to (appid, game_title, header_image).
        """
        clean = query.strip()
        if clean.isdigit():
            appid = int(clean)
            return appid, f"Steam App {appid}", f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"

        try:
            res = await shared_http_client.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": clean, "l": "english", "cc": "US"},
                timeout=8.0
            )
            if res.status_code == 200:
                items = res.json().get("items", [])
                if items:
                    top = items[0]
                    appid = top["id"]
                    title = top["name"]
                    header_img = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
                    return appid, title, header_img
        except Exception as e:
            logger.error(f"SteamReviewsService.resolve_game error for '{query}': {e}")

        return None

    async def fetch_steam_reviews_data(self, appid: int) -> dict | None:
        """
        Fetches official review summary stats plus top positive & critical player reviews from Steam.
        """
        try:
            # 1. Fetch top positive reviews
            pos_res = await shared_http_client.get(
                f"https://store.steampowered.com/appreviews/{appid}",
                params={
                    "json": "1",
                    "language": "english",
                    "review_type": "positive",
                    "purchase_type": "all",
                    "num_per_page": "8",
                    "filter": "summary"
                },
                timeout=10.0
            )

            # 2. Fetch top critical/negative reviews
            neg_res = await shared_http_client.get(
                f"https://store.steampowered.com/appreviews/{appid}",
                params={
                    "json": "1",
                    "language": "english",
                    "review_type": "negative",
                    "purchase_type": "all",
                    "num_per_page": "8",
                    "filter": "summary"
                },
                timeout=10.0
            )

            summary = {}
            pos_reviews = []
            neg_reviews = []

            if pos_res.status_code == 200:
                pos_data = pos_res.json()
                summary = pos_data.get("query_summary", {})
                for r in pos_data.get("reviews", []):
                    text = r.get("review", "").strip()
                    hours = round(r.get("author", {}).get("playtime_forever", 0) / 60, 1)
                    if text and len(text) > 30:
                        pos_reviews.append(f"[Playtime: {hours}h | Helpful: {r.get('votes_up', 0)}]: {text[:400]}")

            if neg_res.status_code == 200:
                neg_data = neg_res.json()
                if not summary:
                    summary = neg_data.get("query_summary", {})
                for r in neg_data.get("reviews", []):
                    text = r.get("review", "").strip()
                    hours = round(r.get("author", {}).get("playtime_forever", 0) / 60, 1)
                    if text and len(text) > 30:
                        neg_reviews.append(f"[Playtime: {hours}h | Helpful: {r.get('votes_up', 0)}]: {text[:400]}")

            total_pos = summary.get("total_positive", 0)
            total_neg = summary.get("total_negative", 0)
            total_revs = summary.get("total_reviews", total_pos + total_neg)
            score_desc = summary.get("review_score_desc", "Mixed")
            pct = round((total_pos / max(total_revs, 1)) * 100, 1) if total_revs > 0 else 0

            return {
                "appid": appid,
                "score_desc": score_desc,
                "positive_pct": pct,
                "total_positive": total_pos,
                "total_negative": total_neg,
                "total_reviews": total_revs,
                "positive_samples": pos_reviews[:6],
                "negative_samples": neg_reviews[:6]
            }

        except Exception as e:
            logger.error(f"SteamReviewsService.fetch_steam_reviews_data error for {appid}: {e}")
            return None

    async def get_reviews_summary(self, query_or_appid: str) -> dict | None:
        """
        Synthesizes player reviews for a game into a comprehensive, structured AI summary.
        Cached in FastCache for 6 hours.
        """
        resolved = await self.resolve_game(query_or_appid)
        if not resolved:
            return None

        appid, game_title, header_img = resolved
        cache_key = f"steam_review_summary_{appid}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        raw_data = await self.fetch_steam_reviews_data(appid)
        if not raw_data or (not raw_data["positive_samples"] and not raw_data["negative_samples"]):
            return None

        if not self.client:
            summary_body = (
                f"📊 <b>Overall Sentiment:</b> {raw_data['score_desc']} ({raw_data['positive_pct']}% Positive)\n"
                f"👍 <b>Positive Reviews:</b> {raw_data['total_positive']:,}\n"
                f"👎 <b>Negative Reviews:</b> {raw_data['total_negative']:,}\n"
                f"💬 <b>Total Reviews:</b> {raw_data['total_reviews']:,}\n\n"
                f"<i>Mistral API key required for deep semantic review synthesis.</i>"
            )
            result = {
                "appid": appid,
                "game_title": game_title,
                "header_image": header_img,
                "summary": summary_body,
                "score_desc": raw_data["score_desc"],
                "positive_pct": raw_data["positive_pct"],
                "total_reviews": raw_data["total_reviews"],
                "store_url": f"https://store.steampowered.com/app/{appid}"
            }
            return result

        prompt = (
            f"You are Giyu Tomioka's gaming intelligence analyzer.\n"
            f"Analyze the following authentic Steam player reviews for the game '{game_title}' (App ID: {appid}).\n\n"
            f"Steam Stats:\n"
            f"- Sentiment: {raw_data['score_desc']} ({raw_data['positive_pct']}% positive from {raw_data['total_reviews']:,} total reviews)\n"
            f"- Positive Reviews Count: {raw_data['total_positive']:,}\n"
            f"- Negative Reviews Count: {raw_data['total_negative']:,}\n\n"
            f"Player Feedback Samples (Positive):\n"
            f"{chr(10).join(raw_data['positive_samples'])}\n\n"
            f"Player Feedback Samples (Negative/Critical):\n"
            f"{chr(10).join(raw_data['negative_samples'])}\n\n"
            f"Produce a structured, engaging, and honest review digest in valid Telegram HTML format with these exact sections:\n"
            f"📊 <b>Community Sentiment:</b> (State the score, rating percentage, and overall consensus in 1 sentence)\n\n"
            f"🟢 <b>The Good (What Players Love):</b>\n"
            f"• (Key strength 1: gameplay/mechanics/combat/story)\n"
            f"• (Key strength 2: world design/visuals/music/immersion)\n"
            f"• (Key strength 3: content depth/replayability)\n\n"
            f"🔴 <b>The Bad (Common Player Complaints):</b>\n"
            f"• (Issue 1: technical/optimization/bugs/crashes if reported)\n"
            f"• (Issue 2: balancing/pacing/monetization/difficulty)\n\n"
            f"⚙️ <b>Performance & State:</b> (1 sentence summarizing technical polish & stability)\n\n"
            f"💡 <b>The Verdict:</b> (1 sentence concluding recommendation: must-buy, buy on sale, or pass)\n\n"
            f"Rules: Output clean Telegram HTML (<b>, <i>, <code>). Keep under 280 words."
        )

        try:
            response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                messages=[
                    {"role": "system", "content": "You are a professional game critic providing concise, accurate summaries of Steam user reviews."},
                    {"role": "user", "content": prompt}
                ]
            )
            ai_digest = response.choices[0].message.content.strip()

            result = {
                "appid": appid,
                "game_title": game_title,
                "header_image": header_img,
                "summary": ai_digest,
                "score_desc": raw_data["score_desc"],
                "positive_pct": raw_data["positive_pct"],
                "total_reviews": raw_data["total_reviews"],
                "store_url": f"https://store.steampowered.com/app/{appid}"
            }

            fast_cache.set(cache_key, result, ttl_seconds=21600.0) # 6 hours cache
            return result

        except Exception as e:
            logger.error(f"SteamReviewsService.get_reviews_summary LLM error: {e}")
            return None
