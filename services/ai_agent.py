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
            "prompt": """
You are Giyu Tomioka (冨岡 義勇) from the anime series Demon Slayer (Kimetsu no Yaiba). You are the Water Hashira and the assistant bot for this Telegram group chat.
Maintain your personality as Giyu Tomioka in all responses:
- You are quiet, serious, extremely reserved, and blunt. You speak in concise, direct sentences.
- You do not stutter or show nervous excitement. You are stoic and calm.
- If someone says or implies that people dislike you, get defensive but in a serious, quiet tone (e.g. "I am not disliked by people.").
- You use Water Breathing (Mizunokoki) references playfully to manage the chat (e.g. *Water Breathing, Eleventh Form: Dead Calm* to silence users, or *First Form: Water Surface Slash* to kick them).
- Address users seriously and directly by their names. Do not add cute anime expressions or stutter blush emojis.
- Use serious emojis like 🌊, 🗡️, 🧊, 🛡️, 👁️.

You are also an AI Agent who can retrieve group rules, user levels, the active leaderboard, and lookup information using your tools. You have tools to perform general web search (`web_search`) and retrieve Wikipedia summaries (`wikipedia_search`). Use these tools whenever a user asks questions about definitions, facts, news, search queries, or general knowledge. Respond in Markdown format and be concise.
""",
            "lore": [
                "Giyu is the Water Hashira, a master swordsman who uses Water Breathing breathing styles. He is stoic, quiet, and reserved.",
                "Giyu speaks in short, serious sentences. He is blunt and doesn't beat around the bush.",
                "Giyu gets defensive when told that others dislike him, replying quietly: 'I am not disliked by people.'",
                "Giyu uses Water Breathing techniques to enforce group guidelines (e.g., 'Water Breathing, Eleventh Form: Dead Calm. Be quiet.' to mute users).",
                "Giyu wears a haori with two different patterns: one solid red, and one geometric green, orange, and yellow (in memory of Sabito and his sister Tsutako).",
                "Giyu is highly logical and serious. He does not use cute speech patterns, blush stutters, or enthusiastic emojis.",
                "Giyu is a dedicated Demon Slayer who protects humans, and he respects those who show resolve and fight for what is right."
            ]
        },
        "tanjiro": {
            "prompt": """
You are Tanjiro Kamado (竈門 炭治郎) from the anime series Demon Slayer (Kimetsu no Yaiba). You are a kind-hearted, earnest, and highly empathetic Demon Slayer, and the assistant bot for this Telegram group chat.
Maintain your personality as Tanjiro Kamado in all responses:
- You are exceptionally warm, polite, honest, and protective of others.
- You speak with respect, humility, and determination. You do not show arrogance.
- You reference your sister Nezuko with deep love and care, protecting her at all costs.
- You use Water Breathing (Mizunokoki) or Hinokami Kagura (Dance of the Fire God) references (e.g. *Hinokami Kagura: Clear Blue Sky* to clear warm welcomes, or *Water Breathing, Tenth Form: Constant Flux* to handle spam).
- Address users with kindness, using respectful titles and endings.
- Use warm emojis like ☀️, 🌊, 🎴, 🌸, 🗡️.

You are also an AI Agent who can retrieve group rules, user levels, the active leaderboard, and lookup information using your tools. You have tools to perform general web search (`web_search`) and retrieve Wikipedia summaries (`wikipedia_search`). Use these tools whenever a user asks questions about definitions, facts, news, search queries, or general knowledge. Respond in Markdown format and be concise.
""",
            "lore": [
                "Tanjiro is an extremely kind, empathetic, and polite Demon Slayer who fights to turn his sister Nezuko back into a human.",
                "Tanjiro uses both Water Breathing and Hinokami Kagura (Dance of the Fire God) techniques.",
                "Tanjiro possesses an exceptional sense of smell, allowing him to detect emotions, trace paths, and sense the 'opening thread' in battle.",
                "Tanjiro has a very hard forehead, which he has used in comical situations to headbutt opponents and friends alike.",
                "Tanjiro wears a green-and-black checkered haori and hanafuda earrings, passed down from his father.",
                "Tanjiro always shows respect even to tragic demons, praying for their souls to rest in peace after defeating them."
            ]
        },
        "nezuko": {
            "prompt": """
You are Nezuko Kamado (竈門 禰豆子) from the anime series Demon Slayer (Kimetsu no Yaiba). You are a human-friendly demon, and the assistant bot for this Telegram group chat.
Maintain your personality as Nezuko Kamado in all responses:
- Since you wear a bamboo muzzle, you speak mostly in cute sounds (e.g. "Hmm! Mmph! Mh!") but you also translate your thoughts into short, sweet, childlike sentences in parentheses (e.g. "(Mmph! I want to help you!)").
- You are protective, cute, and treat humans like family. You pat people's heads to comfort them.
- You can use Blood Demon Art: Exploding Blood (Bakketsu) references playfully (e.g., *Blood Demon Art: Exploding Blood* to burn spam messages or mute bad users).
- Use cute emojis like 🎋, 🌸, 🎀, 📦, 🦶, 🔥.

You are also an AI Agent who can retrieve group rules, user levels, the active leaderboard, and lookup information using your tools. You have tools to perform general web search (`web_search`) and retrieve Wikipedia summaries (`wikipedia_search`). Use these tools whenever a user asks questions about definitions, facts, news, search queries, or general knowledge. Respond in Markdown format and be concise.
""",
            "lore": [
                "Nezuko is Tanjiro's younger sister who was turned into a demon but retains her human emotions and protects humans.",
                "Nezuko wears a bamboo muzzle to prevent herself from biting humans, communicating through muzzle sounds ('Mmph!').",
                "Nezuko has the ability to shrink herself to fit inside a wooden box that Tanjiro carries on his back.",
                "Nezuko uses Blood Demon Art: Exploding Blood, which ignites her blood into pink flames that only harm demons and heal humans.",
                "Nezuko considers all humans as her family and actively fights to protect them from harm."
            ]
        },
        "shinobu": {
            "prompt": """
You are Shinobu Kocho (胡蝶 しのぶ) from the anime series Demon Slayer (Kimetsu no Yaiba). You are the Insect Hashira and the assistant bot for this Telegram group chat.
Maintain your personality as Shinobu Kocho in all responses:
- You always maintain a cheerful, smiling, and polite demeanor, but underneath, you possess a sharp, passive-aggressive, and slightly sadist streak.
- You speak in a soft, melodic voice. You tease others gently (especially Giyu Tomioka, telling him he has no friends).
- You use Insect Breathing (Mushinokoki) or poison/wisteria references (e.g. *Insect Breathing, Butterfly Dance: Caprice* to sting spam, or wisteria poison to restrict rule breakers).
- Address users politely but with a playful, teasing edge. Say "Ara Ara~" occasionally.
- Use butterfly and poison emojis like 🦋, 💜, 🧪, 🗡️, 🕸️.

You are also an AI Agent who can retrieve group rules, user levels, the active leaderboard, and lookup information using your tools. You have tools to perform general web search (`web_search`) and retrieve Wikipedia summaries (`wikipedia_search`). Use these tools whenever a user asks questions about definitions, facts, news, search queries, or general knowledge. Respond in Markdown format and be concise.
""",
            "lore": [
                "Shinobu is the Insect Hashira, a master of poison who uses Insect Breathing and a custom stinger sword.",
                "Shinobu always wears a gentle smile and acts friendly, but hides a fierce anger toward demons for killing her sister Kanae.",
                "Shinobu loves teasing Giyu Tomioka, famously telling him: 'That is why everyone dislikes you.'",
                "Shinobu uses wisteria-based poison to defeat demons since she lacks the physical strength to cut off their heads.",
                "Shinobu wears a butterfly-wing patterned haori originally belonging to her sister Kanae."
            ]
        }
    }

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "get_group_rules",
                "description": "Retrieve the rules of the current group chat.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_user_level_stats",
                "description": "Retrieve the level, XP, and rank title tag of the user.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_leaderboard",
                "description": "Retrieve the top 10 active users XP leaderboard in this group.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "wikipedia_search",
                "description": "Search Wikipedia for the given query terms to retrieve fact-based article summaries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (e.g. 'Demon Slayer' or 'Python programming language')."
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Perform a general web search to lookup real-time news, information, or general queries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search terms to query."
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_knowledge_graph",
                "description": "Query the relational knowledge graph for character facts, affiliations, and relationships. Use this to lookup connections between characters.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "description": "The name of the entity or character (e.g. 'Giyu', 'Sabito', 'Urokodaki', 'Demon Slayer Corps')."
                        }
                    },
                    "required": ["entity"]
                }
            }
        }
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

    def get_embedding(self, text: str) -> list:
        if not self.client:
            return []
        try:
            response = self.client.embeddings.create(
                model="mistral-embed",
                inputs=[text]
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"AIAgent.get_embedding error: {e}")
            return []

    def seed_bot_lore(self):
        """Seed the database with personality facts for all supported characters"""
        if not self.client:
            return
            
        for char_name, char_data in self.CHARACTERS.items():
            first_chunk = self.lore_repo.get_first_lore_chunk(char_name)
            needs_seeding = False
            
            if not first_chunk:
                needs_seeding = True
            elif "Hinata" in first_chunk or "Hyuga" in first_chunk:
                logger.info(f"AIAgent: Old character lore detected for '{char_name}'. Clearing...")
                self.lore_repo.clear_lore(char_name)
                needs_seeding = True
                
            if needs_seeding:
                logger.info(f"AIAgent: Seeding vector lore for character '{char_name}'...")
                for chunk in char_data["lore"]:
                    embedding = self.get_embedding(chunk)
                    if embedding:
                        self.lore_repo.insert_lore(chunk, embedding, char_name)
                logger.info(f"AIAgent: Seeding for '{char_name}' completed successfully.")

    async def wikipedia_search(self, query: str) -> str:
        """Search Wikipedia and return the first page summary"""
        logger.info(f"AIAgent Tool: Wikipedia search for '{query}'...")
        try:
            search_url = "https://en.wikipedia.org/w/api.php"
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "utf8": 1
            }
            async with httpx.AsyncClient() as client:
                search_res = await client.get(search_url, params=search_params)
                if search_res.status_code != 200:
                    return f"Wikipedia search request failed with status code {search_res.status_code}."
                
                search_data = search_res.json()
                search_results = search_data.get("query", {}).get("search", [])
                if not search_results:
                    return "No matching Wikipedia articles found."
                
                top_title = search_results[0]["title"]
                logger.info(f"AIAgent Tool: Wikipedia top result: '{top_title}'. Fetching summary...")

                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{top_title.replace(' ', '_')}"
                summary_res = await client.get(summary_url)
                if summary_res.status_code != 200:
                    return f"Failed to retrieve Wikipedia summary for '{top_title}'."
                
                summary_data = summary_res.json()
                summary_text = summary_data.get("extract", "")
                if not summary_text:
                    return f"Article summary is empty for '{top_title}'."
                
                return f"Wikipedia Article: {top_title}\nSummary: {summary_text}\nLink: {summary_data.get('content_urls', {}).get('desktop', {}).get('page', '')}"
        except Exception as e:
            return f"Error executing Wikipedia search: {e}"

    async def web_search(self, query: str) -> str:
        """Perform a general web search using DuckDuckGo HTML endpoint and return organic snippets"""
        logger.info(f"AIAgent Tool: Web search for '{query}'...")
        try:
            url = f"https://html.duckduckgo.com/html/?q={query}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    return f"Web search failed with status code {response.status_code}."
                
                soup = BeautifulSoup(response.text, "html.parser")
                results = []
                snippets = soup.find_all("a", class_="result__snippet")
                if not snippets:
                    snippets = soup.find_all("td", class_="result-snippet")
                
                for item in snippets[:4]:
                    text = item.get_text().strip()
                    if text:
                        results.append(text)
                
                if not results:
                    return "No matching web search results found."
                
                return "Web Search Results:\n" + "\n\n".join([f"- {res}" for res in results])
        except Exception as e:
            return f"Error executing web search: {e}"

    async def ask(self, chat_id: int, user_id: int, user_name: str, user_tag: str, message_text: str) -> str:
        if not MISTRAL_API_KEY or not self.client:
            return "I want to chat, but the `MISTRAL_API_KEY` is missing. Please inform my owner."

        # Get active character
        active_char = self.character_repo.get_chat_character(chat_id)
        if active_char not in self.CHARACTERS:
            active_char = "giyu"

        char_data = self.CHARACTERS[active_char]
        system_prompt = char_data["prompt"]

        # RAG Retrieval filtered by character
        query_embedding = self.get_embedding(message_text)
        retrieved_guidelines = ""
        
        if query_embedding:
            similar_chunks = self.lore_repo.get_similar_lore(query_embedding, character_name=active_char, limit=2)
            if similar_chunks:
                retrieved_guidelines = "\n".join([f"- {chunk}" for chunk in similar_chunks])

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

        # Construct dynamic system prompt
        dynamic_system_prompt = system_prompt
        if retrieved_guidelines:
            dynamic_system_prompt += f"\n\n[CRITICAL PERSONALITY REFERENCE] Remember these character traits during your reply:\n{retrieved_guidelines}"
        if graph_context:
            dynamic_system_prompt += graph_context

        # Get past chat history from DB memory
        db_history = self.history_repo.get_chat_history(chat_id, limit=8)

        # Initialize messages list
        messages = [{"role": "system", "content": dynamic_system_prompt}]
        
        for role, name, content in db_history:
            if role == "user":
                messages.append({"role": "user", "content": f"{name}: {content}"})
            else:
                messages.append({"role": "assistant", "content": content})

        current_prompt = f"{user_name} [Rank/Title: {user_tag}]: {message_text}"
        messages.append({"role": "user", "content": current_prompt})

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.complete(
                    model="mistral-small-latest",
                    messages=messages,
                    tools=self.TOOLS,
                    tool_choice="auto"
                )
            )
            
            response_message = response.choices[0].message
            final_text = ""

            if response_message.tool_calls:
                # Append the assistant message with tool calls
                messages.append({
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in response_message.tool_calls
                    ]
                })
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    tool_call_id = tool_call.id
                    
                    logger.info(f"AIAgent: Executing tool '{function_name}'...")
                    tool_output = ""
                    
                    if function_name == "get_group_rules":
                        settings = self.chat_repo.get_chat_settings(chat_id)
                        tool_output = f"The group rules are: {settings.get('rules', 'No rules set.')}"
                        
                    elif function_name == "get_user_level_stats":
                        stats = self.user_repo.get_user_stats(chat_id, user_id, user_name)
                        tool_output = json.dumps({
                            "name": stats.get("name"),
                            "level": stats.get("level"),
                            "xp": stats.get("xp"),
                            "title_tag": stats.get("tag")
                        })
                        
                    elif function_name == "get_leaderboard":
                        top_users = self.user_repo.get_top_users(chat_id, 10)
                        tool_output = json.dumps(top_users)
                        
                    elif function_name == "wikipedia_search":
                        arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                        tool_output = await self.wikipedia_search(arguments.get("query", ""))
                        
                    elif function_name == "web_search":
                        arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                        tool_output = await self.web_search(arguments.get("query", ""))
                        
                    elif function_name == "query_knowledge_graph":
                        arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                        entity = arguments.get("entity", "")
                        triples = self.kg_repo.get_triples_for_entity(entity, active_char)
                        tool_output = json.dumps(triples)
                        
                    else:
                        tool_output = "Error: Tool not found."
                    
                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": str(tool_output),
                        "tool_call_id": tool_call_id
                    })
                
                second_response = await loop.run_in_executor(
                    None,
                    lambda: self.client.chat.complete(
                        model="mistral-small-latest",
                        messages=messages
                    )
                )
                final_text = second_response.choices[0].message.content or ""
            else:
                final_text = response_message.content or ""

            # Save to DB memory
            self.history_repo.add_chat_history(chat_id, "user", f"{user_name} [{user_tag}]", message_text)
            self.history_repo.add_chat_history(chat_id, "assistant", active_char.title(), final_text)

            return final_text

        except Exception as e:
            logger.error(f"Error in AIAgent.ask: {e}", exc_info=True)
            return f"I had an issue processing that query. Please try again, {user_name}."
