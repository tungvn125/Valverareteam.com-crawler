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
            try:
                from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager
                from vvr_scraper.voice_bank.storage import get_voice_bank_dir
                from vvr_scraper.utils import get_config_path

                voice_bank_db = VoiceBankDatabaseManager(db_path=get_config_path("voice_bank.db"))
                await voice_bank_db.init_db()
                try:
                    community_voice = await voice_bank_db.find_best_voice(
                        gender=gender.lower(),
                        tags=_infer_tags_from_character(character_name),
                    )
                    if community_voice:
                        canonical_path = os.path.join(
                            get_voice_bank_dir(), community_voice["ref_audio_path"]
                        )
                        spec = VoiceSpec(
                            ref_audio_path=canonical_path,
                            ref_text=community_voice["ref_text"],
                        )
                        self._voice_cache[char_normalized] = spec
                        await voice_bank_db.increment_usage(community_voice["id"])
                        return spec
                finally:
                    await voice_bank_db.close()
            except Exception as e:
                logger.debug(f"Community voice bank lookup failed (non-fatal): {e}")

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
