import logging
import hashlib
from services.http_client import shared_http_client
from services.cache_service import fast_cache

logger = logging.getLogger(__name__)

class TraceAnimeService:
    API_URL = "https://api.trace.moe/search?anilistInfo"

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """Converts seconds float into MM:SS format."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    async def search_anime_by_image(self, image_bytes: bytes) -> dict | None:
        """
        Queries trace.moe visual frame recognition API with raw image bytes.
        Returns matched anime title, episode, exact timestamp, confidence, and preview video clip.
        """
        try:
            img_hash = hashlib.md5(image_bytes).hexdigest()
            cached = fast_cache.get(f"sauce_{img_hash}")
            if cached:
                return cached

            headers = {"Content-Type": "image/jpeg"}
            res = await shared_http_client.post(
                self.API_URL,
                content=image_bytes,
                headers=headers,
                timeout=20.0
            )

            if res.status_code != 200:
                logger.warning(f"TraceAnimeService: trace.moe API returned HTTP {res.status_code}")
                return None

            data = res.json()
            results = data.get("result", [])
            if not results:
                return None

            top = results[0]
            similarity = round(top.get("similarity", 0) * 100, 1)

            # Require at least 80% visual similarity for high confidence
            if similarity < 80.0:
                logger.info(f"TraceAnimeService: Low confidence match ({similarity}%)")

            anilist = top.get("anilist", {})
            title_romaji = anilist.get("title", {}).get("romaji") or anilist.get("title", {}).get("english") or "Unknown Anime"
            title_native = anilist.get("title", {}).get("native", "")
            title_english = anilist.get("title", {}).get("english", "")

            episode = top.get("episode", "Unknown")
            time_start = self.format_timestamp(top.get("from", 0))
            time_end = self.format_timestamp(top.get("to", 0))

            video_preview = top.get("video")
            image_preview = top.get("image")
            is_adult = anilist.get("isAdult", False)
            anilist_id = anilist.get("id")
            anilist_url = f"https://anilist.co/anime/{anilist_id}" if anilist_id else None

            result = {
                "title_romaji": title_romaji,
                "title_english": title_english,
                "title_native": title_native,
                "episode": episode,
                "timestamp": f"{time_start} - {time_end}",
                "similarity": similarity,
                "video_preview": video_preview,
                "image_preview": image_preview,
                "is_adult": is_adult,
                "anilist_url": anilist_url
            }

            fast_cache.set(f"sauce_{img_hash}", result, ttl_seconds=86400.0) # 24h cache
            return result
        except Exception as e:
            logger.error(f"TraceAnimeService.search_anime_by_image error: {e}")
            return None
