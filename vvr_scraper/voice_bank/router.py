"""FastAPI routes for the voice bank API."""

import os
import subprocess
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from ..social.auth import get_auth_user
from ..voice_bank.db import VoiceBankDatabaseManager
from ..voice_bank.models import VoicePreviewRequest, VoiceUpdateRequest, VoiceVoteRequest
from ..voice_bank.service import delete_voice, delist_voice, publish_voice, upload_voice, vote_voice
from ..voice_bank.storage import get_voice_bank_dir, get_voice_file_path

router = APIRouter(prefix="/api/voices", tags=["Voice Bank"])


async def _get_voice_bank_db(request: Request) -> VoiceBankDatabaseManager:
    db = getattr(request.app.state, "voice_bank_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Voice bank database not initialized")
    return db


# --- Upload ---


@router.post("/upload")
async def upload_voice_endpoint(
    request: Request,
    audio: UploadFile = File(...),
    ref_text: str = Form(..., min_length=10, max_length=5000),
    name: str = Form(..., min_length=3, max_length=100),
    description: str = Form(None, max_length=500),
    gender: str = Form(...),
    age_group: str = Form(...),
    language: str = Form("vi"),
    mood: str = Form(None),
    tags: str = Form(""),  # comma-separated
    user=Depends(get_auth_user),
):
    db = await _get_voice_bank_db(request)

    # Validate gender and age_group
    if gender not in ("male", "female", "other"):
        raise HTTPException(status_code=400, detail=f"Invalid gender: {gender}")
    if age_group not in ("child", "teen", "young_adult", "adult", "elder"):
        raise HTTPException(status_code=400, detail=f"Invalid age_group: {age_group}")

    # Parse tags
    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()] if tags else []
    if len(tag_list) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 tags allowed")
    for tag in tag_list:
        if len(tag) > 15:
            raise HTTPException(status_code=400, detail=f"Tag '{tag}' exceeds 15 characters")

    # Validate audio file extension
    suffix = os.path.splitext(audio.filename or "")[1].lower()
    if suffix not in (".wav", ".mp3", ".ogg", ".m4a"):
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Accepted: wav, mp3, ogg, m4a",
        )

    # Stream uploaded file to temp with size limit (30MB)
    max_size = 30 * 1024 * 1024
    read = 0
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            while chunk := await audio.read(8192):
                read += len(chunk)
                if read > max_size:
                    os.unlink(tmp_path)
                    raise HTTPException(status_code=413, detail="File too large (max 30MB)")
                tmp.write(chunk)

        result = await upload_voice(
            db=db,
            user_id=user.id,
            audio_file_path=tmp_path,
            ref_text=ref_text,
            name=name,
            description=description,
            gender=gender,
            age_group=age_group,
            language=language,
            mood=mood,
            tags=tag_list,
        )
    except (ValueError, subprocess.SubprocessError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:  # noqa: S110
                pass

    return result


# --- List Endpoints ---


@router.get("/me")
async def list_my_voices(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_auth_user),
):
    db = await _get_voice_bank_db(request)
    return await db.list_my_voices(user_id=user.id, limit=limit, offset=offset)


@router.get("/community")
async def list_community_voices(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tag: str | None = None,
    gender: str | None = None,
    age_group: str | None = None,
    sort: str = Query(default="votes"),
):
    db = await _get_voice_bank_db(request)
    tags = [tag] if tag else None
    return await db.list_community_voices(
        limit=limit,
        offset=offset,
        tags=tags,
        gender=gender,
        age_group=age_group,
        sort=sort,
    )


# --- Single Voice ---


@router.get("/{voice_id}")
async def get_voice(request: Request, voice_id: str, user=Depends(get_auth_user)):
    db = await _get_voice_bank_db(request)
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice sample not found")
    # Private voices only visible to owner
    if voice["visibility"] == "private" and voice["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Voice sample not found")
    return voice


