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

# Invidious public instances (residential/non-datacenter IPs — never blocked by YT)
INVIDIOUS_INSTANCES = [
    "https://inv.riverside.rocks",
    "https://invidious.nerdvpn.de",
    "https://yt.artemislena.eu",
    "https://inv.tux.pizza",
    "https://invidious.flokinet.to",
    "https://vid.puffyan.us",
    "https://invidious.privacyredirect.com",
    "https://iv.melmac.space",
]


class MediaHandler(BaseHandler):
    def __init__(self):
        self.cached_proxy = None
        self.cached_invidious = None  # last working Invidious instance
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

    async def _invidious_search(self, query: str):
        """Search YouTube via Invidious API. Returns (video_id, title) or None."""
        instances = ([self.cached_invidious] + INVIDIOUS_INSTANCES) if self.cached_invidious else INVIDIOUS_INSTANCES
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            for instance in instances:
                try:
                    r = await client.get(
                        f"{instance}/api/v1/search",
                        params={"q": query, "type": "video", "fields": "videoId,title"}
                    )
                    if r.status_code == 200:
                        results = r.json()
                        if results:
                            self.cached_invidious = instance
                            return results[0]["videoId"], results[0]["title"]
                except Exception as e:
                    logger.debug(f"Invidious search failed on {instance}: {e}")
        return None

    async def _download_via_invidious(self, video_id: str, mode: str, ffmpeg_dir):
        """Download via Invidious watch URL (bypasses YouTube datacenter IP block).
        Returns (file_path, title) or None."""
        instances = ([self.cached_invidious] + INVIDIOUS_INSTANCES) if self.cached_invidious else INVIDIOUS_INSTANCES
        base_opts = {
            'outtmpl': '%(id)s.%(ext)s',
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 1,
            'quiet': True,
            'no_warnings': True,
        }
        if ffmpeg_dir:
            base_opts['ffmpeg_location'] = ffmpeg_dir
        if mode == "audio":
            base_opts['format'] = 'bestaudio/best'
            base_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        else:
            base_opts['format'] = 'best[ext=mp4][filesize<50M]/best[filesize<50M]/best[height<=720]'

        for instance in instances:
            invidious_url = f"{instance}/watch?v={video_id}"
            try:
                with yt_dlp.YoutubeDL({**base_opts}) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, invidious_url, download=True)
                    if not info:
                        continue
                    title = info.get('title', 'Unknown')
                if mode == "audio":
                    file_path = f"{video_id}.mp3"
                    if not os.path.exists(file_path):
                        file_path = next((f for f in os.listdir('.') if f.startswith(video_id) and f.endswith('.mp3')), None)
                else:
                    file_path = None
                    for ext in ('mp4', 'webm', 'mkv'):
                        p = f"{video_id}.{ext}"
                        if os.path.exists(p):
                            file_path = p
                            break
                    if not file_path:
                        file_path = next((f for f in os.listdir('.') if f.startswith(video_id)), None)
                if file_path and os.path.exists(file_path):
                    self.cached_invidious = instance
                    logger.info(f"Invidious success via {instance}: {title}")
                    return file_path, title
            except Exception as e:
                logger.info(f"Invidious {instance} failed for {video_id}: {str(e)[:100]}")
        return None

    async def _do_play(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tier 1: Invidious (YouTube bypass), Tier 2: SoundCloud, Tier 3: direct YT rotation"""
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎵 *Searching YouTube...*", parse_mode="Markdown")

            ffmpeg_dir = './'
            if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
                ffmpeg_dir = None

            is_yt_url = "youtube.com" in query or "youtu.be" in query
            is_sc_url = "soundcloud.com" in query

            yt_video_id = None
            if is_yt_url:
                if "v=" in query:
                    yt_video_id = query.split("v=")[1].split("&")[0].split("?")[0]
                elif "youtu.be/" in query:
                    yt_video_id = query.split("youtu.be/")[1].split("?")[0]

            # TIER 1: Invidious
            if not is_sc_url:
                await status.edit_text("🎵 *Fetching from YouTube...*", parse_mode="Markdown")
                if yt_video_id:
                    vid_id = yt_video_id
                else:
                    result = await self._invidious_search(query)
                    vid_id = result[0] if result else None

                if vid_id:
                    result = await self._download_via_invidious(vid_id, "audio", ffmpeg_dir)
                    if result:
                        file_path, title = result
                        try:
                            await update.message.reply_audio(audio=open(file_path, 'rb'), title=title, performer="YouTube")
                            os.remove(file_path)
                            await status.delete()
                            return
                        except Exception as e:
                            logger.warning(f"Send audio failed: {e}")
                            if os.path.exists(file_path): os.remove(file_path)

            # TIER 2: SoundCloud
            if not is_yt_url:
                await status.edit_text("🎵 *Searching SoundCloud...*", parse_mode="Markdown")
                sc_opts = {
                    'format': 'bestaudio/best', 'outtmpl': '%(id)s.%(ext)s',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                    'noplaylist': True, 'socket_timeout': 30, 'retries': 2, 'quiet': True,
                }
                if ffmpeg_dir: sc_opts['ffmpeg_location'] = ffmpeg_dir
                sc_query = query if is_sc_url else f"scsearch1:{query}"
                try:
                    with yt_dlp.YoutubeDL(sc_opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, sc_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if info:
                            file_path = f"{info['id']}.mp3"
                            if os.path.exists(file_path):
                                await update.message.reply_audio(audio=open(file_path, 'rb'), title=info.get('title', 'Unknown'), performer=info.get('uploader', 'SoundCloud'))
                                os.remove(file_path)
                                await status.delete()
                                logger.info(f"SoundCloud success: {info.get('title')}")
                                return
                except Exception as e:
                    logger.info(f"SoundCloud failed: {str(e)[:100]}")

            # TIER 3: direct yt-dlp player rotation
            await status.edit_text("🎵 *Trying alternate YouTube access...*", parse_mode="Markdown")
            search_query = query if query.startswith("http") else f"ytsearch1:{query}"
            for clients in [['android_music'], ['tv_embedded'], ['ios']]:
                try:
                    opts = {
                        'format': 'bestaudio/best', 'outtmpl': '%(id)s.%(ext)s',
                        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                        'extractor_args': {'youtube': {'player_client': clients}},
                        'noplaylist': True, 'socket_timeout': 20, 'retries': 1, 'quiet': True,
                    }
                    if ffmpeg_dir: opts['ffmpeg_location'] = ffmpeg_dir
                    if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if info:
                            file_path = f"{info.get('id', 'unknown')}.mp3"
                            if os.path.exists(file_path):
                                await update.message.reply_audio(audio=open(file_path, 'rb'), title=info.get('title', 'Unknown'), performer=info.get('uploader', 'YouTube'))
                                os.remove(file_path)
                                await status.delete()
                                return
                except Exception as e:
                    logger.info(f"Direct YT client {clients} failed: {str(e)[:80]}")

            await status.edit_text(
                "❌ *Could not download this track.*\n\n"
                "💡 *Try*: different song name, SoundCloud link, or add `cookies.txt` to Render Secret Files",
                parse_mode="Markdown"
            )

    async def _do_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tier 1: Invidious (YouTube bypass), Tier 2: direct YT rotation, Tier 3: Proxy"""
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎥 *Searching YouTube...*", parse_mode="Markdown")

            ffmpeg_dir = './'
            if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
                ffmpeg_dir = None

            is_yt_url = "youtube.com" in query or "youtu.be" in query
            yt_video_id = None
            if is_yt_url:
                if "v=" in query:
                    yt_video_id = query.split("v=")[1].split("&")[0].split("?")[0]
                elif "youtu.be/" in query:
                    yt_video_id = query.split("youtu.be/")[1].split("?")[0]

            async def _send_video(file_path, title) -> bool:
                if not file_path or not os.path.exists(file_path): return False
                if os.path.getsize(file_path) > 50 * 1024 * 1024:
                    await status.edit_text("❌ Video exceeds Telegram's 50MB limit.")
                    os.remove(file_path)
                    return True
                await update.message.reply_video(video=open(file_path, 'rb'), caption=title)
                os.remove(file_path)
                await status.delete()
                return True

            # TIER 1: Invidious
            await status.edit_text("🎥 *Fetching from YouTube...*", parse_mode="Markdown")
            if yt_video_id:
                vid_id = yt_video_id
            else:
                result = await self._invidious_search(query)
                vid_id = result[0] if result else None

            if vid_id:
                result = await self._download_via_invidious(vid_id, "video", ffmpeg_dir)
                if result:
                    file_path, title = result
                    if await _send_video(file_path, title):
                        return

            # TIER 2: direct yt-dlp player rotation
            await status.edit_text("🎥 *Trying alternate YouTube access...*", parse_mode="Markdown")
            search_query = query if query.startswith("http") else f"ytsearch1:{query}"
            for clients in [['android_music'], ['tv_embedded'], ['ios'], ['mweb']]:
                try:
                    opts = {
                        'format': 'best[ext=mp4][filesize<50M]/best[filesize<50M]/best[height<=720]',
                        'outtmpl': '%(id)s.%(ext)s',
                        'extractor_args': {'youtube': {'player_client': clients}},
                        'noplaylist': True, 'socket_timeout': 20, 'retries': 1, 'quiet': True,
                    }
                    if ffmpeg_dir: opts['ffmpeg_location'] = ffmpeg_dir
                    if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if info:
                            vid_id2 = info.get('id', 'unknown')
                            title2 = info.get('title', 'Video')
                            fp = None
                            for ext in ('mp4', 'webm', 'mkv'):
                                p = f"{vid_id2}.{ext}"
                                if os.path.exists(p): fp = p; break
                            if not fp:
                                fp = next((f for f in os.listdir('.') if f.startswith(vid_id2)), None)
                            if await _send_video(fp, title2):
                                return
                except Exception as e:
                    logger.info(f"Video direct YT client {clients} failed: {str(e)[:80]}")

            # TIER 3: Proxy
            await status.edit_text("🎥 *Trying proxy connection...*", parse_mode="Markdown")
            proxy_url = await self.get_working_proxy()
            if proxy_url:
                try:
                    opts = {
                        'format': 'best[ext=mp4][filesize<50M]/best[filesize<50M]/best[height<=720]',
                        'outtmpl': '%(id)s.%(ext)s',
                        'extractor_args': {'youtube': {'player_client': ['android']}},
                        'noplaylist': True, 'proxy': proxy_url, 'socket_timeout': 30, 'retries': 1, 'quiet': True,
                    }
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if info:
                            vid_id3 = info.get('id', 'unknown')
                            fp = next((f for f in os.listdir('.') if f.startswith(vid_id3)), None)
                            if await _send_video(fp, info.get('title', 'Video')):
                                return
                except Exception as e:
                    logger.warning(f"Video proxy failed: {str(e)[:100]}")

            await status.edit_text(
                "❌ *YouTube video download blocked.*\n\n"
                "💡 Mount a `cookies.txt` in Render → Environment → Secret Files to fix permanently.",
                parse_mode="Markdown"
            )

    async def test_single_proxy(self, proxy_url: str, video_id: str) -> str:
        ydl_opts = {'proxy': proxy_url, 'socket_timeout': 4, 'retries': 0, 'quiet': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await asyncio.to_thread(ydl.extract_info, video_id, download=False)
            return proxy_url
        except Exception:
            return None

    async def get_working_proxy(self, video_id: str = "bW5SQdPSilE") -> str:
        if self.cached_proxy:
            if await self.test_single_proxy(self.cached_proxy, video_id):
                return self.cached_proxy
            self.cached_proxy = None
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=800&country=all&ssl=all&anonymity=all"
        ctx = ssl._create_unverified_context()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res_body = await asyncio.to_thread(urllib.request.urlopen, req, context=ctx, timeout=4)
            proxies = [p.strip() for p in res_body.read().decode('utf-8').split('\n') if p.strip()]
            tasks = [self.test_single_proxy(f"http://{proxy}", video_id) for proxy in proxies[:12]]
            for res in await asyncio.gather(*tasks):
                if res:
                    self.cached_proxy = res
                    return res
        except Exception as e:
            logger.error(f"Failed to fetch proxies: {e}")
        return None

    async def ytest_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        status = await update.message.reply_text("🔬 *Testing Invidious instances + YT clients...*", parse_mode="Markdown")
        results = []
        async with httpx.AsyncClient(timeout=6) as client:
            for instance in INVIDIOUS_INSTANCES[:4]:
                try:
                    r = await client.get(f"{instance}/api/v1/search", params={"q": "test", "type": "video", "fields": "videoId"})
                    results.append(f"{'✅' if r.status_code == 200 else '❌'} Invidious `{instance.split('//')[1]}`: {r.status_code}")
                except Exception as e:
                    results.append(f"❌ Invidious `{instance.split('//')[1]}`: {str(e)[:60]}")
        for name, clients in [('android_music', ['android_music']), ('tv_embedded', ['tv_embedded']), ('mweb', ['mweb'])]:
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'extractor_args': {'youtube': {'player_client': clients}}, 'socket_timeout': 8}) as ydl:
                    ydl.extract_info("bW5SQdPSilE", download=False)
                results.append(f"✅ YT client `{name}`")
            except Exception as e:
                results.append(f"❌ YT client `{name}`: {str(e)[:60]}")
        await status.edit_text("\n".join(results), parse_mode="Markdown")
