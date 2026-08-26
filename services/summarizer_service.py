import logging
import hashlib
from bs4 import BeautifulSoup
from services.http_client import shared_http_client
from services.cache_service import fast_cache
from mistralai.client import Mistral
from config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

class SummarizerService:
    def __init__(self):
        self.client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None

    async def summarize_url(self, url: str) -> dict | None:
        """
        Scrapes article content from a web URL and uses Mistral AI to produce
        a structured, executive 3-bullet takeaway summary.
        """
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cached = fast_cache.get(f"summary_{url_hash}")
        if cached:
            return cached

        # 1. Fetch web page content
        text_content, title = await self._extract_clean_text(url)
        if not text_content or len(text_content) < 80:
            return None

        # 2. Generate summary via Mistral LLM
        if not self.client:
            return {
                "title": title or url,
                "summary": "Mistral API key is missing. Cannot generate AI summary.",
                "url": url
            }

        prompt = (
            f"You are Giyu Tomioka's analytical intelligence processor.\n"
            f"Read the following web page content and produce a crisp, executive summary in clean Telegram markdown formatting:\n\n"
            f"Article Title: {title}\n"
            f"URL: {url}\n\n"
            f"Content:\n{text_content[:4000]}\n\n"
            f"Provide your response in this exact format:\n"
            f"📌 **Key Takeaway:** (1-2 sentence core message)\n"
            f"🔑 **Critical Highlights:**\n"
            f"• (Point 1)\n"
            f"• (Point 2)\n"
            f"• (Point 3)\n"
            f"💡 **Bottom Line:** (1 sentence concluding takeaway)"
        )

        try:
            response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                messages=[
                    {"role": "system", "content": "You are a concise, high-speed analytical summarizer. Output structured summaries without conversational filler."},
                    {"role": "user", "content": prompt}
                ]
            )
            summary_text = response.choices[0].message.content

            result = {
                "title": title or "Web Article",
                "summary": summary_text,
                "url": url
            }
            fast_cache.set(f"summary_{url_hash}", result, ttl_seconds=14400.0) # 4 hours cache
            return result
        except Exception as e:
            logger.error(f"SummarizerService LLM error: {e}")
            return None

    async def _extract_clean_text(self, url: str) -> tuple[str, str]:
        """Extracts clean article paragraphs and page title, stripping boilerplate navigation/scripts."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
            res = await shared_http_client.get(url, headers=headers, timeout=12.0)
            if res.status_code != 200:
                # Fallback to cloudscraper if blocked
                import cloudscraper
                scraper = cloudscraper.create_scraper()
                raw = scraper.get(url, timeout=10)
                html_text = raw.text
            else:
                html_text = res.text

            soup = BeautifulSoup(html_text, "html.parser")

            # Remove unwanted tags
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            # Extract main paragraph texts
            paragraphs = [p.get_text().strip() for p in soup.find_all(["p", "h1", "h2", "h3", "li"]) if len(p.get_text().strip()) > 30]
            clean_text = " ".join(paragraphs[:30])

            return clean_text, title
        except Exception as e:
            logger.error(f"SummarizerService._extract_clean_text error on {url}: {e}")
            return "", ""
