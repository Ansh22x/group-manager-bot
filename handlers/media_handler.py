import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
import yt_dlp

logger = logging.getLogger(__name__)

class MediaHandler(BaseHandler):
    def register(self, app: Application):
        app.add_handler(CommandHandler("play", self.play_cmd))
        app.add_handler(CommandHandler("video", self.video_cmd))
        app.add_handler(CommandHandler("ytest", self.ytest_cmd))

    async def play_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Usage: `/play [song name or link]`", parse_mode="Markdown")
            return

        status = await update.message.reply_text("🎵 *Extracting audio...*", parse_mode="Markdown")
        
        # Check if local FFmpeg exists, otherwise fallback to system global path
        ffmpeg_dir = './'
        if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
            ffmpeg_dir = None

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            # Force android client to bypass YouTube Bot Detection / PO Token checks
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'noplaylist': True,
            'default_search': 'ytsearch',
            'socket_timeout': 15,
            'retries': 2,
        }
        if ffmpeg_dir:
            ydl_opts['ffmpeg_location'] = ffmpeg_dir

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=True)
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
        except Exception as e:
            logger.error(f"Play command error: {e}")
            await status.edit_text(f"❌ Failed to process audio. Details: {e}")

    async def video_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Usage: `/video [video name or link]`", parse_mode="Markdown")
            return

        status = await update.message.reply_text("🎥 *Downloading video...*", parse_mode="Markdown")
        
        # Check if local FFmpeg exists, otherwise fallback to system global path
        ffmpeg_dir = './'
        if not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg')) and not os.path.exists(os.path.join(ffmpeg_dir, 'ffmpeg.exe')):
            ffmpeg_dir = None

        ydl_opts = {
            # Force max 50MB to obey Telegram's bot upload limit
            'format': 'best[ext=mp4][filesize<50M]/best[filesize<50M]', 
            'outtmpl': '%(id)s.%(ext)s',
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'noplaylist': True,
            'default_search': 'ytsearch',
            'socket_timeout': 15,
            'retries': 2,
        }
        if ffmpeg_dir:
            ydl_opts['ffmpeg_location'] = ffmpeg_dir

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=True)
                info = info['entries'][0] if 'entries' in info else info
                file_path = f"{info['id']}.mp4"

            if os.path.exists(file_path):
                if os.path.getsize(file_path) > 50 * 1024 * 1024:
                    await status.edit_text("❌ Video exceeds Telegram's 50MB upload limit.")
                else:
                    await update.message.reply_video(video=open(file_path, 'rb'))
                    await status.delete()
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Video command error: {e}")
            await status.edit_text(f"❌ Download failed. Details: {e}")

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
