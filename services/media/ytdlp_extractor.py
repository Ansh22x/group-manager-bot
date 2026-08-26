import os
import logging
import asyncio
import tempfile
import yt_dlp

logger = logging.getLogger(__name__)

def _safe_remove(path: str | None):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

class YtdlpExtractor:
    """Universal 1,800+ host extractor powered by yt-dlp with multi-client rotation."""

    @staticmethod
    async def download_audio(url: str) -> tuple[str, str] | None:
        """Downloads audio as high-quality MP3 (max 50MB)."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="giyu_audio_ydl_")
        os.close(tmp_fd)

        opts = {
            "format": "bestaudio/best",
            "outtmpl": tmp_path.replace(".mp3", ".%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "max_filesize": 50 * 1024 * 1024,
            "nocheckcertificate": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "mweb", "tv_embedded"]
                }
            }
        }

        try:
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    title = info.get("title", "Audio Track") if info else "Audio Track"
                    return title

            title = await asyncio.to_thread(_extract)
            final_path = tmp_path if os.path.exists(tmp_path) else tmp_path.replace(".mp3", ".m4a")
            if os.path.exists(final_path) and os.path.getsize(final_path) > 1000:
                return final_path, title
            _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"yt-dlp audio download error: {e}")
            _safe_remove(tmp_path)

        return None

    @staticmethod
    async def download_video(url: str, max_size_mb: int = 50) -> tuple[str, str] | None:
        """Downloads video (max 50MB) for direct Telegram delivery."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_video_ydl_")
        os.close(tmp_fd)

        opts = {
            "format": f"bestvideo[ext=mp4][filesize<={max_size_mb}M]+bestaudio[ext=m4a]/best[ext=mp4][filesize<={max_size_mb}M]/best[filesize<={max_size_mb}M]",
            "outtmpl": tmp_path,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 45,
            "max_filesize": max_size_mb * 1024 * 1024,
            "nocheckcertificate": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "mweb", "tv_embedded"]
                }
            }
        }

        try:
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    title = info.get("title", "Video Track") if info else "Video Track"
                    return title

            title = await asyncio.to_thread(_extract)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 5000:
                return tmp_path, title
            _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"yt-dlp video download error: {e}")
            _safe_remove(tmp_path)

        return None
