import os
import logging
import asyncio
import urllib.request
import ssl
import httpx
import re
import cloudscraper
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
import yt_dlp

logger = logging.getLogger(__name__)

# Search nodes (to resolve search query to a YT video ID)
INVIDIOUS_SEARCH_INSTANCES = [
    "https://invidious.flokinet.to",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de"
]

# Static fallback API URLs for Cobalt (Turnstile-free)
COBALT_DEFAULT_APIS = [
    "https://api.cobalt.liubquanti.click",
    "https://cobaltapi.cjs.nz"
]


class MediaHandler(BaseHandler):
    def __init__(self):
        self.cached_proxy = None
        self.cached_cobalt = "https://api.cobalt.liubquanti.click"
        self.cached_invidious = "https://invidious.flokinet.to"
        self.download_semaphore = asyncio.Semaphore(5)

    def register(self, app: Application):
        app.add_handler(CommandHandler("play", self.play_cmd))
        app.add_handler(CommandHandler("video", self.video_cmd))
        app.add_handler(CommandHandler("ytest", self.ytest_cmd))
        app.add_handler(CommandHandler("draw", self.draw_cmd))

    async def play_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        if not context.args:
            await update.message.reply_text("Usage: `/play [song name or YouTube/SoundCloud link]`", parse_mode="Markdown")
            return
        asyncio.create_task(self._do_play(update, context))

    async def video_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        if not context.args:
            await update.message.reply_text("Usage: `/video [video name or YouTube link]`", parse_mode="Markdown")
            return
        asyncio.create_task(self._do_video(update, context))

    # ─────────────────────────────────────────────────────────────────────────
    # Search Resolver
    # ─────────────────────────────────────────────────────────────────────────

    async def _resolve_youtube_url(self, query: str) -> tuple[str, str] | None:
        """Resolves query string to YouTube URL using working search nodes.
        Returns (youtube_url, title) or None."""
        if "youtube.com" in query or "youtu.be" in query:
            return query, "YouTube Link"
            
        instances = [self.cached_invidious] + INVIDIOUS_SEARCH_INSTANCES
        # remove duplicates preserving order
        seen = set()
        instances = [x for x in instances if x and not (x in seen or seen.add(x))]
        
        for instance in instances:
            try:
                async with httpx.AsyncClient(timeout=8, verify=False) as client:
                    r = await client.get(
                        f"{instance}/api/v1/search",
                        params={"q": query, "type": "video", "fields": "videoId,title"}
                    )
                    if r.status_code == 200:
                        results = r.json()
                        if results:
                            self.cached_invidious = instance
                            vid_id = results[0]["videoId"]
                            title = results[0]["title"]
                            return f"https://www.youtube.com/watch?v={vid_id}", title
            except Exception as e:
                logger.debug(f"Search failed on {instance}: {e}")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # cnv.cx Downloader (Tier 1 Primary Strategy)
    # ─────────────────────────────────────────────────────────────────────────

    async def _download_via_cnv(self, target_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads direct stream via cnv.cx + cloudscraper (bypasses YT cloud blocks).
        Returns (local_file_path, title) or None."""
        video_id = None
        patterns = [
            r"v=([^&]+)",
            r"youtu\.be/([^?]+)",
            r"embed/([^?]+)",
            r"v/([^?]+)"
        ]
        for pattern in patterns:
            m = re.search(pattern, target_url)
            if m:
                video_id = m.group(1)
                break
                
        if not video_id:
            return None
            
        headers = {
            "Accept": "*/*",
            "Origin": "https://iframe.y2meta-uk.com",
            "Referer": "https://iframe.y2meta-uk.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            logger.info(f"Trying cnv.cx download pipeline for video_id: {video_id}")
            scraper = cloudscraper.create_scraper()
            
            # Step 1: Get Key
            def get_key():
                r = scraper.get(f"https://cnv.cx/v2/sanity/key?id={video_id}", headers=headers, timeout=10)
                if r.status_code == 200:
                    return r.json().get("key")
                return None
                
            key = await asyncio.to_thread(get_key)
            if not key:
                logger.debug("Failed to obtain cnv.cx sanity key")
                return None
                
            # Step 2: Post to converter
            payload = {
                "link": f"https://youtu.be/{video_id}",
                "format": "mp3" if mode == "audio" else "mp4",
                "audioBitrate": "128",
                "videoQuality": "720",
                "vCodec": "h264",
                "filenameStyle": "pretty"
            }
            
            headers_post = headers.copy()
            headers_post["key"] = key
            
            def do_convert():
                r = scraper.post("https://cnv.cx/v2/converter", json=payload, headers=headers_post, timeout=15)
                if r.status_code == 200:
                    return r.json()
                return None
                
            data = await asyncio.to_thread(do_convert)
            if not data or data.get("status") != "tunnel":
                logger.debug(f"cnv.cx converter returned non-tunnel status: {data}")
                return None
                
            dl_url = data.get("url")
            title = data.get("filename", "Audio Track" if mode == "audio" else "Video Clip")
            title = os.path.splitext(title)[0]
            
            # Step 3: Stream download using cloudscraper
            filename = f"dl_{mode}_{int(asyncio.get_event_loop().time())}." + ("mp3" if mode == "audio" else "mp4")
            
            def do_download():
                resp = scraper.get(dl_url, headers={"Referer": "https://iframe.y2meta-uk.com/"}, stream=True, timeout=90)
                if resp.status_code == 200:
                    with open(filename, "wb") as fh:
                        for chunk in resp.iter_content(chunk_size=65536):
                            fh.write(chunk)
                    return True
                return False
                
            success = await asyncio.to_thread(do_download)
            if success and os.path.exists(filename) and os.path.getsize(filename) > 10000:
                logger.info(f"cnv.cx download successful: {title}")
                return filename, title
                
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            logger.debug(f"cnv.cx download pipeline failed: {e}")
            
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Cobalt API Downloader (Tier 2 Secondary Fallback Strategy)
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_cobalt_endpoints(self) -> list[str]:
        """Fetches online YouTube API endpoints dynamically from cobalt.directory registry using cloudscraper."""
        default = [self.cached_cobalt] + COBALT_DEFAULT_APIS if self.cached_cobalt else COBALT_DEFAULT_APIS
        seen = set()
        endpoints = [x for x in default if x and not (x in seen or seen.add(x))]
        try:
            scraper = cloudscraper.create_scraper()
            def fetch_api():
                r = scraper.get("https://cobalt.directory/api/working?type=api", timeout=8)
                if r.status_code == 200:
                    return r.json().get("data", {}).get("youtube", [])
                return []
            apis = await asyncio.to_thread(fetch_api)
            # Append fetched ones to default order
            for api in apis:
                api_clean = api.rstrip('/')
                if api_clean not in seen:
                    endpoints.append(api_clean)
                    seen.add(api_clean)
        except Exception as e:
            logger.warning(f"Failed to fetch cobalt directory: {e}")
        return endpoints

    async def _download_via_cobalt(self, target_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads direct stream via Cobalt API instances (bypasses YT cloud blocks).
        Returns (local_file_path, title) or None."""
        endpoints = await self._get_cobalt_endpoints()
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
        
        for api in endpoints:
            api_endpoint = f"{api.rstrip('/')}/"
            try:
                logger.info(f"Trying Cobalt endpoint: {api_endpoint}")
                def post_cobalt():
                    return scraper.post(api_endpoint, json=payload, headers=headers, timeout=12)
                r = await asyncio.to_thread(post_cobalt)
                if r.status_code == 200:
                    data = r.json()
                    status = data.get("status")
                    dl_url = data.get("url")
                    if dl_url and status in ("redirect", "stream", "tunnel"):
                        # Download stream file
                        filename = f"dl_{mode}_{int(asyncio.get_event_loop().time())}." + ("mp3" if mode == "audio" else "mp4")
                        
                        def get_stream():
                            resp = scraper.get(dl_url, stream=True, timeout=90)
                            if resp.status_code == 200:
                                with open(filename, "wb") as fh:
                                    for chunk in resp.iter_content(chunk_size=65536):
                                        fh.write(chunk)
                                return True
                            return False
                            
                        success = await asyncio.to_thread(get_stream)
                        if success and os.path.exists(filename) and os.path.getsize(filename) > 10000:
                            self.cached_cobalt = api
                            title = data.get("filename", "Audio Track" if mode == "audio" else "Video Clip")
                            title = os.path.splitext(title)[0]
                            return filename, title
                        if os.path.exists(filename):
                            os.remove(filename)
                elif r.status_code == 400 and "jwt.missing" in r.text:
                    # Turnstile protected, skip silently
                    continue
            except Exception as e:
                logger.debug(f"Cobalt attempt failed on {api}: {e}")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Public Handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _do_play(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎵 *Searching YouTube...*", parse_mode="Markdown")

            is_yt_url = "youtube.com" in query or "youtu.be" in query
            is_sc_url = "soundcloud.com" in query

            # TIER 1: YouTube Downloader (YouTube and others)
            if not is_sc_url:
                await status.edit_text("🎵 *Fetching from YouTube...*", parse_mode="Markdown")
                resolved = await self._resolve_youtube_url(query)
                if resolved:
                    yt_url, yt_title = resolved
                    
                    # Try cnv.cx downloader first (Tier 1)
                    result = await self._download_via_cnv(yt_url, "audio")
                    if not result:
                        # Try Cobalt downloader second (Tier 2 fallback)
                        result = await self._download_via_cobalt(yt_url, "audio")
                        
                    if result:
                        file_path, title = result
                        try:
                            await update.message.reply_audio(
                                audio=open(file_path, 'rb'),
                                title=title,
                                performer="YouTube"
                            )
                            os.remove(file_path)
                            await status.delete()
                            return
                        except Exception as e:
                            logger.warning(f"Audio upload failed: {e}")
                            if os.path.exists(file_path): os.remove(file_path)

            # TIER 3: SoundCloud Fallback
            if not is_yt_url:
                await status.edit_text("🎵 *Searching SoundCloud...*", parse_mode="Markdown")
                sc_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': '%(id)s.%(ext)s',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                    'noplaylist': True,
                    'socket_timeout': 30,
                    'retries': 2,
                    'quiet': True,
                }
                ffmpeg_dir = './'
                if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
                    ffmpeg_dir = None
                if ffmpeg_dir:
                    sc_opts['ffmpeg_location'] = ffmpeg_dir
                
                sc_query = query if is_sc_url else f"scsearch1:{query}"
                try:
                    with yt_dlp.YoutubeDL(sc_opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, sc_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if info:
                            file_path = f"{info['id']}.mp3"
                            if os.path.exists(file_path):
                                await update.message.reply_audio(
                                    audio=open(file_path, 'rb'),
                                    title=info.get('title', 'Unknown'),
                                    performer=info.get('uploader', 'SoundCloud')
                                )
                                os.remove(file_path)
                                await status.delete()
                                logger.info(f"SoundCloud success: {info.get('title')}")
                                return
                except Exception as e:
                    logger.info(f"SoundCloud failed: {str(e)[:100]}")

            await status.edit_text(
                "❌ *Could not download this track.*\n\n"
                "💡 *Try*: different song name, SoundCloud link, or direct video URL.",
                parse_mode="Markdown"
            )

    async def _do_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎥 *Searching YouTube...*", parse_mode="Markdown")

            # TIER 1: YouTube Downloader
            await status.edit_text("🎥 *Fetching from YouTube...*", parse_mode="Markdown")
            resolved = await self._resolve_youtube_url(query)
            if resolved:
                yt_url, yt_title = resolved
                
                # Try cnv.cx downloader first (Tier 1)
                result = await self._download_via_cnv(yt_url, "video")
                if not result:
                    # Try Cobalt downloader second (Tier 2 fallback)
                    result = await self._download_via_cobalt(yt_url, "video")
                    
                if result:
                    file_path, title = result
                    try:
                        if os.path.getsize(file_path) > 50 * 1024 * 1024:
                            await status.edit_text("❌ Video exceeds Telegram's 50MB limit.")
                            os.remove(file_path)
                            return
                            
                        await update.message.reply_video(video=open(file_path, 'rb'), caption=title)
                        os.remove(file_path)
                        await status.delete()
                        return
                    except Exception as e:
                        logger.warning(f"Video upload failed: {e}")
                        if os.path.exists(file_path): os.remove(file_path)

            await status.edit_text(
                "❌ *YouTube video download failed.*\n\n"
                "💡 Try searching another video keyword or paste a direct YouTube link.",
                parse_mode="Markdown"
            )

    async def ytest_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        status = await update.message.reply_text("🔬 *Testing Cobalt endpoints & search...*", parse_mode="Markdown")
        results = []
        
        # Test Invidious search
        try:
            res = await self._resolve_youtube_url("alan walker darkside")
            if res:
                results.append(f"`[OK] Search Resolved`: `{res[0]}`")
            else:
                results.append("`[FAIL] Search returned None`")
        except Exception as e:
            results.append(f"`[FAIL] Search Error`: `{str(e)[:60]}`")
            
        # Test cnv.cx Downloader
        try:
            test_res = await self._download_via_cnv("https://www.youtube.com/watch?v=s7-GTShjcqY", "audio")
            if test_res:
                results.append(f"`[OK] cnv.cx Download`: `{test_res[1]}`")
                if os.path.exists(test_res[0]): os.remove(test_res[0])
            else:
                results.append("`[FAIL] cnv.cx Download returned None`")
        except Exception as e:
            results.append(f"`[FAIL] cnv.cx Error`: `{str(e)[:60]}`")
            
        # Test Cobalt API
        try:
            endpoints = await self._get_cobalt_endpoints()
            results.append(f"`[INFO] Cobalt endpoints count`: `{len(endpoints)}`")
            test_res = await self._download_via_cobalt("https://www.youtube.com/watch?v=s7-GTShjcqY", "audio")
            if test_res:
                results.append(f"`[OK] Cobalt Download`: `{test_res[1]}`")
                if os.path.exists(test_res[0]): os.remove(test_res[0])
            else:
                results.append("`[FAIL] Cobalt Download returned None`")
        except Exception as e:
            results.append(f"`[FAIL] Cobalt Error`: `{str(e)[:60]}`")
            
        await status.edit_text("\n".join(results), parse_mode="Markdown")

    async def draw_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        if not context.args:
            await update.message.reply_text("Usage: `/draw [prompt describing the image]`", parse_mode="Markdown")
            return
        asyncio.create_task(self._do_draw(update, context))

    async def _do_draw(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        prompt = " ".join(context.args)
        status = await update.message.reply_text("🎨 *Drawing... please wait...*", parse_mode="Markdown")
        
        success = False
        filename = f"gen_{int(asyncio.get_event_loop().time())}.jpg"
        
        # Tier 1: Try Perchance
        try:
            logger.info("Attempting Perchance image generation...")
            from perchance import ImageGenerator
            async with ImageGenerator() as gen:
                result = await gen.image(prompt, shape='square')
                binary = await result.download()
                with open(filename, "wb") as f:
                    f.write(binary.read())
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                success = True
                logger.info("Perchance image generation successful!")
        except Exception as e:
            logger.warning(f"Perchance image generation failed: {e}. Falling back to Pollinations.ai...")
            
        # Tier 2: Try Pollinations.ai (Fallback)
        if not success:
            try:
                import urllib.parse
                encoded_prompt = urllib.parse.quote(prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                logger.info(f"Attempting Pollinations.ai image generation from: {url}")
                
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, timeout=40)
                    if response.status_code == 200:
                        with open(filename, "wb") as f:
                            f.write(response.content)
                        if os.path.exists(filename) and os.path.getsize(filename) > 0:
                            success = True
                            logger.info("Pollinations.ai image generation successful!")
            except Exception as pe:
                logger.error(f"Pollinations.ai image generation failed: {pe}")

        if success:
            try:
                await status.delete()
                with open(filename, "rb") as photo_fh:
                    await update.message.reply_photo(photo=photo_fh, caption=f"🎨 <b>Generated Image</b>\n\nPrompt: <code>{prompt}</code>", parse_mode="HTML")
            except Exception as se:
                logger.error(f"Failed to send image: {se}")
                await status.edit_text("❌ Failed to send generated image.")
            finally:
                if os.path.exists(filename):
                    try: os.remove(filename)
                    except Exception: pass
        else:
            await status.edit_text("❌ Image generation failed on all pipelines.")
