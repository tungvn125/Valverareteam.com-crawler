# Task 1 & 2 — Detailed Implementation Plan

> Updated: 2026-04-16  
> Based on full codebase audit of mixing_engine.py, exporter.py, audio_drama.py, db.py, models.py, web UI

---

## Task 1: AudioTimeline với Crossfade (Full Pipeline)

### 1.1 Tổng quan

Thay thế logic mixing inline trong `tao_file_audiodrama()` bằng `AudioTimeline` class có cấu hình, hỗ trợ:
- Crossfade giữa BGM tracks khi mood thay đổi
- CLI flags để kiểm soát mixing parameters
- Web UI settings persistence
- Chunked rendering để tránh tràn RAM

### 1.2 Files cần sửa/tạo mới

| File | Action | Mô tả |
|------|--------|--------|
| `vvr_scraper/mixing_engine.py` | **Sửa chính** | Thêm `TimelineConfig`, `AudioTimeline`, `Track`, `BackgroundTrack`, `Crossfade`, `SFXCue` dataclasses và logic |
| `vvr_scraper/exporter.py` | **Sửa** | Refactor `tao_file_audiodrama()` để dùng `AudioTimeline` thay vì inline mixing; accept `TimelineConfig` parameter |
| `vvr_scraper/cli.py` | **Sửa** | Thêm CLI flags: `--crossfade-ms`, `--bgm-volume`, `--voice-offset-ms`, `--gap-ms` |
| `vvr_scraper/web/routes/api.py` | **Sửa** | Thêm `GET /api/settings` ↔ `POST /api/settings` để persist TimelineConfig |
| `vvr_scraper/web/models.py` | **Sửa** | Thêm `AudioDramaSettings` Pydantic model |
| `vvr_scraper/web/state.py` | **Sửa** | Thêm `audio_drama_settings` vào app state |
| `vvr_scraper/static/js/main.js` | **Sửa** | Thêm Audio Drama settings section trong Settings modal |
| `vvr_scraper/static/style.css` | **Sửa** | CSS cho settings section mới |
| `vvr_scraper/job_models.py` | **Sửa** | Thêm optional `audio_drama_settings` vào `ScrapePayload` |
| `vvr_scraper/job_runner.py` | **Sửa** | Pass `TimelineConfig` từ payload vào exporter |
| `tests/test_mixing_engine.py` | **Tạo mới** | Unit tests cho AudioTimeline |

### 1.3 Implementation chi tiết

#### 1.3.1 `mixing_engine.py` — Dataclasses

```python
from dataclasses import dataclass, field
from typing import Optional
from pydub import AudioSegment

@dataclass
class TimelineConfig:
    crossfade_battle_ms: int = 500      # Mood chuyển nhanh
    crossfade_default_ms: int = 2000     # Default BGM crossfade
    crossfade_voice_ms: int = 1000       # Voice block crossfade (giữ current behavior)
    bgm_volume_db: float = -20.0         # BGM gain (dB)
    voice_overlay_offset_ms: int = 1000  # Voice offset into BGM
    gap_between_segments_ms: int = 500   # Gap giữa voice segments
    voice_fade_in_ms: int = 500          # Voice fade-in
    voice_fade_out_ms: int = 500         # Voice fade-out
    chunk_size_ms: int = 300000          # 5 phút per chunk cho RAM savings

    @classmethod
    def from_dict(cls, d: dict) -> "TimelineConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

#### 1.3.2 `mixing_engine.py` — AudioTimeline

```python
@dataclass
class Track:
    audio: AudioSegment
    segment_type: str   # "voice" | "narrator" | "bgm"
    mood: str           # "peaceful" | "battle" | "tension" | "romance" | ...
    start_ms: int = 0   # Absolute position on timeline

@dataclass
class BackgroundTrack:
    bgm_path: str       # File path or identifier
    mood: str           # Mood tags
    volume_db: float    # Gain in dB
    start_ms: int = 0
    duration_ms: int = 0

