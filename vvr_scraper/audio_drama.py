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
        Handles large chapters by chunking the text and merging the results.
        """
        if not text or not text.strip():
            return []

        # Chunk the text to stay within token limits (approx 10,000 chars per chunk)
        # Chunk the text to stay within token limits (approx 4,000 chars per chunk)
        # 4k chars is the safe limit to ensure the resulting JSON script (which is 
        # much larger than the input) fits within the 4k output token limit.
        max_chunk_size = 4000
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

        system_instruction = (
            "You are an expert scriptwriter for audio dramas. "
            "Your task is to convert a web novel chapter segment into a structured script. "
            "Identify all dialogue and the character speaking, and infer their gender ('male', 'female', or 'unknown'). Everything else is 'narrator'. "
            "In addition to dialogue, you must identify significant mood shifts in the story. "
            "Allowed moods: 'action', 'peaceful', 'mysterious', 'romantic', 'sad', 'suspense'. "
            "Output MUST be a valid JSON object containing a single key 'script' which maps to a list of objects. "
            "Each object in the list must have a 'type' field which is either 'segment' or 'mood_shift'. "
            "For 'segment' type: include 'role', 'text', and 'gender'. "
            "For 'mood_shift' type: include 'mood' (one of the allowed moods). "
            "Combine consecutive segments by the same character. "
            "IMPORTANT: Ensure ALL fields and objects are correctly separated by commas. "
            "Do not add any text outside the JSON object."
        )

        for i, chunk in enumerate(chunks):
            chunk_success = False
            while not chunk_success:
                logger.info(f"Parsing chunk {i+1}/{len(chunks)} of chapter text...")
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model or "gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": f"Chapter Text Segment:\n{chunk}"}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.0,
                        max_tokens=4096
                    )
                    if not response or not hasattr(response, 'choices') or not response.choices:
                        raise ValueError(f"Invalid or empty response from OpenAI for chunk {i+1}")

                    content = response.choices[0].message.content
                    if not content:
                        raise ValueError(f"Empty content in response for chunk {i+1}")
                    
                    # --- JSON Sanity Fix ---
                    # Common LLM mistake: missing comma between fields
                    # e.g., "text": "abc" "gender": "male" -> "text": "abc", "gender": "male"
                    import re
                    # Insert missing comma between a quoted value and the next key
                    content = re.sub(r'(:[ \t]*"(?:[^"\\]|\\.)*")\s*(")', r'\1, \2', content)
                    # Insert missing comma between objects in an array
                    content = re.sub(r'(})\s*({)', r'\1, \2', content)
                    # Remove trailing comma before closing brace or bracket
                    content = re.sub(r',\s*([}\]])', r'\1', content)
                    # -----------------------

                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError as je:
                        logger.error(f"JSON Decode Error in chunk {i+1}: {je}")
                        # Log context around the error position
                        pos = je.pos
                        start_pos = max(0, pos - 50)
                        end_pos = min(len(content), pos + 50)
                        context = content[start_pos:end_pos]
                        # Highlight the error character
                        pointer = " " * (pos - start_pos) + "^"
                        logger.error(f"Context around char {pos}:\n{context}\n{pointer}")
                        
                        # Auto-save failed output for investigation
                        failed_file = f"failed_chunk_{i+1}.txt"
                        try:
                            with open(failed_file, "w", encoding="utf-8") as f:
                                f.write(content)
                            logger.info(f"Đã lưu nội dung lỗi vào: {failed_file}")
                        except Exception as fe:
                            logger.error(f"Không thể lưu file lỗi: {fe}")
                        raise
                        
                    if isinstance(data, list):
                        script_part = data
                    elif isinstance(data, dict):
                        script_part = data.get("script", [])
                    else:
                        raise ValueError(f"Expected list or dict, got {type(data)}")
                    
                    if isinstance(script_part, list):
                        full_script.extend(script_part)
                        chunk_success = True
                    else:
                        raise ValueError(f"Expected list in 'script' key, got {type(script_part)}")

                except Exception as e:
                    logger.error(f"Error parsing chunk {i+1} with OpenAI: {e}")
                    
                    # Ask user to retry if in a terminal
                    try:
                        from rich.prompt import Confirm
                        import sys
                        if sys.stdin.isatty():
                            if Confirm.ask(f"[bold yellow]Chunk {i+1} gặp lỗi. Bạn có muốn thử lại không?[/]", default=True):
                                continue # Retry the same chunk
                            else:
                                logger.warning(f"Bỏ qua chunk {i+1} theo yêu cầu người dùng.")
                                break # Skip to next chunk
                        else:
                            # Not a terminal, don't hang, just skip
                            break
                    except ImportError:
                        # Fallback to standard input if rich is missing (unlikely)
                        choice = input(f"Chunk {i+1} gặp lỗi. Thử lại? (Y/n): ").strip().lower()
                        if choice in ('', 'y', 'yes'):
                            continue
                        break
        
        return full_script

class VoiceManager:
    NARRATOR_VOICE_ID = "EXAVITQu4vr4xnSDxMaL" # Rachel or any default

    def __init__(self, db, story_id: str):
        self.db = db
        self.story_id = story_id
        self._voice_cache = {}
        self._initialized = False
        self._lock = asyncio.Lock()
        self._available_voices = []

    async def _init_cache(self):
        if not self._initialized:
            if hasattr(self.db, 'get_all_story_voices'):
                db_voices = await self.db.get_all_story_voices(self.story_id)
                self._voice_cache.update(db_voices)
            
            # Fetch ElevenLabs voices
            import os
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                logger.warning("ELEVENLABS_API_KEY missing, using fallback empty voice list")
                self._available_voices = []
            else:
                try:
                    from elevenlabs.client import ElevenLabs
                    client = ElevenLabs(api_key=api_key)
                    # Fetch voices blockingly inside thread to avoid async loop issues
                    def fetch_voices():
                        return client.voices.get_all().voices
                    voices = await asyncio.to_thread(fetch_voices)
                    self._available_voices = [v.voice_id for v in voices]
                except Exception as e:
                    logger.error(f"Failed to fetch ElevenLabs voices: {e}")
                    self._available_voices = []

            self._initialized = True

    async def get_voice(self, character_name: str, gender: str = "unknown") -> str:
        """
        Retrieves the voice name for a character. Narrator is always the default.
        """
        if not character_name:
            return self.NARRATOR_VOICE_ID
            
        char_normalized = character_name.lower().strip()
        if char_normalized == "narrator":
            return self.NARRATOR_VOICE_ID

        async with self._lock:
            await self._init_cache()
            
            if char_normalized in self._voice_cache:
                return self._voice_cache[char_normalized]
            
            import random
            assigned_voice = self.NARRATOR_VOICE_ID
            if self._available_voices:
                assigned_voice = random.choice(self._available_voices)

            self._voice_cache[char_normalized] = assigned_voice
            if hasattr(self.db, 'save_character_voice'):
                await self.db.save_character_voice(self.story_id, char_normalized, assigned_voice)
                
            return assigned_voice
