"""
Correction UI API routes — review and fix character attribution in audio drama scripts.
"""

import json
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel

from ..deps import get_db
from ..models import load_vvr_settings

router = APIRouter(prefix="/api/correction", tags=["Corrections"])


# --- Pydantic Models ---


class SegmentCorrection(BaseModel):
    segment_idx: int
    new_role: str


class CorrectionRequest(BaseModel):
    corrections: list[SegmentCorrection]


class ApplySimilarRequest(BaseModel):
    segment_idx: int
    new_role: str
    chapter_idx: int | None = None


class CharacterUpdateRequest(BaseModel):
    voice_id: str | None = None
    color: str | None = None
    aliases: list[str] | None = None
    personality: str | None = None
    speaking_style: str | None = None
    gender: str | None = None
    ref_audio_path: str | None = None
    ref_text: str | None = None
    voice_bank_id: str | None = None


# --- Helpers ---


def _get_tts_provider():
    """Get the configured TTS provider instance."""
    from vvr_scraper import tts as tts_module

    provider_name = tts_module.auto_detect_provider()
    if provider_name == "elevenlabs":
        return tts_module.get_provider("elevenlabs", api_key=os.getenv("ELEVENLABS_API_KEY"))
    elif provider_name == "openai_tts":
        return tts_module.get_provider("openai_tts", base_url=os.getenv("OPENAI_TTS_BASE_URL"))
    else:
        return tts_module.get_provider(provider_name)


def _find_script_files(output_dir: Path, slug: str) -> list[dict]:
    """Find all .script.json files in the novel's output directory."""
    scripts = []
    if not output_dir.exists():
        return scripts

    for script_path in sorted(output_dir.rglob("*.script.json")):
        rel_path = script_path.relative_to(output_dir)
        # Extract chapter index from path like "chapters/1/Title.1.ad.mp3.script.json"
        # or just "Title.ad.mp3.script.json" for whole-novel scripts
        parts = str(rel_path)
        ch_match = re.search(r"chapters[/\\](\d+)", parts)
        chapter_idx = int(ch_match.group(1)) if ch_match else 0

        # Extract display name from filename
        # e.g. "Title.ad.mp3.script.json" -> "Title (Full Audio Drama)"
        # e.g. "chapters/1/Title.1.ad.mp3.script.json" -> "Chapter 1"
        basename = script_path.stem  # removes .script
        if basename.endswith(".ad.mp3"):
            display = basename.replace(".ad.mp3", "")
        else:
            display = basename.replace(".mp3", "")

        mtime = script_path.stat().st_mtime
        scripts.append(
            {
                "path": str(rel_path),
                "chapter_idx": chapter_idx,
                "display": display,
                "mtime": mtime,
                "size": script_path.stat().st_size,
            }
        )

    return scripts


# --- Async Helpers ---


async def _async_get_novel(slug: str) -> dict | None:
    """Async helper to get novel from DB."""
    db = get_db()
    return await db.get_novel_by_slug(slug)


async def _async_get_output_dir(slug: str) -> Path | None:
    """Get output directory, trying DB first then filesystem scan."""
    novel = await _async_get_novel(slug)

    if novel and novel.get("output_folder"):
        output_dir = Path(novel["output_folder"])
        if output_dir.exists():
            return output_dir

    # Fallback: scan default output folder for a matching directory
    settings = load_vvr_settings()
    base_dir = Path(settings.default_output_folder or "novels").absolute()
    if base_dir.exists():
        from ...utils import sanitize_filename

        safe_slug = sanitize_filename(slug.split("/")[-1])
        for item in base_dir.iterdir():
            if item.is_dir() and item.name == safe_slug:
                return item

    return None


# --- API Endpoints ---


@router.get("/{slug:path}/chapters")
async def list_chapters(slug: str):
    """List all chapters with scripts for a novel.
    Scans the output folder for .script.json files."""
    output_dir = await _async_get_output_dir(slug)
    if not output_dir:
        raise HTTPException(status_code=404, detail=f"Novel not found: {slug}")

    scripts = _find_script_files(output_dir, slug)
    return {"slug": slug, "output_dir": str(output_dir), "chapters": scripts}


