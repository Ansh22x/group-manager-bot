import os
import re
import logging
import asyncio
import tempfile
import httpx
import cloudscraper

logger = logging.getLogger(__name__)

# Search nodes (to resolve search query to a YT video ID)
INVIDIOUS_SEARCH_INSTANCES = [
    "https://invidious.flokinet.to",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://iv.datura.network",
    "https://invidious.privacydev.net",
]

# Static fallback API URLs for Cobalt (Turnstile-free)
COBALT_DEFAULT_APIS = [
    "https://api.cobalt.liubquanti.click",
    "https://cobaltapi.cjs.nz"
]


class MediaDownloaderService:
    def __init__(self):
        self.cached_cobalt = "https://api.cobalt.liubquanti.click"
        self.cached_invidious = "https://invidious.flokinet.to"

    # ─────────────────────────────────────────────────────────────────────────
    # SEARCH
    # ─────────────────────────────────────────────────────────────────────────

    async def resolve_youtube_url(self, query: str) -> tuple[str, str] | None:
        """Resolves a query string to a YouTube URL via Invidious search nodes.
        Tries top 3 results and multiple instances before falling back to yt-dlp.
        Returns (youtube_url, title) or None.
        """
        if "youtube.com" in query or "youtu.be" in query:
            return query, "YouTube Link"

        instances = [self.cached_invidious] + INVIDIOUS_SEARCH_INSTANCES
        seen_inst: set = set()
        instances = [x for x in instances if x and not (x in seen_inst or seen_inst.add(x))]

        for instance in instances:
            try:
                async with httpx.AsyncClient(timeout=9, verify=False) as client:
                    r = await client.get(
                        f"{instance}/api/v1/search",
                        params={"q": query, "type": "video", "fields": "videoId,title"}
                    )
                    if r.status_code == 200:
                        results = r.json()
                        # Try the first 3 results - skip playlists / live streams
                        for item in results[:3]:
                            vid_id = item.get("videoId", "")
                            title = item.get("title", "")
                            if vid_id and not vid_id.startswith("PL"):
                                self.cached_invidious = instance
                                logger.info(f"Invidious resolved '{query}' -> {vid_id} ({title})")
                                return f"https://www.youtube.com/watch?v={vid_id}", title
            except Exception as e:
                logger.debug(f"Invidious search failed on {instance}: {e}")

        # Tertiary fallback: yt-dlp ytsearch
        logger.info(f"Invidious search exhausted, trying yt-dlp ytsearch for: {query}")
        try:
            import yt_dlp
            opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                    "noplaylist": True, "socket_timeout": 10}
            def _ytdlp_search():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(f"ytsearch3:{query}", download=False)
                    if info and "entries" in info:
                        for entry in info["entries"]:
                            if entry and entry.get("id"):
                                return f"https://www.youtube.com/watch?v={entry['id']}", entry.get("title", "")
                return None
            result = await asyncio.to_thread(_ytdlp_search)
            if result:
                logger.info(f"yt-dlp ytsearch resolved: {result}")
                return result
        except Exception as e:
            logger.debug(f"yt-dlp ytsearch failed: {e}")

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # DOWNLOAD - cnv.cx pipeline
    # ─────────────────────────────────────────────────────────────────────────

    async def download_via_cnv(self, target_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads via cnv.cx + cloudscraper.
        Returns (local_temp_file_path, title) or None.
        """
        video_id = None
        for pattern in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"embed/([^?]+)", r"v/([^?]+)"]:
            m = re.search(pattern, target_url)
            if m:
                video_id = m.group(1)
                break

        if not video_id:
            return None

        ext = "mp3" if mode == "audio" else "mp4"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix=f"giyu_{mode}_")
        os.close(tmp_fd)

        headers = {
            "Accept": "*/*",
            "Origin": "https://iframe.y2meta-uk.com",
            "Referer": "https://iframe.y2meta-uk.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            logger.info(f"Trying cnv.cx pipeline for video_id: {video_id}")
            scraper = cloudscraper.create_scraper()

            def get_key():
                r = scraper.get(f"https://cnv.cx/v2/sanity/key?id={video_id}", headers=headers, timeout=10)
                return r.json().get("key") if r.status_code == 200 else None

            key = await asyncio.to_thread(get_key)
            if not key:
                logger.debug("cnv.cx: failed to obtain sanity key")
                _safe_remove(tmp_path)
                return None

            payload = {
                "link": f"https://youtu.be/{video_id}",
                "format": ext,
                "audioBitrate": "128",
                "videoQuality": "720",
                "vCodec": "h264",
                "filenameStyle": "pretty"
            }
            headers_post = {**headers, "key": key}

            def do_convert():
                r = scraper.post("https://cnv.cx/v2/converter", json=payload, headers=headers_post, timeout=20)
                return r.json() if r.status_code == 200 else None

            data = await asyncio.to_thread(do_convert)
            if not data or data.get("status") != "tunnel":
                logger.debug(f"cnv.cx converter non-tunnel status: {data}")
                _safe_remove(tmp_path)
                return None

            dl_url = data.get("url")
            title = os.path.splitext(data.get("filename", "Track"))[0]

            def do_download():
                resp = scraper.get(dl_url, headers={"Referer": "https://iframe.y2meta-uk.com/"}, stream=True, timeout=120)
                if resp.status_code == 200:
                    with open(tmp_path, "wb") as fh:
                        for chunk in resp.iter_content(chunk_size=65536):
                            fh.write(chunk)
                    return True
                return False

            success = await asyncio.to_thread(do_download)
            if success and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
                logger.info(f"cnv.cx download successful: {title} -> {tmp_path}")
                return tmp_path, title

        except Exception as e:
            logger.debug(f"cnv.cx pipeline failed: {e}")

        _safe_remove(tmp_path)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # DOWNLOAD - Cobalt pipeline
    # ─────────────────────────────────────────────────────────────────────────

    async def get_cobalt_endpoints(self) -> list[str]:
        """Fetches working Cobalt API endpoints from cobalt.directory registry."""
        default = [self.cached_cobalt] + COBALT_DEFAULT_APIS if self.cached_cobalt else COBALT_DEFAULT_APIS
        seen: set = set()
        endpoints = [x for x in default if x and not (x in seen or seen.add(x))]
        try:
            scraper = cloudscraper.create_scraper()
            def fetch_api():
                r = scraper.get("https://cobalt.directory/api/working?type=api", timeout=8)
                return r.json().get("data", {}).get("youtube", []) if r.status_code == 200 else []
            apis = await asyncio.to_thread(fetch_api)
            for api in apis:
                api_clean = api.rstrip('/')
                if api_clean not in seen:
                    endpoints.append(api_clean)
                    seen.add(api_clean)
        except Exception as e:
            logger.warning(f"Failed to fetch cobalt directory: {e}")
        return endpoints

    async def download_via_cobalt(self, target_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads via Cobalt API instances.
        Returns (local_temp_file_path, title) or None.
        """
        endpoints = await self.get_cobalt_endpoints()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        payload = {
            "url": target_url,
            "downloadMode": "audio" if mode == "audio" else "video",
            "audioFormat": "mp3",
            "videoQuality": "720"
        }
        scraper = cloudscraper.create_scraper()
        ext = "mp3" if mode == "audio" else "mp4"

        for api in endpoints:
            api_endpoint = f"{api.rstrip('/')}/"
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix=f"giyu_{mode}_")
            os.close(tmp_fd)
            try:
                logger.info(f"Trying Cobalt endpoint: {api_endpoint}")
                def post_cobalt():
                    return scraper.post(api_endpoint, json=payload, headers=headers, timeout=12)
                r = await asyncio.to_thread(post_cobalt)

                if r.status_code == 200:
                    data = r.json()
                    dl_url = data.get("url")
                    if dl_url and data.get("status") in ("redirect", "stream", "tunnel"):
                        def get_stream():
                            resp = scraper.get(dl_url, stream=True, timeout=120)
                            if resp.status_code == 200:
                                with open(tmp_path, "wb") as fh:
                                    for chunk in resp.iter_content(chunk_size=65536):
                                        fh.write(chunk)
                                return True
                            return False

                        success = await asyncio.to_thread(get_stream)
                        if success and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
                            self.cached_cobalt = api
                            title = os.path.splitext(data.get("filename", "Track"))[0]
                            logger.info(f"Cobalt download successful: {title} -> {tmp_path}")
                            return tmp_path, title

                elif r.status_code == 400 and "jwt.missing" in r.text:
                    logger.debug(f"Cobalt {api_endpoint}: Turnstile-protected, skipping")

            except Exception as e:
                logger.debug(f"Cobalt attempt failed on {api}: {e}")

            _safe_remove(tmp_path)

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # DOWNLOAD - yt-dlp direct (final fallback)
    # ─────────────────────────────────────────────────────────────────────────

    async def download_via_ytdlp(self, target_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads directly via yt-dlp as last resort.
        Returns (local_temp_file_path, title) or None.
        """
        import yt_dlp
        ext = "mp3" if mode == "audio" else "mp4"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix=f"giyu_ytdlp_")
        os.close(tmp_fd)
        outtmpl = tmp_path.replace(f".{ext}", ".%(ext)s")

        opts: dict = {
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 2,
        }
        if mode == "audio":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }]
        else:
            opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"

        try:
            logger.info(f"Trying yt-dlp direct download for: {target_url}")
            def _do_dl():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(target_url, download=True)
                    return info.get("title", "Track") if info else None

            title = await asyncio.to_thread(_do_dl)
            # yt-dlp writes to outtmpl pattern - find the actual output file
            candidate = tmp_path
            if not os.path.exists(candidate):
                base = tmp_path.rsplit(".", 1)[0]
                for e in [ext, "webm", "m4a", "opus"]:
                    cand = f"{base}.{e}"
                    if os.path.exists(cand):
                        candidate = cand
                        break

            if title and os.path.exists(candidate) and os.path.getsize(candidate) > 10_000:
                logger.info(f"yt-dlp download successful: {title} -> {candidate}")
                return candidate, title

        except Exception as e:
            logger.debug(f"yt-dlp direct download failed: {e}")

        _safe_remove(tmp_path)
        return None


def _safe_remove(path: str):
    """Silently remove a file if it exists."""
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass

