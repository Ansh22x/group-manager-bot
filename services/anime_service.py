import httpx
import random
import logging
import re
from bs4 import BeautifulSoup

from services.http_client import SharedHttpClient
from services.cache_service import fast_cache

logger = logging.getLogger(__name__)

class AnimeService:
    ANILIST_URL = "https://graphql.anilist.co"

    DEMON_SLAYER_QUOTES = [
        {"quote": "I am not disliked by people.", "character": "Giyu Tomioka", "anime": "Demon Slayer"},
        {"quote": "Feel the rage. The powerful, pure rage of not being able to forgive will become your unswerving drive to take action.", "character": "Giyu Tomioka", "anime": "Demon Slayer"},
        {"quote": "No matter how many people you may lose, you have no choice but to go on living. No matter how devastating the blows may be.", "character": "Tanjiro Kamado", "anime": "Demon Slayer"},
        {"quote": "Work at it. All I can do is work hard! That's the story of my life!", "character": "Tanjiro Kamado", "anime": "Demon Slayer"},
        {"quote": "Set your heart ablaze! Pass your limits! I am the Flame Hashira, Kyojuro Rengoku!", "character": "Kyojuro Rengoku", "anime": "Demon Slayer"},
        {"quote": "Life is a series of hardships, nor is it easy. But as long as we live, we have a chance to feel happiness.", "character": "Tanjiro Kamado", "anime": "Demon Slayer"},
        {"quote": "I may be the only swords-lady among the Hashira who cannot cut off a demon's head. But since I can make poisons that can kill demons, I'm quite impressive, don't you think?", "character": "Shinobu Kocho", "anime": "Demon Slayer"},
        {"quote": "Those who regret their own actions, I would never trample on them. Because demons were once human too.", "character": "Tanjiro Kamado", "anime": "Demon Slayer"},
        {"quote": "Don't ever give up. Even if it's painful, even if it's agonizing, don't try to take the easy way out.", "character": "Zenitsu Agatsuma", "anime": "Demon Slayer"},
        {"quote": "If you can only do one thing, hone it to perfection. Hone it to the utmost limit!", "character": "Jigoro Kuwajima", "anime": "Demon Slayer"}
    ]

    @classmethod
    async def search_anime(cls, title: str) -> dict | None:
        """Searches AniList for anime details and cover artwork with in-memory caching."""
        cache_key = f"anime_{title.strip().lower()}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        query = """
        query ($search: String) {
          Page(page: 1, perPage: 1) {
            media(search: $search, type: ANIME, sort: [POPULARITY_DESC]) {
              id
              title {
                romaji
                english
                native
              }
              description(asHtml: false)
              episodes
              duration
              status
              averageScore
              genres
              seasonYear
              studios(isMain: true) {
                nodes {
                  name
                }
              }
              coverImage {
                extraLarge
                large
              }
              siteUrl
            }
          }
        }
        """
        try:
            client = SharedHttpClient.get_client()
            resp = await client.post(cls.ANILIST_URL, json={"query": query, "variables": {"search": title}})
            if resp.status_code == 200:
                media_list = resp.json().get("data", {}).get("Page", {}).get("media", [])
                if media_list:
                    m = media_list[0]
                    desc = m.get("description") or "No synopsis available."
                    desc = BeautifulSoup(desc, "html.parser").get_text()
                    if len(desc) > 350:
                        desc = desc[:350].rsplit(" ", 1)[0] + "..."

                    studios = [s["name"] for s in m.get("studios", {}).get("nodes", []) if s.get("name")]
                    studio_str = ", ".join(studios) if studios else "Unknown"

                    res = {
                        "title": m["title"].get("english") or m["title"].get("romaji"),
                        "romaji": m["title"].get("romaji"),
                        "native": m["title"].get("native"),
                        "score": f"{m['averageScore']}%" if m.get("averageScore") else "N/A",
                        "episodes": m.get("episodes") or "Ongoing / TBA",
                        "duration": f"{m.get('duration')} mins" if m.get("duration") else "N/A",
                        "status": (m.get("status") or "").replace("_", " ").title(),
                        "year": m.get("seasonYear") or "N/A",
                        "genres": ", ".join(m.get("genres", [])[:4]),
                        "studio": studio_str,
                        "synopsis": desc,
                        "cover": m.get("coverImage", {}).get("extraLarge") or m.get("coverImage", {}).get("large"),
                        "url": m.get("siteUrl")
                    }
                    fast_cache.set(cache_key, res, ttl_seconds=3600.0)
                    return res
        except Exception as e:
            logger.error(f"AniList search error for '{title}': {e}")
        return None

    @classmethod
    async def search_manga(cls, title: str) -> dict | None:
        """Searches AniList for manga details and cover artwork with in-memory caching."""
        cache_key = f"manga_{title.strip().lower()}"
        cached = fast_cache.get(cache_key)
        if cached:
            return cached

        query = """
        query ($search: String) {
          Page(page: 1, perPage: 1) {
            media(search: $search, type: MANGA, sort: [POPULARITY_DESC]) {
              id
              title {
                romaji
                english
                native
              }
              description(asHtml: false)
              chapters
              volumes
              status
              averageScore
              genres
              startDate {
                year
              }
              staff(perPage: 2) {
                nodes {
                  name {
                    full
                  }
                }
              }
              coverImage {
                extraLarge
                large
              }
              siteUrl
            }
          }
        }
        """
        try:
            client = SharedHttpClient.get_client()
            resp = await client.post(cls.ANILIST_URL, json={"query": query, "variables": {"search": title}})
            if resp.status_code == 200:
                media_list = resp.json().get("data", {}).get("Page", {}).get("media", [])
                if media_list:
                    m = media_list[0]
                    desc = m.get("description") or "No synopsis available."
                    desc = BeautifulSoup(desc, "html.parser").get_text()
                    if len(desc) > 350:
                        desc = desc[:350].rsplit(" ", 1)[0] + "..."

                    authors = [s["name"]["full"] for s in m.get("staff", {}).get("nodes", []) if s.get("name", {}).get("full")]
                    author_str = ", ".join(authors) if authors else "Unknown"

                    res = {
                        "title": m["title"].get("english") or m["title"].get("romaji"),
                        "romaji": m["title"].get("romaji"),
                        "native": m["title"].get("native"),
                        "score": f"{m['averageScore']}%" if m.get("averageScore") else "N/A",
                        "chapters": m.get("chapters") or "Ongoing / TBA",
                        "volumes": m.get("volumes") or "TBA",
                        "status": (m.get("status") or "").replace("_", " ").title(),
                        "year": m.get("startDate", {}).get("year") or "N/A",
                        "genres": ", ".join(m.get("genres", [])[:4]),
                        "author": author_str,
                        "synopsis": desc,
                        "cover": m.get("coverImage", {}).get("extraLarge") or m.get("coverImage", {}).get("large"),
                        "url": m.get("siteUrl")
                    }
                    fast_cache.set(cache_key, res, ttl_seconds=3600.0)
                    return res
        except Exception as e:
            logger.error(f"AniList manga search error for '{title}': {e}")
        return None

    @classmethod
    def get_random_quote(cls) -> dict:
        return random.choice(cls.DEMON_SLAYER_QUOTES)