@router.get("/{slug:path}/chapter/{chapter_idx}/script")
async def get_chapter_script(slug: str, chapter_idx: int):
    """Read script JSON for a specific chapter."""
    output_dir = await _async_get_output_dir(slug)
    if not output_dir:
        raise HTTPException(status_code=404, detail=f"Novel not found: {slug}")

    # Find the script file for this chapter_idx
    scripts = _find_script_files(output_dir, slug)
    matching = [s for s in scripts if s["chapter_idx"] == chapter_idx]

    if not matching:
        raise HTTPException(status_code=404, detail=f"No script found for chapter {chapter_idx}")

    script_path = output_dir / matching[0]["path"]

    try:
        with open(script_path, encoding="utf-8") as f:
            script_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading script: {e}") from e

    # Enrich with character profile info from DB
    db = get_db()
    profiles = await db.get_character_profiles(slug)

    # Collect unique roles from script
    roles = set()
    for item in script_data:
        if item.get("type") == "segment" and item.get("role"):
            roles.add(item["role"])

    return {
        "chapter_idx": chapter_idx,
        "path": matching[0]["path"],
        "script": script_data,
        "roles": sorted(roles),
        "profiles": [
            {
                "name": p.name,
                "gender": p.gender,
                "voice_id": p.voice_id,
                "aliases": p.aliases,
                "color": p.color,
                "personality": p.personality,
                "speaking_style": p.speaking_style,
            }
            for p in profiles
        ],
    }


@router.post("/{slug:path}/chapter/{chapter_idx}/save")
async def save_corrections(slug: str, chapter_idx: int, body: CorrectionRequest):
    """Save corrected script. Updates .script.json and invalidates audio cache."""
    output_dir = await _async_get_output_dir(slug)
    if not output_dir:
        raise HTTPException(status_code=404, detail=f"Novel not found: {slug}")

    scripts = _find_script_files(output_dir, slug)
    matching = [s for s in scripts if s["chapter_idx"] == chapter_idx]

    if not matching:
        raise HTTPException(status_code=404, detail=f"No script found for chapter {chapter_idx}")

    script_path = output_dir / matching[0]["path"]

    # Load current script
    try:
        with open(script_path, encoding="utf-8") as f:
            script_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading script: {e}") from e

    # Apply corrections
    corrections_map = {c.segment_idx: c.new_role for c in body.corrections}
    applied_count = 0

    # Fetch profiles once for all corrections
    db = get_db()
    profiles = await db.get_character_profiles(slug)
    profile_map = {p.name.lower(): p for p in profiles}

    for i, item in enumerate(script_data):
        if i in corrections_map and item.get("type") == "segment":
            new_role = corrections_map[i]
            item["role"] = new_role
            # Also update gender if we have a profile for the new role
            profile = profile_map.get(new_role.lower())
            if profile and profile.gender:
                item["gender"] = profile.gender
            applied_count += 1

    # Save corrected script
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving script: {e}") from e

    # Invalidate audio cache — delete MP3/WAV files matching this chapter's index
    chapter_dir = script_path.parent
    deleted = []
    chapter_pattern = str(chapter_idx)
    for pattern in ["*.mp3", "*.wav"]:
        for f in chapter_dir.glob(pattern):
            if chapter_pattern in f.name:
                try:
                    f.unlink()
                    deleted.append(str(f.name))
                except OSError:
                    pass

    return {
        "status": "ok",
        "applied": applied_count,
        "invalidated": deleted,
    }