@dataclass
class Crossfade:
    at_ms: int          # Position on timeline
    from_mood: str
    to_mood: str
    duration_ms: int    # Auto-calculated if not set

class AudioTimeline:
    def __init__(self, config: TimelineConfig | None = None):
        self.config = config or TimelineConfig()
        self.tracks: list[Track] = []
        self.backgrounds: list[BackgroundTrack] = []
        self.crossfades: list[Crossfade] = []

    def add_segment(self, audio: AudioSegment, segment_type: str, mood: str, start_ms: int | None = None):
        """Add voice/narration segment. Auto-positions if start_ms is None."""
        ...

    def add_background(self, bgm_path: str, mood: str, volume_db: float | None = None, start_ms: int = 0, duration_ms: int = 0):
        """Add BGM track. Duration auto-calculated from segments if 0."""
        ...

    def add_crossfade(self, at_ms: int, from_mood: str, to_mood: str, duration_ms: int | None = None):
        """Add BGM crossfade point. Duration auto-calculated from mood transition."""
        if duration_ms is None:
            duration_ms = self._get_crossfade_duration(from_mood, to_mood)
        ...

    def _get_crossfade_duration(self, from_mood: str, to_mood: str) -> int:
        fast_transitions = {
            ("peaceful", "battle"), ("romance", "battle"),
            ("peaceful", "tension"), ("battle", "peaceful"),
        }
        if (from_mood, to_mood) in fast_transitions:
            return self.config.crossfade_battle_ms
        return self.config.crossfade_default_ms

    def render(self, output_path: str, mixing_engine: MixingEngine) -> str:
        """Render timeline to file with chunked processing."""
        ...
```

#### 1.3.3 Key Render Logic

**Chunked rendering** tránh tràn RAM:

```python
def render(self, output_path: str, mixing_engine: MixingEngine) -> str:
    # 1. Group tracks by blocks (separated by mood_shifts)
    # 2. For each block:
    #    a. Load BGM, create looped background
    #    b. Join voice segments with GAP_BETWEEN_SEGMENTS_MS
    #    c. Overlay voice on background at VOICE_OVERLAY_OFFSET_MS
    #    d. Apply voice fade_in/fade_out
    # 3. Concatenate blocks with crossfades:
    #    - If consecutive blocks have DIFFERENT moods:
    #      a. Fade-out BGM_i by crossfade_duration at end
    #      b. Fade-in BGM_i+1 by crossfade_duration at start
    #      c. Append with crossfade=CROSSFADE_MS (voice blocks still use voice_ms)
    #    - If SAME mood: simple append with voice crossfade
    # 4. Export to MP3 (via asyncio.to_thread)
    # 5. Return output_path
```

**BGM crossfade** khi mood thay đổi:

```
Before (current):   [BGM_peaceful  | voice | BGM_battle  | voice]
                     └──(1000ms voice crossfade)──┘

After (planned):    [BGM_peaceful  | voice | BGM_battle  | voice]
                     └──(fade peace 500ms)──┘──(fade battle 500ms)──┘
                                             └──(overlap = crossfade_duration)──┘
```

#### 1.3.4 `exporter.py` — Refactor `tao_file_audiodrama()`

Thêm `timeline_config` parameter:

```python
async def tao_file_audiodrama(
    content_list: ContentList,
    filename: str,
    story_id: str,
    db_manager: Any,
    title: str = "Chương truyện",
    timeline_config: TimelineConfig | None = None,  # NEW
) -> None:
```

Thay thế inline mixing (lines 500-676) bằng:

```python
config = timeline_config or TimelineConfig()
timeline = AudioTimeline(config)

