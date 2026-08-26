import time
import logging
import asyncio
import urllib.parse
from datetime import datetime
import httpx
from services.gaming.currency import format_inr, convert_usd_to_inr_str, USD_TO_INR

logger = logging.getLogger(__name__)

class GameDealsService:
    def __init__(self):
        self._cache: dict = {}
        self._store_cache: dict = {}
        self._store_cache_time: float = 0
        self._http_headers = {
            "User-Agent": "GiyuBot-GameDeals/2.0 (contact@giyubot.dev; https://t.me/GiyuBot)"
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
        Searches Steam, SteamDB, CheapShark, and GG.deals for a unified game overview in INR.
        Returns comprehensive pricing in INR, historical low (ATL in INR), review ratings, and links.
        """
        clean_query = query.strip()
        cache_key = f"game_inr_{clean_query.lower()}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        async with httpx.AsyncClient(timeout=12, headers=self._http_headers, follow_redirects=True) as client:
            store_map = await self.get_store_map(client)
            steam_app = None
            appid = None
            game_title = clean_query

            # 1. Steam Storefront Search in India (cc=IN)
            try:
                s_res = await client.get(
                    "https://store.steampowered.com/api/storesearch/",
                    params={"term": clean_query, "l": "english", "cc": "IN"}
                )
                if s_res.status_code == 200:
                    items = s_res.json().get("items", [])
                    if items:
                        top_item = items[0]
                        appid = top_item["id"]
                        game_title = top_item["name"]
            except Exception as e:
                logger.debug(f"Steam storesearch failed for '{clean_query}': {e}")

            # 2. Steam App Details in India (cc=IN)
            app_details = {}
            live_players = None
            if appid:
                try:
                    d_res = await client.get(
                        "https://store.steampowered.com/api/appdetails",
                        params={"appids": appid, "cc": "IN", "l": "english"}
                    )
                    if d_res.status_code == 200:
                        app_details = d_res.json().get(str(appid), {}).get("data", {}) or {}
                        if app_details.get("name"):
                            game_title = app_details["name"]
                except Exception as e:
                    logger.debug(f"Steam appdetails failed for appid {appid}: {e}")

                try:
                    ccu_res = await client.get(
                        f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}",
                        timeout=5
                    )
                    if ccu_res.status_code == 200:
                        count = ccu_res.json().get("response", {}).get("player_count")
                        if count is not None:
                            live_players = count
                except Exception as e:
                    logger.debug(f"Steam CCU lookup error: {e}")

            # 3. CheapShark Game & Historical Low (ATL) Lookup
            cheapshark_deals = []
            cheapest_ever = {}
            steam_rating_text = None
            steam_rating_pct = None
            metacritic_score = None

            try:
                gid = None
                games_list = []
                
                if appid:
                    g_res = await client.get(
                        "https://www.cheapshark.com/api/1.0/games",
                        params={"steamAppID": str(appid)}
                    )
                    if g_res.status_code == 200 and isinstance(g_res.json(), list):
                        games_list = g_res.json()

                if not games_list:
                    g_res = await client.get(
                        "https://www.cheapshark.com/api/1.0/games",
                        params={"title": game_title, "limit": 10}
                    )
                    if g_res.status_code == 200 and isinstance(g_res.json(), list):
                        games_list = g_res.json()

                if games_list:
                    best_match = games_list[0]
                    if appid:
                        for g_item in games_list:
                            if str(g_item.get("steamAppID")) == str(appid):
                                best_match = g_item
                                break
                    
                    gid = best_match.get("gameID")
                    if gid:
                        game_data_res = await client.get(f"https://www.cheapshark.com/api/1.0/games?id={gid}")
                        if game_data_res.status_code == 200:
                            g_data = game_data_res.json()
                            cheapest_ever = g_data.get("cheapestPriceEver", {})
                            if g_data.get("deals"):
                                cheapshark_deals = g_data["deals"]
                            if g_data.get("info"):
                                info = g_data["info"]
                                metacritic_score = metacritic_score or info.get("metacriticScore")
                                steam_rating_text = steam_rating_text or info.get("steamRatingText")
                                steam_rating_pct = steam_rating_pct or info.get("steamRatingPercent")

                if not cheapest_ever:
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
                            metacritic_score = metacritic_score or first_deal.get("metacriticScore")
                            steam_rating_text = steam_rating_text or first_deal.get("steamRatingText")
                            steam_rating_pct = steam_rating_pct or first_deal.get("steamRatingPercent")
                            deal_gid = first_deal.get("gameID")
                            if deal_gid:
                                g_res = await client.get(f"https://www.cheapshark.com/api/1.0/games?id={deal_gid}")
                                if g_res.status_code == 200:
                                    g_data = g_res.json()
                                    cheapest_ever = g_data.get("cheapestPriceEver", {})
                                    if g_data.get("deals"):
                                        cheapshark_deals = g_data["deals"]
            except Exception as e:
                logger.debug(f"CheapShark game lookup error: {e}")

            # 4. Construct Pricing & Details
            price_overview = app_details.get("price_overview", {})
            is_free = app_details.get("is_free", False)

            if is_free:
                steam_final_inr = "Free to Play"
                steam_initial_inr = "Free"
                steam_discount_pct = 0
            elif price_overview:
                steam_final_inr = price_overview.get("final_formatted") or format_inr(price_overview.get("final", 0) / 100)
                steam_initial_inr = price_overview.get("initial_formatted") or format_inr(price_overview.get("initial", 0) / 100)
                steam_discount_pct = price_overview.get("discount_percent", 0)
            else:
                steam_final_inr = "N/A"
                steam_initial_inr = "N/A"
                steam_discount_pct = 0

            # Historical Low in INR
            atl_inr = "N/A"
            atl_date_str = None
            atl_relative_str = None
            is_new_low = False

            if cheapest_ever and "price" in cheapest_ever:
                try:
                    usd_val = float(cheapest_ever["price"])
                    atl_inr = convert_usd_to_inr_str(usd_val)
                    if cheapest_ever.get("date"):
                        dt = datetime.utcfromtimestamp(cheapest_ever["date"])
                        atl_date_str = dt.strftime("%b %d, %Y")
                        diff_days = (datetime.utcnow() - dt).days
                        atl_relative_str = "today" if diff_days == 0 else (f"{diff_days}d ago" if diff_days < 30 else f"{diff_days // 30}mo ago")
                        if diff_days <= 2:
                            is_new_low = True
                except Exception as e:
                    logger.debug(f"Error parsing cheapestPriceEver: {e}")

            # Best Alternative Store / Keyshop Deal
            best_key_store = None
            best_key_price_inr = None
            best_key_deal_url = None

            if cheapshark_deals:
                non_steam = [d for d in cheapshark_deals if str(d.get("storeID")) != "1"]
                target_deal = non_steam[0] if non_steam else cheapshark_deals[0]
                store_id = str(target_deal.get("storeID"))
                best_key_store = store_map.get(store_id, f"Store #{store_id}")
                if "price" in target_deal:
                    best_key_price_inr = convert_usd_to_inr_str(target_deal["price"])
                if target_deal.get("dealID"):
                    best_key_deal_url = f"https://www.cheapshark.com/redirect?dealID={target_deal['dealID']}"

            # Steam & GG.deals URLs
            steam_url = f"https://store.steampowered.com/app/{appid}" if appid else f"https://store.steampowered.com/search/?term={urllib.parse.quote(game_title)}"
            steamdb_url = f"https://steamdb.info/app/{appid}/" if appid else f"https://steamdb.info/search/?a=app&q={urllib.parse.quote(game_title)}"
            ggdeals_url = f"https://gg.deals/games/?title={urllib.parse.quote(game_title)}"

            # Metadata
            genres = ", ".join([g.get("description", "") for g in app_details.get("genres", [])[:3]]) or "Action / Adventure"
            devs = ", ".join(app_details.get("developers", [])) or "Independent"
            release_date = app_details.get("release_date", {}).get("date", "Available Now")
            header_img = app_details.get("header_image") or (f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg" if appid else None)
            desc = app_details.get("short_description", "")
            if len(desc) > 160:
                desc = desc[:157] + "..."

            result = {
                "title": game_title,
                "appid": appid,
                "steam_price": steam_final_inr,
                "steam_initial": steam_initial_inr,
                "steam_discount": steam_discount_pct,
                "historical_low": atl_inr,
                "historical_low_date": atl_date_str,
                "historical_low_relative": atl_relative_str,
                "is_new_low": is_new_low,
                "best_key_store": best_key_store,
                "best_key_price": best_key_price_inr,
                "best_key_deal_url": best_key_deal_url,
                "steam_rating_text": steam_rating_text,
                "steam_rating_percent": steam_rating_pct,
                "metacritic": metacritic_score,
                "live_players": live_players,
                "genres": genres,
                "developer": devs,
                "release_date": release_date,
                "header_image": header_img,
                "description": desc,
                "steam_url": steam_url,
                "steamdb_url": steamdb_url,
                "ggdeals_url": ggdeals_url,
            }

            self._set_cached(cache_key, result, ttl=1800)
            return result

    async def get_top_deals(self, limit: int = 6) -> list[dict]:
        """Retrieves top trending PC game deals converted into Indian Rupees (INR)."""
        cache_key = f"top_deals_inr_{limit}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        async with httpx.AsyncClient(timeout=10, headers=self._http_headers, follow_redirects=True) as client:
            store_map = await self.get_store_map(client)
            try:
                r = await client.get(
                    "https://www.cheapshark.com/api/1.0/deals",
                    params={"sortBy": "Deal Rating", "pageSize": limit, "onSale": "1"}
                )
                if r.status_code == 200:
                    deals_raw = r.json()
                    formatted = []
                    for d in deals_raw:
                        s_id = str(d.get("storeID"))
                        store_name = store_map.get(s_id, "Digital Store")
                        savings = round(float(d.get("savings", 0)))
                        deal_price = convert_usd_to_inr_str(d.get("salePrice", "0"))
                        retail_price = convert_usd_to_inr_str(d.get("normalPrice", "0"))
                        
                        steam_rating = None
                        if d.get("steamRatingText"):
                            pct = f" ({d.get('steamRatingPercent')}%)" if d.get("steamRatingPercent") else ""
                            steam_rating = f"{d.get('steamRatingText')}{pct}"

                        formatted.append({
                            "title": d.get("title", "Unknown Title"),
                            "deal_price": deal_price,
                            "retail_price": retail_price,
                            "savings_pct": savings,
                            "store_name": store_name,
                            "steam_rating": steam_rating,
                            "metacritic": d.get("metacriticScore"),
                            "thumbnail": d.get("thumb"),
                            "deal_url": f"https://www.cheapshark.com/redirect?dealID={d.get('dealID')}",
                            "steam_url": f"https://store.steampowered.com/app/{d.get('steamAppID')}" if d.get("steamAppID") else None
                        })
                    self._set_cached(cache_key, formatted, ttl=1800)
                    return formatted
            except Exception as e:
                logger.error(f"Error fetching top game deals: {e}")
        return []

    async def check_all_time_low(self, query: str) -> dict | None:
        """Dedicated helper that checks if a game is matching or breaking its ATL price in INR."""
        game = await self.search_game(query)
        if not game:
            return None

        return {
            "title": game["title"],
            "steam_price": game["steam_price"],
            "historical_low": game["historical_low"],
            "historical_low_date": game["historical_low_date"],
            "historical_low_relative": game["historical_low_relative"],
            "is_new_low": game["is_new_low"],
            "best_key_store": game["best_key_store"],
            "best_key_price": game["best_key_price"],
            "steam_url": game["steam_url"],
            "steamdb_url": game["steamdb_url"],
            "ggdeals_url": game["ggdeals_url"],
            "header_image": game["header_image"],
        }
