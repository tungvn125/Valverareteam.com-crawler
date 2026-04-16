"""
Data models for the web novel scraper.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class StoryInfo:
    """Information about a story."""

    title: str
    author: str
    description: str
    slug: str | None = None
    genres: list[str] = field(default_factory=list)
    cover_path: str | None = None
    cover_url: str | None = None
    total_chapters: str = "Unknown"
    word_count: str = "Unknown"
    views: str = "-"


@dataclass
class ContentItem:
    """A single content item (text or image)."""

    type: Literal["text", "image"]
    data: str


@dataclass
class Chapter:
    """A chapter with title and content."""

    title: str
    content: list[ContentItem]
    url: str | None = None


@dataclass
class Volume:
    """A volume containing chapters."""

    title: str
    chapters: list[Chapter]


@dataclass
class CharacterProfile:
    """Detailed profile for a character in a story."""

    name: str  # canonical name
    story_id: str
    aliases: list[str] = field(default_factory=list)
    gender: str = "unknown"
    voice_id: str | None = None
    personality: str | None = None
    speaking_style: str | None = None
    emotion_range: float = 0.5
    color: str | None = None


# Type aliases for backward compatibility
ChapterData = dict[str, str | list[dict[str, str]]]
VolumeData = dict[str, str | list[ChapterData]]
StoryInfoDict = dict[str, Any]


def story_info_to_dict(info: StoryInfo) -> StoryInfoDict:
    """Convert StoryInfo to dictionary for backward compatibility."""
    return {
        "title": info.title,
        "author": info.author,
        "description": info.description,
        "slug": info.slug,
        "genres": info.genres or [],
        "cover_path": info.cover_path,
        "cover_url": info.cover_url,
        "total_chapters": info.total_chapters,
        "word_count": info.word_count,
        "views": info.views,
    }


def dict_to_story_info(data: StoryInfoDict) -> StoryInfo:
    """Convert dictionary to StoryInfo."""
    return StoryInfo(
        title=data.get("title") or "Unknown Title",
        author=data.get("author") or "Unknown Author",
        description=data.get("description") or "No Description",
        slug=data.get("slug"),
        genres=data.get("genres") or [],
        cover_path=data.get("cover_path"),
        cover_url=data.get("cover_url"),
        total_chapters=data.get("total_chapters") or "Unknown",
        word_count=data.get("word_count") or "Unknown",
        views=data.get("views") or "-",
    )
