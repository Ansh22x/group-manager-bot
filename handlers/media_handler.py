import os
import logging
import asyncio
import urllib.request
import ssl
import httpx
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
    # Cobalt API Download Core
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_cobalt_endpoints(self) -> list[str]:
        """Fetches online YouTube API endpoints dynamically from cobalt.directory registry."""
        default = [self.cached_cobalt] + COBALT_DEFAULT_APIS if self.cached_cobalt else COBALT_DEFAULT_APIS
        seen = set()
        endpoints = [x for x in default if x and not (x in seen or seen.add(x))]
        try:
            async with httpx.AsyncClient(timeout=6, verify=False) as client:
                r = await client.get("https://cobalt.directory/api/working?type=api")
                if r.status_code == 200:
                    apis = r.json().get("data", {}).get("youtube", [])
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
        
        for api in endpoints:
            api_endpoint = f"{api.rstrip('/')}/"
            try:
                logger.info(f"Trying Cobalt endpoint: {api_endpoint}")
                async with httpx.AsyncClient(timeout=10, verify=False) as client:
                    r = await client.post(api_endpoint, json=payload, headers=headers)
                    if r.status_code == 200:
                        data = r.json()
                        status = data.get("status")
                        dl_url = data.get("url")
                        if dl_url and status in ("redirect", "stream", "tunnel"):
                            # Download stream file
                            filename = f"dl_{mode}_{int(asyncio.get_event_loop().time())}." + ("mp3" if mode == "audio" else "mp4")
                            async with httpx.AsyncClient(timeout=90, follow_redirects=True, verify=False) as dl_client:
                                async with dl_client.stream("GET", dl_url) as response:
                                    if response.status_code == 200:
                                        with open(filename, "wb") as fh:
                                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                                fh.write(chunk)
                                        
                                        if os.path.exists(filename) and os.path.getsize(filename) > 10000:
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

            # TIER 1: Cobalt Downloader (YouTube and others)
            if not is_sc_url:
                await status.edit_text("🎵 *Fetching from YouTube...*", parse_mode="Markdown")
                resolved = await self._resolve_youtube_url(query)
                if resolved:
                    yt_url, yt_title = resolved
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

            # TIER 2: SoundCloud Fallback
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

            # TIER 1: Cobalt Downloader
            await status.edit_text("🎥 *Fetching from YouTube...*", parse_mode="Markdown")
            resolved = await self._resolve_youtube_url(query)
            if resolved:
                yt_url, yt_title = resolved
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
                results.append(f"✅ Invidious search resolved to: `{res[0]}`")
            else:
                results.append("❌ Invidious search returned None")
        except Exception as e:
            results.append(f"❌ Invidious search error: `{str(e)[:60]}`")
            
        # Test Cobalt API
        try:
            endpoints = await self._get_cobalt_endpoints()
            results.append(f"ℹ️ Found `{len(endpoints)}` Cobalt endpoints in directory")
            test_res = await self._download_via_cobalt("https://www.youtube.com/watch?v=s7-GTShjcqY", "audio")
            if test_res:
                results.append(f"✅ Cobalt download success: `{test_res[1]}`")
                if os.path.exists(test_res[0]): os.remove(test_res[0])
            else:
                results.append("❌ Cobalt download returned None")
        except Exception as e:
            results.append(f"❌ Cobalt error: `{str(e)[:60]}`")
            
        await status.edit_text("\n".join(results), parse_mode="Markdown")
