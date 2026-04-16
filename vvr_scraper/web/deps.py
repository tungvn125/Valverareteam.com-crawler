"""
FastAPI dependencies for the web server.
"""

import hmac
import os

from fastapi import Depends, HTTPException
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


def get_db():
    """Returns the database manager from app state.
    Must be called within a request context where app is accessible."""
    from . import app

    return app.state.db
