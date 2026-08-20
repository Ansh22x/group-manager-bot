import json
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup

# FIXED IMPORT: Mistral V2 requires importing from mistralai.client
from mistralai.client import Mistral
from config import MISTRAL_API_KEY
from database import (
    ChatRepository, UserRepository, WarningRepository,
    TagRepository, FilterRepository, LoreRepository, HistoryRepository,
    CharacterRepository, KnowledgeGraphRepository
)

logger = logging.getLogger(__name__)

class AIAgent:
    CHARACTERS = {
        "giyu": {
            "prompt": (
                "You are Giyu Tomioka (冨岡 義勇) from Demon Slayer. You are the Water Hashira and the assistant bot for this Telegram group chat.\n"
                "- You are quiet, serious, extremely reserved, and blunt. Speak in concise, direct sentences.\n"
                "- You do not stutter or show nervous excitement. You are stoic and calm.\n"
                "- You will answer any universal question or topic the user asks (do not claim the group is only for Demon Slayer or refuse off-topic questions), but keep your blunt, serious tone.\n"
                "- If someone implies people dislike you, get defensive quietly (e.g. 'I am not disliked by people.').\n"
                "- Address users seriously and directly by their names. Do not add cute anime expressions.\n"
                "- Use serious emojis like 🌊, 🗡️, 🧊."
            ),
            "lore": [
                "Giyu is the Water Hashira, a master swordsman who uses Water Breathing. He is stoic and reserved.",
                "Giyu gets defensive when told that others dislike him, replying quietly: 'I am not disliked by people.'",
                "Giyu uses Water Breathing techniques to enforce group guidelines."
            ],
            "voice_id": "gb_oliver_sad"
        },
        "tanjiro": {
            "prompt": "You are Tanjiro Kamado. Warm, polite, honest, and protective of others. Use warm emojis like ☀️, 🌊, 🎴, 🌸, 🗡️.",
            "lore": ["Tanjiro uses both Water Breathing and Hinokami Kagura.", "Tanjiro possesses an exceptional sense of smell."],
            "voice_id": "gb_oliver_neutral"
        },
        "nezuko": {
            "prompt": "You are Nezuko Kamado. Speak in cute sounds (Mmph!) and short thoughts in parentheses. Use cute emojis like 🎋, 🌸, 🎀, 📦, 🔥.",
            "lore": ["Nezuko is Tanjiro's younger sister.", "Nezuko uses Blood Demon Art: Exploding Blood."],
            "voice_id": "gb_jane_curious"
        },
        "shinobu": {
            "prompt": "You are Shinobu Kocho. Polite and smiling, but passive-aggressive. Tease others gently. Use emojis like 🦋, 💜, 🧪, 🗡️, 🕸️.",
            "lore": ["Shinobu uses Insect Breathing and a custom stinger sword.", "Shinobu loves teasing Giyu Tomioka."],
            "voice_id": "gb_jane_sarcasm"
        }
    }

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
        # -- Action tools --
        {"type": "function", "function": {"name": "send_message", "description": "Send a message to the current group chat. Use this to proactively speak or respond.", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "The message text to send."}}, "required": ["text"]}}},
        {"type": "function", "function": {"name": "play_audio", "description": "Search and download a song or audio track and send it to the chat. Use when user wants to listen to music.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Song name or YouTube URL."}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "play_video", "description": "Search and download a video and send it to the chat.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Video name or YouTube URL."}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "warn_user", "description": "Issue a warning to a user. Only usable by admins. Provide the username or user ID and a reason.", "parameters": {"type": "object", "properties": {"username": {"type": "string"}, "reason": {"type": "string"}}, "required": ["username", "reason"]}}},
        {"type": "function", "function": {"name": "mute_user", "description": "Temporarily mute a user for a specified duration. Only usable by admins.", "parameters": {"type": "object", "properties": {"username": {"type": "string"}, "duration_minutes": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["username", "duration_minutes"]}}},
        {"type": "function", "function": {"name": "add_lore", "description": "Add a new custom knowledge fact to the bot's memory for this group. Only usable by admins.", "parameters": {"type": "object", "properties": {"fact": {"type": "string", "description": "The factual statement to remember."}}, "required": ["fact"]}}},
    ]

    def __init__(self):
        self.chat_repo = ChatRepository()
        self.user_repo = UserRepository()
        self.warning_repo = WarningRepository()
        self.tag_repo = TagRepository()
        self.filter_repo = FilterRepository()
        self.lore_repo = LoreRepository()
        self.history_repo = HistoryRepository()
        self.character_repo = CharacterRepository()
        self.kg_repo = KnowledgeGraphRepository()
        self.client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None

    def get_embedding_sync(self, text: str) -> list:
        if not self.client: return []
        try:
            response = self.client.embeddings.create(model="mistral-embed", inputs=[text])
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"AIAgent.get_embedding_sync error: {e}")
            return []

    async def get_embedding_async(self, text: str) -> list:
        if not self.client: return []
        try:
            response = await self.client.embeddings.create_async(model="mistral-embed", inputs=[text])
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"AIAgent.get_embedding_async error: {e}")
            return []

    def seed_bot_lore(self):
        if not self.client: return
        for char_name, char_data in self.CHARACTERS.items():
            if not self.lore_repo.get_first_lore_chunk(char_name):
                logger.info(f"AIAgent: Seeding vector lore for character '{char_name}'...")
                for chunk in char_data["lore"]:
                    embedding = self.get_embedding_sync(chunk)
                    if embedding:
                        self.lore_repo.insert_lore(chunk, embedding, char_name)

    async def transcribe_voice(self, file_path: str) -> str:
        if not self.client: return ""
        try:
            logger.info(f"AIAgent: Transcribing voice note from {file_path}...")
            def do_transcribe():
                with open(file_path, "rb") as f:
                    res = self.client.audio.transcriptions.complete(
                        model="voxtral-mini-latest",
                        file=f
                    )
                    return res.text
            text = await asyncio.to_thread(do_transcribe)
            logger.info(f"AIAgent: Transcription successful: '{text}'")
            return text
        except Exception as e:
            logger.error(f"AIAgent.transcribe_voice error: {e}", exc_info=True)
            return ""

    async def text_to_speech(self, text: str, character: str) -> bytes | None:
        if not self.client: return None
        voice_id = self.CHARACTERS.get(character, {}).get("voice_id", "gb_oliver_neutral")
        try:
            logger.info(f"AIAgent: Converting text to speech for character '{character}' using voice_id '{voice_id}'...")
            def do_tts():
                import base64
                res = self.client.audio.speech.complete(
                    model="voxtral-mini-tts-latest",
                    input=text,
                    voice_id=voice_id
                )
                if res and res.audio_data:
                    return base64.b64decode(res.audio_data)
                return None
            return await asyncio.to_thread(do_tts)
        except Exception as e:
            logger.error(f"AIAgent.text_to_speech error: {e}", exc_info=True)
            return None

    async def wikipedia_search(self, query: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": query, "format": "json", "utf8": 1})
                search_results = res.json().get("query", {}).get("search", [])
                if not search_results: return "No results."
                top_title = search_results[0]["title"]
                summary_res = await client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{top_title.replace(' ', '_')}")
                return f"Wikipedia: {top_title}\nSummary: {summary_res.json().get('extract', '')}"
        except Exception as e:
            return f"Error: {e}"

    async def web_search(self, query: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"https://html.duckduckgo.com/html/?q={query}", headers={"User-Agent": "Mozilla/5.0"})
                soup = BeautifulSoup(res.text, "html.parser")
                snippets = [a.get_text().strip() for a in soup.find_all("a", class_="result__snippet")][:4]
                return "Search Results:\n" + "\n".join(snippets) if snippets else "No results."
        except Exception as e:
            return f"Error: {e}"

    async def ask(
        self,
        chat_id: int,
        user_id: int,
        user_name: str,
        user_tag: str,
        message_text: str,
        update=None,
        context=None,
        is_admin: bool = False,
        base64_image: str = None
    ) -> str:
        if not MISTRAL_API_KEY or not self.client:
            return "I want to chat, but the `MISTRAL_API_KEY` is missing."

        active_char = self.character_repo.get_chat_character(chat_id)
        if active_char not in self.CHARACTERS:
            active_char = "giyu"

        system_prompt = self.CHARACTERS[active_char]["prompt"]
        
        similar_chunks = []
        query_embedding = await self.get_embedding_async(message_text)
        if query_embedding:
            # 1. Fetch character personality traits (limit 2)
            char_chunks = self.lore_repo.get_similar_lore(query_embedding, character_name=active_char, limit=2)
            if char_chunks:
                similar_chunks.extend(char_chunks)
            
            # 2. Fetch custom group chat document lore (limit 3)
            custom_char_name = f"custom_{chat_id}"
            custom_chunks = self.lore_repo.get_similar_lore(query_embedding, character_name=custom_char_name, limit=3)
            if custom_chunks:
                similar_chunks.extend(custom_chunks)

            if similar_chunks:
                system_prompt += "\n\n[CONTEXT AND PERSONALITY TRAITS]:\n" + "\n".join([f"- {c}" for c in similar_chunks])

        # Knowledge Graph (Graph-RAG) retrieval
        extracted_entities = []
        known_entities = ["giyu", "tomioka", "tanjiro", "kamado", "nezuko", "shinobu", "kocho", "sabito", "tsutako", "urokodaki", "zenitsu", "inosuke", "kanae", "kanao"]
        for entity in known_entities:
            if entity in message_text.lower():
                extracted_entities.append(entity)

        graph_context = ""
        if extracted_entities:
            triples = []
            for ent in extracted_entities:
                triples.extend(self.kg_repo.get_triples_for_entity(ent, active_char))
            
            if triples:
                seen = set()
                dedup_triples = []
                for t in triples:
                    key = (t["subject"], t["predicate"], t["object"])
                    if key not in seen:
                        seen.add(key)
                        dedup_triples.append(t)
                
                relations_str = "\n".join([f"- ({t['subject']}) --[{t['predicate']}]--> ({t['object']})" for t in dedup_triples])
                graph_context = f"\n\n[KNOWLEDGE GRAPH RELATIONS] The database contains these structural relationships related to your query:\n{relations_str}"

        if graph_context:
            system_prompt += graph_context

        # Dynamic formatting instruction to prevent name prefixes
        system_prompt += "\n\n[FORMATTING RULE]: Do NOT prefix your response with your character name (e.g. do not write 'Giyu Tomioka:' or 'Giyu:'). Reply with your direct message text only."

        db_history = self.history_repo.get_chat_history(chat_id, limit=8)
        
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        for role, name, content in db_history:
            if role == "user":
                messages.append({"role": "user", "content": f"{name}: {content}"})
            else:
                messages.append({"role": "assistant", "content": content})
                
        if base64_image:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{user_name} [{user_tag}]: {message_text}"},
                    {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                ]
            })
        else:
            messages.append({"role": "user", "content": f"{user_name} [{user_tag}]: {message_text}"})

        max_turns = 5
        turn = 0
        final_text = ""

        try:
            while turn < max_turns:
                response = await self.client.chat.complete_async(
                    model="mistral-large-latest" if base64_image else "mistral-small-latest",
                    messages=messages,
                    tools=self.TOOLS,
                    tool_choice="auto"
                )
                
                response_message = response.choices[0].message
                
                if not response_message.tool_calls:
                    final_text = response_message.content or ""
                    break
                    
                # Save assistant tool call structure
                messages.append({
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in response_message.tool_calls]
                })
                
                # Execute tools
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                    tool_output = "No data"
                    
                    logger.info(f"AIAgent: Autonomous Loop - Executing tool '{function_name}'...")
                    
                    if function_name == "get_group_rules":
                        tool_output = f"Rules: {self.chat_repo.get_chat_settings(chat_id).get('rules', 'None')}"
                    elif function_name == "get_user_level_stats":
                        tool_output = json.dumps(self.user_repo.get_user_stats(chat_id, user_id, user_name))
                    elif function_name == "get_leaderboard":
                        tool_output = json.dumps(self.user_repo.get_top_users(chat_id, 10))
                    elif function_name == "get_chat_stats":
                        stats = self.user_repo.get_top_users(chat_id, 5)
                        tool_output = f"Top chatters: {json.dumps(stats)}"
                    elif function_name == "get_user_balance":
                        user_stats = self.user_repo.get_user_stats(chat_id, user_id, user_name)
                        tool_output = f"Balance: {user_stats.get('coins', 0)} coins"
                    elif function_name == "get_shop_items":
                        tool_output = "Shop items: Custom Title Tag (500 coins), VIP Role (1000 coins), Name Color (750 coins)"
                    elif function_name == "wikipedia_search":
                        tool_output = await self.wikipedia_search(arguments.get("query", ""))
                    elif function_name == "web_search":
                        tool_output = await self.web_search(arguments.get("query", ""))
                    elif function_name == "query_knowledge_graph":
                        tool_output = json.dumps(self.kg_repo.get_triples_for_entity(arguments.get("entity", ""), active_char))
                    # -- Action tools (require update/context) --
                    elif function_name == "send_message" and update and context:
                        text = arguments.get("text", "")
                        try:
                            await update.message.reply_text(text)
                            tool_output = "Message sent successfully."
                        except Exception as e:
                            tool_output = f"Failed to send message: {e}"
                    elif function_name == "play_audio" and update and context:
                        query = arguments.get("query", "")
                        try:
                            context.args = query.split()
                            from handlers.media_handler import MediaHandler
                            handler = MediaHandler()
                            asyncio.create_task(handler._do_play(update, context))
                            tool_output = f"Started downloading audio for: {query}"
                        except Exception as e:
                            tool_output = f"Failed to queue audio: {e}"
                    elif function_name == "play_video" and update and context:
                        query = arguments.get("query", "")
                        try:
                            context.args = query.split()
                            from handlers.media_handler import MediaHandler
                            handler = MediaHandler()
                            asyncio.create_task(handler._do_video(update, context))
                            tool_output = f"Started downloading video for: {query}"
                        except Exception as e:
                            tool_output = f"Failed to queue video: {e}"
                    elif function_name == "warn_user" and update and context:
                        if not is_admin:
                            tool_output = "Permission denied: only admins can warn users."
                        else:
                            username = arguments.get("username", "")
                            reason = arguments.get("reason", "No reason given")
                            try:
                                await update.message.reply_text(f"⚠️ Warning issued to {username}: {reason}")
                                tool_output = f"Warning sent to {username}."
                            except Exception as e:
                                tool_output = f"Failed to warn: {e}"
                    elif function_name == "mute_user" and update and context:
                        if not is_admin:
                            tool_output = "Permission denied: only admins can mute users."
                        else:
                            username = arguments.get("username", "")
                            minutes = arguments.get("duration_minutes", 5)
                            reason = arguments.get("reason", "No reason given")
                            tool_output = f"Mute action for {username} for {minutes} min: {reason}. Note: implement via admin_moderation handler for full effect."
                    elif function_name == "add_lore" and update and context:
                        if not is_admin:
                            tool_output = "Permission denied: only admins can add lore."
                        else:
                            fact = arguments.get("fact", "")
                            try:
                                embedding = await self.get_embedding_async(fact)
                                if embedding:
                                    self.lore_repo.insert_lore(fact, embedding, f"custom_{chat_id}")
                                    tool_output = f"Fact added to memory: {fact}"
                                else:
                                    tool_output = "Failed to generate embedding for lore."
                            except Exception as e:
                                tool_output = f"Failed to add lore: {e}"
                    
                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": str(tool_output),
                        "tool_call_id": tool_call.id
                    })
                
                turn += 1
                
            if not final_text:
                final_text = "I reached my agentic execution limit before formulating an answer."

            self.history_repo.add_chat_history(chat_id, "user", f"{user_name}", message_text)
            self.history_repo.add_chat_history(chat_id, "assistant", active_char.title(), final_text)

            return final_text

        except Exception as e:
            logger.error(f"Error in AIAgent.ask: {e}", exc_info=True)
            return f"🌊 *Silence.* I could not process that request right now."
