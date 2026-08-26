import httpx
import logging
import urllib.parse
from bs4 import BeautifulSoup

from services.http_client import SharedHttpClient
from services.cache_service import fast_cache

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def search_duckduckgo(self, query: str, limit: int = 5) -> str:
        """Performs unrestricted web search via DuckDuckGo with SafeSearch OFF (kp=-2) & FastCache."""
        clean_q = query.strip()
        if not clean_q:
            return "No query provided."

        cache_key = f"ddg_{clean_q.lower()}_{limit}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        try:
            encoded = urllib.parse.quote_plus(clean_q)
            url = f"https://html.duckduckgo.com/html/?q={encoded}&kp=-2"
            
            client = SharedHttpClient.get_client()
            r = await client.get(url, headers=self._headers, timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                results = []
                for res in soup.find_all("div", class_="result")[:limit]:
                    title_el = res.find("a", class_="result__a")
                    snippet_el = res.find("a", class_="result__snippet")
                    if title_el:
                        title = title_el.get_text(strip=True)
                        href = title_el.get("href", "")
                        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                        results.append(f"• **{title}**\n  {snippet}\n  Link: {href}")

                if results:
                    final_res = "\n\n".join(results)
                    fast_cache.set(cache_key, final_res, ttl_seconds=600.0)
                    return final_res
                
                # Fallback text extract
                snippets = [s.get_text(strip=True) for s in soup.find_all("a", class_="result__snippet")[:limit]]
                if snippets:
                    final_res = "\n".join(snippets)
                    fast_cache.set(cache_key, final_res, ttl_seconds=600.0)
                    return final_res

        except Exception as e:
            logger.debug(f"DuckDuckGo search error: {e}")

        return f"Web search for '{clean_q}' completed without matching snippets."

    async def search_wikipedia(self, query: str) -> str:
        """Searches Wikipedia summary API with FastCache."""
        clean_q = query.strip()
        if not clean_q:
            return "No query provided."

        cache_key = f"wiki_{clean_q.lower()}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        try:
            encoded = urllib.parse.quote(clean_q)
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
            client = SharedHttpClient.get_client()
            r = await client.get(url, headers=self._headers, timeout=6)
            if r.status_code == 200:
                data = r.json()
                title = data.get("title", clean_q)
                extract = data.get("extract", "")
                if extract:
                    res = f"📚 **Wikipedia: {title}**\n\n{extract}"
                    fast_cache.set(cache_key, res, ttl_seconds=3600.0)
                    return res
        except Exception as e:
            logger.debug(f"Wikipedia search error: {e}")

        return f"No Wikipedia summary found for '{clean_q}'."
