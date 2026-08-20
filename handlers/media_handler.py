import os
import logging
import asyncio
import httpx
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
import yt_dlp
from services.media_downloader import MediaDownloaderService

logger = logging.getLogger(__name__)


class MediaHandler(BaseHandler):
    def __init__(self):
        self.downloader = MediaDownloaderService()
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
                resolved = await self.downloader.resolve_youtube_url(query)
                if resolved:
                    yt_url, yt_title = resolved
                    
                    # Try cnv.cx downloader first (Tier 1)
                    result = await self.downloader.download_via_cnv(yt_url, "audio")
                    if not result:
                        # Try Cobalt downloader second (Tier 2 fallback)
                        result = await self.downloader.download_via_cobalt(yt_url, "audio")
                        
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
            resolved = await self.downloader.resolve_youtube_url(query)
            if resolved:
                yt_url, yt_title = resolved
                
                # Try cnv.cx downloader first (Tier 1)
                result = await self.downloader.download_via_cnv(yt_url, "video")
                if not result:
                    # Try Cobalt downloader second (Tier 2 fallback)
                    result = await self.downloader.download_via_cobalt(yt_url, "video")
                    
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
            res = await self.downloader.resolve_youtube_url("alan walker darkside")
            if res:
                results.append(f"`[OK] Search Resolved`: `{res[0]}`")
            else:
                results.append("`[FAIL] Search returned None`")
        except Exception as e:
            results.append(f"`[FAIL] Search Error`: `{str(e)[:60]}`")
            
        # Test cnv.cx Downloader
        try:
            test_res = await self.downloader.download_via_cnv("https://www.youtube.com/watch?v=s7-GTShjcqY", "audio")
            if test_res:
                results.append(f"`[OK] cnv.cx Download`: `{test_res[1]}`")
                if os.path.exists(test_res[0]): os.remove(test_res[0])
            else:
                results.append("`[FAIL] cnv.cx Download returned None`")
        except Exception as e:
            results.append(f"`[FAIL] cnv.cx Error`: `{str(e)[:60]}`")
            
        # Test Cobalt API
        try:
            endpoints = await self.downloader.get_cobalt_endpoints()
            results.append(f"`[INFO] Cobalt endpoints count`: `{len(endpoints)}`")
            test_res = await self.downloader.download_via_cobalt("https://www.youtube.com/watch?v=s7-GTShjcqY", "audio")
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
        raw_prompt = " ".join(context.args)
        status = await update.message.reply_text("🎨 *Enhancing prompt with Mistral...*", parse_mode="Markdown")
        
        try:
            from services.ai_agent import AIAgent
            agent = AIAgent()
            prompt = await agent.enhance_image_prompt(raw_prompt)
        except Exception as e:
            logger.error(f"Failed to enhance prompt: {e}")
            prompt = raw_prompt
            
        await status.edit_text(f"🎨 <b>Drawing... please wait...</b>\n\n<i>Prompt: {prompt}</i>", parse_mode="HTML")
        
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
                caption_text = (
                    f"🎨 <b>Generated Image</b>\n\n"
                    f"✉️ <b>Request:</b> <code>{raw_prompt}</code>\n"
                    f"✨ <b>Enhanced Prompt:</b> <code>{prompt}</code>"
                )
                if len(caption_text) > 1024:
                    prefix = f"🎨 <b>Generated Image</b>\n\n✉️ <b>Request:</b> <code>{raw_prompt}</code>\n✨ <b>Enhanced Prompt:</b> <code>"
                    suffix = "</code>"
                    available_len = 1024 - len(prefix) - len(suffix)
                    if available_len > 10:
                        truncated_prompt = prompt[:available_len - 3] + "..."
                        caption_text = f"🎨 <b>Generated Image</b>\n\n✉️ <b>Request:</b> <code>{raw_prompt}</code>\n✨ <b>Enhanced Prompt:</b> <code>{truncated_prompt}</code>"
                    else:
                        caption_text = caption_text[:1020] + "..."

                with open(filename, "rb") as photo_fh:
                    await update.message.reply_photo(photo=photo_fh, caption=caption_text, parse_mode="HTML")
            except Exception as se:
                logger.error(f"Failed to send image: {se}")
                await status.edit_text("❌ Failed to send generated image.")
            finally:
                    try:
                        os.remove(filename)
                    except Exception:
                        pass
        else:
            await status.edit_text("❌ Image generation failed on all pipelines.")

