import os
import re
import tempfile
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers.base_handler import BaseHandler
from services.shazam_service import ShazamService
from services.summarizer_service import SummarizerService
from services.translator_service import TranslatorService

logger = logging.getLogger(__name__)

class UtilitiesHandler(BaseHandler):
    def __init__(self):
        self.shazam_service = ShazamService()
        self.summarizer_service = SummarizerService()
        self.translator_service = TranslatorService()

    def register(self, app: Application):
        # Shazam Music Identifier Commands
        app.add_handler(CommandHandler(["shazam", "identify", "whatsong", "findsong"], self.shazam_cmd))

        # Web Summarizer & Digest Commands
        app.add_handler(CommandHandler(["summarize", "summary", "tldr"], self.summarize_cmd))

        # Multi-Language Voice Translator Commands
        app.add_handler(CommandHandler(["tr", "translate"], self.translate_cmd))

    # ---------------- 1. SHAZAM SONG IDENTIFIER ----------------

    async def shazam_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return
        replied = update.message.reply_to_message

        target_msg = replied if replied else update.message
        audio_target = target_msg.audio or target_msg.voice or target_msg.video or target_msg.video_note or target_msg.document

        if not audio_target:
            await update.message.reply_text(
                "🎵 <b>Shazam Audio Identifier</b>\n\n"
                "Reply to any <b>voice note, audio track, video snippet, or video note</b> with <code>/shazam</code> to identify the song!\n\n"
                "<b>Example:</b> Reply to a video clip with <code>/shazam</code>",
                parse_mode="HTML"
            )
            return

        status = await update.message.reply_text("🎧 <i>Listening to audio fingerprint... Searching database...</i>", parse_mode="HTML")

        tmp_path = None
        try:
            file = await context.bot.get_file(audio_target.file_id)
            tmp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()

            await file.download_to_drive(custom_path=tmp_path)

            song = await self.shazam_service.identify_song(tmp_path)
            if not song:
                await status.edit_text("❌ <b>Song not recognized.</b>\n\nCould not identify a matching song from this audio clip. Ensure the music is audible.", parse_mode="HTML")
                return

            text = (
                f"🎵 <b>Song Identified!</b>\n\n"
                f"🎼 <b>Title:</b> {song['title']}\n"
                f"👤 <b>Artist:</b> {song['artist']}\n"
                f"💿 <b>Album:</b> {song['album']}\n"
                f"🏷️ <b>Genre:</b> {song['genre']}\n"
            )
            if song.get("shazam_url"):
                text += f"\n🔗 <a href='{song['shazam_url']}'>View on Shazam</a>"
            if song.get("spotify_link"):
                text += f" • <a href='{song['spotify_link']}'>Open in Spotify</a>"

            if song.get("cover_art"):
                await update.message.reply_photo(
                    photo=song["cover_art"],
                    caption=text,
                    parse_mode="HTML"
                )
                await status.delete()
            else:
                await status.edit_text(text, parse_mode="HTML", disable_web_page_preview=False)

        except Exception as e:
            logger.error(f"Shazam command error: {e}")
            await status.edit_text("❌ Failed to analyze audio stream.")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    # ---------------- 2. AI WEB SUMMARIZER ----------------

    async def summarize_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        url = None
        if context.args:
            url_match = re.search(r"https?://[^\s]+", context.args[0])
            if url_match: url = url_match.group(0)

        if not url and update.message.reply_to_message and update.message.reply_to_message.text:
            url_match = re.search(r"https?://[^\s]+", update.message.reply_to_message.text)
            if url_match: url = url_match.group(0)

        if not url:
            await update.message.reply_text(
                "📰 <b>AI Web Summarizer & Digest</b>\n\n"
                "Extracts clean text from articles or blog posts and delivers an executive summary.\n\n"
                "<b>Usage:</b> <code>/summarize &lt;url&gt;</code>\n"
                "<b>Example:</b> <code>/summarize https://store.steampowered.com/news</code>",
                parse_mode="HTML"
            )
            return

        status = await update.message.reply_text("📖 <i>Analyzing article content... Generating key takeaways...</i>", parse_mode="HTML")

        result = await self.summarizer_service.summarize_url(url)
        if not result or not result.get("summary"):
            await status.edit_text("❌ <b>Could not summarize article.</b>\n\nThe web page could not be accessed, is behind a hard paywall, or contains insufficient text.", parse_mode="HTML")
            return

        header = f"📰 <b>Article Digest:</b> <a href='{url}'>{result['title']}</a>\n\n"
        full_text = header + result["summary"]
        
        await status.edit_text(full_text, parse_mode="Markdown", disable_web_page_preview=True)

    # ---------------- 3. MULTI-LANGUAGE VOICE TRANSLATOR ----------------

    async def translate_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return

        args = context.args or []
        replied = update.message.reply_to_message
        
        target_lang = "ja" # default to Japanese
        text_to_translate = ""

        if len(args) >= 2:
            target_lang = args[0]
            text_to_translate = " ".join(args[1:])
        elif len(args) == 1:
            if replied and replied.text:
                target_lang = args[0]
                text_to_translate = replied.text
            else:
                target_lang = "ja"
                text_to_translate = args[0]
        elif replied and replied.text:
            target_lang = "ja"
            text_to_translate = replied.text

        if not text_to_translate:
            await update.message.reply_text(
                "🌍 <b>Multi-Language Voice Translator</b>\n\n"
                "Translates text and generates native spoken voice pronunciation.\n\n"
                "<b>Usage:</b> <code>/tr [language] [text]</code>\n"
                "<b>Reply:</b> Reply to any message with <code>/tr [language]</code>\n\n"
                "<b>Supported Languages:</b>\n"
                "• <code>ja</code> (Japanese), <code>es</code> (Spanish), <code>fr</code> (French)\n"
                "• <code>de</code> (German), <code>hi</code> (Hindi), <code>ru</code> (Russian)\n"
                "• <code>ar</code> (Arabic), <code>zh</code> (Chinese), <code>ko</code> (Korean)\n"
                "• <code>it</code> (Italian), <code>pt</code> (Portuguese), <code>en</code> (English)\n\n"
                "<b>Example:</b> <code>/tr ja I will protect everyone!</code>",
                parse_mode="HTML"
            )
            return

        status = await update.message.reply_text("🌐 <i>Translating and synthesizing neural voice...</i>", parse_mode="HTML")

        res = await self.translator_service.translate_text(text_to_translate, target_lang)
        if not res:
            await status.edit_text("❌ Translation failed. Please try again later.")
            return

        reply_text = (
            f"🌍 <b>Translation ({res['target_lang']})</b>\n\n"
            f"💬 <b>Original:</b> <i>\"{res['original']}\"</i>\n"
            f"✨ <b>Translated:</b>\n<code>{res['translated']}</code>"
        )

        # Generate neural audio waveform
        voice_file = await self.translator_service.generate_translated_voice(res["translated"], res["voice"])
        try:
            if voice_file and os.path.exists(voice_file):
                await update.message.reply_voice(
                    voice=open(voice_file, "rb"),
                    caption=reply_text,
                    parse_mode="HTML"
                )
                await status.delete()
            else:
                await status.edit_text(reply_text, parse_mode="HTML")
        finally:
            if voice_file and os.path.exists(voice_file):
                try: os.remove(voice_file)
                except Exception: pass
