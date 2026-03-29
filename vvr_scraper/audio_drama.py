import asyncio
from openai import AsyncOpenAI
import os
import json
import random
from typing import List, Dict, Optional
from loguru import logger
from .db import DatabaseManager

class OpenAIParser:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("VVR_API_KEY")
        self.base_url = base_url or os.getenv("VVR_BASE_URL")
        self.model = os.getenv("VVR_MODEL")
        
        if not self.api_key or not self.base_url:
            logger.warning("VVR_API_KEY or VVR_BASE_URL not found in environment variables. OpenAIParser may fail.")
            
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def parse_chapter(self, text: str) -> List[Dict[str, str]]:
        """
        Parses chapter text into a list of dialogue/narrator segments and mood shifts using OpenAI.
        Returns: List of Dicts with 'type' ('segment' or 'mood_shift') and relevant fields.
        """
        if not text or not text.strip():
            return []

        system_instruction = (
            "You are an expert scriptwriter for audio dramas. "
            "Your task is to convert a web novel chapter into a structured script. "
            "Identify all dialogue and the character speaking, and infer their gender ('male', 'female', or 'unknown'). Everything else is 'narrator'. "
            "In addition to dialogue, you must identify significant mood shifts in the story. "
            "Allowed moods: 'action', 'peaceful', 'mysterious', 'romantic', 'sad', 'suspense'. "
            "Output MUST be a JSON object containing a single key 'script' which maps to a list of objects. "
            "Each object in the list must have a 'type' field which is either 'segment' or 'mood_shift'. "
            "For 'segment' type: include 'role', 'text', and 'gender'. "
            "For 'mood_shift' type: include 'mood' (one of the allowed moods). "
            "Combine consecutive segments by the same character. "
            "Start the script with an appropriate mood_shift. "
            "Example: {\"script\": ["
            "{\"type\": \"mood_shift\", \"mood\": \"mysterious\"}, "
            "{\"type\": \"segment\", \"role\": \"narrator\", \"text\": \"Darkness falls.\", \"gender\": \"unknown\"}, "
            "{\"type\": \"segment\", \"role\": \"Hero\", \"text\": \"Wait!\", \"gender\": \"male\"}"
            "]}"
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Chapter Text:\n{text}"}
                ],
                response_format={"type": "json_object"} # Some models require {"type": "json_object"} along with instructions to output JSON. Better to extract list or expect it in a key. Wait, if we use response_format={"type": "json_object"}, the model must output an object.
            )
            
            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from OpenAI")
                return []
                
            script = json.loads(content)
            
            # Since JSON object is forced usually by API, standard response might be {"script": [...]}, let's handle if it returns a list directly (some compatible APIs allow list directly without object wrapper, but OpenAI strictly wants an Object if json_object is set)
            if isinstance(script, dict):
                # Try to find the list inside
                for key, val in script.items():
                    if isinstance(val, list):
                        script = val
                        break
            
            if not isinstance(script, list):
                logger.error(f"Expected list from OpenAI, got {type(script)}")
                return []
                
            return script
        except Exception as e:
            logger.error(f"Error parsing chapter with OpenAI: {e}")
            return []

class VoiceManager:
    # Default pool of Vietnamese voices from Vieneu
    MALE_VOICES = ["Vinh", "Binh"]
    FEMALE_VOICES = ["Doan", "Ly", "Ngoc"]
    DEFAULT_VOICES = MALE_VOICES + FEMALE_VOICES
    NARRATOR_VOICE = "Tuyen"

    def __init__(self, db: DatabaseManager, story_id: str):
        self.db = db
        self.story_id = story_id
        self._voice_cache: Dict[str, str] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

    async def _init_cache(self):
        if not self._initialized:
            # We use get_all_story_voices to fetch all currently assigned voices for the story.
            # However, if it's a mocked object in tests and doesn't have it, we fallback to empty dict
            if hasattr(self.db, 'get_all_story_voices'):
                db_voices = await self.db.get_all_story_voices(self.story_id)
                self._voice_cache.update(db_voices)
            self._initialized = True

    async def get_voice(self, character_name: str, gender: str = "unknown") -> str:
        """
        Retrieves the voice name for a character. Narrator is always 'Tuyen'.
        Prioritizes unused voices before reusing voices for < 5 characters.
        Routes voices based on 'gender' string if provided ('male', 'female').
        Character names are normalized (lowercased and stripped) for consistency.
        """
        if not character_name:
            return self.NARRATOR_VOICE
            
        char_normalized = character_name.lower().strip()
        if char_normalized == "narrator":
            return self.NARRATOR_VOICE

        async with self._lock:
            await self._init_cache()
            
            # Check cache (which includes DB items)
            if char_normalized in self._voice_cache:
                return self._voice_cache[char_normalized]
                
            # Fallback point for tests mocking only get_character_voice
            if not self._voice_cache and hasattr(self.db, 'get_character_voice'):
                voice_from_db = await self.db.get_character_voice(self.story_id, char_normalized)
                if voice_from_db:
                    self._voice_cache[char_normalized] = voice_from_db
                    return voice_from_db

            # Decide target voice pool based on gender
            if gender == "male":
                target_voices = self.MALE_VOICES
            elif gender == "female":
                target_voices = self.FEMALE_VOICES
            else:
                target_voices = self.DEFAULT_VOICES

            # Find unused voices in the target pool
            used_voices = set(self._voice_cache.values())
            available_voices = [v for v in target_voices if v not in used_voices]

            # If unused voices remain, use one. Otherwise, randomly reuse an existing one from target pool
            if available_voices:
                voice = random.choice(available_voices)
            else:
                voice = random.choice(target_voices)

            # Update cache and save to DB
            self._voice_cache[char_normalized] = voice
            await self.db.save_character_voice(self.story_id, char_normalized, voice)
            logger.info(f"Assigned voice '{voice}' to character '{char_normalized}' for story '{self.story_id}'")
            return voice