@router.get("/{voice_id}/audio")
async def get_voice_audio(request: Request, voice_id: str, user=Depends(get_auth_user)):
    db = await _get_voice_bank_db(request)
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice sample not found")
    if voice["visibility"] == "private" and voice["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Voice sample not found")

    abs_path = os.path.realpath(get_voice_file_path(voice["ref_audio_path"]))
    # Path traversal protection: ensure resolved path is inside voice bank directory
    bank_dir = os.path.realpath(get_voice_bank_dir())
    if not abs_path.startswith(bank_dir + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")
    return FileResponse(abs_path, media_type="audio/wav", filename=f"{voice_id}.wav")


# --- Update / Publish / Delist ---


@router.patch("/{voice_id}")
async def update_voice(
    request: Request,
    voice_id: str,
    body: VoiceUpdateRequest,
    user=Depends(get_auth_user),
):
    db = await _get_voice_bank_db(request)
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice sample not found")
    if voice["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="You do not own this voice sample")

    update_data = {}
    if body.name is not None:
        update_data["name"] = body.name
    if body.description is not None:
        update_data["description"] = body.description
    if body.mood is not None:
        update_data["mood"] = body.mood
    if body.tags is not None:
        await db.set_tags(voice_id, body.tags)

    if update_data:
        await db.update_voice_sample(voice_id, **update_data)
    return await db.get_voice_sample(voice_id)


@router.patch("/{voice_id}/publish")
async def publish_voice_endpoint(request: Request, voice_id: str, user=Depends(get_auth_user)):
    db = await _get_voice_bank_db(request)
    try:
        return await publish_voice(db, voice_id, user.id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

@router.patch("/{voice_id}/delist")
async def delist_voice_endpoint(request: Request, voice_id: str, user=Depends(get_auth_user)):
    db = await _get_voice_bank_db(request)
    is_admin = user.role == "admin"
    try:
        return await delist_voice(db, voice_id, user.id, is_admin=is_admin)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

# --- Delete ---


@router.delete("/{voice_id}", status_code=204)
async def delete_voice_endpoint(request: Request, voice_id: str, user=Depends(get_auth_user)):
    db = await _get_voice_bank_db(request)
    is_admin = user.role == "admin"
    try:
        await delete_voice(db, voice_id, user.id, is_admin=is_admin)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None


# --- Vote ---


@router.post("/{voice_id}/vote")
async def vote_voice_endpoint(request: Request, voice_id: str, body: VoiceVoteRequest, user=Depends(get_auth_user)):
    db = await _get_voice_bank_db(request)
    try:
        new_score = await vote_voice(db, voice_id, user.id, body.vote)
        return {"voice_id": voice_id, "vote_score": new_score}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


# --- Preview ---


@router.post("/{voice_id}/preview")
async def preview_voice(request: Request, voice_id: str, body: VoicePreviewRequest, user=Depends(get_auth_user)):
    db = await _get_voice_bank_db(request)
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice sample not found")
    if voice["visibility"] == "private" and voice["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Voice sample not found")

    abs_path = os.path.realpath(get_voice_file_path(voice["ref_audio_path"]))
    # Path traversal protection: ensure resolved path is inside voice bank directory
    bank_dir = os.path.realpath(get_voice_bank_dir())
    if not abs_path.startswith(bank_dir + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    # Lazily instantiate TTS provider (same pattern as correction.py)
    from vvr_scraper import tts as tts_module
    from vvr_scraper.tts.base import VoiceSpec

    provider_name = tts_module.auto_detect_provider()
    provider = tts_module.get_provider(provider_name)

    spec = VoiceSpec(ref_audio_path=abs_path, ref_text=voice["ref_text"])
    try:
        result = await provider.synthesize(text=body.text, voice=spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {e}") from None
    finally:
        try:
            await provider.close()
        except Exception:  # noqa: S110
            pass
    return Response(content=result.audio_bytes, media_type="audio/wav")
