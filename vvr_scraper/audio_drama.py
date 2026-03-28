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
        
        if not self.api_key or not self.base_url:
            logger.warning("VVR_API_KEY or VVR_BASE_URL not found in environment variables. OpenAIParser may fail.")
            
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def parse_chapter(self, text: str) -> List[Dict[str, str]]:
        """
        Parses chapter text into a list of dialogue/narrator segments using OpenAI.
        Returns: List of Dicts with 'role' and 'text'.
        """
        if not text or not text.strip():
            return []

        system_instruction = (
            "You are an expert scriptwriter for audio dramas. "
            "Your task is to convert a web novel chapter into a structured script. "
            "Identify all dialogue and the character speaking. Everything else is 'narrator'. "
            "Combine consecutive segments by the same character. "
            "Output MUST be a JSON list of objects, each with 'role' and 'text'. "
            "Example: [{\"role\": \"narrator\", \"text\": \"Once upon a time...\"}, {\"role\": \"Hero\", \"text\": \"Hello!\"}]"
        )
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini", # Default fast model, can be overridden if needed
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
    DEFAULT_VOICES = ["Hung", "Mai", "Nam", "Linh", "Duc", "Lan", "Vinh"]
    NARRATOR_VOICE = "Tuyen"

    def __init__(self, db: DatabaseManager, story_id: str):
        self.db = db
        self.story_id = story_id

    async def get_voice(self, character_name: str) -> str:
        """
        Retrieves the voice name for a character. Narrator is always 'Tuyen'.
        Assigns a random voice if not already assigned and persists it.
        Character names are normalized (lowercased and stripped) for consistency.
        """
        if not character_name:
            return self.NARRATOR_VOICE
            
        char_normalized = character_name.lower().strip()
        if char_normalized == "narrator":
            return self.NARRATOR_VOICE

        # Check DB for existing mapping using normalized name
        voice = await self.db.get_character_voice(self.story_id, char_normalized)
        if voice:
            return voice

        # Assign new voice from pool
        voice = random.choice(self.DEFAULT_VOICES)
        await self.db.save_character_voice(self.story_id, char_normalized, voice)
        logger.info(f"Assigned voice '{voice}' to character '{char_normalized}' for story '{self.story_id}'")
        return voice
