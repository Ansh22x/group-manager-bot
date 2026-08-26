import os
import re
import logging
import asyncio
import tempfile
import cloudscraper
import httpx

logger = logging.getLogger(__name__)

INVIDIOUS_SEARCH_INSTANCES = [
    "https://invidious.flokinet.to",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yt.artemislena.eu",
    "https://invidious.drgns.space",
    "https://inv.tux.pizza",
    "https://invidious.no-logs.com",
    "https://invidious.private.coffee",
    "https://invidious.einfachzocken.eu",
    "https://invidious.f5.si"
]

def _safe_remove(path: str | None):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

class InvidiousExtractor:
    """Handles Invidious search resolution, cnv.cx conversion, and direct proxy video streams."""

    def __init__(self):
        self.cached_invidious = "https://invidious.flokinet.to"

    async def resolve_youtube_url(self, query: str) -> tuple[str, str] | None:
        """Resolves a search query to a YouTube URL via Invidious search nodes or yt-dlp."""
        if "youtube.com" in query or "youtu.be" in query:
            return query, "YouTube Link"

        instances = [self.cached_invidious] + INVIDIOUS_SEARCH_INSTANCES
        seen_inst = set()
        instances = [x for x in instances if x and not (x in seen_inst or seen_inst.add(x))]

        for instance in instances:
            try:
                async with httpx.AsyncClient(timeout=9, verify=False) as client:
                    r = await client.get(
                        f"{instance}/api/v1/search",
                        params={"q": query, "type": "video", "fields": "videoId,title", "safesearch": "false"}
                    )
                    if r.status_code == 200:
                        results = r.json()
                        for item in results[:3]:
                            vid_id = item.get("videoId", "")
                            title = item.get("title", "")
                            if vid_id and not vid_id.startswith("PL"):
                                self.cached_invidious = instance
                                logger.info(f"Invidious resolved '{query}' -> {vid_id} ({title})")
                                return f"https://www.youtube.com/watch?v={vid_id}", title
            except Exception as e:
                logger.debug(f"Invidious search failed on {instance}: {e}")

        # Fallback to yt-dlp search
        logger.info(f"Invidious search exhausted, trying unrestricted yt-dlp ytsearch for: {query}")
        try:
            import yt_dlp
            opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "socket_timeout": 15,
                "age_limit": 0,
                "nocheckcertificate": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "mweb", "tv_embedded"]
                    }
                }
            }
            def _ytsearch():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    res = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    if res and "entries" in res and res["entries"]:
                        first = res["entries"][0]
                        return first.get("url") or f"https://www.youtube.com/watch?v={first.get('id')}", first.get("title", query)
                    return None

            return await asyncio.to_thread(_ytsearch)
        except Exception as e:
            logger.warning(f"yt-dlp search fallback failed: {e}")

        return None

    async def download_cnv_audio(self, url: str) -> tuple[str, str] | None:
        """Converts YouTube audio to MP3 using cnv.cx."""
        return await self._download_cnv(url, is_audio=True)

    async def download_cnv_video(self, url: str) -> tuple[str, str] | None:
        """Converts YouTube video using cnv.cx."""
        return await self._download_cnv(url, is_audio=False)

    async def _download_cnv(self, url: str, is_audio: bool) -> tuple[str, str] | None:
        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://cnv.cx/"
        }
        format_val = "mp3" if is_audio else "720"
        ext = ".mp3" if is_audio else ".mp4"
        prefix = "giyu_audio_cnv_" if is_audio else "giyu_video_cnv_"

        try:
            def _init_cnv():
                return scraper.post("https://api.cnv.cx/api/v1/init", json={"url": url, "format": format_val}, headers=headers, timeout=12)

            res = await asyncio.to_thread(_init_cnv)
            if res.status_code == 200:
                data = res.json()
                job_id = data.get("id") or data.get("job_id")
                title = data.get("title", "Audio Stream" if is_audio else "Video Stream")
                download_url = data.get("download_url") or data.get("url")

                # Poll job if not ready immediately
                if not download_url and job_id:
                    for _ in range(12):
                        await asyncio.sleep(1.5)
                        def _poll():
                            return scraper.get(f"https://api.cnv.cx/api/v1/status/{job_id}", headers=headers, timeout=8)
                        p_res = await asyncio.to_thread(_poll)
                        if p_res.status_code == 200:
                            p_data = p_res.json()
                            if p_data.get("status") in ("finished", "completed", "ready"):
                                download_url = p_data.get("download_url") or p_data.get("url")
                                break

                if download_url:
                    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix=prefix)
                    os.close(tmp_fd)

                    def _dl():
                        r = scraper.get(download_url, headers=headers, stream=True, timeout=90)
                        if r.status_code == 200:
                            with open(tmp_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=65536):
                                    f.write(chunk)
                            return True
                        return False

                    ok = await asyncio.to_thread(_dl)
                    if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 5000:
                        return tmp_path, title
                    _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"cnv.cx conversion failed: {e}")

        return None
