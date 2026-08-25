import time
import logging
import asyncio
import urllib.parse
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

class GameDealsService:
    def __init__(self):
        self._cache: dict = {}
        self._store_cache: dict = {}
        self._store_cache_time: float = 0
        self._http_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def _get_cached(self, key: str):
        if key in self._cache:
            data, exp = self._cache[key]
            if time.time() < exp:
                return data
            del self._cache[key]
        return None

    def _set_cached(self, key: str, data, ttl: int = 1800):
        self._cache[key] = (data, time.time() + ttl)

    async def get_store_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """Retrieves and caches the CheapShark store ID to store name mapping."""
        if self._store_cache and (time.time() - self._store_cache_time < 86400):
            return self._store_cache
        try:
            r = await client.get("https://www.cheapshark.com/api/1.0/stores", timeout=8)
            if r.status_code == 200:
                self._store_cache = {str(s["storeID"]): s["storeName"] for s in r.json()}
                self._store_cache_time = time.time()
                return self._store_cache
        except Exception as e:
            logger.debug(f"GameDealsService: store lookup error: {e}")
        return self._store_cache or {"1": "Steam", "2": "GamersGate", "3": "GreenManGaming", "7": "GOG", "11": "Humble Store", "15": "Fanatical"}

    async def search_game(self, query: str) -> dict | None:
        """
        Searches Steam, SteamDB, CheapShark, and GG.deals for a unified game overview.
        Returns comprehensive pricing, historical low (ATL), review ratings, and links.
        """
        clean_query = query.strip()
        cache_key = f"game_{clean_query.lower()}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        async with httpx.AsyncClient(timeout=12, headers=self._http_headers, follow_redirects=True) as client:
            store_map = await self.get_store_map(client)
            steam_app = None
            appid = None
            game_title = clean_query

            # ── 1. Steam Storefront Search (Tier 1) ──
            try:
                s_res = await client.get(
                    "https://store.steampowered.com/api/storesearch/",
                    params={"term": clean_query, "l": "english", "cc": "US"}
                )
                if s_res.status_code == 200:
                    items = s_res.json().get("items", [])
                    if items:
                        top_item = items[0]
                        appid = top_item["id"]
                        game_title = top_item["name"]
            except Exception as e:
                logger.debug(f"Steam storesearch failed for '{clean_query}': {e}")

            # ── 2. Steam App Details ──
            app_details = {}
            if appid:
                try:
                    d_res = await client.get(
                        "https://store.steampowered.com/api/appdetails",
                        params={"appids": appid, "cc": "US", "l": "english"}
                    )
                    if d_res.status_code == 200:
                        app_details = d_res.json().get(str(appid), {}).get("data", {}) or {}
                        if app_details.get("name"):
                            game_title = app_details["name"]
                except Exception as e:
                    logger.debug(f"Steam appdetails failed for appid {appid}: {e}")

            # ── 3. CheapShark Deals & Historical Low (ATL) (Tier 2) ──
            cheapshark_deals = []
            cheapest_ever = {}
            steam_rating_text = None
            steam_rating_pct = None
            metacritic_score = None

            try:
                deals_res = None
                if appid:
                    deals_res = await client.get(
                        "https://www.cheapshark.com/api/1.0/deals",
                        params={"steamAppID": str(appid), "pageSize": 10}
                    )
                if not deals_res or deals_res.status_code != 200 or not deals_res.json():
                    deals_res = await client.get(
                        "https://www.cheapshark.com/api/1.0/deals",
                        params={"title": game_title, "pageSize": 10}
                    )

                if deals_res and deals_res.status_code == 200:
                    raw_deals = deals_res.json()
                    if raw_deals and isinstance(raw_deals, list):
                        cheapshark_deals = raw_deals
                        first_deal = raw_deals[0]
                        metacritic_score = first_deal.get("metacriticScore")
                        steam_rating_text = first_deal.get("steamRatingText")
                        steam_rating_pct = first_deal.get("steamRatingPercent")

                        gid = first_deal.get("gameID")
                        if gid:
                            g_res = await client.get(f"https://www.cheapshark.com/api/1.0/games?id={gid}")
                            if g_res.status_code == 200:
                                g_data = g_res.json()
                                cheapest_ever = g_data.get("cheapestPriceEver", {})
                                if g_data.get("deals"):
                                    cheapshark_deals = g_data["deals"]
            except Exception as e:
                logger.debug(f"CheapShark deal lookup error: {e}")

            if not app_details and not cheapshark_deals:
                return None

            # ── 4. Extract Pricing, Discounts & Historical Low ──
            price_overview = app_details.get("price_overview", {})
            is_free = app_details.get("is_free", False)

            if is_free:
                steam_final = "Free to Play"
                steam_initial = "Free"
                steam_discount = 0
            elif price_overview:
                steam_final = price_overview.get("final_formatted", "N/A")
                steam_initial = price_overview.get("initial_formatted", steam_final)
                steam_discount = price_overview.get("discount_percent", 0)
            else:
                steam_final = "N/A"
                steam_initial = "N/A"
                steam_discount = 0

            # Historical all-time low (ATL)
            atl_price_val = None
            atl_price_str = "N/A"
            atl_date_str = ""
            if cheapest_ever and cheapest_ever.get("price"):
                try:
                    atl_price_val = float(cheapest_ever["price"])
                    atl_price_str = f"${atl_price_val:.2f}"
                    if cheapest_ever.get("date"):
                        dt = datetime.fromtimestamp(cheapest_ever["date"])
                        atl_date_str = dt.strftime("%b %Y")
                except Exception:
                    atl_price_str = f"${cheapest_ever.get('price')}"

            is_new_low = False
            current_best_price = None
            
            best_key_store = None
            best_key_price_str = None
            best_key_deal_id = None

            if cheapshark_deals:
                sorted_deals = []
                for d in cheapshark_deals:
                    try:
                        p = float(d.get("salePrice") or d.get("price") or 999999)
                        sorted_deals.append((p, d))
                    except Exception:
                        pass
                sorted_deals.sort(key=lambda x: x[0])

                if sorted_deals:
                    lowest_p, lowest_deal = sorted_deals[0]
                    current_best_price = lowest_p
                    store_id = str(lowest_deal.get("storeID", "1"))
                    best_key_store = store_map.get(store_id, f"Store {store_id}")
                    best_key_price_str = f"${lowest_p:.2f}"
                    best_key_deal_id = lowest_deal.get("dealID")

            if atl_price_val is not None and current_best_price is not None:
                if current_best_price <= (atl_price_val + 0.50):
                    is_new_low = True

            # ── 5. Metadata & Descriptions ──
            short_desc = app_details.get("short_description", "")
            if not short_desc and cheapshark_deals:
                short_desc = "PC Video Game available across digital storefronts."
            import re
            short_desc = re.sub(r"<[^>]+>", "", short_desc).strip()
            if len(short_desc) > 350:
                short_desc = short_desc[:347] + "..."

            genres = [g.get("description", "") for g in app_details.get("genres", [])]
            genre_str = ", ".join([g for g in genres if g]) or "Action / Adventure"

            developers = app_details.get("developers", [])
            dev_str = ", ".join(developers) if developers else "Unknown Developer"

            release_date = app_details.get("release_date", {}).get("date", "N/A")
            header_image = app_details.get("header_image")
            if not header_image and cheapshark_deals:
                header_image = cheapshark_deals[0].get("thumb")

            if not metacritic_score and app_details.get("metacritic"):
                metacritic_score = str(app_details["metacritic"].get("score", ""))

            # ── 6. Generate Deep Links ──
            encoded_title = urllib.parse.quote_plus(game_title)
            steam_url = f"https://store.steampowered.com/app/{appid}/" if appid else f"https://store.steampowered.com/search/?term={encoded_title}"
            steamdb_url = f"https://steamdb.info/app/{appid}/" if appid else f"https://steamdb.info/search/?a=app&q={encoded_title}"
            ggdeals_url = f"https://gg.deals/games/?title={encoded_title}"

            result = {
                "title": game_title,
                "appid": appid,
                "header_image": header_image,
                "description": short_desc,
                "genres": genre_str,
                "developer": dev_str,
                "release_date": release_date,
                "steam_price": steam_final,
                "steam_initial": steam_initial,
                "steam_discount": steam_discount,
                "is_free": is_free,
                "metacritic": metacritic_score,
                "steam_rating_text": steam_rating_text,
                "steam_rating_percent": steam_rating_pct,
                "historical_low": atl_price_str,
                "historical_low_date": atl_date_str,
                "is_new_low": is_new_low,
                "best_key_price": best_key_price_str,
                "best_key_store": best_key_store,
                "best_key_deal_id": best_key_deal_id,
                "steam_url": steam_url,
                "steamdb_url": steamdb_url,
                "ggdeals_url": ggdeals_url,
            }

            self._set_cached(cache_key, result, ttl=1800)
            return result

    async def get_top_deals(self, limit: int = 8) -> list[dict]:
        """
        Retrieves top trending active game sales, highlighting big discounts & historical lows.
        """
        cache_key = f"top_deals_{limit}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        deals_list = []
        async with httpx.AsyncClient(timeout=10, headers=self._http_headers) as client:
            store_map = await self.get_store_map(client)
            try:
                r = await client.get(
                    "https://www.cheapshark.com/api/1.0/deals",
                    params={
                        "sortBy": "Deal Rating",
                        "pageSize": str(limit),
                        "metacritic": "70",
                        "onSale": "1"
                    }
                )
                if r.status_code == 200:
                    raw = r.json()
                    for item in raw:
                        store_id = str(item.get("storeID", "1"))
                        store_name = store_map.get(store_id, "Store")
                        savings = round(float(item.get("savings", 0)))
                        appid = item.get("steamAppID")
                        encoded = urllib.parse.quote_plus(item.get("title", ""))

                        deals_list.append({
                            "title": item.get("title", "Game"),
                            "sale_price": f"${float(item.get('salePrice', 0)):.2f}",
                            "normal_price": f"${float(item.get('normalPrice', 0)):.2f}",
                            "savings": f"-{savings}%",
                            "store": store_name,
                            "metacritic": item.get("metacriticScore"),
                            "steam_rating": item.get("steamRatingText"),
                            "steam_url": f"https://store.steampowered.com/app/{appid}/" if appid else f"https://store.steampowered.com/search/?term={encoded}",
                            "steamdb_url": f"https://steamdb.info/app/{appid}/" if appid else f"https://steamdb.info/search/?a=app&q={encoded}",
                            "ggdeals_url": f"https://gg.deals/games/?title={encoded}",
                            "thumb": item.get("thumb")
                        })
            except Exception as e:
                logger.error(f"GameDealsService.get_top_deals failed: {e}")

        if deals_list:
            self._set_cached(cache_key, deals_list, ttl=900)
        return deals_list
