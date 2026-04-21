import os
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel


def get_jwt_secret() -> str:
    secret = os.getenv("VVR_JWT_SECRET")
    if not secret:
        raise RuntimeError("VVR_JWT_SECRET is required for social auth")
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str, username: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


class AuthUser(BaseModel):
    id: str
    username: str
    role: str


async def get_auth_user(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[7:]
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    # Check if user still exists in the database
    from .db import SocialDatabaseManager
    from ..utils import get_config_path

    db = SocialDatabaseManager(db_path=get_config_path("social.db"))
    await db.init_db()
    try:
        user = await db.get_user_by_id(payload["sub"])
        if not user:
            raise HTTPException(status_code=401, detail="User no longer exists")
    finally:
        await db.close()

    return AuthUser(id=payload["sub"], username=payload["username"], role=payload["role"])


async def require_admin(user: AuthUser = Depends(get_auth_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
