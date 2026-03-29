# ElevenLabs TTS Integration Design

## 1. Overview
This project will replace the local `vieneu` TTS engine with the `elevenlabs` cloud API for audiobook (`tao_file_mp3`) and audio drama (`tao_file_audiodrama`) generation in the `vvr-scraper` application. 
This update removes the heavy PyTorch/Vieneu dependencies and replaces them with a lightweight integration to the ElevenLabs Python SDK.

## 2. Architecture & Configuration
- **Dependencies:** The `vieneu` and `numpy` packages will be removed from `pyproject.toml` (and any `requires.txt` artifacts). They will be replaced by `elevenlabs` (and `pydub` is kept).
- **Authentication:** The application will use the `ELEVENLABS_API_KEY` environment variable. If missing, TTS functions will log an error and abort generation gracefully.
- **Voice Management:** The `VoiceManager` in `vvr_scraper/audio_drama.py` will be completely overhauled. Instead of a hardcoded pool of Vieneu names, it will dynamically fetch available voices from the ElevenLabs API using `elevenlabs.client.ElevenLabs(api_key=...)`.
  - Voices will be categorized dynamically (e.g., using ElevenLabs voice labels/tags to sort into male/female if possible, or picking at random).
  - A default or "first available" voice will be assigned to the Narrator.

## 3. Data Flow
- **`tao_file_mp3` (`vvr_scraper/exporter.py`):**
  - Will no longer use `numpy.concatenate`.
  - The text chunks will be sent sequentially to the ElevenLabs API `client.generate(...)`.
  - The returned binary audio stream (MP3) will be loaded into `pydub.AudioSegment` via `io.BytesIO`.
  - The segments will be concatenated and exported as a single MP3 file using `pydub`.
- **`tao_file_audiodrama` (`vvr_scraper/exporter.py`):**
  - Will function similarly to `tao_file_mp3`, but each segment of dialogue will be synthesized using the specific ElevenLabs Voice ID assigned by `VoiceManager`.
  - The returned audio bytes will be mixed with background music using the existing `MixingEngine`, which already works with `AudioSegment`.

## 4. Error Handling & Testing
- API rate limits, network timeouts, or invalid keys will be caught in a try/except block. Appropriate warnings will be logged via `loguru`. No local caching of audio chunks will be performed.
- The unit tests in `tests/test_exporter_audio.py` that mocked `vieneu.Vieneu` will be rewritten to mock `elevenlabs.client.ElevenLabs` and yield mock binary audio data.

## 5. Scope
The scope is strictly limited to replacing `vieneu` TTS with `elevenlabs` in the exporter and voice manager, updating tests, and updating project configuration files.