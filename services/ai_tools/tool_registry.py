import json
import logging
import asyncio
import os

logger = logging.getLogger(__name__)

TOOLS = [
    # -- Observation tools --
    {"type": "function", "function": {"name": "get_group_rules", "description": "Retrieve the rules of the current group chat.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_user_level_stats", "description": "Retrieve the level, XP, and rank title tag of the user.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_leaderboard", "description": "Retrieve the top 10 active users XP leaderboard in this group.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_chat_stats", "description": "Get overall group chat activity statistics including message counts and active users.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_user_balance", "description": "Get the coin wallet balance of the current user.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_shop_items", "description": "List all items available in the group shop.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "wikipedia_search", "description": "Search Wikipedia.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "web_search", "description": "Perform a web search.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "query_knowledge_graph", "description": "Query character facts.", "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}, "required": ["entity"]}}},
    {"type": "function", "function": {"name": "get_bot_level_stats", "description": "Get the bot's own current level, experience points, unlocked skills, and personality trait ratings in this group.", "parameters": {"type": "object", "properties": {}}}},
    # -- Action tools --
    {"type": "function", "function": {"name": "send_message", "description": "Send a message to the current group chat. Use this to proactively speak or respond.", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "The message text to send."}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "play_audio", "description": "Search and download a song or audio track and send it to the chat. Use when user wants to listen to music.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Song name or YouTube URL."}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "play_video", "description": "Search and download a video and send it to the chat.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Video name or YouTube URL."}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "warn_user", "description": "Issue a warning to a user. Only usable by admins. Provide the username or user ID and a reason.", "parameters": {"type": "object", "properties": {"username": {"type": "string"}, "reason": {"type": "string"}}, "required": ["username", "reason"]}}},
    {"type": "function", "function": {"name": "mute_user", "description": "Temporarily mute a user for a specified duration. Only usable by admins.", "parameters": {"type": "object", "properties": {"username": {"type": "string"}, "duration_minutes": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["username", "duration_minutes"]}}},
    {"type": "function", "function": {"name": "add_lore", "description": "Add a new custom knowledge fact to the bot's memory for this group. Only usable by admins.", "parameters": {"type": "object", "properties": {"fact": {"type": "string", "description": "The factual statement to remember."}}, "required": ["fact"]}}},
    {"type": "function", "function": {"name": "save_user_memory", "description": "Save or update a key fact, detail, or preference about this user to your persistent long-term memory so you remember it in future chats.", "parameters": {"type": "object", "properties": {"memory_key": {"type": "string", "description": "A short camelCase identifier for the fact (e.g. 'favoriteColor', 'userName', 'hobby')."}, "memory_value": {"type": "string", "description": "The description or value of the fact to remember."}}, "required": ["memory_key", "memory_value"]}}},
    {"type": "function", "function": {"name": "save_sticker_to_stock", "description": "Save a Telegram sticker file ID to your personal stock collection if you like the sticker.", "parameters": {"type": "object", "properties": {"file_id": {"type": "string", "description": "The file ID of the sticker."}, "emoji": {"type": "string", "description": "The emoji associated with the sticker."}}, "required": ["file_id", "emoji"]}}},
    {"type": "function", "function": {"name": "send_sticker_reply", "description": "Send a sticker reply to the current group chat using a sticker file ID from your stock collection.", "parameters": {"type": "object", "properties": {"file_id": {"type": "string", "description": "The file ID of the sticker to send."}}, "required": ["file_id"]}}},
    {"type": "function", "function": {"name": "get_sticker_stock", "description": "Retrieve all Telegram sticker file IDs you have saved to your personal collection in this chat.", "parameters": {"type": "object", "properties": {}}}},
    # -- Gaming & Deals Tools --
    {"type": "function", "function": {"name": "search_game_deals", "description": "Search Steam and game keyshops for current price, discount, SteamDB historical all-time low (ATL), review scores, and GG.deals keys.", "parameters": {"type": "object", "properties": {"game_title": {"type": "string", "description": "The title of the video game to search (e.g. 'Elden Ring', 'Cyberpunk 2077')."}}, "required": ["game_title"]}}},
    {"type": "function", "function": {"name": "get_steam_deals", "description": "Retrieve top trending active video game sales, discounts, and games currently at all-time lows.", "parameters": {"type": "object", "properties": {}}}},
]


