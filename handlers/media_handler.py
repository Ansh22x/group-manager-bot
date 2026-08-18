import os
import asyncio
import tempfile
import subprocess
import yt_dlp
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler

logger = logging.getLogger(__name__)

class MediaHandler(BaseHandler):
    def register(self, app: Application):
        app.add_handler(CommandHandler(["play", "music"], self.play_song))
        app.add_handler(CommandHandler(["video", "v"], self.download_video))

    async def play_song(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Please provide a song name or YouTube link!\nExample: <code>/play Gurenge LiSA</code>", parse_mode="HTML")
            return
            
        processing_msg = await update.message.reply_text("🔎 Searching YouTube and downloading audio...")
        
        temp_dir = tempfile.mkdtemp()
        
        # Options for yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, 'song.%(ext)s'),
            'noplaylist': True,
            'default_search': 'ytsearch1',  # Search YouTube and extract 1 entry
            'quiet': True,
            'nocheckcertificate': True
        }
        
        try:
            loop = asyncio.get_event_loop()
            
            def download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=True)
                    if 'entries' in info and len(info['entries']) > 0:
                        entry = info['entries'][0]
                    else:
                        entry = info
                    return entry
                    
            logger.info(f"MediaHandler: Querying YouTube search for '{query}'...")
            entry = await loop.run_in_executor(None, download)
            
            title = entry.get('title', 'Unknown Title')
            uploader = entry.get('uploader', 'Unknown Artist')
            duration = int(entry.get('duration', 0))
            
            downloaded_files = os.listdir(temp_dir)
            if not downloaded_files:
                raise Exception("YouTube audio download failed. File not found.")
                
            input_file = os.path.join(temp_dir, downloaded_files[0])
            output_file = os.path.join(temp_dir, 'song.mp3')
            
            # Transcode input format to standard MP3 via FFmpeg
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", input_file,
                "-vn",                    # Strip video stream
                "-ar", "44100",           # 44.1 kHz sampling
                "-ac", "2",               # Stereo
                "-b:a", "192k",           # 192 kbps audio bitrate
                output_file
            ]
            
            logger.info(f"MediaHandler: Transcoding '{input_file}' to '{output_file}'...")
            subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
            
            # Send file to telegram
            await processing_msg.edit_text("📤 Uploading track to group...")
            with open(output_file, 'rb') as f:
                await context.bot.send_audio(
                    chat_id=update.message.chat_id,
                    audio=f,
                    title=title,
                    performer=uploader,
                    duration=duration,
                    caption=f"🎵 <b>Giyu-Bot Music Downloader</b>\n🌊 Played: <b>{title}</b> by {uploader}",
                    parse_mode="HTML"
                )
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"MediaHandler: Playback error: {e}")
            await processing_msg.edit_text(f"❌ Failed to play song: {e}")
        finally:
            try:
                for f in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, f))
                os.rmdir(temp_dir)
            except Exception:
                pass

    async def download_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Please provide a video name or YouTube link!\nExample: <code>/video Gurenge Music Video</code>", parse_mode="HTML")
            return
            
        processing_msg = await update.message.reply_text("🔎 Searching YouTube and downloading video...")
        
        temp_dir = tempfile.mkdtemp()
        
        # Options for yt-dlp: download MP4 capped at 720p height
        ydl_opts = {
            'format': 'best[ext=mp4][height<=720]/best[height<=720]',
            'outtmpl': os.path.join(temp_dir, 'video.%(ext)s'),
            'noplaylist': True,
            'default_search': 'ytsearch1',
            'quiet': True,
            'nocheckcertificate': True
        }
        
        try:
            loop = asyncio.get_event_loop()
            
            def download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=True)
                    if 'entries' in info and len(info['entries']) > 0:
                        entry = info['entries'][0]
                    else:
                        entry = info
                    return entry
                    
            logger.info(f"MediaHandler: Querying YouTube video for '{query}'...")
            entry = await loop.run_in_executor(None, download)
            
            title = entry.get('title', 'Unknown Title')
            uploader = entry.get('uploader', 'Unknown Artist')
            duration = int(entry.get('duration', 0))
            width = entry.get('width')
            height = entry.get('height')
            
            downloaded_files = os.listdir(temp_dir)
            if not downloaded_files:
                raise Exception("YouTube video download failed. File not found.")
                
            input_file = os.path.join(temp_dir, downloaded_files[0])
            
            # Enforce Telegram standard Bot API upload limit (50 MB)
            file_size = os.path.getsize(input_file)
            if file_size > 50 * 1024 * 1024:
                raise Exception(f"Video file size ({file_size / (1024 * 1024):.1f} MB) exceeds Telegram's 50MB upload limit.")
                
            # Send file to telegram
            await processing_msg.edit_text("📤 Uploading video to group...")
            with open(input_file, 'rb') as f:
                await context.bot.send_video(
                    chat_id=update.message.chat_id,
                    video=f,
                    width=width,
                    height=height,
                    duration=duration,
                    caption=f"🎬 <b>Giyu-Bot Video Downloader</b>\n🌊 Video: <b>{title}</b> by {uploader}",
                    parse_mode="HTML"
                )
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"MediaHandler: Video download error: {e}")
            await processing_msg.edit_text(f"❌ Failed to download video: {e}")
        finally:
            try:
                for f in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, f))
                os.rmdir(temp_dir)
            except Exception:
                pass
