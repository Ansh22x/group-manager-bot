import time
import logging
import asyncio
import urllib.parse
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

USD_TO_INR = 87.50

def format_inr(amount: float | str) -> str:
    """Formats numeric or string amount into Indian Rupee representation (e.g. ₹ 1,499)."""
    if isinstance(amount, str):
        if amount.strip().lower() in ("free", "free to play", "n/a", "none", ""):
            return amount
        try:
            val = float(amount.replace("$", "").replace("₹", "").replace(",", "").strip())
            return f"₹ {round(val):,}"
        except Exception:
            return amount
    try:
        return f"₹ {round(amount):,}"
    except Exception:
        return str(amount)

def convert_usd_to_inr_str(usd_amount: float | str) -> str:
    """Converts USD amount to INR representation."""
    if isinstance(usd_amount, str):
        if usd_amount.strip().lower() in ("free", "free to play", "n/a", "none", ""):
            return usd_amount
        try:
            val = float(usd_amount.replace("$", "").replace(",", "").strip())
            return f"₹ {round(val * USD_TO_INR):,}"
        except Exception:
            return usd_amount
    try:
        return f"₹ {round(usd_amount * USD_TO_INR):,}"
    except Exception:
        return str(usd_amount)


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

            # ── 1. Steam Storefront Search in India (cc=IN) ──
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

            # ── 2. Steam App Details in India (cc=IN) ──
            app_details = {}
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

            # ── 3. CheapShark Game & Historical Low (ATL) Lookup (Tier 2) ──
            cheapshark_deals = []
            cheapest_ever = {}
            steam_rating_text = None
            steam_rating_pct = None
            metacritic_score = None

            try:
                gid = None
                games_list = []
                
                # 3a. Search /games?steamAppID=...
                if appid:
                    g_res = await client.get(
                        "https://www.cheapshark.com/api/1.0/games",
                        params={"steamAppID": str(appid)}
                    )
                    if g_res.status_code == 200 and isinstance(g_res.json(), list):
                        games_list = g_res.json()

                # 3b. Search /games?title=... if not found
                if not games_list:
                    g_res = await client.get(
                        "https://www.cheapshark.com/api/1.0/games",
                        params={"title": game_title, "limit": 10}
                    )
                    if g_res.status_code == 200 and isinstance(g_res.json(), list):
                        games_list = g_res.json()

                if games_list:
                    # Pick exact or best match
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

                # 3c. Fallback to /deals?steamAppID=... or /deals?title=...
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

            if not app_details and not cheapshark_deals and not cheapest_ever:
                return None

            # ── 4. Extract Pricing, Discounts & Historical Low in INR ──
            price_overview = app_details.get("price_overview", {})
            is_free = app_details.get("is_free", False)

            if is_free:
                steam_final = "Free to Play"
                steam_initial = "Free"
                steam_discount = 0
            elif price_overview:
                raw_final = price_overview.get("final_formatted", "")
                raw_initial = price_overview.get("initial_formatted", raw_final)
                steam_final = raw_final if "₹" in raw_final else format_inr(raw_final)
                steam_initial = raw_initial if "₹" in raw_initial else format_inr(raw_initial)
                steam_discount = price_overview.get("discount_percent", 0)
            elif cheapshark_deals:
                # If Steam India price unavailable, convert from CheapShark USD
                d_p = float(cheapshark_deals[0].get("salePrice") or cheapshark_deals[0].get("price") or 0)
                steam_final = convert_usd_to_inr_str(d_p) if d_p > 0 else "N/A"
                steam_initial = steam_final
                steam_discount = 0
            else:
                steam_final = "N/A"
                steam_initial = "N/A"
                steam_discount = 0

            # Historical all-time low (ATL in INR)
            atl_price_val = None
            atl_price_str = "N/A"
            atl_date_str = ""
            atl_relative_str = ""

            if is_free:
                atl_price_str = "₹ 0 (Free to Play)"
                atl_date_str = "Permanent"
                atl_relative_str = "always free"
            elif cheapest_ever and cheapest_ever.get("price"):
                try:
                    atl_price_val = float(cheapest_ever["price"])
                    atl_price_str = convert_usd_to_inr_str(atl_price_val)
                    if cheapest_ever.get("date"):
                        dt = datetime.fromtimestamp(cheapest_ever["date"])
                        atl_date_str = dt.strftime("%b %d, %Y")
                        diff_days = (datetime.now() - dt).days
                        if diff_days <= 1:
                            atl_relative_str = "recently"
                        elif diff_days < 30:
                            atl_relative_str = f"{diff_days}d ago"
                        elif diff_days < 365:
                            m = max(1, diff_days // 30)
                            atl_relative_str = f"{m} mo{'s' if m > 1 else ''} ago"
                        else:
                            y = diff_days // 365
                            rem_m = (diff_days % 365) // 30
                            atl_relative_str = f"{y} yr{'s' if y > 1 else ''} {rem_m} mo ago" if rem_m > 0 else f"{y} yr{'s' if y > 1 else ''} ago"
                except Exception:
                    atl_price_str = convert_usd_to_inr_str(cheapest_ever.get('price'))
            elif steam_final != "N/A":
                atl_price_str = f"{steam_final} (Current Best)"
                atl_date_str = "Current"
                atl_relative_str = "active"

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
                    best_key_price_str = convert_usd_to_inr_str(lowest_p)
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

            best_key_deal_url = f"https://www.cheapshark.com/redirect?dealID={best_key_deal_id}" if best_key_deal_id else None

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
                "historical_low_relative": atl_relative_str,
                "is_new_low": is_new_low,
                "best_key_price": best_key_price_str,
                "best_key_store": best_key_store,
                "best_key_deal_id": best_key_deal_id,
                "best_key_deal_url": best_key_deal_url,
                "steam_url": steam_url,
                "steamdb_url": steamdb_url,
                "ggdeals_url": ggdeals_url,
            }

            self._set_cached(cache_key, result, ttl=1800)
            return result

    async def get_top_deals(self, limit: int = 8) -> list[dict]:
        """
        Retrieves top trending active game sales in INR with dual-source CheapShark & Steam Specials fallback.
        """
        cache_key = f"top_deals_inr_{limit}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        deals_list = []
        seen_titles = set()

        async with httpx.AsyncClient(timeout=10, headers=self._http_headers) as client:
            store_map = await self.get_store_map(client)
            
            # ── Tier 1: CheapShark Top Deals ──
            try:
                r = await client.get(
                    "https://www.cheapshark.com/api/1.0/deals",
                    params={
                        "sortBy": "Deal Rating",
                        "pageSize": "25",
                        "onSale": "1"
                    }
                )
                if r.status_code == 200:
                    raw = r.json()
                    for item in raw:
                        title = item.get("title", "").strip()
                        if not title or title.lower() in seen_titles:
                            continue
                        
                        savings = round(float(item.get("savings", 0)))
                        if savings <= 0:
                            continue

                        store_id = str(item.get("storeID", "1"))
                        store_name = store_map.get(store_id, "Digital Store")
                        appid = item.get("steamAppID")
                        encoded = urllib.parse.quote_plus(title)

                        seen_titles.add(title.lower())
                        deals_list.append({
                            "title": title,
                            "sale_price": convert_usd_to_inr_str(item.get('salePrice', 0)),
                            "normal_price": convert_usd_to_inr_str(item.get('normalPrice', 0)),
                            "savings": f"-{savings}%",
                            "store": store_name,
                            "metacritic": item.get("metacriticScore"),
                            "steam_rating": item.get("steamRatingText"),
                            "steam_url": f"https://store.steampowered.com/app/{appid}/" if appid else f"https://store.steampowered.com/search/?term={encoded}",
                            "steamdb_url": f"https://steamdb.info/app/{appid}/" if appid else f"https://steamdb.info/search/?a=app&q={encoded}",
                            "ggdeals_url": f"https://gg.deals/games/?title={encoded}",
                            "thumb": item.get("thumb")
                        })
                        if len(deals_list) >= limit:
                            break
            except Exception as e:
                logger.debug(f"CheapShark deals fetch error: {e}")

            # ── Tier 2: Steam Specials Fallback (cc=IN) ──
            if len(deals_list) < limit:
                try:
                    s_res = await client.get("https://store.steampowered.com/api/featuredcategories/?cc=IN&l=english")
                    if s_res.status_code == 200:
                        specials = s_res.json().get("specials", {}).get("items", [])
                        for sp in specials:
                            title = sp.get("name", "").strip()
                            if not title or title.lower() in seen_titles:
                                continue

                            discount = sp.get("discount_percent", 0)
                            if discount <= 0:
                                continue

                            f_price = sp.get("final_price", 0) / 100
                            o_price = sp.get("original_price", 0) / 100
                            appid = sp.get("id")
                            encoded = urllib.parse.quote_plus(title)

                            seen_titles.add(title.lower())
                            deals_list.append({
                                "title": title,
                                "sale_price": f"₹ {round(f_price):,}",
                                "normal_price": f"₹ {round(o_price):,}",
                                "savings": f"-{discount}%",
                                "store": "Steam Store",
                                "metacritic": None,
                                "steam_rating": "Very Positive",
                                "steam_url": f"https://store.steampowered.com/app/{appid}/",
                                "steamdb_url": f"https://steamdb.info/app/{appid}/",
                                "ggdeals_url": f"https://gg.deals/games/?title={encoded}",
                                "thumb": sp.get("header_image")
                            })
                            if len(deals_list) >= limit:
                                break
                except Exception as se:
                    logger.debug(f"Steam specials fallback error: {se}")

        if deals_list:
            self._set_cached(cache_key, deals_list, ttl=900)
        return deals_list[:limit]
