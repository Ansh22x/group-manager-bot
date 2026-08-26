import asyncio
import sys
sys.path.insert(0, ".")
from services.gaming.steam_reviews_service import SteamReviewsService

async def main():
    srv = SteamReviewsService()
    res = await srv.get_reviews_summary("Hades")
    if res:
        print("=== GAME TITLE ===")
        print(f"{res['game_title']} (App ID: {res['appid']})")
        print(f"Sentiment: {res['score_desc']} ({res['positive_pct']}%)")
        print(f"Total Reviews: {res['total_reviews']:,}")
        print("\n=== AI PLAYER REVIEWS DIGEST ===")
        print(res["summary"])
        print(f"\nStore URL: {res['store_url']}")
    else:
        print("ERROR: Review summary failed.")

if __name__ == "__main__":
    asyncio.run(main())
