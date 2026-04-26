import asyncio
import json
import os
import random
import re
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from .models import CharacterProfile
from .tts.base import SynthesisResult, TTSProvider, VoiceSpec


class ScriptResult(list):
    """
    A list subclass that holds script segments but also provides
    a 'blocks' view for cinematic grouping.
    """

    @property
    def blocks(self) -> list[dict]:
        """Groups segments into blocks based on mood_shifts."""
        blocks = []
        # Default initial mood if none provided
        current_block = {
            "mood_info": {
                "type": "mood_shift",
                "mood": "peaceful",
                "tags": ["peaceful"],
                "visual_prompt": "",  # Empty to avoid spurious image generation
                "vfx": [],
                "transition": "fade",
                "intensity": 0.5,
                "duration": 1000,
            },
            "segments": [],
        }

        has_started = False
        for item in self:
            if item.get("type") == "mood_shift":
                if not has_started:
                    # First mood shift replaces the default
                    current_block["mood_info"] = item
                    has_started = True
                else:
                    if current_block["segments"]:
                        blocks.append(current_block)
                    current_block = {"mood_info": item, "segments": []}
            else:
                current_block["segments"].append(item)

        if current_block["segments"]:
            blocks.append(current_block)
        return blocks

    def __getitem__(self, key):
        if isinstance(key, str) and key == "blocks":
            return self.blocks
        return super().__getitem__(key)


class _MissingScriptError(ValueError):
    """Raised when step-1 returns reasoning but no 'script' key. Triggers escalation after retries."""

    def __init__(self, reasoning: dict):
        super().__init__("Response has 'reasoning' but missing 'script' key")
        self.reasoning = reasoning


class OpenAIParser:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("VVR_API_KEY")
        self.base_url = base_url or os.getenv("VVR_BASE_URL")
        self.model = os.getenv("VVR_MODEL")
        self.think_model = os.getenv("VVR_THINK_MODEL") or self.model
        self.format_model = os.getenv("VVR_FORMAT_MODEL") or self.model

        if not self.api_key or not self.base_url:
            logger.warning("VVR_API_KEY or VVR_BASE_URL not found in environment variables. OpenAIParser may fail.")

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    def _load_prompt(self, prompt_name: str = "audio_drama_script.md") -> str:
        """Loads a prompt from the prompts directory."""
        try:
            prompt_path = os.path.join(os.path.dirname(__file__), "prompts", prompt_name)
            if os.path.exists(prompt_path):
                with open(prompt_path, encoding="utf-8") as f:
                    return f.read().strip()
            else:
                logger.warning(f"Prompt file not found: {prompt_path}. Using fallback instructions.")
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_name}: {e}")

        # Fallback in case of error
        return "You are an expert scriptwriter for audio dramas. Convert web novel text to JSON script format."

    def _append_parser_context(
        self,
        prompt: str,
        known_characters: list[CharacterProfile] | None = None,
        bgm_moods: list[str] | None = None,
    ) -> str:
        """Append optional parser context shared by all prompt paths."""
        if known_characters:
            prompt += "\n## Known Characters (Context)\n"
            for p in known_characters:
                aliases_str = ", ".join(p.aliases) if p.aliases else "None"
                prompt += f"- **{p.name}** (Gender: {p.gender}): Aliases: {aliases_str}\n"

        if bgm_moods:
            normalized_moods = [str(mood).strip() for mood in bgm_moods if str(mood).strip()]
            if normalized_moods:
                prompt += "\n## Available BGM Moods\n"
                prompt += f"Choose mood_shift.tags strictly from: {json.dumps(normalized_moods, ensure_ascii=False)}\n"

        return prompt

    def _normalize_script_items(self, items: list[dict]) -> list[dict]:
        """Normalize parsed script items for backward-compatible downstream consumption."""
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "mood_shift":
                tags = item.get("tags")
                if tags is None:
                    tags = []
                elif not isinstance(tags, list):
                    tags = [str(tags)]
                mood = item.get("mood")
                if not mood and tags:
                    mood = str(tags[0])
                elif mood and not tags:
                    tags = [str(mood)]
                item["tags"] = tags
                item["mood"] = mood
                if "visual_prompt" not in item:
                    item["visual_prompt"] = ""
                if "vfx" not in item:
                    item["vfx"] = []
                elif isinstance(item["vfx"], str):
                    item["vfx"] = [item["vfx"]]
                if "transition" not in item:
                    item["transition"] = "fade"
                if "intensity" not in item:
                    item["intensity"] = 0.5
                if "duration" not in item:
                    item["duration"] = 1000
            elif item.get("type") == "segment":
                raw = item.get("overlap_with_previous")
                if isinstance(raw, str):
                    item["overlap_with_previous"] = raw.lower() in ("true", "1", "yes")
                elif isinstance(raw, bool):
                    item["overlap_with_previous"] = raw
                elif isinstance(raw, (int, float)):
                    item["overlap_with_previous"] = bool(raw)
                else:
                    item["overlap_with_previous"] = False
        return items

    def _chunk_text(self, text: str, max_chunk_size: int = 30000) -> list[str]:
        """Split text into chunks of at most max_chunk_size characters."""
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_size = 0

        for line in text.splitlines():
            if current_size + len(line) > max_chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_size = 0
            current_chunk.append(line)
            current_size += len(line) + 1

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def _check_ambiguity(self, reasoning: dict) -> bool:
        """
        Returns True if this chunk needs escalation.

        Primary checks (structured fields):
        - confidence == "low"
        - needs_escalation == True
        - ambiguous_lines is non-empty after normalization AND longer than 40 chars

        Fallback keyword scan on speaker_map + ambiguous_lines (NOT mood_analysis):
        - Used when structured fields are missing or malformed
        """
        _EMPTY_MARKERS = {"", "none", "n/a", "không có"}
        _KEYWORD_PATTERN = re.compile(
            r"\b(unclear|ambiguous|not sure|cannot determine|unknown speaker|likely|probably|"
            r"assumed|i inferred|hard to tell|không chắc|không rõ|không xác định|tôi đoán|dường như)\b",
            re.IGNORECASE,
        )

        # ── Primary checks ──────────────────────────────────────────────────────
        confidence = reasoning.get("confidence")
        if isinstance(confidence, str) and confidence.lower() == "low":
            return True

        if reasoning.get("needs_escalation") is True:
            return True

        raw_ambiguous = reasoning.get("ambiguous_lines", "")
        if raw_ambiguous is None:
            raw_ambiguous = ""
        normalized = str(raw_ambiguous).strip().lower()
        if normalized not in _EMPTY_MARKERS and len(str(raw_ambiguous).strip()) > 40:
            return True

        # ── Fallback: keyword scan ───────────────────────────────────────────────
        # Only scan if primary structured fields are missing/malformed
        has_confidence = isinstance(confidence, str) and confidence.lower() in ("high", "medium", "low")
        has_needs_escalation = isinstance(reasoning.get("needs_escalation"), bool)

        if not has_confidence or not has_needs_escalation:
            for field in ("speaker_map", "ambiguous_lines"):
                text = str(reasoning.get(field, "") or "")
                if _KEYWORD_PATTERN.search(text):
                    return True

        return False

    async def _escalate_chunk(
        self,
        chunk: str,
        known_characters: list[CharacterProfile] | None = None,
        original_reasoning: dict | None = None,
        bgm_moods: list[str] | None = None,
    ) -> tuple[list[dict], dict, bool, str]:
        """
        Two-step escalation path.
        Step 2a: free-prose analysis (audio_drama_think.md)
        Step 2b: format-only call (audio_drama_format.md)

        Each step retries independently (MAX_RETRIES).
        Returns (segments, original_reasoning, escalated=True, raw_prose).
        original_reasoning is preserved from step-1 for debugging purposes.
        """
        MAX_RETRIES = 3

        think_prompt = self._load_prompt("audio_drama_think.md")
        think_prompt = self._append_parser_context(think_prompt, known_characters, bgm_moods)

        # ── Step 2a: free-prose reasoning ──────────────────────────────────────
        raw_prose: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Escalation Step 2a (attempt {attempt}/{MAX_RETRIES})...")
                resp = await self.client.chat.completions.create(
                    model=self.think_model or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": think_prompt},
                        {"role": "user", "content": f"Chapter Text Segment:\n{chunk}"},
                    ],
                    temperature=0.7,
                )
                if not resp or not resp.choices:
                    raise ValueError("Empty response from think model")
                raw_prose = resp.choices[0].message.content or ""
                break
            except Exception as e:
                logger.error(f"Step 2a attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(f"Step 2a exhausted {MAX_RETRIES} retries") from e

        # ── Step 2b: format only ────────────────────────────────────────────────
        format_prompt = self._load_prompt("audio_drama_format.md")
        format_prompt = self._append_parser_context(format_prompt, known_characters, bgm_moods)

        segments: list[dict] = []
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Escalation Step 2b (attempt {attempt}/{MAX_RETRIES})...")
                user_content = f"## Original Text\n{chunk}\n\n## Prose Analysis\n{raw_prose}"
                resp2 = await self.client.chat.completions.create(
                    model=self.format_model or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": format_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )
                if not resp2 or not resp2.choices:
                    raise ValueError("Empty response from format model")
                content = resp2.choices[0].message.content or ""

                # JSON sanity fix
                content = re.sub(r'(:[ \t]*"(?:[^"\\]|\\.)*")\s*(")', r"\1, \2", content)
                content = re.sub(r"(})\s*({)", r"\1, \2", content)
                content = re.sub(r",\s*([}\]])", r"\1", content)

                data = json.loads(content)
                script_part = data.get("script", []) if isinstance(data, dict) else data
                if not isinstance(script_part, list):
                    raise ValueError(f"Expected list in 'script', got {type(script_part)}")
                segments = script_part
                break
            except Exception as e:
                logger.error(f"Step 2b attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(f"Step 2b exhausted {MAX_RETRIES} retries") from e

        self._normalize_script_items(segments)

        return segments, original_reasoning or {}, True, raw_prose or ""

    async def _parse_chunk(
        self,
        chunk: str,
        known_characters: list[CharacterProfile] | None = None,
        bgm_moods: list[str] | None = None,
    ) -> tuple[list[dict], dict, bool, str | None]:
        """
        Parse a single chunk via scratchpad call (Step 1).

        Kill switch: if VVR_DISABLE_SCRATCHPAD=1, uses legacy prompt,
        returns (segments, {}, False, None) without reasoning or escalation.

        Returns: (segments, reasoning, escalated, raw_prose)
        """
        # ── Kill switch ──────────────────────────────────────────────────────────
        if os.getenv("VVR_DISABLE_SCRATCHPAD") == "1":
            system_instruction = self._load_prompt("audio_drama_script_legacy.md")
            system_instruction = self._append_parser_context(system_instruction, known_characters, bgm_moods)

            response = await self.client.chat.completions.create(
                model=self.model or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Chapter Text Segment:\n{chunk}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.9,
            )
            if not response or not hasattr(response, "choices") or not response.choices:
                raise ValueError("Invalid or empty response from OpenAI")
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty content in response")

            content = re.sub(r'(:[ \t]*"(?:[^"\\]|\\.)*")\s*(")', r"\1, \2", content)
            content = re.sub(r"(})\s*({)", r"\1, \2", content)
            content = re.sub(r",\s*([}\]])", r"\1", content)

            data = json.loads(content)
            script_part = data if isinstance(data, list) else data.get("script", [])
            if not isinstance(script_part, list):
                raise ValueError(f"Expected list, got {type(script_part)}")

            self._normalize_script_items(script_part)

            return script_part, {}, False, None

        # ── Scratchpad path ──────────────────────────────────────────────────────
        system_instruction = self._load_prompt("audio_drama_script.md")
        system_instruction = self._append_parser_context(system_instruction, known_characters, bgm_moods)

        response = await self.client.chat.completions.create(
            model=self.model or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Chapter Text Segment:\n{chunk}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
        )
        if not response or not hasattr(response, "choices") or not response.choices:
            raise ValueError("Invalid or empty response from OpenAI")

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty content in response")

        content = re.sub(r'(:[ \t]*"(?:[^"\\]|\\.)*")\s*(")', r"\1, \2", content)
        content = re.sub(r"(})\s*({)", r"\1, \2", content)
        content = re.sub(r",\s*([}\]])", r"\1", content)

        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict response, got {type(data)}")

        reasoning = data.get("reasoning")
        script_part = data.get("script")

        # ── Malformed: reasoning missing or not a dict ──────────────────────────
        if not isinstance(reasoning, dict):
            logger.warning("Step 1 'reasoning' is missing or not a dict — escalating.")
            return await self._escalate_chunk(
                chunk,
                known_characters,
                original_reasoning=None,
                bgm_moods=bgm_moods,
            )

        # ── Script missing: raise so parse_chapter retry loop catches it ─────────
        if script_part is None:
            raise _MissingScriptError(reasoning)

        if not isinstance(script_part, list):
            raise ValueError(f"Expected list in 'script', got {type(script_part)}")

        # ── Empty script: valid (narration-only chunk) ───────────────────────────
        if len(script_part) == 0:
            return [], reasoning, False, None

        self._normalize_script_items(script_part)

        # ── Ambiguity check ──────────────────────────────────────────────────────
        if self._check_ambiguity(reasoning):
            logger.info("Ambiguity detected — escalating chunk to 2-step path.")
            return await self._escalate_chunk(
                chunk,
                known_characters,
                original_reasoning=reasoning,
                bgm_moods=bgm_moods,
            )

        return script_part, reasoning, False, None

    async def parse_chapter(
        self,
        text: str,
        known_characters: list[CharacterProfile] | None = None,
        output_prefix: str | None = None,
        bgm_moods: list[str] | None = None,
    ) -> ScriptResult:
        """
        Parses chapter text into a ScriptResult using the scratchpad pipeline.
        Writes sidecar files to output_prefix after all chunks processed.

        output_prefix=None disables sidecar writes (backward compatible).
        """
        if not text or not text.strip():
            return ScriptResult([])

        chunks = self._chunk_text(text)
        full_script: list[dict] = []
        chunk_results: list[tuple[int, bool, dict, str | None]] = []
        # chunk_results: [(index, escalated, reasoning, raw_prose), ...]

        for i, chunk in enumerate(chunks):
            retries = 0
            MAX_RETRIES = 3  # 1 initial + 2 retries

            while retries < MAX_RETRIES:
                retries += 1
                try:
                    logger.info(f"Parsing chunk {i + 1}/{len(chunks)} (Attempt {retries}/{MAX_RETRIES})...")
                    segments, reasoning, escalated, raw_prose = await self._parse_chunk(
                        chunk,
                        known_characters=known_characters,
                        bgm_moods=bgm_moods,
                    )
                    full_script.extend(segments)
                    chunk_results.append((i, escalated, reasoning, raw_prose))
                    break
                except _MissingScriptError as e:
                    logger.warning(f"Chunk {i + 1}: missing 'script' key (Attempt {retries}/{MAX_RETRIES})")
                    if retries < MAX_RETRIES:
                        await asyncio.sleep(2)
                    else:
                        logger.warning(f"Chunk {i + 1}: missing 'script' exhausted retries — escalating.")
                        segments, reasoning, escalated, raw_prose = await self._escalate_chunk(
                            chunk,
                            known_characters,
                            original_reasoning=e.reasoning,
                            bgm_moods=bgm_moods,
                        )
                        full_script.extend(segments)
                        chunk_results.append((i, escalated, reasoning, raw_prose))
                        break
                except Exception as e:
                    logger.error(f"Error parsing chunk {i + 1} (Attempt {retries}/{MAX_RETRIES}): {e}")
                    if retries < MAX_RETRIES:
                        await asyncio.sleep(2)
                    else:
                        logger.error(f"Chunk {i + 1} failed after {MAX_RETRIES} attempts.")
                        raise RuntimeError(
                            f"Failed to parse chapter chunk {i + 1} after {MAX_RETRIES} attempts."
                        ) from e

        # ── Sidecar file writes (kill switch: skip when disabled) ────────────────
        if output_prefix and os.getenv("VVR_DISABLE_SCRATCHPAD") != "1":
            # Always write reasoning.json
            reasoning_data = {
                "chunks": [
                    {
                        "index": idx,
                        "escalated": escalated,
                        "reasoning": reasoning,
                    }
                    for idx, escalated, reasoning, _ in chunk_results
                ]
            }
            reasoning_path = f"{output_prefix}.script.reasoning.json"
            try:
                with open(reasoning_path, "w", encoding="utf-8") as f:
                    json.dump(reasoning_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved reasoning sidecar to {reasoning_path}")
            except Exception as e:
                logger.warning(f"Failed to write reasoning sidecar: {e}")

            # Write raw.md only if at least one chunk escalated
            escalated_chunks = [(idx, raw_prose) for idx, escalated, _, raw_prose in chunk_results if escalated]
            if escalated_chunks:
                raw_md_path = f"{output_prefix}.script.raw.md"
                try:
                    lines = []
                    for idx, raw_prose in escalated_chunks:
                        lines.append(f"## Chunk {idx + 1}\n")  # 1-based
                        lines.append(f"{raw_prose}\n")
                    with open(raw_md_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines))
                    logger.info(f"Saved raw prose sidecar to {raw_md_path}")
                except Exception as e:
                    logger.warning(f"Failed to write raw prose sidecar: {e}")

        return ScriptResult(full_script)


def _infer_tags_from_character(character_name: str) -> list[str]:
    """Infer community voice tags from a character name. MVP keyword matching."""
    name = character_name.lower()
    tags = []
    if any(k in name for k in ("loli", "nhóc", "bé", "con nít", "trẻ con")):
        tags.append("child")
    if any(k in name for k in ("ông", "bà", "lão", "già", "cụ")):
        tags.append("elder")
    if "tsun" in name:
        tags.append("tsundere")
    if any(k in name for k in ("yandere", "điên", "psycho")):
        tags.append("yandere")
    if any(k in name for k in ("chúa", "vua", "hoàng đế", "lord")):
        tags.append("noble")
    return tags


class VoiceManager:
    """Manages voice assignment for characters. Delegates synthesis to TTSProvider."""

    DEFAULT_NARRATOR_VOICE_ID = "ywBZEqUhld86Jeajq94o"

    _global_available_voices = None
    _global_voice_metadata = {}
    _global_init_lock = asyncio.Lock()

    def __init__(self, db, story_id: str, provider: TTSProvider | None = None, voice_bank_db=None):
        self._provider = provider
        self.db = db
        self.story_id = story_id
        self._voice_cache = {}  # char_name -> VoiceSpec
        self._profile_cache = {}
        self._initialized = False
        self._instance_lock = asyncio.Lock()
        self._voice_bank_db = voice_bank_db  # Injected VoiceBankDatabaseManager (optional)

        # Build narrator voice from env config
        narrator_ref = os.getenv("VVR_NARRATOR_REF_AUDIO")
        if narrator_ref:
            self.narrator_voice = VoiceSpec(ref_audio_path=narrator_ref)
        else:
            narrator_id = os.getenv("VVR_NARRATOR_VOICE_ID", self.DEFAULT_NARRATOR_VOICE_ID)
            self.narrator_voice = VoiceSpec(voice_id=narrator_id)

        self._cached_available_voices = []
        self._cached_voice_metadata = {}
        self._closed = False

    async def close(self):
        """Closes resources."""
        if self._closed:
            return
        self._closed = True
        logger.debug("VoiceManager closed.")

    async def _init_cache(self):
        if self._initialized:
            return

        # 1. Load existing assignments and profiles from DB
        if hasattr(self.db, "get_all_story_voices"):
            db_voices = await self.db.get_all_story_voices(self.story_id)
            for k, v in db_voices.items():
                self._voice_cache[k.lower()] = VoiceSpec(voice_id=v)

        if hasattr(self.db, "get_character_profiles"):
            profiles = await self.db.get_character_profiles(self.story_id)
            for p in profiles:
                self._profile_cache[p.name.lower()] = p
                # Build VoiceSpec from profile
                if p.ref_audio_path:
                    self._voice_cache[p.name.lower()] = VoiceSpec(ref_audio_path=p.ref_audio_path, ref_text=p.ref_text)
                elif p.voice_id:
                    self._voice_cache[p.name.lower()] = VoiceSpec(voice_id=p.voice_id)

        # 2. Fetch voices (using global cache) — from provider or ElevenLabs legacy
        # Double-check locking: first check without lock (fast path), then re-check with lock
        if VoiceManager._global_available_voices is None:
            async with self._global_init_lock:
                # Re-check after acquiring lock to handle race condition
                if VoiceManager._global_available_voices is None:
                    if self._provider is not None:
                        # Use the provider's voice discovery
                        try:
                            voices = await self._provider.discover_voices()
                            VoiceManager._global_available_voices = [v.voice_id for v in voices if v.voice_id]
                            VoiceManager._global_voice_metadata = {
                                v.voice_id: {
                                    "name": v.name,
                                    "gender": v.gender.lower() if v.gender else "unknown",
                                    "labels": v.labels,
                                }
                                for v in voices
                                if v.voice_id
                            }
                            logger.info(f"Fetched {len(voices)} voices from provider.")
                        except Exception as e:
                            logger.warning(f"Failed to discover voices from provider: {e}")
                            VoiceManager._global_available_voices = []
                            VoiceManager._global_voice_metadata = {}
                    else:
                        # Legacy ElevenLabs path
                        api_key = os.getenv("ELEVENLABS_API_KEY")
                        if not api_key:
                            logger.warning("ELEVENLABS_API_KEY missing, using fallback empty voice list")
                            VoiceManager._global_available_voices = []
                        else:
                            try:
                                from elevenlabs.client import ElevenLabs

                                client = ElevenLabs(api_key=api_key)

                                def fetch_voices():
                                    return client.voices.get_all().voices

                                voices = await asyncio.to_thread(fetch_voices)
                                VoiceManager._global_available_voices = [v.voice_id for v in voices]
                                VoiceManager._global_voice_metadata = {
                                    v.voice_id: {
                                        "name": v.name,
                                        "gender": v.labels.get("gender", "unknown").lower() if v.labels else "unknown",
                                        "labels": v.labels if v.labels else {},
                                    }
                                    for v in voices
                                }
                                logger.info(f"Fetched {len(voices)} voices from ElevenLabs.")
                            except Exception as e:
                                logger.error(f"Failed to fetch ElevenLabs voices: {e}")
                                VoiceManager._global_available_voices = []

                # Always cache the global state (inside lock, after potential init)
                self._cached_available_voices = VoiceManager._global_available_voices
                self._cached_voice_metadata = VoiceManager._global_voice_metadata
        else:
            # Fast path: global already initialized, just cache it
            self._cached_available_voices = VoiceManager._global_available_voices
            self._cached_voice_metadata = VoiceManager._global_voice_metadata

        self._initialized = True

    async def get_known_characters(self) -> list[CharacterProfile]:
        """Returns all known character profiles for this story."""
        await self._init_cache()
        return list(self._profile_cache.values())

    async def reload_cache(self) -> None:
        """Reload DB-backed story voice/profile caches for this manager instance."""
        async with self._instance_lock:
            self._voice_cache.clear()
            self._profile_cache.clear()
            self._initialized = False
            await self._init_cache()

    async def get_voice(self, character_name: str | None, gender: str = "unknown") -> VoiceSpec:
        """Resolve character -> VoiceSpec."""
        if not character_name:
            return self.narrator_voice

        char_normalized = character_name.lower().strip()
        if char_normalized == "narrator":
            return self.narrator_voice

        async with self._instance_lock:
            await self._init_cache()

            # Check cache
            if char_normalized in self._voice_cache:
                return self._voice_cache[char_normalized]

            # Check profile cache
            if char_normalized in self._profile_cache:
                profile = self._profile_cache[char_normalized]
                if profile.ref_audio_path:
                    spec = VoiceSpec(ref_audio_path=profile.ref_audio_path, ref_text=profile.ref_text)
                    self._voice_cache[char_normalized] = spec
                    return spec
                if profile.voice_id:
                    spec = VoiceSpec(voice_id=profile.voice_id)
                    self._voice_cache[char_normalized] = spec
                    return spec

            # 3. Community Voice Bank lookup
            voice_bank_db = None
            try:
                from vvr_scraper.utils import get_config_path
                from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager
                from vvr_scraper.voice_bank.storage import get_voice_bank_dir

                # Use injected DB instance if available, otherwise create new (backward compatibility)
                if self._voice_bank_db is not None:
                    voice_bank_db = self._voice_bank_db
                else:
                    voice_bank_db = VoiceBankDatabaseManager(db_path=get_config_path("voice_bank.db"))
                    await voice_bank_db.init_db()

                community_voice = await voice_bank_db.find_best_voice(
                    gender=gender.lower(),
                    tags=_infer_tags_from_character(character_name),
                )
                if community_voice:
                    canonical_path = os.path.join(get_voice_bank_dir(), community_voice["ref_audio_path"])
                    spec = VoiceSpec(
                        ref_audio_path=canonical_path,
                        ref_text=community_voice["ref_text"],
                    )
                    self._voice_cache[char_normalized] = spec
                    await voice_bank_db.increment_usage(community_voice["id"])
                    return spec
            except Exception as e:
                logger.debug(f"Community voice bank lookup failed (non-fatal): {e}")
            finally:
                # Only close if we created a new instance (backward compatibility)
                if voice_bank_db is not None and self._voice_bank_db is None:
                    await voice_bank_db.close()

            # Auto-assign from available voices (ElevenLabs legacy path)
            available_ids = self._cached_available_voices
            assigned_ids = {v.voice_id for v in self._voice_cache.values() if v.voice_id}
            candidate_ids = [
                vid for vid in available_ids if vid != self.narrator_voice.voice_id and vid not in assigned_ids
            ]

            if not candidate_ids:
                candidate_ids = [vid for vid in available_ids if vid != self.narrator_voice.voice_id]

            if not candidate_ids:
                assigned_voice = self.narrator_voice
            else:
                gender_candidates = [
                    vid for vid in candidate_ids if self._cached_voice_metadata.get(vid, {}).get("gender") == gender
                ]
                final_pool = gender_candidates if gender_candidates else candidate_ids
                chosen_id = random.choice(final_pool)  # noqa: S311
                assigned_voice = VoiceSpec(voice_id=chosen_id)

            # Save to profile and DB
            profile = self._profile_cache.get(char_normalized)
            if not profile:
                profile = CharacterProfile(
                    name=character_name.strip(),
                    story_id=self.story_id,
                    gender=gender,
                )
                self._profile_cache[char_normalized] = profile

            if assigned_voice.voice_id:
                profile.voice_id = assigned_voice.voice_id
            if gender != "unknown" and profile.gender == "unknown":
                profile.gender = gender

            self._voice_cache[char_normalized] = assigned_voice

            if hasattr(self.db, "save_character_profile"):
                await self.db.save_character_profile(profile)

            return assigned_voice

    def resolve_aliases(self, script_segments: list[dict]) -> list[dict]:
        """NLP-based alias resolution for script segments."""
        alias_map = {}
        for p in self._profile_cache.values():
            for alias in p.aliases:
                alias_map[alias.lower().strip()] = p.name

        for seg in script_segments:
            role = seg.get("role")
            if not role or role.lower() == "narrator":
                continue
            role_normalized = role.lower().strip()
            if role_normalized in alias_map:
                seg["role"] = alias_map[role_normalized]

        return script_segments

    async def synthesize(self, voice: VoiceSpec, text: str, **kwargs: Any) -> SynthesisResult:
        """Delegate synthesis to provider. Provider is required."""
        if not self._provider:
            raise ValueError("VoiceManager requires a TTSProvider. Legacy path removed.")
        return await self._provider.synthesize(text, voice)
