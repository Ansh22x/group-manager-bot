import os
import json
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup

from mistralai.client import Mistral
from config import MISTRAL_API_KEY
from database import (
    ChatRepository, UserRepository, WarningRepository,
    TagRepository, FilterRepository, LoreRepository, HistoryRepository,
    CharacterRepository, KnowledgeGraphRepository, BotMemoryRepository,
    BotStatsRepository, BotStickerRepository, EconomyRepository, ShopRepository
)
from services.ai_tools import TOOLS, AIToolExecutor
from services.game_deals_service import GameDealsService

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

    TOOLS = TOOLS

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
        self.bot_mem_repo = BotMemoryRepository()
        self.bot_stats_repo = BotStatsRepository()
        self.bot_sticker_repo = BotStickerRepository()
        self.economy_repo = EconomyRepository()
        self.shop_repo = ShopRepository()
        self.game_deals_service = GameDealsService()

        self.tool_executor = AIToolExecutor(self)
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

    async def enhance_image_prompt(self, prompt: str) -> str:
        if not self.client: return prompt
        try:
            logger.info(f"AIAgent: Enhancing image generation prompt: '{prompt}'...")
            system_instruction = (
                "You are an expert AI prompt engineer. Your task is to take a simple, raw user image prompt "
                "and enhance it to be highly descriptive, artistic, and detailed for a text-to-image generator (like Stable Diffusion).\n"
                "- Keep the original subject and core meaning of the prompt intact.\n"
                "- Add details about the setting, lighting (e.g. cinematic, volumetric, dramatic), atmosphere, "
                "art style, and quality tags (e.g. highly detailed, 8k resolution, masterpieces, sharp focus).\n"
                "- Respond ONLY with the enhanced prompt. Do not add any introductory or explanatory text."
            )
            response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Enhance this prompt: {prompt}"}
                ]
            )
            enhanced = response.choices[0].message.content.strip()
            if enhanced.startswith('"') and enhanced.endswith('"'):
                enhanced = enhanced[1:-1].strip()
            logger.info(f"AIAgent: Enhanced prompt: '{enhanced}'")
            return enhanced
        except Exception as e:
            logger.error(f"AIAgent.enhance_image_prompt error: {e}")
            return prompt

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

    @staticmethod
    def _cosine_similarity(a: list, b: list) -> float:
        """Compute cosine similarity between two embedding vectors."""
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from a message for graph-RAG entity lookup."""
        _STOPWORDS = {
            "a", "an", "the", "is", "it", "in", "on", "at", "by", "to", "of", "and",
            "or", "for", "with", "this", "that", "be", "as", "are", "was", "were",
            "what", "who", "how", "why", "when", "where", "can", "do", "did", "does",
            "me", "my", "i", "you", "your", "he", "she", "we", "they", "his", "her",
            "tell", "about", "know", "think", "say", "get", "just", "like",
        }
        import re as _re
        words = _re.sub(r"[^\w\s]", "", text.lower()).split()
        return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


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
        base64_image: str = None,
        image_mime: str = "image/jpeg"
    ) -> str:
        if not MISTRAL_API_KEY or not self.client:
            return "I want to chat, but the `MISTRAL_API_KEY` is missing."

        active_char = self.character_repo.get_chat_character(chat_id)
        if active_char not in self.CHARACTERS:
            active_char = "giyu"

        # Retrieve persistent memories of this user
        user_mems = self.bot_mem_repo.get_user_memories(chat_id, user_id)
        memories_context = ""
        if user_mems:
            memories_str = "\n".join([f"- {k}: {v}" for k, v in user_mems.items()])
            memories_context = f"\n\n[YOUR MEMORIES ABOUT USER {user_name}]:\n{memories_str}"

        # Retrieve bot stats/traits/skills
        bot_stats = self.bot_stats_repo.get_bot_stats(chat_id)
        import json
        try:
            traits_dict = json.loads(bot_stats["traits"])
            traits_str = ", ".join([f"{k}: {v}" for k, v in traits_dict.items()])
        except Exception:
            traits_str = bot_stats["traits"]
        stats_context = (
            f"\n\n[YOUR BOT STATS & PERSONALITY STATE]:\n"
            f"- Current Level: {bot_stats['level']}\n"
            f"- Evolving Personality Traits: {traits_str}\n"
            f"- Unlocked Skills: {bot_stats['unlocked_skills']}\n"
            f"Note: Your responses should subtly reflect your personality traits and level. You gain experience points (XP) when users chat with you, causing you to level up, evolve your traits, and unlock new abilities."
        )

        system_prompt = self.CHARACTERS[active_char]["prompt"] + memories_context + stats_context
        
        similar_chunks = []
        query_embedding = await self.get_embedding_async(message_text)
        if query_embedding:
            LORE_SIMILARITY_THRESHOLD = 0.70

            # 1. Fetch character personality traits (limit 3, with threshold)
            all_char_chunks = self.lore_repo.get_similar_lore_with_scores(query_embedding, character_name=active_char, limit=4)
            for content, score in all_char_chunks:
                if score >= LORE_SIMILARITY_THRESHOLD:
                    similar_chunks.append(content)
                    if len(similar_chunks) >= 2:
                        break

            # 2. Fetch custom group chat document lore (limit 4, with threshold)
            custom_char_name = f"custom_{chat_id}"
            all_custom_chunks = self.lore_repo.get_similar_lore_with_scores(query_embedding, character_name=custom_char_name, limit=5)
            for content, score in all_custom_chunks:
                if score >= LORE_SIMILARITY_THRESHOLD:
                    similar_chunks.append(content)
                    if len(similar_chunks) >= 5:
                        break

            if similar_chunks:
                system_prompt += "\n\n[RELEVANT CONTEXT FROM MEMORY]:\n" + "\n".join([f"- {c}" for c in similar_chunks])

        # Knowledge Graph (Graph-RAG) retrieval - keyword-based entity extraction
        extracted_entities = self._extract_keywords(message_text)
        # Also check against known KDS entity names for exact match boosting
        known_entities = [
            "giyu", "tomioka", "tanjiro", "kamado", "nezuko", "shinobu", "kocho",
            "sabito", "tsutako", "urokodaki", "zenitsu", "inosuke", "kanae", "kanao",
            "muzan", "kagaya", "rengoku", "tengen", "mitsuri", "obanai", "gyomei",
            "sanemi", "yoriichi", "hashira", "demon", "breathing", "slayer", "corps",
        ]
        # Merge: prefer known entity names (for precise KG hits) but also use keywords
        all_entity_candidates = list({*extracted_entities, *[e for e in known_entities if e in message_text.lower()]})

        graph_context = ""
        if all_entity_candidates:
            triples = []
            for ent in all_entity_candidates:
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
                    {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{base64_image}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": f"{user_name} [{user_tag}]: {message_text}"})

        max_turns = 5
        turn = 0
        final_text = ""

        try:
            while turn < max_turns:
                # Vision turn: use Pixtral (Mistral's multimodal model) WITHOUT tools
                # Subsequent turns: use mistral-small-latest WITH tools
                use_vision = bool(base64_image) and turn == 0
                model = "pixtral-large-latest" if use_vision else "mistral-small-latest"
                api_kwargs: dict = {"model": model, "messages": messages}
                if not use_vision:
                    api_kwargs["tools"] = self.TOOLS
                    api_kwargs["tool_choice"] = "auto"

                VISION_FALLBACK_MODELS = ["pixtral-large-latest", "pixtral-12b-2409"]
                last_err = None
                for attempt in range(3):
                    try:
                        # On vision retries, fall back to the smaller pixtral model
                        if use_vision and attempt > 0:
                            api_kwargs["model"] = VISION_FALLBACK_MODELS[min(attempt, len(VISION_FALLBACK_MODELS) - 1)]
                        response = await self.client.chat.complete_async(**api_kwargs)
                        last_err = None
                        break
                    except Exception as retry_err:
                        last_err = retry_err
                        logger.warning(f"AIAgent.ask: Attempt {attempt+1} failed ({retry_err}). Retrying...")
                        if attempt == 2:
                            raise retry_err
                        await asyncio.sleep(1.5 * (attempt + 1))

                response_message = response.choices[0].message

                # If vision model returned empty (refusal/content filter), fall back to text-only
                if use_vision and (not response_message.content or not response_message.content.strip()):
                    logger.warning("AIAgent.ask: Vision model returned empty response. Falling back to text-only retry.")
                    base64_image = None  # Strip image for next turn
                    messages[-1] = {"role": "user", "content": f"{user_name} [{user_tag}]: {message_text} (Note: I sent an image but describe your reaction based on the context.)"}
                    turn += 1
                    continue

                if not response_message.tool_calls:
                    final_text = response_message.content or ""
                    break
                    
                # Save assistant tool call structure
                messages.append({
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in response_message.tool_calls]
                })
                
                # Execute tools autonomously via AIToolExecutor
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else (tool_call.function.arguments or {})
                    logger.info(f"AIAgent: Autonomous Loop - Executing tool '{function_name}'...")
                    
                    tool_output = await self.tool_executor.execute(
                        function_name=function_name,
                        arguments=arguments,
                        chat_id=chat_id,
                        user_id=user_id,
                        user_name=user_name,
                        is_admin=is_admin,
                        update=update,
                        context=context
                    )
                    
                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": str(tool_output),
                        "tool_call_id": tool_call.id
                    })
                
                turn += 1
                
            if not final_text:
                final_text = "I reached my agentic execution limit before formulating an answer."

            # Award XP to bot and handle potential level-up
            try:
                level, leveled_up = self.bot_stats_repo.add_xp(chat_id, 10)
                if leveled_up:
                    stats = self.bot_stats_repo.get_bot_stats(chat_id)
                    final_text += f"\n\n🌊 *[LEVEL UP!]* I have leveled up to **Level {level}**. My personality has evolved, and I have unlocked new skills: `{stats['unlocked_skills']}`."
            except Exception as le:
                logger.error(f"Failed to update bot stats: {le}")

            self.history_repo.add_chat_history(chat_id, "user", f"{user_name}", message_text)
            self.history_repo.add_chat_history(chat_id, "assistant", active_char.title(), final_text)

            return final_text

        except Exception as e:
            logger.error(f"Error in AIAgent.ask: {e}", exc_info=True)
            return f"🌊 *Silence.* I could not process that request right now."
