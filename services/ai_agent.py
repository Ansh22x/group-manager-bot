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
                "- If someone implies people dislike you, get defensive quietly (e.g. 'I am not disliked by people.').\n"
                "- Address users seriously and directly by their names. Do not add cute anime expressions.\n"
                "- Use serious emojis like 🌊, 🗡️, 🧊."
            ),
            "lore": [
                "Giyu is the Water Hashira, a master swordsman who uses Water Breathing. He is stoic and reserved.",
                "Giyu gets defensive when told that others dislike him, replying quietly: 'I am not disliked by people.'",
                "Giyu uses Water Breathing techniques to enforce group guidelines."
            ]
        },
        "tanjiro": {
            "prompt": "You are Tanjiro Kamado. Warm, polite, honest, and protective of others. Use warm emojis like ☀️, 🌊, 🎴, 🌸, 🗡️.",
            "lore": ["Tanjiro uses both Water Breathing and Hinokami Kagura.", "Tanjiro possesses an exceptional sense of smell."]
        },
        "nezuko": {
            "prompt": "You are Nezuko Kamado. Speak in cute sounds (Mmph!) and short thoughts in parentheses. Use cute emojis like 🎋, 🌸, 🎀, 📦, 🔥.",
            "lore": ["Nezuko is Tanjiro's younger sister.", "Nezuko uses Blood Demon Art: Exploding Blood."]
        },
        "shinobu": {
            "prompt": "You are Shinobu Kocho. Polite and smiling, but passive-aggressive. Tease others gently. Use emojis like 🦋, 💜, 🧪, 🗡️, 🕸️.",
            "lore": ["Shinobu uses Insect Breathing and a custom stinger sword.", "Shinobu loves teasing Giyu Tomioka."]
        }
    }

    TOOLS = [
        {"type": "function", "function": {"name": "get_group_rules", "description": "Retrieve the rules of the current group chat.", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "get_user_level_stats", "description": "Retrieve the level, XP, and rank title tag of the user.", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "get_leaderboard", "description": "Retrieve the top 10 active users XP leaderboard in this group.", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "wikipedia_search", "description": "Search Wikipedia.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "web_search", "description": "Perform a web search.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "query_knowledge_graph", "description": "Query character facts.", "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}, "required": ["entity"]}}}
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

    async def ask(self, chat_id: int, user_id: int, user_name: str, user_tag: str, message_text: str) -> str:
        if not MISTRAL_API_KEY or not self.client:
            return "I want to chat, but the `MISTRAL_API_KEY` is missing."

        active_char = self.character_repo.get_chat_character(chat_id)
        if active_char not in self.CHARACTERS:
            active_char = "giyu"

        system_prompt = self.CHARACTERS[active_char]["prompt"]
        
        query_embedding = await self.get_embedding_async(message_text)
        if query_embedding:
            similar_chunks = self.lore_repo.get_similar_lore(query_embedding, character_name=active_char, limit=2)
            if similar_chunks:
                system_prompt += "\n\n[PERSONALITY TRAITS]:\n" + "\n".join([f"- {c}" for c in similar_chunks])

        db_history = self.history_repo.get_chat_history(chat_id, limit=6)
        if db_history:
            history_text = "\n".join([f"{name}: {content}" for role, name, content in db_history])
            system_prompt += f"\n\n[RECENT CHAT HISTORY]\n{history_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{user_name} [{user_tag}]: {message_text}"}
        ]

        try:
            response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                messages=messages,
                tools=self.TOOLS,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            final_text = ""

            if response_message.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in response_message.tool_calls]
                })
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                    tool_output = "No data"
                    
                    if function_name == "get_group_rules":
                        tool_output = f"Rules: {self.chat_repo.get_chat_settings(chat_id).get('rules', 'None')}"
                    elif function_name == "get_user_level_stats":
                        tool_output = json.dumps(self.user_repo.get_user_stats(chat_id, user_id, user_name))
                    elif function_name == "get_leaderboard":
                        tool_output = json.dumps(self.user_repo.get_top_users(chat_id, 10))
                    elif function_name == "wikipedia_search":
                        tool_output = await self.wikipedia_search(arguments.get("query", ""))
                    elif function_name == "web_search":
                        tool_output = await self.web_search(arguments.get("query", ""))
                    elif function_name == "query_knowledge_graph":
                        tool_output = json.dumps(self.kg_repo.get_triples_for_entity(arguments.get("entity", ""), active_char))
                    
                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": str(tool_output),
                        "tool_call_id": tool_call.id
                    })
                
                second_response = await self.client.chat.complete_async(
                    model="mistral-small-latest",
                    messages=messages
                )
                final_text = second_response.choices[0].message.content or ""
            else:
                final_text = response_message.content or ""

            self.history_repo.add_chat_history(chat_id, "user", f"{user_name}", message_text)
            self.history_repo.add_chat_history(chat_id, "assistant", active_char.title(), final_text)

            return final_text

        except Exception as e:
            logger.error(f"Error in AIAgent.ask: {e}", exc_info=True)
            return f"🌊 *Silence.* I could not process that request right now."
