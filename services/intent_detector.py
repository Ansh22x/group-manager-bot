import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class IntentResult:
    triggered: bool
    intent_type: str        # 'question', 'play_audio', 'play_video', 'moderation', 'none'
    subject: Optional[str]  # Extracted subject e.g. song name, user mention
    confidence: float       # 0.0 to 1.0

# Keyword triggers — zero API cost, checked first
_PLAY_KEYWORDS  = {"play", "song", "music", "track", "audio", "baja", "bajao", "suna", "sunao"}
_VIDEO_KEYWORDS = {"video", "clip", "watch", "show me", "dikha"}
_MOD_KEYWORDS   = {"ban", "mute", "kick", "warn", "restrict", "silence"}
_BOT_NAMES      = {"giyu", "giyuu", "tomioka", "bot"}

def detect_intent_fast(text: str, bot_username: str) -> IntentResult:
    """
    Fast, zero-cost keyword-based intent detector.
    Returns an IntentResult without any LLM calls.
    Checks:
      1. Direct @mention of the bot
      2. Bot name keywords (giyu, tomioka)
      3. Media keywords (play, video)
      4. Moderation keywords (ban, mute)
    """
    lower = text.lower().strip()
    bot_user_lower = (bot_username or "").lower()

    # Direct @mention always triggers
    is_mentioned = bot_user_lower and f"@{bot_user_lower}" in lower

    # Bot name trigger
    has_bot_name = any(name in lower for name in _BOT_NAMES)

    # Media keyword triggers (even without mention)
    has_play  = any(kw in lower for kw in _PLAY_KEYWORDS)
    has_video = any(kw in lower for kw in _VIDEO_KEYWORDS)
    has_mod   = any(kw in lower for kw in _MOD_KEYWORDS)

    # Only trigger if bot is mentioned/named OR it's a simple media request
    addressed_to_bot = is_mentioned or has_bot_name

    if not addressed_to_bot and not (has_play or has_video):
        return IntentResult(triggered=False, intent_type="none", subject=None, confidence=0.0)

    # Determine intent type
    if has_play and not has_video:
        # Extract subject: everything after the trigger word
        subject = _extract_after_keyword(lower, _PLAY_KEYWORDS)
        return IntentResult(triggered=True, intent_type="play_audio", subject=subject, confidence=0.9)

    if has_video:
        subject = _extract_after_keyword(lower, _VIDEO_KEYWORDS)
        return IntentResult(triggered=True, intent_type="play_video", subject=subject, confidence=0.9)

    if addressed_to_bot and has_mod:
        return IntentResult(triggered=True, intent_type="moderation", subject=text, confidence=0.85)

    if addressed_to_bot:
        # General question or conversation
        clean = lower
        for name in _BOT_NAMES:
            clean = clean.replace(name, "").strip()
        if bot_user_lower:
            clean = clean.replace(f"@{bot_user_lower}", "").strip()
        subject = clean.strip(",. ") or text
        return IntentResult(triggered=True, intent_type="question", subject=subject, confidence=0.8)

    return IntentResult(triggered=False, intent_type="none", subject=None, confidence=0.0)


def _extract_after_keyword(text: str, keywords: set) -> str:
    """Extract the subject phrase that follows a keyword."""
    words = text.split()
    for i, word in enumerate(words):
        if word in keywords:
            remainder = " ".join(words[i + 1:]).strip()
            # Strip @mention or bot name from remainder
            for name in _BOT_NAMES:
                remainder = remainder.replace(name, "").strip()
            return remainder or text
    return text
