from fastapi import APIRouter, Depends, HTTPException

from ..web.deps import get_social_db
from .auth import create_access_token, get_auth_user, hash_password, require_admin, verify_password
from .models import InviteCreateRequest, LoginRequest, RegisterRequest

auth_router = APIRouter()
admin_router = APIRouter()
social_router = APIRouter()
websocket_router = APIRouter()


@auth_router.post("/register")
async def register(payload: RegisterRequest, social_db=Depends(get_social_db)):
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
async def login(payload: LoginRequest, social_db=Depends(get_social_db)):
    user = await social_db.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    return {"user": user, "token": token}


@auth_router.get("/me")
async def me(user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    row = await social_db.get_user_by_id(user.id)
    return {"user": row}


@admin_router.post("/invites")
async def create_invite(payload: InviteCreateRequest, user=Depends(require_admin), social_db=Depends(get_social_db)):
    invite = await social_db.create_random_invite(created_by=user.id, max_uses=payload.max_uses)
    return invite


@admin_router.get("/invites")
async def list_invites(user=Depends(require_admin), social_db=Depends(get_social_db)):
    return await social_db.list_invite_codes()
