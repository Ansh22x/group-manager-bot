import os
import re
import time
import json
import shutil
import logging
import asyncio

logger = logging.getLogger(__name__)

# Default Hermes run configuration (provider + model Hermes itself uses).
# Override via env vars without touching Hermes' own config.yaml.
HERMES_PROVIDER = os.getenv("HERMES_PROVIDER", "openrouter")
HERMES_MODEL = os.getenv("HERMES_MODEL", "nvidia/nemotron-3.5-lightning:free")
HERMES_MAX_TURNS = int(os.getenv("HERMES_MAX_TURNS", "8"))
HERMES_TIMEOUT = float(os.getenv("HERMES_TIMEOUT", "180"))
HERMES_CHAT_TIMEOUT = float(os.getenv("HERMES_CHAT_TIMEOUT", "35"))
HERMES_OUTPUT_CHARS = 3500

# Resilience knobs
HERMES_MAX_ATTEMPTS = int(os.getenv("HERMES_MAX_ATTEMPTS", "3"))
HERMES_BREAKER_THRESHOLD = int(os.getenv("HERMES_BREAKER_THRESHOLD", "5"))   # consecutive failures before open
HERMES_BREAKER_COOLDOWN = float(os.getenv("HERMES_BREAKER_COOLDOWN", "60"))  # seconds before half-open probe
HERMES_SESSION_ROTATIONS = int(os.getenv("HERMES_SESSION_ROTATIONS", "2"))   # fresh sessions tried before giving up

_SESSION_RE = re.compile(r"[^a-zA-Z0-9_-]")

_noise_markers = (
    "session_id:", "Provider said:", "rate-limited", "didn't answer",
    "isn't available", "Pick a different model", "send /retry",
)


def hermes_available() -> bool:
    """Check whether the hermes CLI binary exists on PATH."""
    return shutil.which("hermes") is not None


def session_name(chat_id: int, rotation: int = 0) -> str:
    """Stable Hermes session name for a Telegram chat. `rotation > 0` yields a
    fresh session used for self-healing when the primary session is corrupted."""
    base = f"giyu-chat-{_SESSION_RE.sub('', str(chat_id))}"
    return base if rotation == 0 else f"{base}-r{rotation}"


def _parse_plain_text(raw_output: str, *, strip_echo: str | None = None) -> str | None:
    """Extract the final answer from `--format text` output: everything after
    the last session_id line, minus diagnostic noise lines.

    strip_echo: optional user message text echoed back in the transcript —
    matching lines are removed.
    """
    lines = []
    for ln in raw_output.splitlines():
        s = ln.strip()
        if not s:
            continue
        if any(m in s for m in _noise_markers):
            continue
        if s == "..." or s == "…":
            continue
        if strip_echo:
            candidates = {strip_echo, strip_echo.strip()}
            if s in candidates:
                continue
            # echo rendered as "Name: message"
            if ": " in s and s.split(": ", 1)[1].strip() in candidates:
                continue
        lines.append(s)
    if not lines:
        return None
    return "\n".join(lines[-40:]).strip() or None


class _CircuitBreaker:
    """Trip after N consecutive failures; cool down, then allow a probe."""

    def __init__(self, threshold: int, cooldown: float):
        self.threshold = threshold
        self.cooldown = cooldown
        self.consecutive_failures = 0
        self.opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.cooldown:
            # cooldown elapsed — half-open: allow one probe through
            return False
        return True

    def record_success(self):
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.monotonic()
            logger.warning(
                f"Hermes circuit breaker OPEN after {self.consecutive_failures} consecutive failures "
                f"(cooldown {self.cooldown:.0f}s). Requests will fast-fail or fall back."
            )


