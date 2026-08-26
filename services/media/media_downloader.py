import os
import logging
from services.media.cobalt_downloader import CobaltDownloader
from services.media.invidious_extractor import InvidiousExtractor
from services.media.social_extractor import SocialMediaExtractor, _safe_remove
from services.media.ytdlp_extractor import YtdlpExtractor

logger = logging.getLogger(__name__)

class MediaDownloaderService:
    """Universal Media Downloader orchestrating 5-tier fallback pipelines across 1,800+ hosts."""

    def __init__(self):
        self.cobalt = CobaltDownloader()
        self.invidious = InvidiousExtractor()
        self.social = SocialMediaExtractor()
        self.ytdlp = YtdlpExtractor()

    async def resolve_youtube_url(self, query: str) -> tuple[str, str] | None:
        return await self.invidious.resolve_youtube_url(query)

    async def download_media(self, url: str) -> tuple[str | None, str, str | None] | None:
        """Universal downloader (TikTok, Instagram, Terabox, YouTube, Twitter, etc.).
        Returns (local_file_path, title, direct_stream_url).
        """
        clean_url = url.strip()

        # Tier 1: Specialized Extractors
        if "tiktok.com" in clean_url or "douyin.com" in clean_url:
            res = await self.social.download_tiktok_tikwm(clean_url)
            if res:
                return res[0], res[1], None

        if "terabox" in clean_url or "1024tera" in clean_url or "teraboxapp" in clean_url:
            res = await self.social.download_terabox(clean_url)
            if res:
                return res

        # Tier 2: Cobalt API Rotation
        res = await self.cobalt.download_media(clean_url, is_audio=False)
        if res:
            return res

        # Tier 3: cnv.cx pipeline
        res = await self.invidious.download_cnv_video(clean_url)
        if res:
            return res[0], res[1], None

        # Tier 4: HTML5 deep sniffer
        res = await self.social.extract_html5_video(clean_url)
        if res:
            return res[0], res[1], None

        # Tier 5: yt-dlp universal engine
        res = await self.ytdlp.download_video(clean_url)
        if res:
            return res[0], res[1], None

        return None

    async def download_audio_only(self, url: str) -> tuple[str | None, str, str | None] | None:
        """Downloads audio as MP3 across all fallback pipelines."""
        clean_url = url.strip()

        # Tier 1: Cobalt API Rotation (Audio mode)
        res = await self.cobalt.download_media(clean_url, is_audio=True)
        if res:
            return res

        # Tier 2: cnv.cx conversion
        res = await self.invidious.download_cnv_audio(clean_url)
        if res:
            return res[0], res[1], None

        # Tier 3: yt-dlp audio extraction
        res = await self.ytdlp.download_audio(clean_url)
        if res:
            return res[0], res[1], None

        return None

    async def download_direct_video(self, url: str, max_size_mb: int = 50) -> tuple[str | None, str, str | None] | None:
        return await self.download_media(url)

    async def search_and_stream_audio(self, query: str) -> tuple[str | None, str, str | None] | None:
        resolved = await self.resolve_youtube_url(query)
        if not resolved:
            return None
        yt_url, title = resolved
        res = await self.download_audio_only(yt_url)
        if res:
            return res[0], res[1] or title, res[2]
        return None

    async def search_and_stream_video(self, query: str, max_size_mb: int = 50) -> tuple[str | None, str, str | None] | None:
        resolved = await self.resolve_youtube_url(query)
        if not resolved:
            return None
        yt_url, title = resolved
        res = await self.download_direct_video(yt_url, max_size_mb)
        if res:
            return res[0], res[1] or title, res[2]
        return None
