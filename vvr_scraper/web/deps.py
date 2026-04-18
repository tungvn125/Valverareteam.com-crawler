"""
FastAPI dependencies for the web server.
"""

import hmac
import os

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger

security = HTTPBasic()


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    """OPDS authentication dependency."""
    user = os.getenv("VVR_OPDS_USER")
    password = os.getenv("VVR_OPDS_PASS")

    if not user or not password:
        logger.warning("VVR_OPDS_USER or VVR_OPDS_PASS not set. OPDS authentication is disabled.")
        raise HTTPException(
            status_code=401,
            detail="OPDS authentication not configured. Set VVR_OPDS_USER and VVR_OPDS_PASS.",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not hmac.compare_digest(credentials.username.encode(), user.encode()) or not hmac.compare_digest(
        credentials.password.encode(), password.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_db(request: Request | None = None):
    """Returns the database manager from request/app state.

    Prefer the current request when available so route handlers do not need to
    reach through the module-level FastAPI app singleton.
    """
    if request is not None:
        state = request.app.state
    else:
        from . import app

        state = app.state

    db = getattr(state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db
