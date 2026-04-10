"""
FastAPI dependencies for the web server.
"""

import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger

security = HTTPBasic()


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    """OPDS authentication dependency."""
    user = os.getenv("VVR_OPDS_USER", "admin")
    password = os.getenv("VVR_OPDS_PASS", "password")

    if not os.getenv("VVR_OPDS_USER") or not os.getenv("VVR_OPDS_PASS"):
        logger.warning("VVR_OPDS_USER or VVR_OPDS_PASS not set. Using default 'admin/password'.")

    if credentials.username != user or credentials.password != password:
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
