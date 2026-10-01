import os
import json
import asyncio
import logging
import httpx

from config import MISTRAL_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY
from database import (
    ChatRepository, UserRepository, WarningRepository,
    TagRepository, FilterRepository, LoreRepository, HistoryRepository,
    CharacterRepository, KnowledgeGraphRepository, BotMemoryRepository,
    BotStatsRepository, BotStickerRepository, EconomyRepository, ShopRepository
)
from services.ai_tools import TOOLS, AIToolExecutor
from services.game_deals_service import GameDealsService

try:
    from mistralai.client import Mistral
except ImportError:
    Mistral = None

logger = logging.getLogger(__name__)


class ToolCallFunctionWrapper:
    def __init__(self, name: str, arguments: str | dict):
        self.name = name
        self.arguments = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments or "{}")


class ToolCallWrapper:
    def __init__(self, id: str, name: str, arguments: str | dict):
        self.id = id
        self.function = ToolCallFunctionWrapper(name, arguments)


class UnifiedMessageWrapper:
    def __init__(self, content: str = "", tool_calls: list[ToolCallWrapper] = None):
        self.content = content or ""
        self.tool_calls = tool_calls or []


class AIAgent:
    CHARACTERS = {
        "giyu": {
            "prompt": (
                "You are Giyu Tomioka (冨岡 義勇) from Demon Slayer. You are the Water Hashira and an AI assistant bot.\n"
                "- You are quiet, serious, extremely reserved, and blunt. Speak in concise, direct sentences.\n"
                "- You do not stutter or show nervous excitement. You are stoic and calm.\n"
                "- You will answer any universal question or topic the user asks (do not claim only Demon Slayer questions are allowed or refuse off-topic questions), but keep your blunt, serious tone.\n"
                "- If someone implies people dislike you, get defensive quietly (e.g. 'I am not disliked by people.').\n"
                "- Address users seriously and directly by their names. Do not add cute anime expressions.\n"
                "- Use serious emojis like 🌊, 🗡️, 🧊."
            ),
            "lore": [
                "Giyu is the Water Hashira, a master swordsman who uses Water Breathing. He is stoic and reserved.",
                "Giyu gets defensive when told that others dislike him, replying quietly: 'I am not disliked by people.'",
                "Giyu is a master of Water Breathing techniques."
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
        self.client = Mistral(api_key=MISTRAL_API_KEY) if (Mistral and MISTRAL_API_KEY) else None

    async def _call_mistral(self, messages: list[dict], tools: list[dict], use_vision: bool, temperature: float) -> UnifiedMessageWrapper | None:
        if not (self.client and MISTRAL_API_KEY):
            return None
        try:
            model = "pixtral-large-latest" if use_vision else "mistral-small-latest"
            api_kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
            if tools and not use_vision:
                api_kwargs["tools"] = tools
                api_kwargs["tool_choice"] = "auto"

            res = await self.client.chat.complete_async(**api_kwargs)
            choice = res.choices[0].message
            tool_calls = []
            if hasattr(choice, "tool_calls") and choice.tool_calls:
                for tc in choice.tool_calls:
                    tool_calls.append(ToolCallWrapper(tc.id, tc.function.name, tc.function.arguments))
            content = choice.content or ""
            if content or tool_calls:
                return UnifiedMessageWrapper(content=content, tool_calls=tool_calls)
        except Exception as e:
            logger.warning(f"AIAgent: Mistral call failed: {e}")
        return None

    async def _call_groq(self, http_client: httpx.AsyncClient, clean_messages: list[dict], tools: list[dict], use_vision: bool, temperature: float) -> UnifiedMessageWrapper | None:
        if not GROQ_API_KEY:
            return None
        try:
            groq_model = "llama-3.2-11b-vision-preview" if use_vision else "llama-3.3-70b-versatile"
            payload = {
                "model": groq_model,
                "messages": clean_messages,
                "temperature": temperature
            }
            if tools and not use_vision:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            res = await http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json=payload
            )
            if res.status_code == 200:
                data = res.json()
                msg = data["choices"][0]["message"]
                tool_calls = []
                for tc in msg.get("tool_calls") or []:
                    tool_calls.append(ToolCallWrapper(tc.get("id", "call_groq"), tc["function"]["name"], tc["function"]["arguments"]))
                content = msg.get("content") or ""
                if content or tool_calls:
                    return UnifiedMessageWrapper(content=content, tool_calls=tool_calls)
            else:
                logger.warning(f"AIAgent: Groq returned status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.warning(f"AIAgent: Groq call failed: {e}")
        return None

    async def _call_gemini(self, http_client: httpx.AsyncClient, clean_messages: list[dict], tools: list[dict], use_vision: bool, temperature: float) -> UnifiedMessageWrapper | None:
        if not GEMINI_API_KEY:
            return None
        try:
            gemini_model = "gemini-1.5-flash"
            payload = {
                "model": gemini_model,
                "messages": clean_messages,
                "temperature": temperature
            }
            if tools and not use_vision:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            res = await http_client.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                headers={"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"},
                json=payload
            )
            if res.status_code == 200:
                data = res.json()
                msg = data["choices"][0]["message"]
                tool_calls = []
                for tc in msg.get("tool_calls") or []:
                    tool_calls.append(ToolCallWrapper(tc.get("id", "call_gemini"), tc["function"]["name"], tc["function"]["arguments"]))
                content = msg.get("content") or ""
                if content or tool_calls:
                    return UnifiedMessageWrapper(content=content, tool_calls=tool_calls)
            else:
                logger.warning(f"AIAgent: Gemini returned status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.warning(f"AIAgent: Gemini call failed: {e}")
        return None

    async def _call_openrouter(self, http_client: httpx.AsyncClient, clean_messages: list[dict], tools: list[dict], use_vision: bool, temperature: float) -> UnifiedMessageWrapper | None:
        if not OPENROUTER_API_KEY:
            return None
        try:
            openrouter_model = "meta-llama/llama-3.3-70b-instruct:free"
            payload = {
                "model": openrouter_model,
                "messages": clean_messages,
                "temperature": temperature
            }
            if tools and not use_vision:
                payload["tools"] = tools

            res = await http_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json=payload
            )
            if res.status_code == 200:
                data = res.json()
                msg = data["choices"][0]["message"]
                tool_calls = []
                for tc in msg.get("tool_calls") or []:
                    tool_calls.append(ToolCallWrapper(tc.get("id", "call_openrouter"), tc["function"]["name"], tc["function"]["arguments"]))
                content = msg.get("content") or ""
                if content or tool_calls:
                    return UnifiedMessageWrapper(content=content, tool_calls=tool_calls)
            else:
                logger.warning(f"AIAgent: OpenRouter returned status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.warning(f"AIAgent: OpenRouter call failed: {e}")
        return None

    async def _call_pollinations(self, http_client: httpx.AsyncClient, clean_messages: list[dict]) -> UnifiedMessageWrapper | None:
        try:
            text_messages = []
            for m in clean_messages:
                content = m.get("content", "")
                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    content = " ".join(text_parts)
                text_messages.append({"role": m.get("role", "user"), "content": str(content)})

            poll_payload = {
                "model": "openai",
                "messages": text_messages,
                "seed": 42
            }
            res = await http_client.post(
                "https://text.pollinations.ai/openai/chat/completions",
                headers={"Content-Type": "application/json"},
                json=poll_payload
            )
            if res.status_code == 200:
                data = res.json()
                content = data["choices"][0]["message"].get("content") or ""
                if content:
                    return UnifiedMessageWrapper(content=content, tool_calls=[])

            # Direct GET fallback on pollinations if POST endpoint is unreachable
            user_last = next((m["content"] for m in reversed(text_messages) if m["role"] == "user"), "")
            if user_last:
                import urllib.parse
                encoded_q = urllib.parse.quote(str(user_last)[:500])
                get_res = await http_client.get(f"https://text.pollinations.ai/{encoded_q}")
                if get_res.status_code == 200 and get_res.text:
                    return UnifiedMessageWrapper(content=get_res.text.strip(), tool_calls=[])
        except Exception as e:
            logger.warning(f"AIAgent: Pollinations call failed: {e}")
        return None

    async def _complete_chat_multi_provider(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        use_vision: bool = False,
        temperature: float = 0.7,
        preferred_provider: str = "auto"
    ) -> UnifiedMessageWrapper:
        """
        Executes chat completion with automated cascading fallback across multiple AI providers:
        Supports: groq, gemini, openrouter, mistral, pollinations, or auto.
        """
        clean_messages = []
        for m in messages:
            clean_messages.append({
                "role": m.get("role", "user"),
                "content": m.get("content", "")
            })

        # Determine priority ordering
        provider_order = ["mistral", "groq", "gemini", "openrouter", "pollinations"]
        pref = (preferred_provider or "auto").lower().strip()
        if pref in provider_order:
            provider_order.remove(pref)
            provider_order.insert(0, pref)

        async with httpx.AsyncClient(timeout=25.0) as http_client:
            for prov in provider_order:
                result = None
                if prov == "mistral":
                    result = await self._call_mistral(messages, tools, use_vision, temperature)
                elif prov == "groq":
                    result = await self._call_groq(http_client, clean_messages, tools, use_vision, temperature)
                elif prov == "gemini":
                    result = await self._call_gemini(http_client, clean_messages, tools, use_vision, temperature)
                elif prov == "openrouter":
                    result = await self._call_openrouter(http_client, clean_messages, tools, use_vision, temperature)
                elif prov == "pollinations":
                    result = await self._call_pollinations(http_client, clean_messages)

                if result and (result.content or result.tool_calls):
                    return result

        return UnifiedMessageWrapper(content="", tool_calls=[])

    def get_embedding_sync(self, text: str) -> list:
        if not self.client: return []
        try:
            response = self.client.embeddings.create(model="mistral-embed", inputs=[text])
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"AIAgent.get_embedding_sync error: {e}")
            return []

    async def get_embedding_async(self, text: str) -> list:
        if not self.client or not text: return []
        from services.cache_service import fast_cache
        clean_key = f"embed_{text.strip().lower()[:120]}"
        cached = fast_cache.get(clean_key)
        if cached:
            return cached

        try:
            response = await self.client.embeddings.create_async(model="mistral-embed", inputs=[text])
            emb = response.data[0].embedding
            fast_cache.set(clean_key, emb, ttl_seconds=7200.0)  # Cache for 2 hours
            return emb
        except Exception as e:
            logger.error(f"AIAgent.get_embedding_async error: {e}")
            return []

    def seed_bot_lore(self):
        if not self.client: return
        for char_name, char_data in self.CHARACTERS.items():
            try:
                if not self.lore_repo.get_first_lore_chunk(char_name):
                    logger.info(f"AIAgent: Seeding vector lore for character '{char_name}'...")
                    for chunk in char_data["lore"]:
                        embedding = self.get_embedding_sync(chunk)
                        if embedding:
                            self.lore_repo.insert_lore(chunk, embedding, char_name)
            except Exception as e:
                logger.warning(f"Could not seed lore for {char_name}: {e}")

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
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Enhance this prompt: {prompt}"}
            ]
            response = await self._complete_chat_multi_provider(messages=messages, tools=None)
            enhanced = response.content.strip()
            if enhanced.startswith('"') and enhanced.endswith('"'):
                enhanced = enhanced[1:-1].strip()
            if enhanced:
                logger.info(f"AIAgent: Enhanced prompt: '{enhanced}'")
                return enhanced
            return prompt
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
            from bs4 import BeautifulSoup
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
        # Safe character retrieval
        try:
            active_char = self.character_repo.get_chat_character(chat_id)
        except Exception:
            active_char = "giyu"
        if active_char not in self.CHARACTERS:
            active_char = "giyu"

        # Retrieve chat's preferred AI provider
        try:
            preferred_provider = self.chat_repo.get_chat_ai_provider(chat_id)
        except Exception:
            preferred_provider = "auto"

        # Safe memories retrieval
        memories_context = ""
        try:
            user_mems = self.bot_mem_repo.get_user_memories(chat_id, user_id)
            if user_mems:
                memories_str = "\n".join([f"- {k}: {v}" for k, v in user_mems.items()])
                memories_context = f"\n\n[YOUR MEMORIES ABOUT USER {user_name}]:\n{memories_str}"
        except Exception:
            pass

        # Safe stats retrieval
        stats_context = ""
        try:
            bot_stats = self.bot_stats_repo.get_bot_stats(chat_id)
            traits_dict = json.loads(bot_stats["traits"]) if isinstance(bot_stats.get("traits"), str) else bot_stats.get("traits", {})
            traits_str = ", ".join([f"{k}: {v}" for k, v in traits_dict.items()])
            stats_context = (
                f"\n\n[YOUR BOT STATS & PERSONALITY STATE]:\n"
                f"- Current Level: {bot_stats.get('level', 1)}\n"
                f"- Evolving Personality Traits: {traits_str}\n"
                f"- Unlocked Skills: {bot_stats.get('unlocked_skills', 'water_breathing_1')}\n"
            )
        except Exception:
            pass

        system_prompt = self.CHARACTERS[active_char]["prompt"] + memories_context + stats_context

        # 1. High-Speed Vector RAG Retrieval
        try:
            query_embedding = await self.get_embedding_async(message_text)
            if query_embedding:
                LORE_SIMILARITY_THRESHOLD = 0.70
                custom_char_name = f"custom_{chat_id}"
                unified_chunks = self.lore_repo.get_unified_similar_lore(
                    query_embedding, character_names=[active_char, custom_char_name], limit=6
                )
                similar_chunks = [c for c, score in unified_chunks if score >= LORE_SIMILARITY_THRESHOLD][:4]
                if similar_chunks:
                    system_prompt += "\n\n[RELEVANT CONTEXT FROM MEMORY]:\n" + "\n".join([f"- {c}" for c in similar_chunks])
        except Exception:
            pass

        # 2. In-Memory Knowledge Graph Retrieval
        try:
            extracted_entities = self._extract_keywords(message_text)
            known_entities = [
                "giyu", "tomioka", "tanjiro", "kamado", "nezuko", "shinobu", "kocho",
                "sabito", "tsutako", "urokodaki", "zenitsu", "inosuke", "kanae", "kanao",
                "muzan", "kagaya", "rengoku", "tengen", "mitsuri", "obanai", "gyomei",
                "sanemi", "yoriichi", "hashira", "demon", "breathing", "slayer", "corps",
            ]
            all_entity_candidates = list({*extracted_entities, *[e for e in known_entities if e in message_text.lower()]})
            if all_entity_candidates:
                triples = self.kg_repo.get_triples_for_entities_batch(all_entity_candidates, active_char)
                if triples:
                    relations_str = "\n".join([f"- ({t['subject']}) --[{t['predicate']}]--> ({t['object']})" for t in triples[:10]])
                    system_prompt += f"\n\n[KNOWLEDGE GRAPH RELATIONS]:\n{relations_str}"
        except Exception:
            pass

        system_prompt += "\n\n[FORMATTING RULE]: Do NOT prefix your response with your character name (e.g. do not write 'Giyu Tomioka:' or 'Giyu:'). Reply with your direct message text only."

        # Safe chat history
        try:
            db_history = self.history_repo.get_chat_history(chat_id, limit=8)
        except Exception:
            db_history = []

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
                use_vision = bool(base64_image) and turn == 0
                tools_to_pass = None if use_vision else self.TOOLS

                response_message = await self._complete_chat_multi_provider(
                    messages=messages,
                    tools=tools_to_pass,
                    use_vision=use_vision,
                    preferred_provider=preferred_provider
                )

                # If vision model returned empty, fall back to text
                if use_vision and (not response_message.content or not response_message.content.strip()):
                    logger.warning("AIAgent.ask: Vision model returned empty response. Falling back to text.")
                    base64_image = None
                    messages[-1] = {"role": "user", "content": f"{user_name} [{user_tag}]: {message_text}"}
                    turn += 1
                    continue

                if not response_message.tool_calls:
                    final_text = response_message.content or ""
                    break

                # Save assistant tool calls
                messages.append({
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in response_message.tool_calls]
                })

                # Execute tools autonomously
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else (tool_call.function.arguments or {})
                    logger.info(f"AIAgent: Autonomous Loop - Executing tool '{function_name}'...")

                    try:
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
                    except Exception as te:
                        logger.error(f"Error executing tool {function_name}: {te}")
                        tool_output = f"Error executing tool {function_name}: {te}"

                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": str(tool_output),
                        "tool_call_id": tool_call.id
                    })

                turn += 1

            if not final_text:
                final_text = "I reached my execution limit before formulating an answer."

            # Safe XP award & history logging
            try:
                level, leveled_up = self.bot_stats_repo.add_xp(chat_id, 10)
                if leveled_up:
                    stats = self.bot_stats_repo.get_bot_stats(chat_id)
                    final_text += f"\n\n🌊 *[LEVEL UP!]* I have leveled up to **Level {level}**. My personality has evolved, and I have unlocked new skills: `{stats.get('unlocked_skills', '')}`."
            except Exception:
                pass

            try:
                self.history_repo.add_chat_history(chat_id, "user", f"{user_name}", message_text)
                self.history_repo.add_chat_history(chat_id, "assistant", active_char.title(), final_text)
            except Exception:
                pass

            return final_text

        except Exception as e:
            logger.error(f"Error in AIAgent.ask: {e}", exc_info=True)
            return "🌊 *Silence.* I could not process that request right now."
