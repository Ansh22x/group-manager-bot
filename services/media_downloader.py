import os
import re
import logging
import asyncio
import httpx
import cloudscraper

logger = logging.getLogger(__name__)

# Search nodes (to resolve search query to a YT video ID)
INVIDIOUS_SEARCH_INSTANCES = [
    "https://invidious.flokinet.to",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de"
]

# Static fallback API URLs for Cobalt (Turnstile-free)
COBALT_DEFAULT_APIS = [
    "https://api.cobalt.liubquanti.click",
    "https://cobaltapi.cjs.nz"
]

class MediaDownloaderService:
    def __init__(self):
        self.cached_cobalt = "https://api.cobalt.liubquanti.click"
        self.cached_invidious = "https://invidious.flokinet.to"

    async def resolve_youtube_url(self, query: str) -> tuple[str, str] | None:
        """Resolves query string to YouTube URL using working search nodes.
        Returns (youtube_url, title) or None."""
        if "youtube.com" in query or "youtu.be" in query:
            return query, "YouTube Link"
            
        instances = [self.cached_invidious] + INVIDIOUS_SEARCH_INSTANCES
        # remove duplicates preserving order
        seen = set()
        instances = [x for x in instances if x and not (x in seen or seen.add(x))]
        
        for instance in instances:
            try:
                async with httpx.AsyncClient(timeout=8, verify=False) as client:
                    r = await client.get(
                        f"{instance}/api/v1/search",
                        params={"q": query, "type": "video", "fields": "videoId,title"}
                    )
                    if r.status_code == 200:
                        results = r.json()
                        if results:
                            self.cached_invidious = instance
                            vid_id = results[0]["videoId"]
                            title = results[0]["title"]
                            return f"https://www.youtube.com/watch?v={vid_id}", title
            except Exception as e:
                logger.debug(f"Search failed on {instance}: {e}")
        return None

    async def download_via_cnv(self, target_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads direct stream via cnv.cx + cloudscraper (bypasses YT cloud blocks).
        Returns (local_file_path, title) or None."""
        video_id = None
        patterns = [
            r"v=([^&]+)",
            r"youtu\.be/([^?]+)",
            r"embed/([^?]+)",
            r"v/([^?]+)"
        ]
        for pattern in patterns:
            m = re.search(pattern, target_url)
            if m:
                video_id = m.group(1)
                break
                
        if not video_id:
            return None
            
        headers = {
            "Accept": "*/*",
            "Origin": "https://iframe.y2meta-uk.com",
            "Referer": "https://iframe.y2meta-uk.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            logger.info(f"Trying cnv.cx download pipeline for video_id: {video_id}")
            scraper = cloudscraper.create_scraper()
            
            # Step 1: Get Key
            def get_key():
                r = scraper.get(f"https://cnv.cx/v2/sanity/key?id={video_id}", headers=headers, timeout=10)
                if r.status_code == 200:
                    return r.json().get("key")
                return None
                
            key = await asyncio.to_thread(get_key)
            if not key:
                logger.debug("Failed to obtain cnv.cx sanity key")
                return None
                
            # Step 2: Post to converter
            payload = {
                "link": f"https://youtu.be/{video_id}",
                "format": "mp3" if mode == "audio" else "mp4",
                "audioBitrate": "128",
                "videoQuality": "720",
                "vCodec": "h264",
                "filenameStyle": "pretty"
            }
            
            headers_post = headers.copy()
            headers_post["key"] = key
            
            def do_convert():
                r = scraper.post("https://cnv.cx/v2/converter", json=payload, headers=headers_post, timeout=15)
                if r.status_code == 200:
                    return r.json()
                return None
                
            data = await asyncio.to_thread(do_convert)
            if not data or data.get("status") != "tunnel":
                logger.debug(f"cnv.cx converter returned non-tunnel status: {data}")
                return None
                
            dl_url = data.get("url")
            title = data.get("filename", "Audio Track" if mode == "audio" else "Video Clip")
            title = os.path.splitext(title)[0]
            
            # Step 3: Stream download using cloudscraper
            filename = f"dl_{mode}_{int(asyncio.get_event_loop().time())}." + ("mp3" if mode == "audio" else "mp4")
            
            def do_download():
                resp = scraper.get(dl_url, headers={"Referer": "https://iframe.y2meta-uk.com/"}, stream=True, timeout=90)
                if resp.status_code == 200:
                    with open(filename, "wb") as fh:
                        for chunk in resp.iter_content(chunk_size=65536):
                            fh.write(chunk)
                    return True
                return False
                
            success = await asyncio.to_thread(do_download)
            if success and os.path.exists(filename) and os.path.getsize(filename) > 10000:
                logger.info(f"cnv.cx download successful: {title}")
                return filename, title
                
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            logger.debug(f"cnv.cx download pipeline failed: {e}")
            
        return None

    async def get_cobalt_endpoints(self) -> list[str]:
        """Fetches online YouTube API endpoints dynamically from cobalt.directory registry using cloudscraper."""
        default = [self.cached_cobalt] + COBALT_DEFAULT_APIS if self.cached_cobalt else COBALT_DEFAULT_APIS
        seen = set()
        endpoints = [x for x in default if x and not (x in seen or seen.add(x))]
        try:
            scraper = cloudscraper.create_scraper()
            def fetch_api():
                r = scraper.get("https://cobalt.directory/api/working?type=api", timeout=8)
                if r.status_code == 200:
                    return r.json().get("data", {}).get("youtube", [])
                return []
            apis = await asyncio.to_thread(fetch_api)
            # Append fetched ones to default order
            for api in apis:
                api_clean = api.rstrip('/')
                if api_clean not in seen:
                    endpoints.append(api_clean)
                    seen.add(api_clean)
        except Exception as e:
            logger.warning(f"Failed to fetch cobalt directory: {e}")
        return endpoints

    async def download_via_cobalt(self, target_url: str, mode: str) -> tuple[str, str] | None:
        """Downloads direct stream via Cobalt API instances (bypasses YT cloud blocks).
        Returns (local_file_path, title) or None."""
        endpoints = await self.get_cobalt_endpoints()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        payload = {
            "url": target_url,
            "downloadMode": "audio" if mode == "audio" else "video",
            "audioFormat": "mp3",
            "videoQuality": "720"
        }
        
        scraper = cloudscraper.create_scraper()
        
        for api in endpoints:
            api_endpoint = f"{api.rstrip('/')}/"
            try:
                logger.info(f"Trying Cobalt endpoint: {api_endpoint}")
                def post_cobalt():
                    return scraper.post(api_endpoint, json=payload, headers=headers, timeout=12)
                r = await asyncio.to_thread(post_cobalt)
                if r.status_code == 200:
                    data = r.json()
                    status = data.get("status")
                    dl_url = data.get("url")
                    if dl_url and status in ("redirect", "stream", "tunnel"):
                        # Download stream file
                        filename = f"dl_{mode}_{int(asyncio.get_event_loop().time())}." + ("mp3" if mode == "audio" else "mp4")
                        
                        def get_stream():
                            resp = scraper.get(dl_url, stream=True, timeout=90)
                            if resp.status_code == 200:
                                with open(filename, "wb") as fh:
                                    for chunk in resp.iter_content(chunk_size=65536):
                                        fh.write(chunk)
                                return True
                            return False
                            
                        success = await asyncio.to_thread(get_stream)
                        if success and os.path.exists(filename) and os.path.getsize(filename) > 10000:
                            self.cached_cobalt = api
                            title = data.get("filename", "Audio Track" if mode == "audio" else "Video Clip")
                            title = os.path.splitext(title)[0]
                            return filename, title
                        if os.path.exists(filename):
                            os.remove(filename)
                elif r.status_code == 400 and "jwt.missing" in r.text:
                    # Turnstile protected, skip silently
                    continue
            except Exception as e:
                logger.debug(f"Cobalt attempt failed on {api}: {e}")
        return None
