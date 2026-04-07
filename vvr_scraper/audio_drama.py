import asyncio
import io
from openai import AsyncOpenAI
import os
import json
import random
import base64
import httpx
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
                'vfx': [],
                'transition': 'fade',
                'intensity': 0.5,
                'duration': 1000
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
                                
                        full_script.extend(script_part)
                        chunk_success = True
                    else:
                        raise ValueError(f"Expected list in 'script' key, got {type(script_part)}")

                except Exception as e:
                    logger.error(f"Error parsing chunk {i+1} with OpenAI: {e}")
                    
                    # Automate retry up to 2 times (total 3 attempts)
                    retries = 0
                    while retries < 2:
                        retries += 1
                        logger.info(f"Retrying chunk {i+1} (Attempt {retries+1}/3)...")
                        await asyncio.sleep(2)
                        try:
                            # Re-call OpenAI inside retry loop
                            script = await self._parse_chunk(chunks[i])
                            if script:
                                full_script.extend(script)
                                break
                        except Exception as inner_e:
                            if retries == 2:
                                logger.error(f"Chunk {i+1} failed after 3 attempts: {inner_e}. Skipping.")
                    
                    # If failed all retries, proceed to next chunk
                    continue
        
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
        self._client = httpx.AsyncClient(timeout=None)

    async def close(self):
        """Closes the internal httpx client."""
        await self._client.aclose()
        logger.debug("VoiceManager HTTP client closed.")

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

    async def synthesize(self, voice_id: str, text: str, stability: float = 0.35) -> tuple[bytes, List[Dict]]:
        """
        Synthesizes text using ElevenLabs stream-with-timestamps endpoint.
        Returns a tuple of (audio_bytes, word_alignments).
        """
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            logger.error("ELEVENLABS_API_KEY not found in environment")
            raise ValueError("ELEVENLABS_API_KEY required")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-with-timestamps"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }
        data = {
            "text": text,
            "model_id": "eleven_v3",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }

        audio_buffer = io.BytesIO()
        all_alignments = []

        try:
            async with self._client.stream("POST", url, headers=headers, json=data) as response:
                if response.status_code != 200:
                    error_msg = await response.aread()
                    logger.error(f"ElevenLabs error ({response.status_code}): {error_msg}")
                    raise Exception(f"ElevenLabs API error: {response.status_code}")

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
                        continue
        except Exception as e:
            logger.error(f"Network error during synthesis: {e}")
            raise

        # Get full audio bytes
        full_audio = audio_buffer.getvalue()
        audio_buffer.close()

        # Process alignments into word-level timestamps as requested
        # alignment contains: characters, character_start_times_seconds, character_end_times_seconds
        word_alignments = []
        
        current_word_chars = []
        current_word_start = None
        last_end = 0
        
        for alignment in all_alignments:
            chars = alignment.get('characters', [])
            starts = alignment.get('character_start_times_seconds', [])
            ends = alignment.get('character_end_times_seconds', [])
            
            for char, start, end in zip(chars, starts, ends):
                if char.isspace():
                    if current_word_chars:
                        # Finish current word
                        word_text = "".join(current_word_chars)
                        word_alignments.append({
                            "word": word_text,
                            "start": int(current_word_start * 1000),
                            "end": int(last_end * 1000)
                        })
                        current_word_chars = []
                        current_word_start = None
                    continue
                
                if not current_word_chars:
                    current_word_start = start
                current_word_chars.append(char)
                last_end = end
                
        # Handle last word if any
        if current_word_chars:
            word_text = "".join(current_word_chars)
            word_alignments.append({
                "word": word_text,
                "start": int(current_word_start * 1000),
                "end": int(last_end * 1000)
            })
            
        return full_audio, word_alignments
