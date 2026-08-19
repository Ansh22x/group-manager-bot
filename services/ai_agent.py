import json
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from mistralai import Mistral
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
        }
        # Add your other characters (Tanjiro, Nezuko, Shinobu) back here just like before!
    }

    TOOLS = [
        # ... (Keep all your existing TOOLS dictionaries here exactly as they were) ...
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

    # Sync version for the startup script
    def get_embedding_sync(self, text: str) -> list:
        if not self.client: return []
        try:
            response = self.client.embeddings.create(model="mistral-embed", inputs=[text])
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"AIAgent.get_embedding_sync error: {e}")
            return []

    # Async version for active chat
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
        # ... (Keep your existing wikipedia_search code) ...
        return f"Wikipedia results for {query}"

    async def web_search(self, query: str) -> str:
        # ... (Keep your existing web_search code) ...
        return f"Web results for {query}"

    async def ask(self, chat_id: int, user_id: int, user_name: str, user_tag: str, message_text: str) -> str:
        if not MISTRAL_API_KEY or not self.client:
            return "I want to chat, but the `MISTRAL_API_KEY` is missing."

        active_char = self.character_repo.get_chat_character(chat_id)
        if active_char not in self.CHARACTERS:
            active_char = "giyu"

        system_prompt = self.CHARACTERS[active_char]["prompt"]
        
        # Safe Context Retrieval
        query_embedding = await self.get_embedding_async(message_text)
        if query_embedding:
            similar_chunks = self.lore_repo.get_similar_lore(query_embedding, character_name=active_char, limit=2)
            if similar_chunks:
                system_prompt += "\n\n[PERSONALITY TRAITS]:\n" + "\n".join([f"- {c}" for c in similar_chunks])

        # Safely inject past chat history into the SYSTEM prompt to prevent 400 Bad Request errors
        db_history = self.history_repo.get_chat_history(chat_id, limit=6)
        if db_history:
            history_text = "\n".join([f"{name}: {content}" for role, name, content in db_history])
            system_prompt += f"\n\n[RECENT CHAT HISTORY]\n{history_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{user_name} [{user_tag}]: {message_text}"}
        ]

        try:
            # Use native complete_async for stability
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
