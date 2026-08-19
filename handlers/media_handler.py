import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
import yt_dlp

logger = logging.getLogger(__name__)

class MediaHandler(BaseHandler):
    def register(self, app: Application):
        app.add_handler(CommandHandler("play", self.play_cmd))
        app.add_handler(CommandHandler("video", self.video_cmd))

    async def play_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Usage: `/play [song name or link]`", parse_mode="Markdown")
            return

        status = await update.message.reply_text("🎵 *Extracting audio...*", parse_mode="Markdown")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '%(id)s.%(ext)s',
            'ffmpeg_location': './',  # Points to the FFmpeg we installed via build.sh
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            # Spoof Safari to bypass YouTube Bot Detection
            'extractor_args': {'youtube': {'player_client': ['tv', 'web_safari']}},
            'noplaylist': True,
            'default_search': 'ytsearch'
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=True)
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
            await status.edit_text("❌ Failed to process audio. YouTube may have blocked the request.")

    async def video_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Usage: `/video [video name or link]`", parse_mode="Markdown")
            return

        status = await update.message.reply_text("🎥 *Downloading video...*", parse_mode="Markdown")
        
        ydl_opts = {
            # Force max 50MB to obey Telegram's bot upload limit
            'format': 'best[ext=mp4][filesize<50M]/best[filesize<50M]', 
            'outtmpl': '%(id)s.%(ext)s',
            'ffmpeg_location': './', 
            'extractor_args': {'youtube': {'player_client': ['tv', 'web_safari']}},
            'noplaylist': True,
            'default_search': 'ytsearch'
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=True)
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
            await status.edit_text("❌ Download failed. YouTube may have blocked the request.")
