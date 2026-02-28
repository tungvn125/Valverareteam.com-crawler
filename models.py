"""
Data models for the web novel scraper.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Union, Literal, TypedDict


@dataclass
class StoryInfo:
    """Information about a story."""
    title: str
    author: str
    description: str
    cover_path: Optional[str] = None


@dataclass
class ContentItem:
    """A single content item (text or image)."""
    type: Literal["text", "image"]
    data: str


@dataclass
class Chapter:
    """A chapter with title and content."""
    title: str
    content: List[ContentItem]
    url: Optional[str] = None


@dataclass
class Volume:
    """A volume containing chapters."""
    title: str
    chapters: List[Chapter]


# Type aliases for backward compatibility
ChapterData = Dict[str, Union[str, List[Dict[str, str]]]]
VolumeData = Dict[str, Union[str, List[ChapterData]]]
StoryInfoDict = Dict[str, Optional[str]]


def story_info_to_dict(info: StoryInfo) -> StoryInfoDict:
    """Convert StoryInfo to dictionary for backward compatibility."""
    return {
        "title": info.title,
        "author": info.author,
        "description": info.description,
        "cover_path": info.cover_path
    }


def dict_to_story_info(data: StoryInfoDict) -> StoryInfo:
    """Convert dictionary to StoryInfo."""
    return StoryInfo(
        title=data.get("title") or "Unknown Title",
        author=data.get("author") or "Unknown Author",
        description=data.get("description") or "No Description",
        cover_path=data.get("cover_path")
    )