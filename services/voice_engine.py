import os
import re
import tempfile
import logging
import edge_tts
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class VoiceEngine:
    VOICE_MAP = {
        "giyu": "en-US-ChristopherNeural",
        "tanjiro": "en-US-GuyNeural",
        "nezuko": "en-US-AnaNeural",
        "shinobu": "en-US-JennyNeural"
    }

    @classmethod
    def clean_text_for_speech(cls, text: str) -> str:
        """Strips HTML, markdown, URLs, and code blocks for clean natural TTS audio."""
        if not text: return ""
        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]*`", "", text)
        # Strip HTML tags
        soup = BeautifulSoup(text, "html.parser")
        clean = soup.get_text(separator=" ")
        # Remove URLs
        clean = re.sub(r"https?://\S+", "", clean)
        # Remove telegram commands
        clean = re.sub(r"/\w+", "", clean)
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        # Truncate to 600 characters for snappy natural voice note length
        if len(clean) > 600:
            clean = clean[:600].rsplit(" ", 1)[0] + "."
        return clean

    @classmethod
    async def generate_voice(cls, text: str, character: str = "giyu") -> str | None:
        """Generates an OGG Opus audio file compatible with Telegram voice bubbles.
        Returns the absolute local temporary file path or None.
        """
        clean_text = cls.clean_text_for_speech(text)
        if not clean_text or len(clean_text) < 2:
            return None

        voice = cls.VOICE_MAP.get(character.lower(), "en-US-ChristopherNeural")
        
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".ogg", prefix=f"giyu_voice_{character}_")
        os.close(tmp_fd)

        try:
            communicate = edge_tts.Communicate(clean_text, voice)
            await communicate.save(tmp_path)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 500:
                return tmp_path
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"Voice generation failed: {e}")
            if os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except Exception: pass
        return None
