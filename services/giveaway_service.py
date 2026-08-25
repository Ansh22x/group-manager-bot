import time
import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

class GiveawayService:
    def __init__(self):
        self._cache: dict = {}
        self._seen_ids: set = set()
        self._http_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def fetch_all_giveaways(self) -> list[dict]:
        """Fetches all active giveaways from GamerPower API with caching."""
        cache_key = "all_giveaways"
        if cache_key in self._cache:
            data, exp = self._cache[cache_key]
            if time.time() < exp:
                return data

        giveaways = []
        try:
            async with httpx.AsyncClient(timeout=12, headers=self._http_headers, follow_redirects=True) as client:
                r = await client.get("https://www.gamerpower.com/api/giveaways", params={"platform": "pc"})
                if r.status_code == 200:
                    giveaways = r.json()
                    self._cache[cache_key] = (giveaways, time.time() + 600)  # 10 minute cache
        except Exception as e:
            logger.error(f"GiveawayService.fetch_all_giveaways failed: {e}")

        return giveaways

    async def get_giveaways(self, source: str = "all", limit: int = 6) -> list[dict]:
        """
        Retrieves active giveaways filtered by source platform.
        Supported sources: 'alienware', 'medal', 'amd', 'steam', 'epic', 'gog', 'all'.
        """
        raw = await self.fetch_all_giveaways()
        if not raw:
            return []

        source_lower = source.strip().lower()
        filtered = []

        for item in raw:
            item_str = f"{item.get('title', '')} {item.get('description', '')} {item.get('platforms', '')} {item.get('instructions', '')}".lower()
            
            match = False
            if source_lower in ("all", "pc"):
                match = True
            elif source_lower in ("alienware", "alienwarearena"):
                match = "alienware" in item_str
            elif source_lower in ("medal", "medal.tv", "medaltv"):
                match = "medal" in item_str
            elif source_lower in ("amd", "amd gaming", "radeon", "ryzen"):
                match = "amd" in item_str or "radeon" in item_str or "ryzen" in item_str
            elif source_lower in ("steam", "valve"):
                match = "steam" in item.get("platforms", "").lower() or "steam" in item.get("title", "").lower()
            elif source_lower in ("epic", "epic games", "epicgames"):
                match = "epic" in item_str
            elif source_lower in ("gog", "gog.com"):
                match = "gog" in item_str
            else:
                # Custom keyword match
                match = source_lower in item_str

            if match:
                clean_instructions = item.get("instructions", "").replace("\r\n", " ").strip()
                if len(clean_instructions) > 200:
                    clean_instructions = clean_instructions[:197] + "..."

                filtered.append({
                    "id": item.get("id"),
                    "title": item.get("title", "Free Game"),
                    "worth": item.get("worth", "N/A"),
                    "type": item.get("type", "Game"),
                    "platforms": item.get("platforms", "PC"),
                    "description": item.get("description", ""),
                    "instructions": clean_instructions,
                    "url": item.get("open_giveaway_url") or item.get("gamerpower_url"),
                    "image": item.get("image") or item.get("thumbnail"),
                    "end_date": item.get("end_date", "N/A"),
                })

        return filtered[:limit]

    async def get_new_giveaways(self) -> list[dict]:
        """
        Detects newly released giveaways that have not been broadcasted yet.
        Used by the automated background alerting job.
        """
        raw = await self.fetch_all_giveaways()
        if not raw:
            return []

        # If seen_ids is empty (first boot), populate without alerting backlog
        if not self._seen_ids:
            self._seen_ids = {item.get("id") for item in raw if item.get("id")}
            return []

        new_items = []
        for item in raw:
            item_id = item.get("id")
            if item_id and item_id not in self._seen_ids:
                self._seen_ids.add(item_id)
                # Prioritize key platforms: Alienware, AMD, Medal, Steam 100% off, Epic
                new_items.append({
                    "id": item_id,
                    "title": item.get("title", "New Free Game"),
                    "worth": item.get("worth", "N/A"),
                    "platforms": item.get("platforms", "PC"),
                    "description": item.get("description", ""),
                    "url": item.get("open_giveaway_url") or item.get("gamerpower_url"),
                    "image": item.get("image") or item.get("thumbnail"),
                })

        return new_items
