from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models import ContentItem, StoryInfo


@dataclass
class SearchResult:
    title: str
    url: str
    author: str | None = None
    cover: str | None = None


@dataclass
class ChapterTreeItem:
    title: str
    url: str
    locked: bool = False


@dataclass
class VolumeTreeItem:
    volume: str
    chapters: list[ChapterTreeItem] = field(default_factory=list)


class BaseSource(ABC):
    base_urls: list[str] = []

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]:
        """Search for novels by query."""
        pass

    @abstractmethod
    async def get_info(self, url: str) -> StoryInfo:
        """Get novel info (title, author, cover, etc)."""
        pass

    @abstractmethod
    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        """Get chapter list with volume structure.

        Returns list of VolumeTreeItem, each containing a volume name
        and list of ChapterTreeItem. For flat sources without volumes,
        return a single VolumeTreeItem with volume="Volume 1".
        """
        pass

    @abstractmethod
    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        """Get chapter content."""
        pass

    @abstractmethod
    async def aclose(self) -> None:
        """Close owned resources (e.g. HTTP clients)."""
        pass

    def matches(self, url: str) -> bool:
        """Check if this source can handle the given URL."""
        return any(base in url for base in self.base_urls)


_SOURCE_CACHE: dict[str, BaseSource] = {}


def get_source(url: str, client: Any | None = None, browser: Any | None = None) -> BaseSource | None:
    """Factory function to get the correct source instance for a URL."""
    from .lnhako import LnHakoSource
    from .truyenfull import TruyenFullSource

    # Only cache default internally-owned source instances.
    # Calls that inject client/browser should keep explicit lifecycle behavior.
    use_cache = client is None and browser is None

    sources = [
        ("truyenfull.vision", TruyenFullSource, {"client": client}),
        ("ln.hako.vn", LnHakoSource, {"client": client, "browser": browser}),
    ]

    for domain, source_cls, kwargs in sources:
        if use_cache and domain in _SOURCE_CACHE:
            source = _SOURCE_CACHE[domain]
        else:
            source = source_cls(**kwargs)
            if use_cache:
                _SOURCE_CACHE[domain] = source
        if source.matches(url):
            return source
    return None
