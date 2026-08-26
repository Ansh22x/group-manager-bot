import os
import logging
import asyncio
import tempfile
import cloudscraper
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def _safe_remove(path: str | None):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

class SocialMediaExtractor:
    """Extracts media from TikTok, Terabox, Instagram, and generic HTML5/M3U8 video players."""

    @staticmethod
    async def download_tiktok_tikwm(url: str) -> tuple[str, str] | None:
        """Downloads HD watermark-free TikTok video via TikWM API."""
        scraper = cloudscraper.create_scraper()
        api = "https://www.tikwm.com/api/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            logger.info(f"Downloading TikTok via TikWM: {url}")
            def post_tikwm():
                return scraper.post(api, data={"url": url}, headers=headers, timeout=12)
            
            r = await asyncio.to_thread(post_tikwm)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 0 and data.get("data"):
                    info = data["data"]
                    play_url = info.get("play") or info.get("wmplay")
                    title = info.get("title") or f"TikTok Video by @{info.get('author', {}).get('unique_id', 'user')}"
                    
                    if play_url:
                        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_tiktok_")
                        os.close(tmp_fd)
                        
                        def stream_video():
                            resp = scraper.get(play_url, headers=headers, stream=True, timeout=90)
                            if resp.status_code == 200:
                                with open(tmp_path, "wb") as f:
                                    for chunk in resp.iter_content(chunk_size=65536):
                                        f.write(chunk)
                                return True
                            return False

                        ok = await asyncio.to_thread(stream_video)
                        if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 5000:
                            logger.info(f"TikWM download successful: {title} -> {tmp_path}")
                            return tmp_path, title
                        _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"TikWM scraper failed: {e}")
        return None

    @staticmethod
    async def download_terabox(url: str) -> tuple[str | None, str, str | None] | None:
        """Extracts and downloads Terabox videos/files.
        Returns (local_file_path_if_small, title, direct_download_url).
        """
        scraper = cloudscraper.create_scraper()
        logger.info(f"Extracting Terabox file from: {url}")

        # Try direct extraction using yt-dlp first
        try:
            import yt_dlp
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_terabox_")
            os.close(tmp_fd)
            opts = {
                "outtmpl": tmp_path.replace(".mp4", ".%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30
            }
            def _ytdl_tera():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return info.get("title", "Terabox File"), info.get("url")
            
            title, direct_url = await asyncio.to_thread(_ytdl_tera)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
                return tmp_path, title, direct_url
            _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"yt-dlp Terabox extractor failed: {e}")

        # Fallback to Terabox API parsing
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            def _fetch_api():
                return scraper.post("https://teradownloader.com/api/application-data", json={"url": url}, headers=headers, timeout=10)
            res = await asyncio.to_thread(_fetch_api)
            if res.status_code == 200:
                data = res.json()
                d_url = data.get("download_url") or data.get("url")
                title = data.get("file_name") or data.get("title") or "Terabox File"
                if d_url:
                    return None, title, d_url
        except Exception as e:
            logger.debug(f"Terabox API resolver error: {e}")

        return None

    @staticmethod
    async def extract_html5_video(url: str) -> tuple[str, str] | None:
        """Deep sniffs web pages for direct MP4, WebM or M3U8 video streams."""
        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url
        }
        try:
            logger.info(f"Scanning HTML5 media streams for: {url}")
            def get_page():
                return scraper.get(url, headers=headers, timeout=12)
            
            res = await asyncio.to_thread(get_page)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                title = soup.title.string.strip() if soup.title and soup.title.string else "Online Video"
                
                # Check <video> and <source> tags
                for v_tag in soup.find_all(["video", "source"]):
                    src = v_tag.get("src")
                    if src and (src.endswith(".mp4") or ".mp4?" in src or "blob:" not in src):
                        if src.startswith("//"): src = "https:" + src
                        elif src.startswith("/"):
                            from urllib.parse import urljoin
                            src = urljoin(url, src)
                        
                        # Download stream
                        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="giyu_html5_")
                        os.close(tmp_fd)
                        
                        def dl_stream():
                            r_stream = scraper.get(src, headers=headers, stream=True, timeout=60)
                            if r_stream.status_code == 200:
                                with open(tmp_path, "wb") as f:
                                    for chunk in r_stream.iter_content(chunk_size=65536):
                                        f.write(chunk)
                                return True
                            return False
                            
                        ok = await asyncio.to_thread(dl_stream)
                        if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10000:
                            return tmp_path, title
                        _safe_remove(tmp_path)
        except Exception as e:
            logger.debug(f"HTML5 video extractor error: {e}")
        return None