@router.post("/{slug:path}/apply-similar")
async def apply_similar(slug: str, body: ApplySimilarRequest):
    """Find and apply role change to similar segments (same old role) across a chapter or all chapters."""
    output_dir = await _async_get_output_dir(slug)
    if not output_dir:
        raise HTTPException(status_code=404, detail=f"Novel not found: {slug}")

    scripts = _find_script_files(output_dir, slug)
    if not scripts:
        raise HTTPException(status_code=404, detail="No scripts found for this novel")

    changed_count = 0
    changed_indices: list[dict] = []
    pending_writes: list[dict] = []

    # Determine which scripts to search
    if body.chapter_idx is not None:
        target_scripts = [s for s in scripts if s["chapter_idx"] == body.chapter_idx]
    else:
        target_scripts = scripts

    if not target_scripts:
        raise HTTPException(status_code=404, detail="No matching script found")

    # Get the old role from the source segment
    source_item = None
    readable_scripts = 0

    for s in target_scripts:
        script_path = output_dir / s["path"]
        try:
            with open(script_path, encoding="utf-8") as f:
                script_data = json.load(f)
        except Exception as e:
            logger.debug(f"Skipping invalid script file {script_path}: {e}")
            continue

        readable_scripts += 1

        if body.segment_idx < len(script_data) and script_data[body.segment_idx].get("type") == "segment":
            source_item = script_data[body.segment_idx]
            break

    if readable_scripts == 0:
        if body.chapter_idx is not None:
            detail = f"No readable script found for chapter {body.chapter_idx}"
        else:
            detail = "No readable scripts found for this novel"
        raise HTTPException(status_code=500, detail=detail)

    if not source_item:
        raise HTTPException(status_code=404, detail=f"Segment {body.segment_idx} not found")

    old_role = source_item.get("role", "")

    # Prepare all modifications before writing anything to disk.
    for s in target_scripts:
        script_path = output_dir / s["path"]
        try:
            with open(script_path, encoding="utf-8") as f:
                script_data = json.load(f)
        except Exception as e:
            logger.debug(f"Skipping invalid script file {script_path}: {e}")
            continue

        modified = False
        for i, item in enumerate(script_data):
            if (
                item.get("type") == "segment"
                and item.get("role") == old_role
                and not (s["chapter_idx"] == body.chapter_idx and i == body.segment_idx)
            ):
                item["role"] = body.new_role
                modified = True
                changed_count += 1
                changed_indices.append({"chapter_idx": s["chapter_idx"], "segment_idx": i})

        if modified:
            pending_writes.append({"path": script_path, "data": script_data})

    backups: list[tuple[Path, Path]] = []
    temp_paths: list[Path] = []

    try:
        for pending in pending_writes:
            script_path = pending["path"]
            fd, temp_name = tempfile.mkstemp(dir=script_path.parent, prefix=f".{script_path.name}.", suffix=".tmp")
            os.close(fd)
            temp_path = Path(temp_name)
            temp_paths.append(temp_path)

            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(pending["data"], f, ensure_ascii=False, indent=2)
            except OSError as e:
                raise HTTPException(status_code=500, detail=f"Error saving script: {e} ({script_path.name})") from e

        for pending, temp_path in zip(pending_writes, temp_paths, strict=True):
            script_path = pending["path"]
            try:
                backup_fd, backup_name = tempfile.mkstemp(
                    dir=script_path.parent,
                    prefix=f".{script_path.name}.",
                    suffix=".bak",
                )
                os.close(backup_fd)
                backup_path = Path(backup_name)
                backup_path.write_bytes(script_path.read_bytes())
                backups.append((script_path, backup_path))
                os.replace(temp_path, script_path)
            except OSError as e:
                for restore_path, backup_path in reversed(backups):
                    os.replace(backup_path, restore_path)
                raise HTTPException(status_code=500, detail=f"Error saving script: {e} ({script_path.name})") from e
    finally:
        for temp_path in temp_paths:
            if temp_path.exists():
                temp_path.unlink()
        for _, backup_path in backups:
            if backup_path.exists():
                backup_path.unlink()

    return {
        "status": "ok",
        "changed_count": changed_count,
        "changed_indices": changed_indices,
    }


@router.get("/{slug:path}/characters")
async def get_characters(slug: str):
    """Get character profiles for a novel from DB."""
    db = get_db()
    profiles = await db.get_character_profiles(slug)

    return {
        "slug": slug,
        "characters": [
            {
                "name": p.name,
                "aliases": p.aliases,
                "gender": p.gender,
                "voice_id": p.voice_id,
                "personality": p.personality,
                "speaking_style": p.speaking_style,
                "emotion_range": p.emotion_range,
                "color": p.color,
            }
            for p in profiles
        ],
    }


