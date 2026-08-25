import httpx
import logging
import urllib.parse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def search_duckduckgo(self, query: str, limit: int = 5) -> str:
        """Performs unrestricted web search via DuckDuckGo with SafeSearch OFF (kp=-2)."""
        clean_q = query.strip()
        if not clean_q:
            return "No query provided."

        try:
            encoded = urllib.parse.quote_plus(clean_q)
            # kp=-2 turns SafeSearch completely OFF (returns all adult / mature / explicit / unfiltered results)
            url = f"https://html.duckduckgo.com/html/?q={encoded}&kp=-2"
            
            async with httpx.AsyncClient(timeout=10, headers=self._headers, follow_redirects=True) as client:
                r = await client.get(url)
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
                        return "\n\n".join(results)
                    
                    # Fallback text extract
                    snippets = [s.get_text(strip=True) for s in soup.find_all("a", class_="result__snippet")[:limit]]
                    if snippets:
                        return "\n".join(snippets)

        except Exception as e:
            logger.debug(f"DuckDuckGo search error: {e}")

        return f"Web search for '{clean_q}' completed without matching snippets."

    async def search_wikipedia(self, query: str) -> str:
        """Searches Wikipedia summary API."""
        clean_q = query.strip()
        if not clean_q:
            return "No query provided."

        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(clean_q)}"
            async with httpx.AsyncClient(timeout=8, headers=self._headers) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    extract = data.get("extract")
                    if extract:
                        return f"**Wikipedia ({data.get('title', clean_q)}):**\n{extract}"
        except Exception as e:
            logger.debug(f"Wikipedia search error: {e}")

        return f"No Wikipedia summary found for '{clean_q}'."
