"""
Pydantic models and settings for the web server.
"""

import json
import os

from loguru import logger
from pydantic import BaseModel

from ..utils import get_config_path

# --- Request/Response Models ---


class DownloadRequest(BaseModel):
    slug: str
    formats: list[str] = ["EPUB"]
    grouping: str = "tatca"
    tasks: int = 5
    skip_illustrations: bool = False
    output_folder: str | None = None
    selected_urls: list[str] | None = None


class BatchImportRequest(BaseModel):
    items: list[str]


class FreesoundCallbackRequest(BaseModel):
    code: str


# --- Settings ---


class Settings(BaseModel):
    num_workers: int = 1
    default_output_folder: str = "novels"


SETTINGS_FILE_NAME = "vvr_settings.json"


def load_vvr_settings() -> Settings:
    settings_file = get_config_path(SETTINGS_FILE_NAME)
    if os.path.exists(settings_file):
        try:
            with open(settings_file, encoding="utf-8") as f:
                return Settings(**json.load(f))
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    return Settings()


def save_vvr_settings(settings: Settings):
    try:
        settings_file = get_config_path(SETTINGS_FILE_NAME)
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings.model_dump(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
