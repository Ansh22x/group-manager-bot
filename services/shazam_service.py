import os
import logging
from shazamio import Shazam
from services.cache_service import fast_cache

logger = logging.getLogger(__name__)

class ShazamService:
    def __init__(self):
        self.shazam = Shazam()

    async def identify_song(self, file_path: str) -> dict | None:
        """
        Recognizes song details from an audio or video file path using Shazam.
        Returns a structured dictionary with metadata, cover art, and links.
        """
        try:
            out = await self.shazam.recognize_song(file_path)
            if not out or not out.get("track"):
                return None

            track = out["track"]
            title = track.get("title", "Unknown Title")
            artist = track.get("subtitle", "Unknown Artist")
            
            # Extract high-res cover art
            images = track.get("images", {})
            cover_art = images.get("coverarthq") or images.get("coverart") or images.get("background")

            # Extract genre & album
            genres = track.get("genres", {}).get("primary", "General")
            sections = track.get("sections", [])
            album = "Unknown Album"
            for sec in sections:
                if sec.get("type") == "SONG":
                    for meta in sec.get("metadata", []):
                        if meta.get("title") == "Album":
                            album = meta.get("text", album)

            # Extract external provider links
            hub = track.get("hub", {})
            providers = hub.get("providers", [])
            spotify_link = None
            for p in providers:
                if p.get("type") == "SPOTIFY":
                    for action in p.get("actions", []):
                        if action.get("uri"):
                            spotify_link = action.get("uri")

            shazam_url = track.get("url")

            return {
                "title": title,
                "artist": artist,
                "album": album,
                "genre": genres,
                "cover_art": cover_art,
                "spotify_link": spotify_link,
                "shazam_url": shazam_url
            }
        except Exception as e:
            logger.error(f"ShazamService.identify_song error: {e}")
            return None
