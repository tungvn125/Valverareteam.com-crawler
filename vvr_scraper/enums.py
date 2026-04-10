"""
Enums and constants for the VVR-Scraper project.
Replaces magic string literals with type-safe enum values.
"""

from enum import StrEnum


class JobStatus(StrEnum):
    """Status values for job tracking."""

    PENDING = "pending"
    WAITING = "waiting"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NovelStatus(StrEnum):
    """Status values for novel tracking."""

    PENDING = "pending"
    SYNCED = "synced"
    UNAVAILABLE = "unavailable"
    ARCHIVED = "archived"


# Whitelisted column names for dynamic SQL construction.
# Only these columns may be used in programmatic UPDATE/INSERT statements
# to prevent SQL injection via column name manipulation.
ALLOWED_NOVEL_COLUMNS = frozenset(
    {
        "title",
        "slug",
        "author",
        "description",
        "cover_url",
        "status",
        "last_chapter_count",
        "last_downloaded_at",
        "output_folder",
        "formats",
        "genres",
        "last_synced_count",
        "server_chapter_count",
        "has_updates",
        "last_checked_at",
    }
)

ALLOWED_JOB_COLUMNS = frozenset(
    {
        "status",
        "updated_at",
        "progress",
        "error_summary",
        "error_log_path",
    }
)
