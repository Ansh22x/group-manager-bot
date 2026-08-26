import os
import re
import logging
import tempfile
import edge_tts
from services.cache_service import fast_cache
from mistralai.client import Mistral
from config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

class TranslatorService:
    LANGUAGE_MAP = {
        "ja": {"name": "Japanese (日本語)", "voice": "ja-JP-NanamiNeural", "aliases": ["japanese", "jp", "nihongo"]},
        "es": {"name": "Spanish (Español)", "voice": "es-ES-AlvaroNeural", "aliases": ["spanish", "esp"]},
        "fr": {"name": "French (Français)", "voice": "fr-FR-HenriNeural", "aliases": ["french"]},
        "de": {"name": "German (Deutsch)", "voice": "de-DE-ConradNeural", "aliases": ["german", "deutsch"]},
        "hi": {"name": "Hindi (हिन्दी)", "voice": "hi-IN-MadhurNeural", "aliases": ["hindi", "in"]},
        "ru": {"name": "Russian (Русский)", "voice": "ru-RU-DmitryNeural", "aliases": ["russian"]},
        "ar": {"name": "Arabic (العربية)", "voice": "ar-SA-HamedNeural", "aliases": ["arabic"]},
        "zh": {"name": "Chinese (中文)", "voice": "zh-CN-YunxiNeural", "aliases": ["chinese", "mandarin"]},
        "ko": {"name": "Korean (한국어)", "voice": "ko-KR-InJoonNeural", "aliases": ["korean"]},
        "it": {"name": "Italian (Italiano)", "voice": "it-IT-DiegoNeural", "aliases": ["italian"]},
        "pt": {"name": "Portuguese (Português)", "voice": "pt-BR-AntonioNeural", "aliases": ["portuguese", "pt"]},
        "en": {"name": "English", "voice": "en-US-ChristopherNeural", "aliases": ["english", "eng"]}
    }

    def __init__(self):
        self.client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None

    def resolve_language(self, lang_input: str) -> tuple[str, dict]:
        """Resolves language code or alias to standard key and configuration."""
        clean = lang_input.lower().strip()
        if clean in self.LANGUAGE_MAP:
            return clean, self.LANGUAGE_MAP[clean]
        for code, data in self.LANGUAGE_MAP.items():
            if clean in data["aliases"]:
                return code, data
        return "ja", self.LANGUAGE_MAP["ja"] # Default to Japanese

    async def translate_text(self, text: str, target_lang: str = "ja") -> dict | None:
        """Translates text to the target language using Mistral AI."""
        code, meta = self.resolve_language(target_lang)
        cache_key = f"tr_{code}_{hash(text)}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        if not self.client:
            return None

        prompt = (
            f"Translate the following text accurately and naturally into {meta['name']}.\n"
            f"Preserve the tone, formatting, and cultural nuance.\n"
            f"Output ONLY the translated text without explanations, prefixes, or quotes.\n\n"
            f"Text to translate:\n{text}"
        )

        try:
            response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                messages=[
                    {"role": "system", "content": "You are a professional multi-language translator. Provide clean, direct translations without conversational commentary."},
                    {"role": "user", "content": prompt}
                ]
            )
            translated = response.choices[0].message.content.strip()

            result = {
                "original": text,
                "translated": translated,
                "target_lang": meta["name"],
                "lang_code": code,
                "voice": meta["voice"]
            }
            fast_cache.set(cache_key, result, ttl_seconds=86400.0)
            return result
        except Exception as e:
            logger.error(f"TranslatorService translation error: {e}")
            return None

    async def generate_translated_voice(self, text: str, voice_name: str) -> str | None:
        """Generates an authentic Neural voice audio note for the translated text."""
        try:
            # Clean special characters/emojis for TTS clarity
            clean_speech = re.sub(r"[#*_~`<>@\[\]\(\)\{\}]", "", text).strip()
            if not clean_speech:
                clean_speech = text

            tmp_ogg = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
            tmp_ogg_path = tmp_ogg.name
            tmp_ogg.close()

            communicate = edge_tts.Communicate(clean_speech, voice_name)
            await communicate.save(tmp_ogg_path)

            if os.path.exists(tmp_ogg_path) and os.path.getsize(tmp_ogg_path) > 0:
                return tmp_ogg_path
            return None
        except Exception as e:
            logger.error(f"TranslatorService voice synthesis error: {e}")
            return None