for i, block in enumerate(blocks):
    # ... existing synthesis logic (unchanged) ...
    
    # Add voice segments to timeline
    for j, segment in enumerate(voice_segments):
        timeline.add_segment(segment, "voice" if segments[j]["role"] != "narrator" else "narrator", 
                            mood_info.get("mood", "peaceful"))
    
    # Add BGM
    timeline.add_background(bgm_track_path, mood_info.get("mood", "peaceful"), volume_db=config.bgm_volume_db)
    
    # Add crossfade if mood changed from previous block
    if i > 0 and blocks[i-1]["mood_info"]["mood"] != mood_info["mood"]:
        timeline.add_crossfade(at_ms=current_block_start_ms, 
                              from_mood=blocks[i-1]["mood_info"]["mood"],
                              to_mood=mood_info["mood"])

# Render
final_audio = timeline.render(filename, mixing_engine)
```

#### 1.3.5 CLI Flags (`cli.py`)

Thêm vào argparse:

```python
parser.add_argument("--crossfade-ms", type=int, default=None, help="BGM crossfade duration (ms). Default: 2000")
parser.add_argument("--bgm-volume", type=float, default=None, help="BGM volume in dB. Default: -20.0")
parser.add_argument("--voice-offset-ms", type=int, default=None, help="Voice offset into BGM (ms). Default: 1000")
parser.add_argument("--gap-ms", type=int, default=None, help="Gap between segments (ms). Default: 500")
```

Map to `TimelineConfig` trong `process_novel()` → `_generate_files()` → `tao_file_audiodrama()`.

#### 1.3.6 Web UI Settings

Thêm vào `Settings` model:

```python
class AudioDramaSettings(BaseModel):
    crossfade_default_ms: int = 2000
    crossfade_battle_ms: int = 500
    voice_overlay_offset_ms: int = 1000
    gap_between_segments_ms: int = 500
    bgm_volume_db: float = -20.0
```

Frontend: thêm section "Audio Drama" trong Settings modal với range sliders.

#### 1.3.7 Tests

```python
# tests/test_mixing_engine.py
def test_timeline_config_defaults():
    config = TimelineConfig()
    assert config.crossfade_default_ms == 2000
    assert config.bgm_volume_db == -20.0

def test_crossfade_duration_battle():
    config = TimelineConfig()
    timeline = AudioTimeline(config)
    assert timeline._get_crossfade_duration("peaceful", "battle") == 500
    assert timeline._get_crossfade_duration("peaceful", "romance") == 2000

def test_timeline_add_segment():
    timeline = AudioTimeline()
    segment = AudioSegment.silent(duration=1000)
    timeline.add_segment(segment, "voice", "peaceful")
    assert len(timeline.tracks) == 1

def test_render_single_block():
    # Create a simple single-block timeline and verify output
    ...
```

### 1.4 Thứ tự thực hiện

| Order | Task | File | Ước tính |
|-------|------|------|----------|
| 1 | Thêm `TimelineConfig` dataclass | `mixing_engine.py` | 0.5 ngày |
| 2 | Thêm `AudioTimeline`, `Track`, `BackgroundTrack`, `Crossfade` | `mixing_engine.py` | 1 ngày |
| 3 | Implement `AudioTimeline.render()` với chunked processing | `mixing_engine.py` | 1 ngày |
| 4 | Refactor `tao_file_audiodrama()` dùng AudioTimeline | `exporter.py` | 0.5 ngày |
| 5 | Thêm CLI flags và truyền TimelineConfig | `cli.py`, `job_models.py` | 0.5 ngày |
| 6 | Web UI settings persistence + UI | `api.py`, `models.py`, `main.js`, `style.css` | 0.5 ngày |
| 7 | Unit tests | `tests/test_mixing_engine.py` | 0.5 ngày |
| **Total** | | | **4.5 ngày** |

### 1.5 Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| RAM overflow cho audio dài | Trung bình | Chunked rendering (5 phút/chunk), `del` segments sau khi render |
| BGM crossfade tạo artifact | Thấp | pydub có sẵn `append(crossfade=...)` + fade-in/fade-out built-in |
| Breaking change cho `tao_file_mp4` | Thấp | `TimelineConfig` defaults match current hard-coded values |
| Freesound download trong crossfade loop | Thấp | BGM download vẫn nằm ngoài timeline render (giữ nguyên logic hiện tại) |

---

## Task 2: Manual Correction Web UI

### 2.1 Tổng quan

Cho phép user review và fix character attribution trước khi generate audio drama. File-based approach: đọc/ghi `.script.json` files trong output folder.

### 2.2 Files cần tạo/sửa

| File | Action | Mô tả |
|------|--------|--------|
| `vvr_scraper/web/routes/correction.py` | **Tạo mới** | API routes cho correction flow |
| `vvr_scraper/static/correction.html` | **Tạo mới** | Trang correction UI (SPA-like) |
| `vvr_scraper/static/js/correction.js` | **Tạo mới** | Frontend logic cho correction |
| `vvr_scraper/static/style.css` | **Sửa** | Thêm CSS cho correction UI |
| `vvr_scraper/web/__init__.py` | **Sửa** | Register correction router |
| `vvr_scraper/static/js/main.js` | **Sửa** | Thêm "Correct" button vào library card actions |
| `vvr_scraper/static/js/api.js` | **Sửa** | Thêm API wrappers cho correction endpoints |

### 2.3 API Endpoints (`correction.py`)

```python
router = APIRouter(prefix="/api/correction", tags=["Corrections"])

