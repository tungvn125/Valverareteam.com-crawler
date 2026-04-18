import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from .auth import create_access_token, get_auth_user, hash_password, require_admin, verify_password
from .db import group_reactions_by_anchor
from .models import (
    CommentCreateRequest,
    CommentUpdateRequest,
    InviteCreateRequest,
    LoginRequest,
    ReactionCreateRequest,
    RegisterRequest,
)
from .websocket import social_ws_manager

auth_router = APIRouter()
admin_router = APIRouter()
social_router = APIRouter()
websocket_router = APIRouter()

RATE_BUCKETS: dict[tuple[str, str], list[float]] = defaultdict(list)


async def _get_social_db(request: Request):
    db = getattr(request.app.state, "social_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Social database not initialized")
    return db


def enforce_rate_limit(user_id: str, action: str, limit: int, window_seconds: int):
    now = time.monotonic()
    key = (user_id, action)
    RATE_BUCKETS[key] = [ts for ts in RATE_BUCKETS[key] if now - ts < window_seconds]
    if len(RATE_BUCKETS[key]) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    RATE_BUCKETS[key].append(now)


@auth_router.post("/register")
async def register(payload: RegisterRequest, social_db=Depends(_get_social_db)):
    try:
        user = await social_db.register_user_with_invite(
            invite_code=payload.invite_code,
            username=payload.username,
            hashed_password=hash_password(payload.password),
            display_name=payload.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    return {"user": user, "token": token}


@auth_router.post("/login")
async def login(payload: LoginRequest, social_db=Depends(_get_social_db)):
    user = await social_db.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    return {"user": user, "token": token}


@auth_router.get("/me")
async def me(user=Depends(get_auth_user), social_db=Depends(_get_social_db)):
    row = await social_db.get_user_by_id(user.id)
    return {"user": row}


@admin_router.post("/invites")
async def create_invite(payload: InviteCreateRequest, user=Depends(require_admin), social_db=Depends(_get_social_db)):
    invite = await social_db.create_random_invite(created_by=user.id, max_uses=payload.max_uses)
    return invite


@admin_router.get("/invites")
async def list_invites(user=Depends(require_admin), social_db=Depends(_get_social_db)):
    return await social_db.list_invite_codes()


@social_router.get("/books/{slug}/chapters/{cid}/reactions")
async def list_reactions(
    slug: str,
    cid: str,
    anchor: str | None = None,
    user=Depends(get_auth_user),
    social_db=Depends(_get_social_db),
):
    rows = await social_db.list_reactions(slug, cid, anchor)
    return {"anchors": group_reactions_by_anchor(rows)}


@social_router.post("/books/{slug}/chapters/{cid}/reactions")
async def create_reaction(
    slug: str,
    cid: str,
    payload: ReactionCreateRequest,
    user=Depends(get_auth_user),
    social_db=Depends(_get_social_db),
):
    enforce_rate_limit(user.id, "reaction", 5, 1)
    try:
        reaction = await social_db.create_reaction(user.id, slug, cid, payload.anchor, payload.reaction_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reaction_data = await social_db.get_reaction(reaction)
    if reaction_data:
        await social_ws_manager.broadcast(slug, cid, {"type": "reaction", "data": reaction_data})
    return reaction_data


@social_router.delete("/reactions/{reaction_id}", status_code=204)
async def delete_reaction(reaction_id: str, user=Depends(get_auth_user), social_db=Depends(_get_social_db)):
    reaction = await social_db.get_reaction(reaction_id)
    if not reaction:
        raise HTTPException(status_code=404, detail="Reaction not found")
    if reaction["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's reaction")
    await social_db.delete_reaction(reaction_id)
    await social_ws_manager.broadcast(
        reaction["book_slug"], reaction["chapter_id"], {"type": "reaction_deleted", "data": {"id": reaction_id}}
    )


@social_router.get("/books/{slug}/chapters/{cid}/comments")
async def list_comments(
    slug: str,
    cid: str,
    anchor: str | None = None,
    user=Depends(get_auth_user),
    social_db=Depends(_get_social_db),
):
    return await social_db.list_comments(slug, cid, anchor)


@social_router.post("/books/{slug}/chapters/{cid}/comments")
async def create_comment(
    slug: str,
    cid: str,
    payload: CommentCreateRequest,
    user=Depends(get_auth_user),
    social_db=Depends(_get_social_db),
):
    enforce_rate_limit(user.id, "comment", 1, 3)
    try:
        comment_id = await social_db.create_comment(
            user.id, slug, cid, payload.anchor, payload.content, payload.parent_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    comment = await social_db.get_comment(comment_id)
    if comment:
        await social_ws_manager.broadcast(slug, cid, {"type": "comment", "data": comment})
    return comment


@social_router.put("/comments/{comment_id}")
async def update_comment(
    comment_id: str,
    payload: CommentUpdateRequest,
    user=Depends(get_auth_user),
    social_db=Depends(_get_social_db),
):
    existing = await social_db.get_comment(comment_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Comment not found")
    if existing["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Cannot edit another user's comment")
    return await social_db.update_comment(comment_id, payload.content)


@social_router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, user=Depends(get_auth_user), social_db=Depends(_get_social_db)):
    existing = await social_db.get_comment(comment_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Comment not found")
    if existing["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
    await social_db.delete_comment(comment_id)
    await social_ws_manager.broadcast(
        existing["book_slug"], existing["chapter_id"], {"type": "comment_deleted", "data": {"id": comment_id}}
    )


@websocket_router.websocket("/ws/social/{book_slug}/{chapter_id}")
async def social_ws(book_slug: str, chapter_id: str, websocket: WebSocket):
    await social_ws_manager.connect(book_slug, chapter_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        social_ws_manager.disconnect(book_slug, chapter_id, websocket)
