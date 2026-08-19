import os
import logging
import asyncio
import urllib.request
import json
import ssl
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
import yt_dlp

logger = logging.getLogger(__name__)

class MediaHandler(BaseHandler):
    def __init__(self):
        self.cached_proxy = None
        # Cap concurrent downloads at 5 to stay within Render's free 512MB RAM
        self.download_semaphore = asyncio.Semaphore(5)

    def register(self, app: Application):
        app.add_handler(CommandHandler("play", self.play_cmd))
        app.add_handler(CommandHandler("video", self.video_cmd))
        app.add_handler(CommandHandler("ytest", self.ytest_cmd))

    async def play_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Thin wrapper — immediately acknowledges the request and spawns a background download task."""
        if not update.message: return
        if not context.args:
            await update.message.reply_text("Usage: `/play [song name or link]`", parse_mode="Markdown")
            return
        asyncio.create_task(self._do_play(update, context))

    async def video_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Thin wrapper — immediately acknowledges the request and spawns a background download task."""
        if not update.message: return
        if not context.args:
            await update.message.reply_text("Usage: `/video [video name or link]`", parse_mode="Markdown")
            return
        asyncio.create_task(self._do_video(update, context))

    async def _do_play(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Background coroutine: 3-tier audio download. Runs under Semaphore(5).
        Tier 1: Direct download via player client rotation (fastest, no proxy needed)
        Tier 2: Proxy download (if datacenter IP is blocked by YouTube's main API)
        Tier 3: SoundCloud fallback (always works, unlimited bandwidth)
        """
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎵 *Searching...*", parse_mode="Markdown")

            # FFmpeg location check
            ffmpeg_dir = './'
            if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
                ffmpeg_dir = None

            search_query = query if query.startswith("http") else f"ytsearch1:{query}"

            def _make_audio_opts(player_clients, proxy=None, cookies=None):
                opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': '%(id)s.%(ext)s',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                    'extractor_args': {'youtube': {'player_client': player_clients}},
                    'noplaylist': True,
                    'socket_timeout': 60,
                    'retries': 2,
                    'quiet': True,
                    'no_warnings': True,
                }
                if proxy:
                    opts['proxy'] = proxy
                if cookies:
                    opts['cookiefile'] = cookies
                if ffmpeg_dir:
                    opts['ffmpeg_location'] = ffmpeg_dir
                return opts

            # ── TIER 1: Direct download, player client rotation ───────────────
            await status.edit_text("🎵 *Downloading audio...*", parse_mode="Markdown")
            tier1_clients = [
                ['android_music'],   # Android Music app — different quota, often bypasses datacenter block
                ['tv_embedded'],     # YouTube TV embedded — relaxed restrictions
                ['mweb'],            # Mobile web — lighter fingerprint
            ]
            video_id = None
            video_title = "Unknown Title"
            video_uploader = "Unknown Artist"
            youtube_success = False

            for clients in tier1_clients:
                try:
                    opts = _make_audio_opts(clients, cookies='cookies.txt' if os.path.exists('cookies.txt') else None)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if not info:
                            continue
                        video_id = info.get('id', 'unknown')
                        video_title = info.get('title', 'Unknown Title')
                        video_uploader = info.get('uploader', 'Unknown Artist')
                    file_path = f"{video_id}.mp3"
                    if os.path.exists(file_path):
                        await update.message.reply_audio(
                            audio=open(file_path, 'rb'),
                            title=video_title,
                            performer=video_uploader
                        )
                        os.remove(file_path)
                        await status.delete()
                        youtube_success = True
                        logger.info(f"Tier 1 success with client {clients}: {video_title}")
                        break
                except Exception as e:
                    logger.info(f"Tier 1 client {clients} failed: {str(e)[:100]}")
                    continue

            if youtube_success:
                return

            # ── TIER 2: Proxy download ────────────────────────────────────────
            await status.edit_text("🎵 *Trying alternate connection...*", parse_mode="Markdown")
            proxy_url = await self.get_working_proxy()
            if proxy_url:
                try:
                    opts = _make_audio_opts(['android', 'android_music'], proxy=proxy_url)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if info:
                            video_id = info.get('id', 'unknown')
                            video_title = info.get('title', 'Unknown Title')
                            video_uploader = info.get('uploader', 'Unknown Artist')
                            file_path = f"{video_id}.mp3"
                            if os.path.exists(file_path):
                                await update.message.reply_audio(
                                    audio=open(file_path, 'rb'),
                                    title=video_title,
                                    performer=video_uploader
                                )
                                os.remove(file_path)
                                await status.delete()
                                youtube_success = True
                                logger.info(f"Tier 2 proxy success: {video_title}")
                except Exception as e:
                    logger.warning(f"Tier 2 proxy download failed: {str(e)[:150]}")

            if youtube_success:
                return

            # ── TIER 3: SoundCloud fallback ───────────────────────────────────
            if "youtube.com" in query or "youtu.be" in query:
                await status.edit_text(
                    "❌ *YouTube direct link blocked.*\n\nMount a `cookies.txt` in Render Secret Files to bypass.",
                    parse_mode="Markdown"
                )
                return

            await status.edit_text("⚠️ *Searching SoundCloud...*", parse_mode="Markdown")
            sc_opts = {
                'format': 'bestaudio/best',
                'outtmpl': '%(id)s.%(ext)s',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                'noplaylist': True,
                'socket_timeout': 60,
                'retries': 3,
                'quiet': True,
            }
            if ffmpeg_dir:
                sc_opts['ffmpeg_location'] = ffmpeg_dir
            try:
                with yt_dlp.YoutubeDL(sc_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, f"scsearch1:{query}", download=True)
                    info = info['entries'][0] if 'entries' in info else info
                    file_path = f"{info['id']}.mp3"
                if os.path.exists(file_path):
                    await update.message.reply_audio(
                        audio=open(file_path, 'rb'),
                        title=info.get('title', 'Unknown Title'),
                        performer=info.get('uploader', 'Unknown Artist')
                    )
                    os.remove(file_path)
                    await status.delete()
                else:
                    raise FileNotFoundError("SoundCloud output file not found.")
            except Exception as sc_error:
                logger.error(f"SoundCloud fallback failed: {sc_error}")
                await status.edit_text(
                    f"❌ *All sources failed.*\n\n`{str(sc_error)[:200]}`",
                    parse_mode="Markdown"
                )



    async def test_single_proxy(self, proxy_url: str, video_id: str) -> str:
        """Helper to test a single proxy connection. Returns proxy_url on success, None on failure."""
        ydl_opts = {
            'proxy': proxy_url,
            'socket_timeout': 4,
            'retries': 0
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await asyncio.to_thread(ydl.extract_info, video_id, download=False)
            return proxy_url
        except Exception:
            return None

    async def get_working_proxy(self, video_id: str = "bW5SQdPSilE") -> str:
        """Fetches public HTTP proxies and returns the first one that successfully queries the video details without blocking"""
        # 1. Check if cached proxy is still working to bypass the search instantly
        if self.cached_proxy:
            logger.info("Testing cached proxy...")
            working = await self.test_single_proxy(self.cached_proxy, video_id)
            if working:
                logger.info(f"Using working cached proxy: {self.cached_proxy}")
                return self.cached_proxy
            else:
                logger.info("Cached proxy is no longer working. Searching for a new one...")
                self.cached_proxy = None

        # 2. Fetch new proxy list and test concurrently
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=800&country=all&ssl=all&anonymity=all"
        context = ssl._create_unverified_context()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res_body = await asyncio.to_thread(urllib.request.urlopen, req, context=context, timeout=4)
            proxies_text = res_body.read().decode('utf-8')
            proxies = [p.strip() for p in proxies_text.split('\n') if p.strip()]
            
            # Test up to the first 12 proxies concurrently
            tasks = [self.test_single_proxy(f"http://{proxy}", video_id) for proxy in proxies[:12]]
            results = await asyncio.gather(*tasks)
            
            # Find the first working proxy
            for res in results:
                if res:
                    self.cached_proxy = res
                    logger.info(f"Found and cached new working proxy: {res}")
                    return res
        except Exception as e:
            logger.error(f"Failed to fetch public proxies: {e}")
        return None

    async def _do_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Background coroutine: 3-tier video download. Runs under Semaphore(5).
        Tier 1: Direct via player client rotation (android_music, tv_embedded, mweb)
        Tier 2: Proxy download (bypasses datacenter IP block)
        Tier 3: Informative error with cookies.txt instructions
        """
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎥 *Searching...*", parse_mode="Markdown")

            ffmpeg_dir = './'
            if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
                ffmpeg_dir = None

            search_query = query if query.startswith("http") else f"ytsearch1:{query}"

            def _make_video_opts(player_clients, proxy=None, cookies=None):
                opts = {
                    'format': 'best[ext=mp4][filesize<50M]/best[filesize<50M]/best[height<=720]',
                    'outtmpl': '%(id)s.%(ext)s',
                    'extractor_args': {'youtube': {'player_client': player_clients}},
                    'noplaylist': True,
                    'socket_timeout': 60,
                    'retries': 2,
                    'quiet': True,
                    'no_warnings': True,
                }
                if proxy:
                    opts['proxy'] = proxy
                if cookies:
                    opts['cookiefile'] = cookies
                if ffmpeg_dir:
                    opts['ffmpeg_location'] = ffmpeg_dir
                return opts

            def _send_video_file(vid_id, vid_title):
                for ext in ('mp4', 'webm', 'mkv'):
                    p = f"{vid_id}.{ext}"
                    if os.path.exists(p):
                        return p
                # wildcard search
                found = next((f for f in os.listdir('.') if f.startswith(vid_id)), None)
                return found

            # ── TIER 1: Direct download, player client rotation ───────────────
            await status.edit_text("🎥 *Downloading video...*", parse_mode="Markdown")
            tier1_clients = [
                ['android_music'],
                ['tv_embedded'],
                ['mweb'],
            ]
            video_id = None
            video_title = "Unknown Video"
            youtube_success = False

            for clients in tier1_clients:
                try:
                    opts = _make_video_opts(clients, cookies='cookies.txt' if os.path.exists('cookies.txt') else None)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if not info:
                            continue
                        video_id = info.get('id', 'unknown')
                        video_title = info.get('title', 'Unknown Video')
                    file_path = _send_video_file(video_id, video_title)
                    if file_path:
                        if os.path.getsize(file_path) > 50 * 1024 * 1024:
                            await status.edit_text("❌ Video exceeds Telegram's 50MB upload limit.")
                            os.remove(file_path)
                        else:
                            await update.message.reply_video(video=open(file_path, 'rb'), caption=video_title)
                            os.remove(file_path)
                            await status.delete()
                        youtube_success = True
                        logger.info(f"Video Tier 1 success with client {clients}: {video_title}")
                        break
                except Exception as e:
                    logger.info(f"Video Tier 1 client {clients} failed: {str(e)[:100]}")
                    continue

            if youtube_success:
                return

            # ── TIER 2: Proxy download ────────────────────────────────────────
            await status.edit_text("🎥 *Trying alternate connection...*", parse_mode="Markdown")
            proxy_url = await self.get_working_proxy()
            if proxy_url:
                try:
                    opts = _make_video_opts(['android', 'android_music'], proxy=proxy_url)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)
                        info = info['entries'][0] if 'entries' in info else info
                        if info:
                            video_id = info.get('id', 'unknown')
                            video_title = info.get('title', 'Unknown Video')
                            file_path = _send_video_file(video_id, video_title)
                            if file_path:
                                if os.path.getsize(file_path) > 50 * 1024 * 1024:
                                    await status.edit_text("❌ Video exceeds Telegram's 50MB upload limit.")
                                    os.remove(file_path)
                                else:
                                    await update.message.reply_video(video=open(file_path, 'rb'), caption=video_title)
                                    os.remove(file_path)
                                    await status.delete()
                                youtube_success = True
                                logger.info(f"Video Tier 2 proxy success: {video_title}")
                except Exception as e:
                    logger.warning(f"Video Tier 2 proxy failed: {str(e)[:150]}")

            if youtube_success:
                return

            # ── TIER 3: All failed ────────────────────────────────────────────
            await status.edit_text(
                "❌ *YouTube download blocked.*\n\n"
                "Mount a `cookies.txt` in Render → Environment → Secret Files to bypass bot detection.",
                parse_mode="Markdown"
            )

    async def ytest_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        query = "bW5SQdPSilE" # test video ID (Hakuna Matata or similar)
        status = await update.message.reply_text("🔬 *Testing yt-dlp player clients...*", parse_mode="Markdown")
        
        clients_to_test = [
            ('tv', ['tv']),
            ('mweb', ['mweb']),
            ('web_creator', ['web_creator']),
            ('ios', ['ios']),
            ('android', ['android']),
            ('web', ['web']),
            ('tv_embedded', ['tv', 'web_safari'])
        ]
        
        results = []
        for name, clients in clients_to_test:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'test_{name}.%(ext)s',
                'extractor_args': {'youtube': {'player_client': clients}},
                'noplaylist': True,
                'default_search': 'ytsearch'
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(query, download=False)
                results.append(f"✅ *{name}*: Success")
            except Exception as e:
                err_msg = str(e).split('\n')[0][:120]
                results.append(f"❌ *{name}*: {err_msg}")
        
        await status.edit_text("\n".join(results), parse_mode="Markdown")
