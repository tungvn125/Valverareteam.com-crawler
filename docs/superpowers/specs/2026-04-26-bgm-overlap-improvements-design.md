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
- `bgm_moods` is threaded through the real parser call paths:
  - scratchpad Step 1 prompt assembly in `OpenAIParser._parse_chunk()` (`vvr_scraper/prompts/audio_drama_script.md`)
  - legacy kill-switch branch inside `OpenAIParser._parse_chunk()` when `VVR_DISABLE_SCRATCHPAD=1` (`vvr_scraper/prompts/audio_drama_script_legacy.md`)
  - escalation Step 2b prompt assembly in `OpenAIParser._escalate_chunk()` (`vvr_scraper/prompts/audio_drama_format.md`)
  - optionally escalation Step 2a prose-analysis prompt (`vvr_scraper/prompts/audio_drama_think.md`) if implementation finds it useful to keep analysis vocabulary aligned with final formatting.
- In each JSON-emitting prompt path, after appending known characters context, append:
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
| `vvr_scraper/audio_drama.py` | `parse_chapter` accepts `bgm_moods`; injects into scratchpad, escalation format, and legacy prompt paths |
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

Prompt files are updated to document the new optional field:

- `vvr_scraper/prompts/audio_drama_script.md` (scratchpad path, Step 1)
- `vvr_scraper/prompts/audio_drama_format.md` (escalation format-only path, Step 2b)
- `vvr_scraper/prompts/audio_drama_script_legacy.md` (legacy kill-switch path)

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

The `audio_drama.py` script normalizer (currently handling only `mood_shift` field defaults) is extended to normalize `segment` items: ensures `overlap_with_previous` defaults to `false` when absent. This preserves backwards compatibility with cached script JSON files that do not contain the new field.

The exporter enrichment pass must preserve the new field. Current `exporter.py` rebuilds non-`mood_shift` items into new segment dicts during voice assignment; that step must copy `overlap_with_previous` from the parsed segment into the enriched segment, otherwise the flag will be lost before mixing.

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
- Track `segment_start_offsets_ms: list[int]` during voice assembly; this list is the single source of truth for both audio placement and manifest event timing.
- If `segments[j].get("overlap_with_previous")` and `j > 0`:
  - `overlap_start = segment_start_offsets_ms[j - 1] + len(voice_segments[j - 1]) // 2` (50% into the previous segment).
  - If `overlap_start + len(vs)` exceeds the current `combined_voice` duration, pad `combined_voice` with silence before overlaying. Do not rely on mocks or undocumented extension behavior.
  - `combined_voice = combined_voice.overlay(vs, position=overlap_start)`.
  - `segment_start_offsets_ms.append(overlap_start)`.
  - `combined_position_ms = max(combined_position_ms, overlap_start + len(vs))`.
- Otherwise:
  - `segment_start_offsets_ms.append(combined_position_ms)`.
  - Append the segment at the cursor.
  - Advance cursor by segment duration, plus `cfg.gap_between_segments_ms` when another segment follows.

Edge cases:
- Multiple consecutive overlapping segments (3+): supported in a simple chained form. Each subsequent overlapping segment starts at 50% into its immediate predecessor, using `segment_start_offsets_ms[j - 1] + len(previous) // 2`. This is not a full group/chorus layout engine.
- The final `combined_voice` duration may be shorter than sequential concatenation; this is intentional (overlapping speech is naturally shorter).

**C. Event timing correction**

The dialogue event timestamp loop uses the same `segment_start_offsets_ms` computed during voice assembly. Avoid ad-hoc subtraction from `segment_offset_in_block_ms`, because it can drift with chained overlaps.

```python
seg_start_ms = block_start_ms + cfg.voice_overlay_offset_ms + segment_start_offsets_ms[j]
seg_duration_ms = len(voice_segments[j])
seg_end_ms = seg_start_ms + seg_duration_ms
```

**Files changed:**
| File | Change |
|------|--------|
| `vvr_scraper/prompts/audio_drama_script.md` | Add `overlap_with_previous` to Segment schema + usage instructions |
| `vvr_scraper/prompts/audio_drama_format.md` | Add `overlap_with_previous` to Segment schema |
| `vvr_scraper/prompts/audio_drama_script_legacy.md` | Add `overlap_with_previous` to Segment schema + usage instructions |
| `vvr_scraper/audio_drama.py` | Normalize `overlap_with_previous` to `false` when absent |
| `vvr_scraper/exporter.py` | Preserve `overlap_with_previous` during enrichment; overlap mixing logic; manifest timing from `segment_start_offsets_ms` |

---

## Non-goals
- Dynamic ducking / sidechain compression during speech.
- Per-segment BGM assignment.
- Variable overlap offset (always 50% of previous segment duration).
- Full group/chorus layout for complex 3+ simultaneous speakers. Simple chained 3+ overlaps are supported as described above.

---

## Testing strategy
- **Parser prompt integration:** `tests/test_audio_drama_mood.py` / `tests/test_audio_drama_scratchpad.py` — verify `bgm_moods` can be passed into `parse_chapter()` and appears in scratchpad, escalation format, and legacy prompt assembly without breaking existing parse behavior.
- **Freesound:** `tests/test_freesound_manager.py` — verify query construction includes `music background` and the filter includes `duration:[30 TO *]`.
- **Overlap metadata preservation:** exporter-focused test — verify `overlap_with_previous` survives voice assignment/enrichment and is visible to the block voice assembly loop.
- **Overlap audio/timing:** use real `pydub.AudioSegment.silent(...)` where possible, not only mocks whose `overlay()` returns `self`. Verify segment start offsets, combined duration, and manifest `seg_start_ms` all match.
- **Existing BGM manager:** `tests/test_bgm_manager.py` already covers `available_moods`; only add tests if behavior changes.
- **Manual:** Generate audio drama for a chapter with known simultaneous speech (e.g., the "A!" scene in `Tôi Thuê Cô Gái Mình Thích...`) and verify the audio sounds correct.

---

## Implementation risks and compatibility notes
- Cached script JSON files may not contain `overlap_with_previous`; all consumers must treat missing as `false`.
- New segment metadata can be lost during alias resolution or exporter enrichment unless explicitly copied.
- `AudioTimeline.render()` uses block crossfades; overlap timing should remain strictly in-block and should rely on block timings returned by `render()` plus per-segment offsets.
- Freesound query hardening improves odds of music-like results but does not guarantee perfect BGM. Long ambience files may still appear.
- If the local BGM library is sparse or uses unusual directory names, strict mood selection may reduce descriptive nuance. This is acceptable because the goal is to maximize local track hit rate.
