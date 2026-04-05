import asyncio
from openai import AsyncOpenAI
import os
import json
import random
from typing import List, Dict, Optional
from loguru import logger
from .db import DatabaseManager

class ScriptResult(list):
    """
    A list subclass that holds script segments but also provides 
    a 'blocks' view for cinematic grouping.
    """
    @property
    def blocks(self) -> List[Dict]:
        """Groups segments into blocks based on mood_shifts."""
        blocks = []
        # Default initial mood if none provided
        current_block = {
            'mood_info': {
                'type': 'mood_shift', 
                'mood': 'peaceful', 
                'tags': ['peaceful'],
                'visual_prompt': 'A peaceful setting.',
                'vfx': ['none'],
                'transition': 'fade'
            }, 
            'segments': []
        }
        
        has_started = False
        for item in self:
            if item.get('type') == 'mood_shift':
                if not has_started:
                    # First mood shift replaces the default
                    current_block['mood_info'] = item
                    has_started = True
                else:
                    if current_block['segments']:
                        blocks.append(current_block)
                    current_block = {'mood_info': item, 'segments': []}
            else:
                current_block['segments'].append(item)
        
        if current_block['segments']:
            blocks.append(current_block)
        return blocks

    def __getitem__(self, key):
        if isinstance(key, str) and key == 'blocks':
            return self.blocks
        return super().__getitem__(key)

class OpenAIParser:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
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
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            else:
                logger.warning(f"Prompt file not found: {prompt_path}. Using fallback instructions.")
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_name}: {e}")
        
        # Fallback in case of error
        return "You are an expert scriptwriter for audio dramas. Convert web novel text to JSON script format."

    async def parse_chapter(self, text: str) -> List[Dict[str, str]]:
        """
        Parses chapter text into a list of dialogue/narrator segments and mood shifts using OpenAI.
        Handles large chapters by chunking the text and merging the results.
        """
        if not text or not text.strip():
            return []

        # Chunk the text to stay within token limits (approx 4,000 chars per chunk)
        # 4k chars is the safe limit to ensure the resulting JSON script (which is 
        # much larger than the input) fits within the 4k output token limit.
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
        system_instruction = self._load_prompt()

        for i, chunk in enumerate(chunks):
            chunk_success = False
            retries = 0
            MAX_RETRIES = 2
            while not chunk_success and retries < MAX_RETRIES:
                retries += 1
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
                        # Normalize mood_shift objects for backward/forward compatibility (v2.5)
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
                            # Not a terminal, retry automatically up to MAX_RETRIES
                            continue
                    except ImportError:
                        # Fallback to standard input if rich is missing (unlikely)
                        import sys
                        if sys.stdin.isatty():
                            choice = input(f"Chunk {i+1} gặp lỗi. Thử lại? (Y/n): ").strip().lower()
                            if choice in ('', 'y', 'yes'):
                                continue
                        else:
                            # Not a terminal, do not block
                            pass
                        break
        
        return ScriptResult(full_script)

class VoiceManager:
    # Default narrator voice: "Anh" (Vietnamese Female)
    DEFAULT_NARRATOR_VOICE_ID = "ywBZEqUhld86Jeajq94o"
    
    # Global cache to avoid redundant API calls across chapters
    _global_available_voices = None
    _global_voice_metadata = {} # {voice_id: {'gender': str, 'name': str}}
    _global_init_lock = asyncio.Lock()

    def __init__(self, db, story_id: str):
        self.db = db
        self.story_id = story_id
        self._voice_cache = {}
        self._initialized = False
        self._instance_lock = asyncio.Lock()
        
        # Override narrator ID from env if provided
        self.narrator_voice_id = os.getenv("VVR_NARRATOR_VOICE_ID", self.DEFAULT_NARRATOR_VOICE_ID)

    async def _init_cache(self):
        if self._initialized:
            return

        # 1. Load existing assignments from DB
        if hasattr(self.db, 'get_all_story_voices'):
            db_voices = await self.db.get_all_story_voices(self.story_id)
            self._voice_cache.update(db_voices)
        
        # 2. Fetch ElevenLabs voices (using global cache)
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
                                'name': v.name,
                                'gender': v.labels.get('gender', 'unknown').lower() if v.labels else 'unknown'
                            }
                            for v in voices
                        }
                        logger.info(f"Fetched {len(voices)} voices from ElevenLabs.")
                    except Exception as e:
                        logger.error(f"Failed to fetch ElevenLabs voices: {e}")
                        VoiceManager._global_available_voices = []

        self._initialized = True

    async def get_voice(self, character_name: str, gender: str = "unknown") -> str:
        """
        Retrieves the voice ID for a character. Narrator is always the default.
        Assigns a new voice if not already cached, respecting gender if possible.
        """
        if not character_name:
            return self.narrator_voice_id
            
        char_normalized = character_name.lower().strip()
        if char_normalized == "narrator":
            return self.narrator_voice_id

        async with self._instance_lock:
            await self._init_cache()
            
            # Check cache (instance and DB)
            if char_normalized in self._voice_cache:
                return self._voice_cache[char_normalized]
            
            # Filter available voices
            gender = gender.lower()
            available_ids = VoiceManager._global_available_voices or []
            
            # Exclude narrator and already assigned voices to maximize variety
            assigned_ids = set(self._voice_cache.values())
            candidate_ids = [vid for vid in available_ids if vid != self.narrator_voice_id and vid not in assigned_ids]
            
            # If no unassigned voices, allow reuse of non-narrator voices
            if not candidate_ids:
                candidate_ids = [vid for vid in available_ids if vid != self.narrator_voice_id]
            
            # If STILL no candidates (pool is empty or only narrator exists), use narrator
            if not candidate_ids:
                assigned_voice = self.narrator_voice_id
            else:
                # Filter by gender if specified
                gender_candidates = [
                    vid for vid in candidate_ids 
                    if VoiceManager._global_voice_metadata.get(vid, {}).get('gender') == gender
                ]
                
                # If no matching gender, fallback to all candidates
                final_pool = gender_candidates if gender_candidates else candidate_ids
                
                # Pick a random voice from the pool
                assigned_voice = random.choice(final_pool)
            
            # Save to cache and DB
            self._voice_cache[char_normalized] = assigned_voice
            if hasattr(self.db, 'save_character_voice'):
                await self.db.save_character_voice(self.story_id, char_normalized, assigned_voice)
                
            logger.debug(f"Assigned voice '{assigned_voice}' ({VoiceManager._global_voice_metadata.get(assigned_voice, {}).get('name', 'Unknown')}) to character '{character_name}' (gender: {gender})")
            return assigned_voice