@router.put("/{slug:path}/characters/{character_name}")
async def update_character(slug: str, character_name: str, body: CharacterUpdateRequest):
    """Update a character profile (voice, color, aliases, etc.)."""
    db = get_db()
    profiles = await db.get_character_profiles(slug)
    existing = next((p for p in profiles if p.name.lower() == character_name.lower()), None)

    from ...models import CharacterProfile

    if existing:
        # Update existing profile
        if body.voice_id is not None:
            existing.voice_id = body.voice_id
        if body.color is not None:
            existing.color = body.color
        if body.aliases is not None:
            existing.aliases = body.aliases
        if body.personality is not None:
            existing.personality = body.personality
        if body.speaking_style is not None:
            existing.speaking_style = body.speaking_style
        if body.gender is not None:
            existing.gender = body.gender
        if body.ref_audio_path is not None:
            existing.ref_audio_path = body.ref_audio_path
        if body.ref_text is not None:
            existing.ref_text = body.ref_text
        if body.voice_bank_id is not None:
            from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager
            from vvr_scraper.voice_bank.storage import get_voice_file_path
            from vvr_scraper.utils import get_config_path

            vb_db = VoiceBankDatabaseManager(db_path=get_config_path("voice_bank.db"))
            await vb_db.init_db()
            try:
                voice = await vb_db.get_voice_sample(body.voice_bank_id)
                if voice and voice["visibility"] in ("public", "private"):
                    existing.ref_audio_path = get_voice_file_path(voice["ref_audio_path"])
                    existing.ref_text = voice["ref_text"]
            finally:
                await vb_db.close()
        await db.save_character_profile(existing)
    else:
        # Resolve ref_audio_path and ref_text from voice_bank_id if provided
        resolved_ref_audio_path = body.ref_audio_path
        resolved_ref_text = body.ref_text
        if body.voice_bank_id is not None:
            from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager
            from vvr_scraper.voice_bank.storage import get_voice_file_path
            from vvr_scraper.utils import get_config_path

            vb_db = VoiceBankDatabaseManager(db_path=get_config_path("voice_bank.db"))
            await vb_db.init_db()
            try:
                voice = await vb_db.get_voice_sample(body.voice_bank_id)
                if voice and voice["visibility"] in ("public", "private"):
                    resolved_ref_audio_path = get_voice_file_path(voice["ref_audio_path"])
                    resolved_ref_text = voice["ref_text"]
            finally:
                await vb_db.close()

        profile = CharacterProfile(
            name=character_name,
            story_id=slug,
            aliases=body.aliases or [],
            gender=body.gender or "unknown",
            voice_id=body.voice_id,
            ref_audio_path=resolved_ref_audio_path,
            ref_text=resolved_ref_text,
            personality=body.personality,
            speaking_style=body.speaking_style,
            color=body.color,
        )
        await db.save_character_profile(profile)

    return {"status": "ok", "character": character_name}


@router.get("/voices/list")
async def list_voices():
    """List available voices from the configured TTS provider."""
    try:
        provider = _get_tts_provider()
        voices = await provider.discover_voices()
        await provider.close()
        return {
            "voices": [{"voice_id": v.voice_id, "name": v.name, "gender": v.gender, "labels": v.labels} for v in voices]
        }
    except Exception as e:
        logger.error(f"Error listing voices: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/voices/preview")
async def preview_voice(
    voice_id: str | None = None,
    ref_audio_path: str | None = None,
    text: str = Query(default="Xin chào, tôi là người kể chuyện."),
):
    """Generate a short audio preview using the configured TTS provider."""
    if len(text) > 150:
        text = text[:150]

    try:
        provider = _get_tts_provider()
        from vvr_scraper.tts.base import VoiceSpec

        voice = VoiceSpec(voice_id=voice_id, ref_audio_path=ref_audio_path)
        audio = await provider.preview_voice(voice, text)
        await provider.close()
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"Error generating voice preview: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
