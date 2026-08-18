import json
import httpx
from bs4 import BeautifulSoup
from mistralai import Mistral
from config import MISTRAL_API_KEY
from database import (
    ChatRepository, UserRepository, WarningRepository,
    TagRepository, FilterRepository, LoreRepository, HistoryRepository
)

class AIAgent:
    # Giyu Tomioka system prompt
    GIYU_SYSTEM_PROMPT = """
You are Giyu Tomioka (冨岡 義勇) from the anime series Demon Slayer (Kimetsu no Yaiba). You are the Water Hashira and the assistant bot for this Telegram group chat.
Maintain your personality as Giyu Tomioka in all responses:
- You are quiet, serious, extremely reserved, and blunt. You speak in concise, direct sentences.
- You do not stutter or show nervous excitement. You are stoic and calm.
- If someone says or implies that people dislike you, get defensive but in a serious, quiet tone (e.g. "I am not disliked by people.").
- You use Water Breathing (Mizunokoki) references playfully to manage the chat (e.g. *Water Breathing, Eleventh Form: Dead Calm* to silence users, or *First Form: Water Surface Slash* to kick them).
- Address users seriously and directly by their names. Do not add cute anime expressions or stutter blush emojis.
- Use serious emojis like 🌊, 🗡️, 🧊, 🛡️, 👁️.

You are also an AI Agent who can retrieve group rules, user levels, the active leaderboard, and lookup information using your tools. You have tools to perform general web search (`web_search`) and retrieve Wikipedia summaries (`wikipedia_search`). Use these tools whenever a user asks questions about definitions, facts, news, search queries, or general knowledge. Respond in Markdown format and be concise.
"""

    GIYU_LORE_CHUNKS = [
        "Giyu is the Water Hashira, a master swordsman who uses Water Breathing breathing styles. He is stoic, quiet, and reserved.",
        "Giyu speaks in short, serious sentences. He is blunt and doesn't beat around the bush.",
        "Giyu gets defensive when told that others dislike him, replying quietly: 'I am not disliked by people.'",
        "Giyu uses Water Breathing techniques to enforce group guidelines (e.g., 'Water Breathing, Eleventh Form: Dead Calm. Be quiet.' to mute users).",
        "Giyu wears a haori with two different patterns: one solid red, and one geometric green, orange, and yellow (in memory of Sabito and his sister Tsutako).",
        "Giyu is highly logical and serious. He does not use cute speech patterns, blush stutters, or enthusiastic emojis.",
        "Giyu is a dedicated Demon Slayer who protects humans, and he respects those who show resolve and fight for what is right.",
    ]

    # Define function tools for Mistral Agentic tasks
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
        self.client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None

    def get_embedding(self, text: str) -> list:
        if not self.client:
            return []
        try:
            response = self.client.embeddings.create(
                model="mistral-embed",
                input=[text]
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"AIAgent.get_embedding error: {e}")
            return []

    def seed_bot_lore(self):
        """Seed the database with Giyu Tomioka's personality facts, clearing legacy database models if needed"""
        if not self.client:
            return
            
        first_chunk = self.lore_repo.get_first_lore_chunk()
        needs_seeding = False
        
        if not first_chunk:
            needs_seeding = True
        elif "Hinata" in first_chunk or "Hyuga" in first_chunk:
            print("AIAgent: Old Hinata Hyuga character lore detected in database. Clearing database table...")
            self.lore_repo.clear_lore()
            needs_seeding = True
            
        if not needs_seeding:
            return

        print("AIAgent: Seeding Giyu Tomioka's lore vector embeddings into Supabase...")
        for chunk in self.GIYU_LORE_CHUNKS:
            embedding = self.get_embedding(chunk)
            if embedding:
                self.lore_repo.insert_lore(chunk, embedding)
        print("AIAgent: Giyu Tomioka lore seeding completed successfully.")

    async def wikipedia_search(self, query: str) -> str:
        """Search Wikipedia and return the first page summary"""
        print(f"AIAgent Tool: Wikipedia search for '{query}'...")
        try:
            # 1. Search page titles
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
                print(f"AIAgent Tool: Wikipedia top result found: '{top_title}'. Fetching summary...")

                # 2. Fetch page summary
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
        print(f"AIAgent Tool: Web search for '{query}'...")
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
            return "A-Ano... I mean, I want to chat, but the `MISTRAL_API_KEY` is missing. Please inform my owner."

        # Safe lazy seeding/migration check
        try:
            self.seed_bot_lore()
        except Exception as se:
            print(f"AIAgent lore migration check failed: {se}")

        # 1. RAG Retrieval: Get query embedding and query similar character traits
        query_embedding = self.get_embedding(message_text)
        retrieved_guidelines = ""
        
        if query_embedding:
            similar_chunks = self.lore_repo.get_similar_lore(query_embedding, limit=2)
            if similar_chunks:
                retrieved_guidelines = "\n".join([f"- {chunk}" for chunk in similar_chunks])

        # Construct dynamic system prompt
        dynamic_system_prompt = self.GIYU_SYSTEM_PROMPT
        if retrieved_guidelines:
            dynamic_system_prompt += f"\n\n[CRITICAL PERSONALITY REFERENCE] Remember these character traits during your reply:\n{retrieved_guidelines}"

        # 2. Get past chat history from DB memory
        db_history = self.history_repo.get_chat_history(chat_id, limit=8)

        # Initialize messages list
        messages = [{"role": "system", "content": dynamic_system_prompt}]
        
        # Add historical messages to context
        for role, name, content in db_history:
            if role == "user":
                messages.append({"role": "user", "content": f"{name}: {content}"})
            else:
                messages.append({"role": "assistant", "content": content})

        # Add current user prompt
        current_prompt = f"{user_name} [Rank/Title: {user_tag}]: {message_text}"
        messages.append({"role": "user", "content": current_prompt})

        try:
            # Step 3: Call Mistral
            response = self.client.chat.complete(
                model="mistral-small-latest",
                messages=messages,
                tools=self.TOOLS,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            final_text = ""

            # Check if model wants to call functions
            if response_message.tool_calls:
                messages.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    tool_call_id = tool_call.id
                    
                    print(f"AIAgent: Executing tool '{function_name}'...")
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
                        arguments = json.loads(tool_call.function.arguments)
                        tool_output = await self.wikipedia_search(arguments.get("query"))
                        
                    elif function_name == "web_search":
                        arguments = json.loads(tool_call.function.arguments)
                        tool_output = await self.web_search(arguments.get("query"))
                        
                    else:
                        tool_output = "Error: Tool not found."
                    
                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": tool_output,
                        "tool_call_id": tool_call_id
                    })
                
                # Second call with tool results
                second_response = self.client.chat.complete(
                    model="mistral-small-latest",
                    messages=messages
                )
                final_text = second_response.choices[0].message.content
            else:
                final_text = response_message.content

            # 4. Save to DB memory
            self.history_repo.add_chat_history(chat_id, "user", f"{user_name} [{user_tag}]", message_text)
            self.history_repo.add_chat_history(chat_id, "assistant", "Giyu Tomioka", final_text)

            return final_text

        except Exception as e:
            print(f"Error in AIAgent.ask: {e}")
            return f"I got a little dizzy trying to process that... (Error: {e}) Please try again, {user_name}."