@router.get("/{slug}/chapters")
async def list_chapters(slug: str):
    """List all chapters with scripts for a novel. 
    Scans {output_folder}/{slug}/ for .script.json files."""

@router.get("/{slug}/chapter/{chapter_idx}")
async def get_chapter_script(slug: str, chapter_idx: int):
    """Read .script.json for a specific chapter.
    Returns segments with role assignments."""

@router.post("/{slug}/chapter/{chapter_idx}/save")
async def save_corrections(slug: str, chapter_idx: int, body: CorrectionRequest):
    """Save corrected script. 
    - Update .script.json file
    - Invalidate audio cache (*.mp3 in same chapter dir)"""

@router.post("/{slug}/apply-similar")
async def apply_similar(slug: str, body: ApplySimilarRequest):
    """Find and apply role change to similar segments across the chapter.
    Uses fuzzy matching on text content."""

@router.get("/{slug}/characters")
async def get_characters(slug: str):
    """Get character profiles for a novel from DB."""

@router.put("/{slug}/characters/{character_name}")
async def update_character(slug: str, character_name: str, body: CharacterUpdate):
    """Update a character profile (voice, color, aliases)."""

@router.get("/voices/preview")
async def preview_voice(voice_id: str, text: str):
    """Generate short audio sample for voice preview using ElevenLabs."""
```

**Pydantic models:**

```python
class CorrectionRequest(BaseModel):
    corrections: list[SegmentCorrection]  # [{segment_idx: int, new_role: str}]

class SegmentCorrection(BaseModel):
    segment_idx: int
    new_role: str

class ApplySimilarRequest(BaseModel):
    segment_idx: int
    new_role: str
    chapter_idx: int | None = None  # None = apply to all chapters

class CharacterUpdate(BaseModel):
    voice_id: str | None = None
    color: str | None = None
    aliases: list[str] | None = None
```

### 2.4 File-based Script Storage

Script files được lưu tại `{output_folder}/{story_title}/*.script.json`:

```
{output_folder}/
└── Bạn Gái Đối Xử Với Tôi Quá Tốt/
    ├── Bạn Gái Đối Xử Với Tôi Quá Tốt.mp3
    ├── Bạn Gái Đối Xử Với Tôi Quá Tốt.ad.mp3   (audio drama)
    ├── Bạn Gái Đối Xử Với Tôi Quá Tốt.ad.mp3.script.json
    ├── manifest.json
    └── backgrounds/
        └── ...
```

**Reading logic:**
```python
def find_script_files(slug: str) -> list[dict]:
    """Find all .script.json files for a novel.
    Scans DB for output_folder, then glob for *.script.json."""
    db = get_db()
    novel = await db.get_novel_by_slug(slug)
    if not novel:
        raise HTTPException(404)
    output_folder = novel["output_folder"]
    scripts = glob.glob(os.path.join(output_folder, "**/*.script.json"), recursive=True)
    return [{"path": s, "chapter_idx": parse_idx(s), "mtime": os.path.getmtime(s)} for s in scripts]
