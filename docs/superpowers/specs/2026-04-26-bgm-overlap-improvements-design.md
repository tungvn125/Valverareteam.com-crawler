# BGM & Overlapping Dialogue Improvements — Design

## Date: 2026-04-26

---

## Problem 1: BGM Quality — Freesound returns SFX instead of music

### Current behavior
- Two-tier fallback: local BGM library (by mood subdir) → Freesound API → silence.
- Freesound search uses raw mood tags (`" ".join(tags)`) with filter `type:(wav OR flac)`.
- Freesound is primarily a sound effects library; searches for "peaceful", "tension" return individual SFX (birds chirping, door creaks), not music beds.
- The local BGM library supports `available_moods` but LLM does not know which moods exist — it invents mood tags that may not match the library.

### Solution

**A. Inject available BGM moods into LLM prompt**

At script generation time, provide the LLM with the list of available BGM moods from the local library. The LLM then chooses `mood_shift.tags` only from this list, maximizing local BGM hit rate.

- `OpenAIParser.parse_chapter()` gains a new optional parameter: `bgm_moods: list[str] | None = None`.
- In `_parse_chunk()` and `_parse_chunk_legacy()`, after appending known characters context, append:
  ```
  ## Available BGM Moods
  Choose mood_shift.tags strictly from: ["calm", "sad", "tense", ...]
  ```
- The caller (`tao_file_audiodrama` in `exporter.py`) passes `bgm_manager.available_moods` to `parse_chapter()`.

**B. Improve Freesound query**

In `FreesoundManager._search_bgm_sync()`:
- Query auto-appends `music background`: `query = f"{' '.join(tags)} music background"`.
- Duration filter: append ` duration:[30 TO *]` to the format filter, ensuring only tracks longer than 30s are returned.

**Files changed:**
| File | Change |
|------|--------|
| `vvr_scraper/audio_drama.py` | `parse_chapter` accepts `bgm_moods`; injects into system prompt in both legacy and scratchpad paths |
| `vvr_scraper/exporter.py` | Pass `bgm_manager.available_moods` into `parser.parse_chapter()` |
| `vvr_scraper/freesound_manager.py` | Query enhancement in `_search_bgm_sync()` |

---

## Problem 2: Overlapping dialogue — two characters speaking simultaneously

### Current behavior
- When two characters speak at the same time (e.g., both shout "A!" simultaneously), the LLM outputs two sequential `segment` objects.
- The pipeline concatenates them with a silence gap — sounds unnatural for moments of simultaneous speech.
- The raw analysis (`.script.raw.md`) correctly identifies the simultaneous speech, but the JSON script has no way to represent it.

### Solution

**A. Add `overlap_with_previous` flag to segment schema**

Two prompt files are updated to document the new optional field:

- `prompts/audio_drama_script.md` (scratchpad path, Step 1)
- `prompts/audio_drama_format.md` (escalation format-only path, Step 2b)

Segment schema gains:
```json
{
  "type": "segment",
  "role": "Kiyomiya",
  "gender": "male",
  "text": "[shouting] A!",
  "overlap_with_previous": true
}
```

Prompt guidance: "When two or more characters speak simultaneously (overlapping dialogue, simultaneous exclamations, or one character cutting in), the second segment MUST set `overlap_with_previous: true`."

The `audio_drama.py` script normalizer (currently handling only `mood_shift` field defaults) is extended to normalize `segment` items: ensures `overlap_with_previous` defaults to `false` when absent.

**B. Pipeline mixing: overlay instead of concatenate**

In `exporter.py` (lines 720–724), the current sequential concatenation:
```python
combined_voice = AudioSegment.silent(duration=0)
for j, vs in enumerate(voice_segments):
    combined_voice += vs
    if j < len(voice_segments) - 1:
        combined_voice += AudioSegment.silent(duration=cfg.gap_between_segments_ms)
```

Is replaced with overlap-aware logic:
- Track a `combined_position_ms` cursor as segments are placed.
- If `segments[j].get("overlap_with_previous")` and `j > 0`:
  - `overlap_start = combined_position_ms - len(voice_segments[j-1]) // 2` (50% into previous segment).
  - `combined_voice = combined_voice.overlay(vs, position=overlap_start)` (pydub auto-extends if needed).
  - `combined_position_ms = max(combined_position_ms, overlap_start + len(vs))`.
- Otherwise: concatenate as before (append + gap, advance cursor).

Edge cases:
- Multiple consecutive overlapping segments (3+): each subsequent segment starts at 50% into its immediate predecessor using the cumulative position cursor. The combined audio duration grows naturally via pydub's auto-extension.
- The final `combined_voice` duration may be shorter than sequential concatenation; this is intentional (overlapping speech is naturally shorter).

**C. Event timing correction**

The event/manifest calculation (line 790) adjusts `segment_offset_in_block_ms` for overlapping segments so the manifest reflects the earlier start time:
```python
if segments[j].get("overlap_with_previous") and j > 0:
    segment_offset_in_block_ms -= len(voice_segments[j-1]) // 2
```

**Files changed:**
| File | Change |
|------|--------|
| `prompts/audio_drama_script.md` | Add `overlap_with_previous` to Segment schema + usage instructions |
| `prompts/audio_drama_format.md` | Add `overlap_with_previous` to Segment schema |
| `vvr_scraper/audio_drama.py` | Normalize `overlap_with_previous` to `false` when absent |
| `vvr_scraper/exporter.py` | Overlap mixing logic in voice concatenation + event timing offset |

---

## Non-goals
- Dynamic ducking / sidechain compression during speech.
- Per-segment BGM assignment.
- Variable overlap offset (always 50% of previous segment duration).
- Per-character simultaneous mixing (e.g., 3+ characters at once — each subsequent segment overlays cumulatively at 50% of its predecessor).

---

## Testing strategy
- **Unit:** `tests/test_bgm_manager.py` — confirm `available_moods` returns expected list.
- **Unit:** `tests/test_freesound_manager.py` — verify query construction includes `music background` and duration filter.
- **Integration:** `tests/test_task4_block_mixing.py` — add test case for overlapping segments (2 mock AudioSegments with known durations; verify overlay position and combined duration).
- **Manual:** Generate audio drama for a chapter with known simultaneous speech (e.g., the "A!" scene in `Tôi Thuê Cô Gái Mình Thích...`) and verify the audio sounds correct.
