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
        """Background coroutine: full proxy search + audio download. Runs under Semaphore(5)."""
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎵 *Extracting audio...*", parse_mode="Markdown")

            # Check if local FFmpeg exists, otherwise fallback to system global path
            ffmpeg_dir = './'
            if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
                ffmpeg_dir = None

            # Fetch working proxy
            await status.edit_text("🎵 *Searching working connection proxy...*", parse_mode="Markdown")
            proxy_url = await self.get_working_proxy()

            # 1. Search via flat extract
            search_query = query if query.startswith("http") else f"ytsearch:{query}"
            search_opts = {
                'format': 'bestaudio/best',
                'extract_flat': True,
                'noplaylist': True,
                'socket_timeout': 10,
                'retries': 1
            }
            if proxy_url:
                search_opts['proxy'] = proxy_url

            try:
                with yt_dlp.YoutubeDL(search_opts) as ydl:
                    search_info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)
                    if 'entries' in search_info:
                        entries = search_info.get('entries', [])
                        if not entries:
                            await status.edit_text("❌ No search results found on YouTube.")
                            return
                        video_info = entries[0]
                    else:
                        video_info = search_info
                    video_id = video_info.get('id')
                    video_title = video_info.get('title', 'Unknown Title')
                    video_uploader = video_info.get('uploader', 'Unknown Artist')
            except Exception as e:
                video_id = None
                if "youtube.com" in query or "youtu.be" in query:
                    if "v=" in query:
                        video_id = query.split("v=")[1].split("&")[0]
                    elif "youtu.be/" in query:
                        video_id = query.split("youtu.be/")[1].split("?")[0]
                if not video_id:
                    logger.error(f"Search failed: {e}")
                    await status.edit_text(f"❌ Failed to search YouTube. Details: {e}")
                    return
                video_title = "Audio Stream"
                video_uploader = "YouTube"

            # 2. Download via proxy (must use same proxy for both extraction & download
            #    because YouTube embeds the client IP in the signed CDN stream URL)
            await status.edit_text("🎵 *Downloading audio...*", parse_mode="Markdown")
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{video_id}.%(ext)s',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                'extractor_args': {'youtube': {'player_client': ['android']}},
                'noplaylist': True,
                'socket_timeout': 30,
                'retries': 3,
            }
            if proxy_url:
                ydl_opts['proxy'] = proxy_url
                logger.info(f"Downloading audio via proxy (IP-locked): {proxy_url}")
            elif os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            if ffmpeg_dir:
                ydl_opts['ffmpeg_location'] = ffmpeg_dir

            youtube_success = False
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await asyncio.to_thread(ydl.download, [watch_url])
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
            except Exception as download_error:
                logger.warning(f"YouTube download failed: {download_error}. Falling back to SoundCloud...")

            # 3. SoundCloud fallback
            if not youtube_success:
                if "youtube.com" in query or "youtu.be" in query:
                    await status.edit_text(
                        "❌ YouTube download blocked. Mount a `cookies.txt` in your Render Secret Files to bypass.",
                        parse_mode="Markdown"
                    )
                    return
                await status.edit_text("⚠️ *YouTube blocked. Searching SoundCloud fallback...*", parse_mode="Markdown")
                sc_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': '%(id)s.%(ext)s',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                    'noplaylist': True,
                    'socket_timeout': 30,
                    'retries': 3,
                }
                if ffmpeg_dir:
                    sc_opts['ffmpeg_location'] = ffmpeg_dir
                try:
                    with yt_dlp.YoutubeDL(sc_opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, f"scsearch:{query}", download=True)
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
                        f"❌ Failed on both YouTube and SoundCloud.\n\n*Error:* {sc_error}",
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
        """Background coroutine: full proxy search + video download. Runs under Semaphore(5)."""
        async with self.download_semaphore:
            query = " ".join(context.args)
            status = await update.message.reply_text("🎥 *Downloading video...*", parse_mode="Markdown")

            # Check if local FFmpeg exists
            ffmpeg_dir = './'
            if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
                ffmpeg_dir = None

            # Fetch working proxy
            await status.edit_text("🎥 *Searching working connection proxy...*", parse_mode="Markdown")
            proxy_url = await self.get_working_proxy()

            # 1. Search via flat extract
            search_query = query if query.startswith("http") else f"ytsearch:{query}"
            search_opts = {
                'format': 'best[ext=mp4]/best',
                'extract_flat': True,
                'noplaylist': True,
                'socket_timeout': 10,
                'retries': 1
            }
            if proxy_url:
                search_opts['proxy'] = proxy_url

            try:
                with yt_dlp.YoutubeDL(search_opts) as ydl:
                    search_info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)
                    if 'entries' in search_info:
                        entries = search_info.get('entries', [])
                        if not entries:
                            await status.edit_text("❌ No search results found on YouTube.")
                            return
                        video_info = entries[0]
                    else:
                        video_info = search_info
                    video_id = video_info.get('id')
                    video_title = video_info.get('title', 'Unknown Video')
            except Exception as e:
                video_id = None
                if "youtube.com" in query or "youtu.be" in query:
                    if "v=" in query:
                        video_id = query.split("v=")[1].split("&")[0]
                    elif "youtu.be/" in query:
                        video_id = query.split("youtu.be/")[1].split("?")[0]
                if not video_id:
                    logger.error(f"Video search failed: {e}")
                    await status.edit_text(f"❌ Failed to search YouTube. Details: {e}")
                    return
                video_title = "Video Stream"

            # 2. Download via proxy (must use same proxy for both extraction & download
            #    because YouTube embeds the client IP in the signed CDN stream URL)
            await status.edit_text("🎥 *Downloading video...*", parse_mode="Markdown")
            ydl_opts = {
                'format': 'best[ext=mp4][filesize<50M]/best[filesize<50M]/best',
                'outtmpl': f'{video_id}.%(ext)s',
                'extractor_args': {'youtube': {'player_client': ['android']}},
                'noplaylist': True,
                'socket_timeout': 30,
                'retries': 3,
            }
            if proxy_url:
                ydl_opts['proxy'] = proxy_url
                logger.info(f"Downloading video via proxy (IP-locked): {proxy_url}")
            elif os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            if ffmpeg_dir:
                ydl_opts['ffmpeg_location'] = ffmpeg_dir

            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await asyncio.to_thread(ydl.download, [watch_url])
                file_path = f"{video_id}.mp4"
                if os.path.exists(file_path):
                    if os.path.getsize(file_path) > 50 * 1024 * 1024:
                        await status.edit_text("❌ Video exceeds Telegram's 50MB upload limit.")
                    else:
                        await update.message.reply_video(video=open(file_path, 'rb'), caption=video_title)
                        await status.delete()
                    os.remove(file_path)
                else:
                    found_file = next((f for f in os.listdir('.') if f.startswith(video_id) and f.endswith('.webm')), None)
                    if found_file:
                        await update.message.reply_video(video=open(found_file, 'rb'), caption=video_title)
                        os.remove(found_file)
                        await status.delete()
                    else:
                        raise FileNotFoundError("Output video file not found.")
            except Exception as e:
                logger.error(f"Video download failed: {e}")
                await status.edit_text(f"❌ Video download failed. Details: {e}")




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
