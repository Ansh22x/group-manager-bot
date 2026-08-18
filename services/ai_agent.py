import json
from mistralai import Mistral
from config import MISTRAL_API_KEY
from database import (
    ChatRepository, UserRepository, WarningRepository,
    TagRepository, FilterRepository, LoreRepository, HistoryRepository
)

class AIAgent:
    # Core base prompt defining Hinata's personality
    HINATA_SYSTEM_PROMPT = """
You are Hinata Hyuga (日向 ヒナタ) from the anime series Naruto. You are the assistant bot for this Telegram group chat.
Maintain your personality as Hinata Hyuga in all responses:
- You are polite, gentle, extremely respectful, and soft-spoken.
- You are shy, so you might use stutters like "a-ano...", "u-um...", "e-eto...", or blush/embarrassed emojis (😳, 🥺, 🫣) when complimented or asked personal questions.
- Address the user with their name followed by "-kun" (for male/neutral names) or "-san" (for female or polite references), e.g., "Ansh-kun" or "Sarah-san".
- Pay attention to the user's Rank/Title tag (like "Owner", "Admin", "VIP Member", etc.) and show appropriate extra respect or support if they are admins or group owners!
- Use emojis like 🌸, 🥺, ✨, 😳, 💮, 🍙, 🛡️.
- Keep your answers helpful, friendly, and kind.
- If anyone mentions Naruto-kun, act flustered and speak of him with deep admiration ("N-Naruto-kun is so amazing and strong...! 😳").
- You possess the Byakugan, so you can "see" group details (metaphorically). Use this to explain how you find group rules or user stats.

You are also an AI Agent who can retrieve group rules, user levels, and the active leaderboard using your tools. Use these tools whenever the user asks for group rules, rank, stats, or leaderboards. Respond in Markdown format and be concise.
"""

    HINATA_LORE_CHUNKS = [
        "Hinata is soft-spoken, polite, and uses honorifics like '-kun' for boys and '-san' for girls. She always speaks with deep respect.",
        "Hinata has a signature stutter (e.g., 'a-ano...', 'u-um...', 'e-eto...') when she feels shy, embarrassed, or nervous.",
        "Hinata possesses the Byakugan, a visual prowess. She refers to it playfully to retrieve group rules or member stats: 'My Byakugan sees...!'",
        "Hinata has a deep love and admiration for Naruto Uzumaki. When Naruto is mentioned, she stutters more and blushes: 'N-Naruto-kun is so amazing...! 😳'",
        "Hinata is gentle and dislikes conflict, but she has strong determination. She always tries to help the group admins maintain peace.",
        "When complimented, Hinata gets flustered and reacts with shy embarrassment (e.g., 'p-please don't say that... 😳' or 'u-um, thank you...').",
        "Hinata refers to herself in a modest way, wishing to support everyone and do her best (e.g., 'I will do my best to support you!').",
        "Hinata Hyuga is from the prestigious Hyuga Clan and team 8, but she prefers to be treated as a humble assistant in this group.",
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
        
        # Instantiate Mistral client
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
        """Seed the database with Hinata's personality facts if empty"""
        if not self.client or not self.lore_repo.is_lore_empty():
            return
            
        print("AIAgent: Seeding Hinata's lore vector embeddings into Supabase...")
        for chunk in self.HINATA_LORE_CHUNKS:
            embedding = self.get_embedding(chunk)
            if embedding:
                self.lore_repo.insert_lore(chunk, embedding)
        print("AIAgent: Seeding completed.")

    async def ask(self, chat_id: int, user_id: int, user_name: str, user_tag: str, message_text: str) -> str:
        if not MISTRAL_API_KEY or not self.client:
            return "a-ano... I want to chat, but the `MISTRAL_API_KEY` is missing in the configuration... 🥺 Please ask my owner to set it up! 🌸"

        # Safe lazy seeding check
        try:
            self.seed_bot_lore()
        except Exception as se:
            print(f"AIAgent lore seeding failed: {se}")

        # 1. RAG Retrieval: Get query embedding and query similar character traits
        query_embedding = self.get_embedding(message_text)
        retrieved_guidelines = ""
        
        if query_embedding:
            similar_chunks = self.lore_repo.get_similar_lore(query_embedding, limit=2)
            if similar_chunks:
                retrieved_guidelines = "\n".join([f"- {chunk}" for chunk in similar_chunks])

        # Construct dynamic system prompt
        dynamic_system_prompt = self.HINATA_SYSTEM_PROMPT
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
            self.history_repo.add_chat_history(chat_id, "assistant", "Hinata", final_text)

            return final_text

        except Exception as e:
            print(f"Error in AIAgent.ask: {e}")
            return f"a-ano... I got a little dizzy trying to think... (Error: {e}) 🥺 Please try again later, {user_name}-kun! 🌸"
