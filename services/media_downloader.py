import os
import re
import logging
import asyncio
import tempfile
import httpx
import cloudscraper
from bs4 import BeautifulSoup

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
                        params={"q": query, "type": "video", "fields": "videoId,title", "safesearch": "false"}
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

        # Tertiary fallback: yt-dlp ytsearch (Unrestricted android & mweb player client)
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

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 1: Specialized Fast Extractors (TikTok, Terabox)
    # ─────────────────────────────────────────────────────────────────────────

    async def download_tiktok_tikwm(self, url: str) -> tuple[str, str] | None:
        """Downloads HD watermark-free TikTok video via TikWM API."""
        scraper = cloudscraper.create_scraper()
        api = "https://www.tikwm.com/api/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            logger.info(f"Downloading TikTok via TikWM: {url}")
            def post_tikwm():
                return scraper.post(api, data={"url": url}, headers=headers, timeout=12)
            
            r = await asyncio.to_thread(post_tikwm)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 0 and data.get("data"):
                    info = data["data"]
                    play_url = info.get("play") or info.get("wmplay")
                    title = info.get("title") or f"TikTok Video by @{info.get('author', {}).get('unique_id', 'user')}"
                    
                    if play_url:
                        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_tiktok_")
                        os.close(tmp_fd)
                        
                        def stream_video():
                            resp = scraper.get(play_url, headers=headers, stream=True, timeout=90)
                            if resp.status_code == 200:
                                with open(tmp_path, "wb") as f:
                                    for chunk in resp.iter_content(chunk_size=65536):
                                        f.write(chunk)
                                return True
                            return False

                        ok = await asyncio.to_thread(stream_video)
                        if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 5000:
                            logger.info(f"TikWM download successful: {title} -> {tmp_path}")
                            return tmp_path, title
                        _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"TikWM scraper failed: {e}")
        return None

    async def download_terabox(self, url: str) -> tuple[str | None, str, str | None] | None:
        """Extracts and downloads Terabox videos/files.
        Returns (local_file_path_if_small, title, direct_download_url).
        """
        scraper = cloudscraper.create_scraper()
        logger.info(f"Extracting Terabox file from: {url}")

        # List of Terabox worker/resolvers
        resolvers = [
            f"https://terabox-dl.qtcloud.workers.dev/api/get-info?url={url}",
            f"https://ytshorts.savetube.me/api/v1/terabox-downloader"
        ]
        
        # Try direct extraction using yt-dlp first
        try:
            import yt_dlp
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_terabox_")
            os.close(tmp_fd)
            opts = {
                "outtmpl": tmp_path.replace(".mp4", ".%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30
            }
            def _ytdl_tera():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return info.get("title", "Terabox File"), info.get("url")
            
            title, direct_url = await asyncio.to_thread(_ytdl_tera)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
                return tmp_path, title, direct_url
            _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"yt-dlp Terabox extractor failed: {e}")

        # Fallback to Terabox API parsing
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            def _fetch_api():
                return scraper.post("https://teradownloader.com/api/application-data", json={"url": url}, headers=headers, timeout=10)
            res = await asyncio.to_thread(_fetch_api)
            if res.status_code == 200:
                data = res.json()
                d_url = data.get("download_url") or data.get("url")
                title = data.get("file_name") or data.get("title") or "Terabox File"
                if d_url:
                    return None, title, d_url
        except Exception as e:
            logger.debug(f"Terabox API resolver error: {e}")

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 2: cnv.cx pipeline (YouTube audio/video)
    # ─────────────────────────────────────────────────────────────────────────

    async def download_xfs_host(self, url: str) -> tuple[str, str] | None:
        """Handles XFS / XVideoSharing hosts (abstream, streamwish, doodstream, etc.) that use POST download forms."""
        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url
        }
        try:
            logger.info(f"Resolving XFS host download: {url}")
            def get_page():
                return scraper.get(url, headers=headers, timeout=15)
            
            r = await asyncio.to_thread(get_page)
            if r.status_code != 200:
                return None

            soup = BeautifulSoup(r.text, "html.parser")
            form = soup.find("form")
            if not form:
                return None

            data = {}
            for inp in form.find_all("input"):
                if inp.get("name"):
                    data[inp["name"]] = inp.get("value", "")

            post_headers = dict(headers)
            post_headers["Origin"] = "/".join(url.split("/")[:3])
            post_headers["Referer"] = url

            def post_form():
                return scraper.post(url, data=data, headers=post_headers, timeout=15)

            resp = await asyncio.to_thread(post_form)
            if resp.status_code != 200:
                return None

            # Find direct MP4 link in POST response
            p_soup = BeautifulSoup(resp.text, "html.parser")
            dl_link = None
            for a in p_soup.find_all("a"):
                href = a.get("href", "")
                if ".mp4" in href or "delucloud" in href or "download" in a.get_text().lower():
                    if href.startswith("http"):
                        dl_link = href
                        break

            if not dl_link:
                mp4_matches = re.findall(r'https?://[^\s"\'<>]+\.mp4(?:\?[^\s"\'<>]*)?', resp.text)
                if mp4_matches:
                    dl_link = mp4_matches[0]

            if dl_link:
                title = "Video File"
                title_tag = p_soup.find("title") or soup.find("title")
                if title_tag:
                    title = title_tag.text.strip()
                
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_xfs_")
                os.close(tmp_fd)

                dl_headers = dict(headers)
                dl_headers["Referer"] = url
                dl_headers["Origin"] = post_headers["Origin"]

                def stream_dl():
                    r = scraper.get(dl_link, headers=dl_headers, stream=True, timeout=180)
                    if r.status_code == 200:
                        with open(tmp_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=65536):
                                f.write(chunk)
                        return True
                    return False

                ok = await asyncio.to_thread(stream_dl)
                if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
                    return tmp_path, title
                _safe_remove(tmp_path)

        except Exception as e:
            logger.debug(f"XFS host resolution error: {e}")
        return None

    async def download_via_cnv(self, youtube_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads audio/video via cnv.cx API.
        Returns (local_temp_file_path, title) or None.
        """
        match = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", youtube_url)
        if not match:
            logger.debug(f"cnv.cx: Could not extract video ID from {youtube_url}")
            return None
        video_id = match.group(1)

        format_val = "mp3" if mode == "audio" else "720"
        api_url = f"https://cnv.cx/v2/api/tunnel?url=https://www.youtube.com/watch?v={video_id}&format={format_val}"

        ext = "mp3" if mode == "audio" else "mp4"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix=f"giyu_cnv_{mode}_")
        os.close(tmp_fd)

        scraper = cloudscraper.create_scraper()
        try:
            logger.info(f"Trying cnv.cx tunnel for YouTube ID: {video_id} ({format_val})")
            def do_init():
                return scraper.get(api_url, timeout=12)

            resp = await asyncio.to_thread(do_init)
            if resp.status_code != 200:
                logger.debug(f"cnv.cx tunnel returned {resp.status_code}")
                _safe_remove(tmp_path)
                return None

            data = resp.json()
            if data.get("status") != "tunnel" or not data.get("url"):
                logger.debug(f"cnv.cx converter non-tunnel status: {data}")
                _safe_remove(tmp_path)
                return None

            dl_url = data.get("url")
            title = os.path.splitext(data.get("filename", "Track"))[0]

            def do_download():
                r = scraper.get(dl_url, headers={"Referer": "https://iframe.y2meta-uk.com/"}, stream=True, timeout=120)
                if r.status_code == 200:
                    with open(tmp_path, "wb") as fh:
                        for chunk in r.iter_content(chunk_size=65536):
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
    # TIER 3: Cobalt pipeline (Multi-platform: Instagram, FB, TikTok, X, Reddit...)
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

    async def download_via_cobalt(self, target_url: str, mode: str = "video") -> tuple[str, str] | None:
        """Downloads via Cobalt API instances (Instagram, TikTok, FB, Twitter, Reddit, etc.).
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
                logger.info(f"Trying Cobalt endpoint {api_endpoint} for: {target_url}")
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
                            title = os.path.splitext(data.get("filename", "Media"))[0]
                            logger.info(f"Cobalt download successful: {title} -> {tmp_path}")
                            return tmp_path, title

                elif r.status_code == 400 and "jwt.missing" in r.text:
                    logger.debug(f"Cobalt {api_endpoint}: Turnstile-protected, skipping")

            except Exception as e:
                logger.debug(f"Cobalt attempt failed on {api}: {e}")

            _safe_remove(tmp_path)

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 4: yt-dlp Universal Engine (1,800+ Websites)
    # ─────────────────────────────────────────────────────────────────────────

    async def download_via_ytdlp(self, target_url: str, mode: str = "video", referer: str | None = None) -> tuple[str, str] | None:
        """Downloads directly via yt-dlp supporting over 1,800 platforms.
        Returns (local_temp_file_path, title) or None.
        """
        import yt_dlp
        ext = "mp3" if mode == "audio" else "mp4"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix=f"giyu_ytdlp_")
        os.close(tmp_fd)
        outtmpl = tmp_path.replace(f".{ext}", ".%(ext)s")

        ref_header = referer or target_url
        origin_header = "/".join(ref_header.split("/")[:3]) if ref_header.startswith("http") else ref_header

        opts: dict = {
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 45,
            "retries": 3,
            "age_limit": 0,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "mweb", "tv_embedded"]
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": ref_header,
                "Origin": origin_header,
                "Accept": "*/*"
            }
        }
        if mode == "audio":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }]
        else:
            opts["format"] = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"

        try:
            logger.info(f"Trying yt-dlp universal extractor for: {target_url}")
            def _do_dl():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(target_url, download=True)
                    return info.get("title", "Media") if info else None

            title = await asyncio.to_thread(_do_dl)
            
            # Find the actual downloaded file on disk
            candidate = tmp_path
            if not os.path.exists(candidate):
                base = tmp_path.rsplit(".", 1)[0]
                for e in [ext, "mkv", "webm", "m4a", "opus", "mp4"]:
                    cand = f"{base}.{e}"
                    if os.path.exists(cand):
                        candidate = cand
                        break

            if title and os.path.exists(candidate) and os.path.getsize(candidate) > 10_000:
                logger.info(f"yt-dlp universal download successful: {title} -> {candidate}")
                return candidate, title

        except Exception as e:
            logger.debug(f"yt-dlp universal download failed: {e}")

        _safe_remove(tmp_path)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 5: Direct Media Stream / File URL Downloader
    # ─────────────────────────────────────────────────────────────────────────

    async def download_direct_file(self, url: str, mode: str = "video") -> tuple[str, str] | None:
        """Downloads direct media file streams with stream inspection."""
        clean_url = url.split("?")[0].lower()
        is_direct_video = any(clean_url.endswith(f".{ext}") for ext in ["mp4", "webm", "mov", "mkv", "avi", "flv", "m4v", "ts"])
        is_direct_audio = any(clean_url.endswith(f".{ext}") for ext in ["mp3", "m4a", "wav", "aac", "ogg", "opus", "flac"])

        if not (is_direct_video or is_direct_audio):
            return None

        ext = "mp3" if is_direct_audio else "mp4"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": "https://www.google.com/"
        }
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix="giyu_direct_")
        os.close(tmp_fd)

        try:
            logger.info(f"Downloading direct media URL: {url}")
            async with httpx.AsyncClient(timeout=120, follow_redirects=True, headers=headers) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code == 200:
                        with open(tmp_path, "wb") as f:
                            async for chunk in resp.aiter_bytes(chunk_size=65536):
                                f.write(chunk)
                        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
                            title = clean_url.split("/")[-1] or ("Audio File" if is_direct_audio else "Video File")
                            return tmp_path, title
        except Exception as e:
            logger.debug(f"Direct stream download error: {e}")

        _safe_remove(tmp_path)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 5: Generic HTML5 / Script / m3u8 / Iframe Deep Video Sniffer
    # ─────────────────────────────────────────────────────────────────────────

    async def download_html5_video(self, page_url: str) -> tuple[str, str] | None:
        """Fetches arbitrary webpage, unpacks obfuscated JS, resolves iframes, and extracts media streams."""
        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": page_url
        }
        
        try:
            logger.info(f"Deep sniffing video from webpage: {page_url}")
            def fetch_html(url: str):
                return scraper.get(url, headers=headers, timeout=12)
            
            resp = await asyncio.to_thread(fetch_html, page_url)
            if resp.status_code != 200:
                return None

            html_text = resp.text
            soup = BeautifulSoup(html_text, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.text.strip() if title_tag else "Web Video"

            candidate_streams = []

            # 1. Check OpenGraph / Twitter meta tags
            og_video = (
                soup.find("meta", property="og:video") or 
                soup.find("meta", property="og:video:url") or 
                soup.find("meta", property="og:video:secure_url") or
                soup.find("meta", attrs={"name": "twitter:player:stream"}) or
                soup.find("meta", attrs={"itemprop": "contentUrl"})
            )
            if og_video and og_video.get("content"):
                candidate_streams.append(og_video["content"])

            # 2. Check <video> or <source> tags
            for v_tag in soup.find_all("video"):
                if v_tag.get("src"): candidate_streams.append(v_tag["src"])
                for s in v_tag.find_all("source"):
                    if s.get("src"): candidate_streams.append(s["src"])

            # 3. Extract via Regex & Packed JS Unpacker
            candidate_streams.extend(self._extract_streams_from_text(html_text))

            # 4. If nothing found, check embedded <iframe> tags
            if not candidate_streams:
                for iframe in soup.find_all("iframe"):
                    src = iframe.get("src") or iframe.get("data-src")
                    if src and not any(ad in src.lower() for ad in ["google", "doubleclick", "adservice", "analytics"]):
                        if src.startswith("//"): src = "https:" + src
                        elif src.startswith("/") and not src.startswith("//"):
                            from urllib.parse import urljoin
                            src = urljoin(page_url, src)
                        
                        logger.info(f"Checking embedded iframe player: {src}")
                        try:
                            iframe_resp = await asyncio.to_thread(fetch_html, src)
                            if iframe_resp.status_code == 200:
                                candidate_streams.extend(self._extract_streams_from_text(iframe_resp.text))
                                if candidate_streams: break
                        except Exception as ie:
                            logger.debug(f"Iframe fetch failed: {ie}")

            # 5. Process candidate video streams
            for vid_url in candidate_streams:
                vid_url = vid_url.strip().replace("\\/", "/")
                if not vid_url.startswith("http"): continue
                
                # If HLS (.m3u8), download & mux via yt-dlp with parent referer
                if ".m3u8" in vid_url.lower():
                    logger.info(f"Muxing extracted HLS m3u8 stream: {vid_url} with referer {page_url}")
                    y_res = await self.download_via_ytdlp(vid_url, "video", referer=page_url)
                    if y_res: return y_res

                # If Direct MP4/WebM stream, download via HTTP with referer
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_sniffed_")
                os.close(tmp_fd)

                def stream_dl():
                    req_headers = dict(headers)
                    req_headers["Referer"] = page_url
                    req_headers["Origin"] = "/".join(page_url.split("/")[:3]) if page_url.startswith("http") else page_url
                    r = scraper.get(vid_url, headers=req_headers, stream=True, timeout=120)
                    if r.status_code == 200:
                        with open(tmp_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=65536):
                                f.write(chunk)
                        return True
                    return False

                ok = await asyncio.to_thread(stream_dl)
                if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
                    return tmp_path, title
                _safe_remove(tmp_path)

        except Exception as e:
            logger.debug(f"Deep video sniffer error: {e}")
        return None

    def _extract_streams_from_text(self, text: str) -> list[str]:
        """Finds all potential video stream URLs inside arbitrary HTML/JS."""
        urls = []
        urls.extend(re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|mp4|webm|mov)(?:\?[^\s"\'<>]*)?', text))
        urls.extend(re.findall(r'(?:file|source|src|url|hls|stream)\s*:\s*["\'](https?://[^"\']+)["\']', text, re.IGNORECASE))
        
        # Check for Dean Edwards packed JS
        packed_blocks = re.findall(r"eval\(function\(p,a,c,k,e,d\).*?\.split\('\|'\)\)\)", text)
        for block in packed_blocks:
            unpacked = self._unpack_packer(block)
            if unpacked:
                urls.extend(re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|mp4|webm|mov)(?:\?[^\s"\'<>]*)?', unpacked))
                urls.extend(re.findall(r'(?:file|source|src|url|hls|stream)\s*:\s*["\'](https?://[^"\']+)["\']', unpacked, re.IGNORECASE))

        seen = set()
        cleaned = []
        for u in urls:
            u_clean = u.replace("\\/", "/").strip()
            if u_clean and u_clean not in seen:
                seen.add(u_clean)
                cleaned.append(u_clean)
        return cleaned

    def _unpack_packer(self, packed_js: str) -> str:
        """Unpacks Dean Edwards p,a,c,k,e,d JavaScript obfuscation."""
        match = re.search(r"\}\('(.*)',\s*(\d+),\s*(\d+),\s*'(.*?)'\.split\('\|'\)", packed_js)
        if not match: return ""
        payload, radix_str, count_str, symtab_str = match.groups()
        radix = int(radix_str)
        symtab = symtab_str.split('|')
        
        def unbase(val_str: str) -> int:
            digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            res = 0
            for c in val_str: res = res * radix + digits.find(c)
            return res

        def replace_word(w_match):
            w = w_match.group(0)
            try:
                idx = unbase(w)
                if idx < len(symtab) and symtab[idx]: return symtab[idx]
            except Exception: pass
            return w

        return re.sub(r"\b\w+\b", replace_word, payload)

    # ─────────────────────────────────────────────────────────────────────────
    # UNIVERSAL MASTER PIPELINE
    # ─────────────────────────────────────────────────────────────────────────

    async def download_universal(self, url: str, mode: str = "video") -> dict | None:
        """Universal multi-platform downloader waterfall.
        Returns a dict:
        {
            "file_path": str | None,
            "title": str,
            "direct_url": str | None,
            "type": "video" | "audio" | "document",
            "platform": str,
            "filesize": int
        }
        """
        url_lower = url.lower()
        platform = "Web"

        # 0. Check Direct Media Stream / File URL
        direct_res = await self.download_direct_file(url, mode)
        if direct_res:
            fpath, title = direct_res
            return {
                "file_path": fpath,
                "title": title,
                "direct_url": None,
                "type": "audio" if mode == "audio" or fpath.endswith(".mp3") else "video",
                "platform": "Direct Media",
                "filesize": os.path.getsize(fpath)
            }
        
        # 1. Detect Platform
        if "tiktok.com" in url_lower:
            platform = "TikTok"
            res = await self.download_tiktok_tikwm(url)
            if res:
                fpath, title = res
                return {
                    "file_path": fpath,
                    "title": title,
                    "direct_url": None,
                    "type": "video",
                    "platform": platform,
                    "filesize": os.path.getsize(fpath)
                }

        elif any(d in url_lower for d in ["terabox", "1024tera", "freeterabox", "terasharelink"]):
            platform = "Terabox"
            tera_res = await self.download_terabox(url)
            if tera_res:
                fpath, title, direct_url = tera_res
                return {
                    "file_path": fpath,
                    "title": title,
                    "direct_url": direct_url,
                    "type": "document" if (fpath and not fpath.endswith(".mp4")) else "video",
                    "platform": platform,
                    "filesize": os.path.getsize(fpath) if fpath else 0
                }

        elif any(d in url_lower for d in ["abstream.to", "streamwish", "filemoon", "doodstream", "vidhide"]):
            platform = "Stream Host"
            xfs_res = await self.download_xfs_host(url)
            if xfs_res:
                fpath, title = xfs_res
                return {
                    "file_path": fpath,
                    "title": title,
                    "direct_url": None,
                    "type": "video",
                    "platform": platform,
                    "filesize": os.path.getsize(fpath)
                }

        elif "instagram.com" in url_lower:
            platform = "Instagram"
        elif "facebook.com" in url_lower or "fb.watch" in url_lower:
            platform = "Facebook"
        elif "twitter.com" in url_lower or "x.com" in url_lower:
            platform = "Twitter/X"
        elif "reddit.com" in url_lower:
            platform = "Reddit"
        elif "pinterest.com" in url_lower or "pin.it" in url_lower:
            platform = "Pinterest"
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            platform = "YouTube"
            if mode == "audio":
                cnv_res = await self.download_via_cnv(url, "audio")
                if cnv_res:
                    fpath, title = cnv_res
                    return {
                        "file_path": fpath,
                        "title": title,
                        "direct_url": None,
                        "type": "audio",
                        "platform": platform,
                        "filesize": os.path.getsize(fpath)
                    }

        # 2. Try Cobalt Multi-Node Relay
        cobalt_res = await self.download_via_cobalt(url, mode)
        if cobalt_res:
            fpath, title = cobalt_res
            return {
                "file_path": fpath,
                "title": title,
                "direct_url": None,
                "type": "audio" if mode == "audio" else "video",
                "platform": platform,
                "filesize": os.path.getsize(fpath)
            }

        # 3. Try Universal yt-dlp Engine (1800+ websites)
        ytdlp_res = await self.download_via_ytdlp(url, mode)
        if ytdlp_res:
            fpath, title = ytdlp_res
            return {
                "file_path": fpath,
                "title": title,
                "direct_url": None,
                "type": "audio" if mode == "audio" else "video",
                "platform": platform,
                "filesize": os.path.getsize(fpath)
            }

        # 4. Try Generic HTML5 Video Sniffer
        html5_res = await self.download_html5_video(url)
        if html5_res:
            fpath, title = html5_res
            return {
                "file_path": fpath,
                "title": title,
                "direct_url": None,
                "type": "video",
                "platform": platform,
                "filesize": os.path.getsize(fpath)
            }

        return None


def _safe_remove(path: str):
    """Silently remove a file if it exists."""
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass
