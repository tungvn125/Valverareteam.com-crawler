import asyncio
import base64
import io
import json
import os
import random

import httpx
from loguru import logger
from openai import AsyncOpenAI

from .models import CharacterProfile
from .tts.base import TTSProvider, VoiceSpec, SynthesisResult
from typing import Any


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
                "visual_prompt": "A peaceful setting.",
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


class OpenAIParser:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("VVR_API_KEY")
        self.base_url = base_url or os.getenv("VVR_BASE_URL")
        self.model = os.getenv("VVR_MODEL")

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

    async def _parse_chunk(self, chunk: str, known_characters: list[CharacterProfile] | None = None) -> list[dict]:
        """Parses a single chunk of text into a script list."""
        system_instruction = self._load_prompt()

        if known_characters:
            char_context = "\n## Known Characters (Context)\n"
            char_context += "Use these characters for role identification and alias resolution:\n"
            for p in known_characters:
                aliases_str = ", ".join(p.aliases) if p.aliases else "None"
                char_context += f"- **{p.name}** (Gender: {p.gender}): Aliases: {aliases_str}\n"
            system_instruction += char_context

        response = await self.client.chat.completions.create(
            model=self.model or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Chapter Text Segment:\n{chunk}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        if not response or not hasattr(response, "choices") or not response.choices:
            raise ValueError("Invalid or empty response from OpenAI")

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty content in response")

        # --- JSON Sanity Fix ---
        import re

        content = re.sub(r'(:[ \t]*"(?:[^"\\]|\\.)*")\s*(")', r"\1, \2", content)
        content = re.sub(r"(})\s*({)", r"\1, \2", content)
        content = re.sub(r",\s*([}\]])", r"\1", content)
        # -----------------------

        data = json.loads(content)
        if isinstance(data, list):
            script_part = data
        elif isinstance(data, dict):
            script_part = data.get("script", [])
        else:
            raise ValueError(f"Expected list or dict, got {type(data)}")

        if not isinstance(script_part, list):
            raise ValueError(f"Expected list in 'script' key, got {type(script_part)}")

        # Normalize mood_shift objects
        for item in script_part:
            if isinstance(item, dict) and item.get("type") == "mood_shift":
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

                # New normalization (Task 1 fix)
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

        return script_part

    async def parse_chapter(self, text: str, known_characters: list[CharacterProfile] | None = None) -> ScriptResult:
        """
        Parses chapter text into a list of dialogue/narrator segments and mood shifts using OpenAI.
        Handles large chapters by chunking the text and merging the results.
        """
        if not text or not text.strip():
            return ScriptResult([])

        # Chunk the text
        max_chunk_size = 30000
        chunks = []
        current_chunk = []
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

        full_script = []

        for i, chunk in enumerate(chunks):
            retries = 0
            MAX_RETRIES = 3  # 1 initial + 2 retries

            while retries < MAX_RETRIES:
                retries += 1
                try:
                    logger.info(f"Parsing chunk {i + 1}/{len(chunks)} (Attempt {retries}/{MAX_RETRIES})...")
                    script_part = await self._parse_chunk(chunk, known_characters=known_characters)
                    full_script.extend(script_part)
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

        return ScriptResult(full_script)


class VoiceManager:
    """Manages voice assignment for characters. Delegates synthesis to TTSProvider."""

    DEFAULT_NARRATOR_VOICE_ID = "ywBZEqUhld86Jeajq94o"

    _global_available_voices = None
    _global_voice_metadata = {}
    _global_init_lock = asyncio.Lock()

    def __init__(self, db, story_id: str, provider: TTSProvider | None = None):
        self._provider = provider
        self.db = db
        self.story_id = story_id
        self._voice_cache = {}  # char_name -> VoiceSpec
        self._profile_cache = {}
        self._initialized = False
        self._instance_lock = asyncio.Lock()

        # Build narrator voice from env config
        narrator_ref = os.getenv("VVR_NARRATOR_REF_AUDIO")
        if narrator_ref:
            self.narrator_voice = VoiceSpec(ref_audio_path=narrator_ref)
        else:
            narrator_id = os.getenv("VVR_NARRATOR_VOICE_ID", self.DEFAULT_NARRATOR_VOICE_ID)
            self.narrator_voice = VoiceSpec(voice_id=narrator_id)

        self._client = httpx.AsyncClient(timeout=300.0)
        self._cached_available_voices = []
        self._cached_voice_metadata = {}

    async def close(self):
        """Closes resources."""
        await self._client.aclose()
        if self._provider and hasattr(self._provider, "close"):
            await self._provider.close()
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
                    self._voice_cache[p.name.lower()] = VoiceSpec(
                        ref_audio_path=p.ref_audio_path, ref_text=p.ref_text
                    )
                elif p.voice_id:
                    self._voice_cache[p.name.lower()] = VoiceSpec(voice_id=p.voice_id)

        # 2. Fetch ElevenLabs voices (using global cache) — only if no provider
        if self._provider is None:
            async with self._global_init_lock:
                if VoiceManager._global_available_voices is None:
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
                                }
                                for v in voices
                            }
                            logger.info(f"Fetched {len(voices)} voices from ElevenLabs.")
                        except Exception as e:
                            logger.error(f"Failed to fetch ElevenLabs voices: {e}")
                            VoiceManager._global_available_voices = []

                self._cached_available_voices = VoiceManager._global_available_voices
                self._cached_voice_metadata = VoiceManager._global_voice_metadata

        self._initialized = True

    async def get_known_characters(self) -> list[CharacterProfile]:
        """Returns all known character profiles for this story."""
        await self._init_cache()
        return list(self._profile_cache.values())

    async def get_voice(self, character_name: str, gender: str = "unknown") -> VoiceSpec:
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

            # Auto-assign from available voices (ElevenLabs legacy path)
            gender = gender.lower()
            available_ids = self._cached_available_voices
            assigned_ids = {v.voice_id for v in self._voice_cache.values() if v.voice_id}
            candidate_ids = [vid for vid in available_ids if vid != self.narrator_voice.voice_id and vid not in assigned_ids]

            if not candidate_ids:
                candidate_ids = [vid for vid in available_ids if vid != self.narrator_voice.voice_id]

            if not candidate_ids:
                assigned_voice = self.narrator_voice
            else:
                gender_candidates = [
                    vid
                    for vid in candidate_ids
                    if self._cached_voice_metadata.get(vid, {}).get("gender") == gender
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
        """Delegate synthesis to provider, or fall back to legacy ElevenLabs."""
        if self._provider:
            return await self._provider.synthesize(text, voice)

        # Legacy path: direct ElevenLabs call (backward compat when no provider)
        from .tts.base import WordAlignment

        voice_id = voice.voice_id or self.narrator_voice.voice_id
        stability = kwargs.get("stability", 0.35)
        audio_bytes, word_alignments_raw = await self._synthesize_elevenlabs_legacy(voice_id, text, stability)

        word_alignments = (
            [WordAlignment(word=w["word"], start=w["start"], end=w["end"]) for w in word_alignments_raw]
            if word_alignments_raw
            else None
        )

        duration_ms = _estimate_duration_ms_legacy(audio_bytes)
        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=44100,
            duration_ms=duration_ms,
            word_alignments=word_alignments,
        )

    async def _synthesize_elevenlabs_legacy(self, voice_id: str, text: str, stability: float):
        """Legacy ElevenLabs synthesis (backward compat when no provider)."""
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY required")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-with-timestamps"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        data = {
            "text": text,
            "model_id": "eleven_v3",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        audio_buffer = io.BytesIO()
        all_alignments = []

        async with self._client.stream("POST", url, headers=headers, json=data) as response:
            if response.status_code != 200:
                error_msg = await response.aread()
                raise Exception(f"ElevenLabs API error ({response.status_code}): {error_msg}")
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if "audio_base64" in chunk:
                        audio_buffer.write(base64.b64decode(chunk["audio_base64"]))
                    if "alignment" in chunk:
                        all_alignments.append(chunk["alignment"])
                except Exception as e:
                    logger.warning(f"Error parsing alignment chunk: {e}")

        full_audio = audio_buffer.getvalue()
        audio_buffer.close()

        word_alignments = []
        current_word_chars = []
        current_word_start = None
        last_end = 0

        for alignment in all_alignments:
            chars = alignment.get("characters", [])
            starts = alignment.get("character_start_times_seconds", [])
            ends = alignment.get("character_end_times_seconds", [])
            for char, start, end in zip(chars, starts, ends, strict=False):
                if char.isspace():
                    if current_word_chars:
                        word_text = "".join(current_word_chars)
                        word_alignments.append({"word": word_text, "start": int(current_word_start * 1000), "end": int(last_end * 1000)})
                        current_word_chars = []
                        current_word_start = None
                    continue
                if not current_word_chars:
                    current_word_start = start
                current_word_chars.append(char)
                last_end = end

        if current_word_chars:
            word_text = "".join(current_word_chars)
            word_alignments.append({"word": word_text, "start": int(current_word_start * 1000), "end": int(last_end * 1000)})

        return full_audio, word_alignments


def _estimate_duration_ms_legacy(audio_bytes: bytes) -> int:
    """Estimate audio duration from MP3 bytes."""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        return len(seg)
    except Exception:
        return int(len(audio_bytes) * 8 / 128)