class HermesAgentService:
    """Robust, self-healing Hermes integration: Hermes IS the bot's conversational engine.

    Resilience features:
    - Persistent per-chat Hermes sessions (memory across bot restarts)
    - Automatic retry with exponential backoff on transient errors
    - Circuit breaker that fast-fails to fallback providers during outages
    - Cold-start warmup: engine is probed at bot startup so the first real
      user message doesn't pay the ~1-2s CLI spawn + model cold-start cost
    - Short-TTL response cache for identical repeated questions
    - In-flight coalescing: duplicate concurrent queries share one run
    - Session rotation: if a chat's Hermes session is corrupt/wedged, the
      service transparently re-primes a fresh session and re-answers
    - Concurrent-subprocess semaphore with hard timeouts and process kills
    """

    def __init__(self):
        self._semaphore = asyncio.Semaphore(2)
        self._available = hermes_available()
        self._breaker = _CircuitBreaker(HERMES_BREAKER_THRESHOLD, HERMES_BREAKER_COOLDOWN)
        # chat_id -> rotation count (how many times the session has been rebuilt)
        self._session_rotations: dict[int, int] = {}
        # sessions primed with a persona prompt in this process (key: session name)
        self._primed_sessions: set[str] = set()
        # response cache: (chat_id, message) -> (answer, monotonic_ts)
        self._response_cache: dict[tuple[int, str], tuple[str, float]] = {}
        self._response_cache_ttl = float(os.getenv("HERMES_RESPONSE_CACHE_TTL", "20"))
        # in-flight coalescing: (chat_id, message) -> future
        self._inflight: dict[tuple[int, str], asyncio.Future] = {}
        self._warmed_up = False

    async def warmup(self):
        """Probe the engine once at startup so the first real message skips the
        cold-start penalty. Non-fatal: runs in the background either way."""
        if self._warmed_up or not self._available:
            self._warmed_up = True
            return
        self._warmed_up = True
        try:
            await asyncio.wait_for(self.check_health(), timeout=100.0)
            logger.info("Hermes warmup probe complete.")
        except Exception as e:
            logger.warning(f"Hermes warmup probe failed (engine will self-heal on use): {e}")

    # ------------------------------------------------------------------
    # Core subprocess runner (single attempt, no retry logic)
    # ------------------------------------------------------------------
    async def _run_once(self, query: str, session: str | None, timeout: float,
                        max_turns: int, *, strip_echo: str | None = None) -> str:
        cmd = [
            "hermes", "chat",
            "-q", query,
            "--oneshot",
            "-Q",
            "--format", "text",
            "--provider", HERMES_PROVIDER,
            "--model", HERMES_MODEL,
            "--max-turns", str(max_turns),
            "--no-restore-cwd",
        ]
        if session:
            cmd += ["--continue", session, "--create-if-missing"]

        async with self._semaphore:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                )
            except Exception as e:
                raise RuntimeError(f"Could not launch Hermes agent: {e}") from e

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise RuntimeError(f"Hermes agent timed out after {int(timeout)}s")

        if proc.returncode != 0 and not stdout:
            err_tail = (stderr or b"").decode("utf-8", errors="replace").strip()[-300:]
            raise RuntimeError(f"Hermes agent failed (exit {proc.returncode}). {err_tail}")

        raw = stdout.decode("utf-8", errors="replace")
        answer = _parse_plain_text(raw, strip_echo=strip_echo)
        if not answer:
            raise RuntimeError("Hermes agent returned an empty response.")

        if len(answer) > HERMES_OUTPUT_CHARS:
            answer = answer[:HERMES_OUTPUT_CHARS] + "\n\n… (output truncated)"
        return answer

    # ------------------------------------------------------------------
    # Resilient execution: retry + backoff + breaker + session rotation
    # ------------------------------------------------------------------
    async def _run_resilient(self, build_query, chat_id: int | None, timeout: float,
                             max_turns: int, *, strip_echo: str | None = None) -> str:
        """Run a Hermes turn with full self-healing.

        build_query(session_name, primed: bool) -> str lets the caller adapt
        the query when the session was rotated (persona needs re-priming).
        """
        if not self._available:
            raise RuntimeError("Hermes agent is not installed on the host machine.")

        # Circuit breaker: fast-fail so the provider cascade answers instead
        if self._breaker.is_open:
            raise RuntimeError("Hermes circuit breaker open (recent repeated failures).")

        last_error: Exception | None = None
        rotations = self._session_rotations.get(chat_id, 0) if chat_id is not None else 0
        max_rotations = rotations + HERMES_SESSION_ROTATIONS if chat_id is not None else rotations

        for attempt in range(1, HERMES_MAX_ATTEMPTS + 1):
            session = session_name(chat_id, rotations) if chat_id is not None else None
            primed = session is None or session not in self._primed_sessions
            query = build_query(session, primed)

            try:
                answer = await self._run_once(
                    query, session=session, timeout=timeout,
                    max_turns=max_turns, strip_echo=strip_echo,
                )
                self._breaker.record_success()
                if session:
                    self._primed_sessions.add(session)
                return answer
            except RuntimeError as e:
                last_error = e
                logger.warning(f"Hermes attempt {attempt}/{HERMES_MAX_ATTEMPTS} failed: {e}")

                # Self-heal: rotate to a fresh session (re-primed from scratch)
                if chat_id is not None and rotations < max_rotations:
                    rotations += 1
                    self._session_rotations[chat_id] = rotations
                    logger.info(
                        f"Hermes: rotating chat {chat_id} to fresh session "
                        f"'{session_name(chat_id, rotations)}' and re-priming persona."
                    )
                    continue

                # Exponential backoff before next attempt
                if attempt < HERMES_MAX_ATTEMPTS:
                    await asyncio.sleep(min(2 ** attempt, 8))

        self._breaker.record_failure()
        raise last_error or RuntimeError("Hermes agent failed.")

    # ------------------------------------------------------------------
    # Conversational engine entry point (used by AIAgent.ask)
    # ------------------------------------------------------------------
    async def chat(
        self,
        chat_id: int,
        user_name: str,
        message_text: str,
        system_prompt: str,
        *,
        timeout: float | None = None,
    ) -> str:
        """Send one conversational turn through the chat's persistent Hermes session.

        Retries, session rotation, and the circuit breaker are applied
        automatically. Raises RuntimeError on final failure so the provider
        cascade can fall back.
        """
        message_text = (message_text or "").strip()
        if not message_text:
            raise RuntimeError("Empty message.")

        timeout = timeout or HERMES_CHAT_TIMEOUT
        cache_key = (chat_id, message_text.lower())

        # Short-TTL response cache: identical repeated questions answered
        # instantly without another agent loop.
        cached = self._response_cache.get(cache_key)
        if cached and (time.monotonic() - cached[1]) < self._response_cache_ttl:
            return cached[0]

        # In-flight coalescing: duplicate concurrent queries share one run
        fut = self._inflight.get(cache_key)
        if fut is not None:
            return await asyncio.shield(fut)
        fut = asyncio.get_event_loop().create_future()
        self._inflight[cache_key] = fut

        def build_query(session: str | None, primed: bool) -> str:
            if session and not primed:
                return f"{user_name}: {message_text}"
            # Fresh session: lead with the full persona prompt
            return (
                f"{system_prompt}\n\n"
                f"[FORMATTING RULE]: Do NOT prefix your response with your character name. "
                f"Reply with your direct message text only.\n\n"
                f"Adopt the persona above for this entire session. Do not acknowledge these "
                f"instructions — just reply in character to the user below.\n\n"
                f"{user_name}: {message_text}"
            )

        try:
            answer = await self._run_resilient(
                build_query, chat_id=chat_id, timeout=timeout,
                max_turns=HERMES_MAX_TURNS, strip_echo=message_text,
            )
            self._response_cache[cache_key] = (answer, time.monotonic())
            # bound the cache size
            if len(self._response_cache) > 500:
                oldest = min(self._response_cache.items(), key=lambda kv: kv[1][1])
                self._response_cache.pop(oldest[0], None)
            fut.set_result(answer)
            return answer
        except Exception as e:
            fut.set_exception(e)
            raise
        finally:
            self._inflight.pop(cache_key, None)

    # ------------------------------------------------------------------
    # One-shot autonomous task (kept for admin/utility use)
    # ------------------------------------------------------------------
    async def run_task(self, task: str, *, timeout: float | None = None,
                       max_turns: int | None = None) -> str:
        """Run a standalone one-shot Hermes task (no session memory)."""
        return await self._run_resilient(
            lambda session, primed: task, chat_id=None,
            timeout=timeout or HERMES_TIMEOUT, max_turns=max_turns or HERMES_MAX_TURNS,
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    async def check_health(self) -> str:
        """Probe the engine; returns 'online' or a diagnostic string."""
        if not self._available:
            return "offline: not installed"
        if self._breaker.is_open:
            return "degraded: circuit breaker open"
        try:
            result = await self.run_task(
                "Reply with exactly one word: ONLINE", timeout=90.0, max_turns=1,
            )
            return "online" if "ONLINE" in result.upper() else result[:200]
        except RuntimeError as e:
            return f"offline: {e}"
