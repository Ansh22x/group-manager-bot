import logging
import httpx
from services.http_client import shared_http_client

logger = logging.getLogger(__name__)

COBALT_DEFAULT_APIS = [
    "https://api.cobalt.liubquanti.click",
    "https://cobaltapi.cjs.nz"
]

class CobaltDownloader:
    def __init__(self):
        self.cached_cobalt = "https://api.cobalt.liubquanti.click"

    async def get_active_instance(self) -> str:
        """Finds a working Cobalt instance with fast health checks."""
        for inst in [self.cached_cobalt] + COBALT_DEFAULT_APIS:
            try:
                r = await shared_http_client.get(f"{inst}/api/serverInfo", timeout=3.0)
                if r.status_code == 200:
                    self.cached_cobalt = inst
                    return inst
            except Exception:
                pass
        return self.cached_cobalt

    async def extract_stream(self, url: str, is_audio: bool = False) -> tuple[str, str] | None:
        """Requests stream download URL from Cobalt API."""
        instance = await self.get_active_instance()
        payload = {
            "url": url,
            "downloadMode": "audio" if is_audio else "auto",
            "videoQuality": "720" if not is_audio else "max",
            "youtubeVideoCodec": "h264"
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        try:
            r = await shared_http_client.post(
                f"{instance}/api/json",
                json=payload,
                headers=headers,
                timeout=15.0
            )
            if r.status_code == 200:
                data = r.json()
                stream_url = data.get("url")
                filename = data.get("filename") or ("audio.mp3" if is_audio else "video.mp4")
                if stream_url:
                    return stream_url, filename
        except Exception as e:
            logger.debug(f"Cobalt extraction failed on {instance}: {e}")
        return None
