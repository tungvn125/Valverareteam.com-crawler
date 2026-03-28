# Audio-Drama Generator Design Spec

## 1. Overview
The Audio-Drama Generator is an advanced feature for `vvr-scraper` that elevates the standard TTS audiobook experience into a multi-character "Radio Play". It uses a "Hybrid Cloud Pipeline" architecture: Google Gemini (Pro/Flash) parses the chapter text to identify speakers and dialogue, and the local `Vieneu` TTS engine generates the audio.

## 2. Parsing Architecture
- **Module:** `vvr_scraper/audio_drama.py` (New)
- **Engine:** Google Gemini (via `google-generativeai` SDK).
- **Functionality:** Raw chapter text is sent to Gemini with a system prompt enforcing a strict JSON schema.
- **JSON Schema:**
  ```json
  {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "role": { "type": "string", "description": "Character name or 'narrator'" },
        "text": { "type": "string", "description": "The dialogue or narration text" }
      },
      "required": ["role", "text"]
    }
  }
  ```

## 3. Voice Mapping & Persistence
- **Voice Roster:** The `AudioDramaProcessor` maintains a mapping of character names to `Vieneu` voices.
- **Persistence:** Character-to-voice mappings are stored in the `vvr_library.db` SQLite database in a new `character_voices` table:
  - `story_id` (TEXT), `character_name` (TEXT), `voice_name` (TEXT)
- **Assignment Logic:** 
  - **Narrator:** Always uses a fixed neutral voice (e.g., `Tuyen`).
  - **Characters:** For a new character, the system randomly assigns a voice from the available `Vieneu` pool (excluding the narrator's voice). This assignment is then persisted to the DB for consistency in future chapters.

## 4. Voice Execution
- **Execution:** The processor iterates through the JSON script, generating individual audio chunks for each line using `Vieneu.infer()`, and concatenates them into a single file at the end using `numpy.concatenate`.

## 5. Integration, Checkpointing & Error Handling
- **Integration:** 
  - A new function `tao_file_audiodrama()` in `vvr_scraper/exporter.py`.
  - The existing `tao_file_mp3()` remains as a fallback.
- **Error Handling:** 
  - If Gemini fails (API error, rate limit, or invalid JSON), the system falls back to `tao_file_mp3()`.
  - Content safety filters in Gemini should be set to `BLOCK_NONE` to avoid issues with fantasy/action violence in novels.
- **Checkpointing:** 
  - Parsed JSON scripts are saved as `.json` files in the story's temporary directory before TTS begins. 
  - If audio generation fails mid-way, the script is reused to avoid re-calling Gemini.
- **Dependencies:** Add `google-generativeai` to `pyproject.toml`.