class AIToolExecutor:
    """Dispatches and executes autonomous agentic tools with self-healing error formatting."""

    def __init__(self, agent):
        self.agent = agent

    async def execute(self, function_name: str, arguments: dict, chat_id: int, user_id: int, user_name: str, is_admin: bool, update, context) -> str:
        try:
            if function_name == "get_group_rules":
                settings = self.agent.chat_repo.get_chat_settings(chat_id)
                return settings.get("rules", "No rules set.")

            elif function_name == "get_user_level_stats":
                stats = self.agent.user_repo.get_user_stats(chat_id, user_id, user_name)
                return f"Level: {stats['level']}, XP: {stats['xp']}, Rank Title: {stats['tag']}"

            elif function_name == "get_leaderboard":
                top = self.agent.user_repo.get_top_users(chat_id, limit=5)
                return json.dumps(top) if top else "No activity recorded yet."

            elif function_name == "get_chat_stats":
                summary = self.agent.user_repo.get_chat_summary_stats(chat_id)
                return json.dumps(summary)

            elif function_name == "get_user_balance":
                bal = self.agent.economy_repo.get_balance(chat_id, user_id)
                return f"Water Coins: {bal}"

            elif function_name == "get_shop_items":
                items = self.agent.shop_repo.get_shop_items()
                return json.dumps(items)

            elif function_name == "wikipedia_search":
                q = arguments.get("query", "")
                from services.search_service import SearchService
                return await SearchService().search_wikipedia(q)

            elif function_name == "web_search":
                q = arguments.get("query", "")
                from services.search_service import SearchService
                return await SearchService().search_duckduckgo(q)

            elif function_name == "query_knowledge_graph":
                entity = arguments.get("entity", "")
                active_char = self.agent.character_repo.get_chat_character(chat_id)
                triples = self.agent.kg_repo.get_triples_for_entity(entity, active_char)
                return json.dumps(triples) if triples else f"No knowledge graph triples found for '{entity}'."

            elif function_name == "send_message" and update and context:
                text = arguments.get("text", "")
                if text:
                    await update.message.reply_text(text)
                    return "Message sent successfully."
                return "No text provided."

            elif function_name == "play_audio" and update and context:
                query = arguments.get("query", "")
                from services.media_downloader import MediaDownloader
                downloader = MediaDownloader()
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, downloader.search_youtube, query)
                if info:
                    fpath, ftitle = await loop.run_in_executor(None, downloader.download_audio, info["url"])
                    if fpath and os.path.exists(fpath):
                        try:
                            with open(fpath, "rb") as audio_file:
                                await update.message.reply_audio(audio=audio_file, title=ftitle, performer="Giyu Music")
                                return f"Audio sent: {ftitle}"
                        finally:
                            if os.path.exists(fpath):
                                try: os.remove(fpath)
                                except Exception: pass
                return "Could not find or download that song."

            elif function_name == "play_video" and update and context:
                query = arguments.get("query", "")
                from services.media_downloader import MediaDownloader
                downloader = MediaDownloader()
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, downloader.search_youtube, query)
                if info:
                    fpath, ftitle = await loop.run_in_executor(None, downloader.download_video, info["url"])
                    if fpath and os.path.exists(fpath):
                        try:
                            with open(fpath, "rb") as vid_file:
                                await update.message.reply_video(video=vid_file, caption=f"🎬 <b>{ftitle}</b>", parse_mode="HTML")
                                return f"Video sent: {ftitle}"
                        finally:
                            if os.path.exists(fpath):
                                try: os.remove(fpath)
                                except Exception: pass
                return "Could not find or download that video."

            elif function_name == "warn_user" and update and context:
                if not is_admin:
                    return "Permission denied: only admins can warn users."
                username = arguments.get("username", "")
                reason = arguments.get("reason", "No reason given")
                await update.message.reply_text(f"⚠️ Warning issued to {username}: {reason}")
                return f"Warning sent to {username}."

            elif function_name == "mute_user" and update and context:
                if not is_admin:
                    return "Permission denied: only admins can mute users."
                username = arguments.get("username", "")
                minutes = arguments.get("duration_minutes", 5)
                reason = arguments.get("reason", "No reason given")
                return f"Mute action for {username} for {minutes} min: {reason}."

            elif function_name == "add_lore" and update and context:
                if not is_admin:
                    return "Permission denied: only admins can add lore."
                fact = arguments.get("fact", "")
                embedding = await self.agent.get_embedding_async(fact)
                if embedding:
                    self.agent.lore_repo.insert_lore(fact, embedding, f"custom_{chat_id}")
                    return f"Fact added to memory: {fact}"
                return "Failed to generate embedding for lore."

            elif function_name == "get_bot_level_stats":
                stats = self.agent.bot_stats_repo.get_bot_stats(chat_id)
                try:
                    traits_dict = json.loads(stats.get("traits", "{}"))
                    traits_str = ", ".join([f"{k}: {v}" for k, v in traits_dict.items()])
                except Exception:
                    traits_str = str(stats.get("traits", "unknown"))
                return (
                    f"Bot Level: {stats.get('level', 1)} | "
                    f"XP: {stats.get('xp', 0)} | "
                    f"Personality Traits: {traits_str} | "
                    f"Unlocked Skills: {stats.get('unlocked_skills', 'none')}"
                )

            elif function_name == "save_user_memory":
                mem_key = arguments.get("memory_key", "")
                mem_val = arguments.get("memory_value", "")
                if mem_key and mem_val:
                    self.agent.bot_mem_repo.save_memory(chat_id, user_id, mem_key, mem_val)
                    return f"Successfully saved to long-term memory: {mem_key} = {mem_val}"
                return "Invalid key or value."

            elif function_name == "save_sticker_to_stock":
                fid = arguments.get("file_id", "")
                emo = arguments.get("emoji", "")
                if fid:
                    self.agent.bot_sticker_repo.save_sticker(chat_id, fid, emo)
                    return f"Successfully saved sticker to collection: {fid} ({emo})"
                return "Invalid file_id."

            elif function_name == "send_sticker_reply" and update and context:
                fid = arguments.get("file_id", "")
                if fid:
                    await update.message.reply_sticker(sticker=fid)
                    return "Sticker reply sent successfully."
                return "Invalid file_id."

            elif function_name == "get_sticker_stock":
                return json.dumps(self.agent.bot_sticker_repo.get_sticker_stock(chat_id))

            elif function_name == "search_game_deals":
                game_title = arguments.get("game_title", "")
                if not game_title:
                    return "No game title specified."
                g = await self.agent.game_deals_service.search_game(game_title)
                if g:
                    return (
                        f"Game: {g['title']}\n"
                        f"- Steam Price: {g['steam_price']} (Discount: {g['steam_discount']}%)\n"
                        f"- SteamDB Historical Low (ATL): {g['historical_low']} (Last hit: {g['historical_low_date']} • {g.get('historical_low_relative', '')})\n"
                        f"- Is Current Low: {'YES (At/Near Historical Low!)' if g['is_new_low'] else 'No'}\n"
                        f"- Best Keyshop Deal: {g.get('best_key_price')} ({g.get('best_key_store')})\n"
                        f"- Reviews: Steam: {g.get('steam_rating_text')} ({g.get('steam_rating_percent')}%) | Metacritic: {g.get('metacritic')}\n"
                        f"- Summary: {g.get('description')}\n"
                        f"- Deep Links: Steam ({g['steam_url']}) | SteamDB ({g['steamdb_url']}) | GG.deals ({g['ggdeals_url']})"
                    )
                return f"No game found matching '{game_title}'. You can suggest checking spelling or search the web."

            elif function_name == "get_steam_deals":
                deals = await self.agent.game_deals_service.get_top_deals(limit=5)
                if deals:
                    return "Top Trending Deals:\n" + "\n".join([
                        f"- {d['title']}: {d['sale_price']} (was {d['normal_price']}, {d['savings']}) on {d['store']} [Steam: {d['steam_url']}, SteamDB: {d['steamdb_url']}, GG.deals: {d['ggdeals_url']}]"
                        for d in deals
                    ])
                return "No active deals found right now."

            else:
                return f"Unknown tool name: {function_name}"

        except Exception as e:
            logger.error(f"Error executing tool '{function_name}': {e}", exc_info=True)
            return f"Tool execution observation: encountered error '{e}'. You may proceed with alternate information or fallback tools."