```

**Cache invalidation** khi save corrections:
```python
def invalidate_audio_cache(script_path: str):
    """Remove audio files in the same directory as the script."""
    chapter_dir = os.path.dirname(script_path)
    for pattern in ["*.mp3", "*.wav", "manifest.json"]:
        for f in Path(chapter_dir).glob(pattern):
            f.unlink(missing_ok=True)
```

### 2.5 Frontend UI Layout (`correction.html`)

Single-page app, accessible từ library card "Correct" button:

```
┌─────────────────────────────────────────────────────────────┐
│  [← Back to Library]    Bạn Gái Đối Xử Với Tôi Quá Tốt     │
├─────────────────────────────────────────────────────────────┤
│  Chapter Navigation:  [Ch.1] [Ch.2] [Ch.3] ...            │
├─────────────────────────────────────────────────────────────┤
│  Character Legend (collapsible):                             │
│  🔵 Narrator   → [voice dropdown] [🔊 preview]             │
│  🟢 Mahiru     → [voice dropdown] [🔊 preview]   🎨 #4ade80│
│  🟡 Yudai      → [voice dropdown] [🔊 preview]   🎨 #facc15│
│  ⚪ Unknown(3)  → [Assign All ▼]                           │
├─────────────────────────────────────────────────────────────┤
│  Segment List (scrollable):                                  │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ 🔵 Narrator: "Ánh nắng chiều..."                       ││
│  │    [narrator ▼] [emotion: 0.5]                          ││
│  ├──────────────────────────────────────────────────────────┤│
│  │ 🟢 Mahiru: "Cậu thật là..."                            ││
│  │    [Mahiru ▼] [🔄 Apply to similar]                     ││
│  ├──────────────────────────────────────────────────────────┤│
│  │ ⚪ "Hắn ta nói nhỏ...", segment_idx=12                 ││
│  │    [Unknown ▼] → user selects "Yudai"                  ││
│  │    ✨ "Apply 'Yudai' to 5 similar segments?"           ││
│  ├──────────────────────────────────────────────────────────┤│
│  │ → mood_shift: {"mood": "tension", "tags": ["tension"]} ││
│  └──────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  [Preview Audio] [Save Corrections] [Regenerate Chapter]   │
└─────────────────────────────────────────────────────────────┘
```

### 2.6 "Apply to Similar" Logic

```python
def find_similar_segments(segments: list[dict], target_idx: int) -> list[int]:
    """Find segments with the same role AND similar text pattern."""
    target = segments[target_idx]
    target_role = target.get("role", "narrator")
    target_text = target.get("text", "")
    
    # Extract key phrases (3+ char words, remove stop words)
    similar_indices = []
    for i, seg in enumerate(segments):
        if i == target_idx or seg.get("type") == "mood_shift":
            continue
        if seg.get("role") == target_role:
            similar_indices.append(i)
    
    return similar_indices
```

### 2.7 Voice Preview Implementation

```python
@router.get("/voices/preview")
async def preview_voice(voice_id: str, text: str = "Xin chào, tôi là người kể chuyện."):
    """Generate short audio sample using ElevenLabs."""
    if len(text) > 150:
        text = text[:150]
    
    voice_manager = VoiceManager(db=get_db(), story_id="preview")
    try:
        audio_bytes, _ = await voice_manager.synthesize(voice_id, text, stability=0.5)
        return Response(content=audio_bytes, media_type="audio/mp3")
    finally:
        await voice_manager.close()
