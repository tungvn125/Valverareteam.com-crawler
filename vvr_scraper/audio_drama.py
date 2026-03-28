import os
import json
import random
from typing import List, Dict, Optional
import google.generativeai as genai
from loguru import logger
from .db import DatabaseManager

class GeminiParser:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            logger.warning("Neither GEMINI_API_KEY nor GOOGLE_API_KEY found in environment variables. GeminiParser may fail.")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def parse_chapter(self, text: str) -> List[Dict[str, str]]:
        """
        Parses chapter text into a list of dialogue/narrator segments using Gemini.
        Returns: List of Dicts with 'character' and 'text'.
        """
        if not text or not text.strip():
            return []

        system_instruction = (
            "You are an expert scriptwriter for audio dramas. "
            "Your task is to convert a web novel chapter into a structured script. "
            "Identify all dialogue and the character speaking. Everything else is 'narrator'. "
            "Combine consecutive segments by the same character. "
            "Output MUST be a JSON list of objects, each with 'character' and 'text'. "
            "Example: [{\"character\": \"narrator\", \"text\": \"Once upon a time...\"}, {\"character\": \"Hero\", \"text\": \"Hello!\"}]"
        )
        
        try:
            # Using generate_content_async with a clear prompt
            response = await self.model.generate_content_async(
                f"{system_instruction}\n\nChapter Text:\n{text}",
                generation_config={"response_mime_type": "application/json"}
            )
            
            if not response.text:
                logger.error("Empty response from Gemini")
                return []
                
            script = json.loads(response.text)
            if not isinstance(script, list):
                logger.error(f"Expected list from Gemini, got {type(script)}")
                return []
                
            return script
        except Exception as e:
            logger.error(f"Error parsing chapter with Gemini: {e}")
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