```

### 2.8 Integration với Library

Trong `main.js`, thêm "Correct" button cho novels có audio drama formats:

```javascript
// Trong renderLibrary() hoặc filterLibrary()
const hasAudioDrama = novel.formats && novel.formats.includes('AD-MP3');
const correctBtn = hasAudioDrama 
    ? `<button class="btn-secondary btn-sm correct-novel-btn">Sửa kịch bản</button>`
    : '';

card.querySelector('.correct-novel-btn').onclick = (e) => {
    e.stopPropagation();
    window.open(`/static/correction.html?slug=${novel.slug}`, '_blank');
};
```

### 2.9 Correction.js Module Structure

```javascript
// correction.js
import { state } from './state.js';
import * as api from './api.js';

// State
let currentSlug = '';
let currentChapterIdx = 0;
let chapters = [];
let script = null;
let characters = [];

// API calls
export async function fetchChapters(slug) { ... }
export async function fetchScript(slug, chapterIdx) { ... }
export async function saveCorrections(slug, chapterIdx, corrections) { ... }
export async function applySimilar(slug, segmentIdx, newRole) { ... }
export async function fetchCharacters(slug) { ... }
export async function updateCharacter(slug, name, data) { ... }
export async function previewVoice(voiceId, text) { ... }

// Rendering
export function renderCharacterLegend(characters) { ... }
export function renderSegmentList(script) { ... }
export function renderChapterNavigation(chapters) { ... }

// Init
export async function init(slug) { ... }
```

### 2.10 Thứ tự thực hiện

| Order | Task | File | Ước tính |
|-------|------|------|----------|
| 1 | Backend: Correction API routes | `correction.py` | 1 ngày |
| 2 | Backend: Voice preview endpoint | `correction.py` | 0.5 ngày |
| 3 | Backend: Apply-similar logic | `correction.py` | 0.5 ngày |
| 4 | Backend: Register router + api.js wrappers | `web/__init__.py`, `api.js` | 0.25 ngày |
| 5 | Frontend: correction.html + correction.js structure | New files | 1 ngày |
| 6 | Frontend: Segment list + role dropdown rendering | `correction.js` | 0.5 ngày |
| 7 | Frontend: Character legend + voice preview | `correction.js` | 0.5 ngày |
| 8 | Frontend: Apply-similar UI | `correction.js` | 0.5 ngày |
| 9 | Frontend: CSS styling | `style.css` | 0.5 ngày |
| 10 | Frontend: Library integration ("Correct" button) | `main.js` | 0.25 ngày |
| 11 | Integration testing | — | 0.5 ngày |
| **Total** | | | **6 ngày** |

### 2.11 Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Script JSON format thay đổi giữa exporter versions | Trung bình | Version field trong .script.json, migration logic trong API |
| ElevenLabs API rate limits cho voice preview | Cao | Cache preview audio (1 file/voice), giới hạn 150 chars, rate limit 1 request/5s |
| Apply-similar sai do NLP đơn giản | Trung bình | Chỉ match cùng role + text pattern, luôn confirm bằng UI |
| File I/O race condition khi save + regenerate | Thấp | File lock hoặc sequential processing (save → regenerate) |
| Large script files (100+ segments) chậm trên UI | Thấp | Virtual scrolling hoặc pagination cho segment list |

---

## Tổng Kết Timeline

| Task | Ước tính | Dependencies | Priority |
|------|-----------|-------------|----------|
| **Task 1: AudioTimeline + CLI flags** | 4.5 ngày | — | P0 (core improvement) |
| **Task 2: Correction Web UI** | 6 ngày | Task 1 (uses TimelineConfig) | P1 (UX improvement) |
| **Total** | **10.5 ngày** | | |

### Recommended Execution Order

1. **Week 1**: Task 1 steps 1–4 (TimelineConfig, AudioTimeline, render, exporter refactor)
2. **Week 2**: Task 1 steps 5–7 (CLI flags, Web settings, tests) + Task 2 steps 1–4 (Backend API)
3. **Week 3**: Task 2 steps 5–11 (Frontend UI)
4. **Buffer**: 1.5 ngày cho integration testing và bug fixes